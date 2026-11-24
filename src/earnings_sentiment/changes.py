"""'What changed' between two filings of an analysis: new, removed and reworded sentences.

Research basis: Cohen, Malloy & Nguyen, "Lazy Prices" (Journal of Finance, 2020)
found that when a company substantially changes the wording of its 10-K/10-Q
(especially risk factors and MD&A) versus the prior report, future returns tend
to be weaker. This module makes those edits visible; it does not trade on them.
"""

from __future__ import annotations

import functools
import re
import threading

from .analysis import Analysis, QuarterResult
from .edgar import EdgarClient
from .sentiment import LM_CATEGORIES, FinBertUnavailable, finbert_sentences, load_lm_dictionary
from .textdiff import Change, clean_sentence, diff_sentences, word_diff
from .textextract import extract_section, html_to_text, sentences

SECTION_NAMES = {"mdna": "MD&A", "risk": "Risk factors"}
CAUTION = ("negative", "uncertainty", "litigious", "constraining")
MAX_MODEL_SENTENCES = 400
# Share of sentences new or substantively reworded, year on year. Calibrated on Apple and
# Microsoft 10-Q/10-K filings 2025-26, where MD&A typically lands between 30% and 52%.
LIGHT, HEAVY = 20, 55
_TOKEN = re.compile(r"[A-Za-z]+")

_cache: dict[tuple, dict] = {}
_cache_lock = threading.Lock()


def comparison_for(a: Analysis, label: str, vs: str) -> tuple[QuarterResult, QuarterResult | None]:
    q = next((x for x in a.quarters if x.fq.label == label), None)
    if q is None:
        raise KeyError(label)
    target = q.fq.prev() if vs == "prev" else q.fq.year_ago()
    return q, next((x for x in a.quarters if x.fq == target), None)


def options(a: Analysis) -> list[dict]:
    """Which quarters can be compared, and against what, within this analysis."""
    out = []
    for q in reversed(a.quarters):
        _, prev = comparison_for(a, q.fq.label, "prev")
        _, yoy = comparison_for(a, q.fq.label, "yoy")
        out.append({"quarter": q.fq.label, "form": q.filing.form,
                    "prev": prev.fq.label if prev else None, "prev_form": prev.filing.form if prev else None,
                    "yoy": yoy.fq.label if yoy else None, "yoy_form": yoy.filing.form if yoy else None})
    return out


@functools.lru_cache(maxsize=48)
def _section_sentences(url: str, form: str, section: str, user_agent: str) -> tuple[str, ...]:
    text = html_to_text(EdgarClient(user_agent).get(url))
    return tuple(sentences(extract_section(text, form, section)))


def _tags(sentence: str) -> list[str]:
    lex, _ = load_lm_dictionary()
    toks = {t.upper() for t in _TOKEN.findall(sentence)}
    return [c.lower() for c in LM_CATEGORIES if toks & lex[c]]


def _item(c: Change, tone: dict[str, float]) -> dict:
    tags = _tags(c.text)
    t = tone.get(c.text)
    d = {"text": clean_sentence(c.text), "tags": tags, "tone": None if t is None else round(t, 3),
         "notable": bool(set(tags) & set(CAUTION)) or (t is not None and abs(t) >= 0.5)}
    if c.kind == "reworded":
        d["before"] = clean_sentence(c.before)
        d["similarity"] = c.similarity
        d["ops"] = word_diff(d["before"], d["text"])
        edited = sum(len(t.split()) for op, t in d["ops"] if op == "+")
        removed = sum(len(t.split()) for op, t in d["ops"] if op == "-")
        # what the edit itself added: cautionary words present now but not before
        before_tags = set(_tags(c.before))
        d["new_tags"] = [x for x in tags if x not in before_tags]
        d["notable"] = d["notable"] and (bool(set(d["new_tags"]) & set(CAUTION)) or t is not None and abs(t) >= 0.5)
        # a word or two swapped (e.g. "program" -> "programs") with no new cautionary language
        d["minor"] = max(edited, removed) <= 2 and not set(d["new_tags"]) & set(CAUTION)
    return d


def _summary(section: str, n_new: int, n_old: int, added: list[dict], removed: list[dict],
             reworded: list[dict], base: str) -> str:
    substantive = [x for x in reworded if not x.get("minor")]
    changed = len(added) + len(substantive)
    if not n_new:
        return ""
    share = 100 * changed / n_new
    lead = (f"{changed} of {n_new} sentences ({share:.0f}%) are new or substantively reworded compared with "
            f"{base}; {len(removed)} earlier sentences were dropped.")
    if section == "risk":
        # Risk factors are cautious by design, so the useful signal is whether the list grew or shrank.
        grow = n_new - n_old
        pct = 100 * grow / n_old if n_old else 0
        if abs(pct) < 5:
            tail = " The section is about the same length as before."
        elif grow > 0:
            tail = f" The section grew by {grow} sentences (+{pct:.0f}%): more risks described, or described at more length."
        else:
            tail = f" The section shrank by {-grow} sentences ({pct:.0f}%)."
        scale = " That is a light touch." if share < LIGHT else (" That is a heavy rewrite, worth a closer read." if share >= HEAVY else "")
        return lead + scale + tail
    add_c = sum(1 for x in added if set(x["tags"]) & set(CAUTION))
    rem_c = sum(1 for x in removed if set(x["tags"]) & set(CAUTION))
    if add_c > rem_c * 1.25 and add_c - rem_c >= 3:
        lean = (f" The new text leans more cautious: {add_c} new sentences use negative, uncertain or legal "
                f"language, against {rem_c} that were dropped.")
    elif rem_c > add_c * 1.25 and rem_c - add_c >= 3:
        lean = (f" The edits read as less cautious: {rem_c} dropped sentences used negative, uncertain or legal "
                f"language, against {add_c} new ones.")
    else:
        lean = " Cautionary language added and dropped is roughly balanced."
    if share < LIGHT:
        scale = " That is a light touch; most of the text carried over."
    elif share < HEAVY:
        scale = " That is within the usual range for a year-on-year update."
    else:
        scale = " That is a heavy rewrite, which is worth a closer read."
    return lead + scale + lean


def compare(a: Analysis, label: str, vs: str, section: str, user_agent: str) -> dict:
    if vs not in ("prev", "yoy") or section not in SECTION_NAMES:
        raise ValueError("vs must be prev|yoy and section mdna|risk")
    q, base = comparison_for(a, label, vs)
    head = {"quarter": q.fq.label, "vs": vs, "section": section, "section_name": SECTION_NAMES[section],
            "new_filing": {"label": q.fq.label, "form": q.filing.form, "filed": q.filing.filing_date,
                           "url": q.filing.document_url}}
    if base is None:
        return head | {"available": False, "note": (
            f"{'The previous quarter' if vs == 'prev' else 'The same quarter a year earlier'} is not part of this "
            "analysis. Run it with more quarters to compare further back.")}
    head["old_filing"] = {"label": base.fq.label, "form": base.filing.form, "filed": base.filing.filing_date,
                          "url": base.filing.document_url}
    key = (q.filing.accession, base.filing.accession, section, a.model_id if a.used_finbert else None)
    with _cache_lock:
        if key in _cache:
            return head | _cache[key]

    new = list(_section_sentences(q.filing.document_url, q.filing.form, section, user_agent))
    old = list(_section_sentences(base.filing.document_url, base.filing.form, section, user_agent))
    notes = []
    if q.filing.form != base.filing.form:
        notes.append(f"This compares a {q.filing.form} with a {base.filing.form}. Annual and quarterly reports are "
                     "laid out differently, so expect more new and dropped text than usual; 'vs a year ago' "
                     "compares like with like.")
    if len(new) < 3 or len(old) < 3:
        thin = q if len(new) < 3 else base
        notes.append(f"The {SECTION_NAMES[section]} section of the {thin.fq.label} {thin.filing.form} is very short "
                     "or could not be found. Quarterly reports often just refer back to the annual report's risk "
                     "factors.")
    diff = diff_sentences(new, old)

    tone: dict[str, float] = {}
    # As in the main analysis, the model scores MD&A only: risk factors are negative by design.
    if a.used_finbert and a.model_id and section == "mdna":
        texts = [c.text for c in diff.added + diff.reworded + diff.removed][:MAX_MODEL_SENTENCES]
        try:
            tone = {s.text: s.score for s in finbert_sentences(texts, a.model_id)}
        except FinBertUnavailable as exc:
            notes.append(str(exc))

    added = [_item(c, tone) for c in diff.added]
    removed = [_item(c, tone) for c in diff.removed]
    reworded = [_item(c, tone) for c in diff.reworded]
    body = {
        "available": True,
        "counts": {"new_total": diff.total_new, "old_total": diff.total_old, "unchanged": diff.unchanged,
                   "added": len(added), "removed": len(removed), "reworded": len(reworded),
                   "minor": sum(1 for x in reworded if x.get("minor")),
                   "share_changed": round((len(added) + sum(1 for x in reworded if not x.get("minor")))
                                          / diff.total_new, 4) if diff.total_new else 0.0},
        "summary": _summary(section, diff.total_new, diff.total_old, added, removed, reworded,
                            f"{base.fq.label} ({base.filing.form})"),
        "notes": notes,
        "model_name": a.model_name if tone else None,
        "added": added, "removed": removed, "reworded": reworded,
    }
    with _cache_lock:
        _cache[key] = body
        while len(_cache) > 64:
            _cache.pop(next(iter(_cache)))
    return head | body
