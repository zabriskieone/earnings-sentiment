"""What changed in the words: sentence-level comparison of two filings.

Given the sentences of a section (MD&A or risk factors) in a filing and in an
earlier filing, classify each as:

* unchanged - same sentence (ignoring numbers, dates and whitespace);
* reworded  - clearly the same sentence with edits (similarity >= threshold);
* added     - only in the newer filing;
* removed   - only in the earlier filing.

Numbers are masked before matching so that "net sales increased 8%" and
"net sales increased 12%" count as the same sentence with an edit, rather
than flooding the result with routine figure updates.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

_NUM = re.compile(r"(?<![a-z])[$€£]?\d[\d,]*(\.\d+)?\s*(%|percent|billion|million|bps|basis points)?", re.I)
_MONTHS = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
_DATE = re.compile(rf"{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}|{_MONTHS}\s+\d{{4}}", re.I)
_YEAR_WORDS = re.compile(r"\b(fiscal\s+)?(19|20)\d{2}\b", re.I)
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w<> ]+")
_BULLET = re.compile(r"^[\s•·▪◦‣\-–—*]+")


def normalize(sentence: str) -> str:
    """Lower-case, mask dates/years/numbers, collapse whitespace and quotes."""
    s = sentence.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    s = _DATE.sub(" <date> ", s)
    s = _YEAR_WORDS.sub(" <year> ", s)
    s = _NUM.sub(" <n> ", s)
    s = _PUNCT.sub(" ", s)  # commas, quotes, bullets and full stops don't make a sentence different
    return _SPACE.sub(" ", s).strip()


def clean_sentence(sentence: str) -> str:
    """Drop leading bullet markers so list items read as text."""
    return _BULLET.sub("", sentence).strip()


@dataclass
class Change:
    kind: str  # added | removed | reworded
    text: str
    before: str = ""  # for reworded: the earlier wording
    similarity: float = 0.0


@dataclass
class DiffResult:
    added: list[Change] = field(default_factory=list)
    removed: list[Change] = field(default_factory=list)
    reworded: list[Change] = field(default_factory=list)
    unchanged: int = 0
    total_new: int = 0
    total_old: int = 0

    @property
    def share_changed(self) -> float:
        return 1 - self.unchanged / self.total_new if self.total_new else 0.0


def diff_sentences(new: list[str], old: list[str], threshold: float = 0.72) -> DiffResult:
    res = DiffResult(total_new=len(new), total_old=len(old))
    old_norm: dict[str, list[int]] = {}
    for i, s in enumerate(old):
        old_norm.setdefault(normalize(s), []).append(i)
    used_old: set[int] = set()
    pending_new: list[int] = []

    # 1) exact matches after normalisation
    for j, s in enumerate(new):
        idxs = [i for i in old_norm.get(normalize(s), []) if i not in used_old]
        if idxs:
            used_old.add(idxs[0])
            res.unchanged += 1
        else:
            pending_new.append(j)

    # 2) fuzzy matches for what is left (best pair first), compared word by word.
    # A cheap word-overlap check skips pairs that cannot reach the threshold.
    rest_old = [i for i in range(len(old)) if i not in used_old]
    old_n = {i: normalize(old[i]) for i in rest_old}
    old_w = {i: old_n[i].split() for i in rest_old}
    old_set = {i: set(w) for i, w in old_w.items()}
    candidates: list[tuple[float, int, int]] = []
    for j in pending_new:
        nw = normalize(new[j]).split()
        ns = set(nw)
        if not ns:
            continue
        for i in rest_old:
            ow = old_w[i]
            if not ow or 2 * min(len(nw), len(ow)) / (len(nw) + len(ow)) < threshold:
                continue
            os_ = old_set[i]
            if 2 * len(ns & os_) / (len(ns) + len(os_)) < threshold - 0.1:
                continue
            r = difflib.SequenceMatcher(None, nw, ow, autojunk=False).ratio()
            if r >= threshold:
                candidates.append((r, j, i))
    candidates.sort(reverse=True)
    matched_new: set[int] = set()
    for r, j, i in candidates:
        if j in matched_new or i in used_old:
            continue
        matched_new.add(j)
        used_old.add(i)
        if normalize(new[j]) == old_n[i]:
            res.unchanged += 1  # only figures, dates or punctuation differ
        else:
            res.reworded.append(Change("reworded", new[j], before=old[i], similarity=round(r, 3)))

    res.added = [Change("added", new[j]) for j in pending_new if j not in matched_new]
    res.removed = [Change("removed", old[i]) for i in range(len(old)) if i not in used_old]
    return res


def word_diff(before: str, after: str) -> list[tuple[str, str]]:
    """[(op, text)] with op in {'=', '+', '-'} for highlighting a reworded sentence.

    Words are compared after normalisation, so a figure or year that merely rolled
    forward ("2025" -> "2026") or a moved comma is shown as unchanged (new wording).
    """
    a, b = before.split(), after.split()
    ka, kb = [normalize(w) or w for w in a], [normalize(w) or w for w in b]
    out: list[tuple[str, str]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(("=", " ".join(b[j1:j2])))
        else:
            if i2 > i1:
                out.append(("-", " ".join(a[i1:i2])))
            if j2 > j1:
                out.append(("+", " ".join(b[j1:j2])))
    return out
