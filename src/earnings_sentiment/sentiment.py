"""Two complementary sentiment scorers.

1. Loughran-McDonald (LM) dictionary
   Loughran, T. & McDonald, B. (2011). "When Is a Liability Not a Liability?
   Textual Analysis, Dictionaries, and 10-Ks." Journal of Finance 66(1), 35-65.
   https://doi.org/10.1111/j.1540-6261.2010.01625.x
   Word lists: https://sraf.nd.edu/loughranmcdonald-master-dictionary/
   Transparent and deterministic: the same text always gets the same score.

2. FinBERT
   Araci, D. (2019). "FinBERT: Financial Sentiment Analysis with Pre-trained
   Language Models." https://arxiv.org/abs/1908.10063
   Model: https://huggingface.co/ProsusAI/finbert
   Reads each sentence in context, so it handles phrasing that word counts miss.
"""

from __future__ import annotations

import csv
import functools
import re
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

from . import config
from .textextract import sentences as split_sentences

NEGATIONS = {"NO", "NOT", "NONE", "NEITHER", "NEVER", "NOBODY"}
LM_CATEGORIES = ("Positive", "Negative", "Uncertainty", "Litigious", "Constraining")


@functools.lru_cache(maxsize=1)
def load_lm_dictionary() -> tuple[dict[str, set[str]], str]:
    """Return ({category: words}, source description).

    Uses the official master dictionary if a copy is dropped into data/
    (any file named LoughranMcDonald_MasterDictionary*.csv), otherwise the copy
    bundled with the MIT-licensed `pysentiment2` package.
    """
    data_dir = config.PROJECT_ROOT / "data"
    official = sorted(data_dir.glob("LoughranMcDonald_MasterDictionary*.csv")) if data_dir.exists() else []
    if official:
        path: Path = official[-1]
        source = f"Official LM master dictionary ({path.name})"
        fh = path.open(encoding="utf-8", errors="ignore")
    else:
        path = Path(str(resources.files("pysentiment2") / "static" / "LM.csv"))
        source = "LM master dictionary bundled with pysentiment2"
        fh = path.open(encoding="utf-8", errors="ignore")
    words: dict[str, set[str]] = {c: set() for c in LM_CATEGORIES}
    with fh:
        reader = csv.DictReader(fh)
        for row in reader:
            w = (row.get("Word") or "").strip().upper()
            if not w:
                continue
            for cat in LM_CATEGORIES:
                v = (row.get(cat) or "0").strip()
                if v and v not in ("0", "0.0"):
                    words[cat].add(w)
    return words, source


_TOKEN = re.compile(r"[A-Za-z]+")


@dataclass
class LMScore:
    words: int = 0
    positive: int = 0
    negative: int = 0
    uncertainty: int = 0
    litigious: int = 0
    constraining: int = 0

    @property
    def net_tone(self) -> float | None:
        denom = self.positive + self.negative
        return (self.positive - self.negative) / denom if denom else None

    def pct(self, attr: str) -> float | None:
        return 100.0 * getattr(self, attr) / self.words if self.words else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["net_tone"] = self.net_tone
        for a in ("positive", "negative", "uncertainty", "litigious", "constraining"):
            d[f"{a}_pct"] = self.pct(a)
        return d


def lm_score(text: str) -> LMScore:
    lex, _ = load_lm_dictionary()
    tokens = [t.upper() for t in _TOKEN.findall(text)]
    s = LMScore(words=len(tokens))
    for i, tok in enumerate(tokens):
        if tok in lex["Positive"]:
            # LM (2011): a positive word preceded within three words by a negation is not counted
            if not NEGATIONS.intersection(tokens[max(0, i - 3) : i]):
                s.positive += 1
        if tok in lex["Negative"]:
            s.negative += 1
        if tok in lex["Uncertainty"]:
            s.uncertainty += 1
        if tok in lex["Litigious"]:
            s.litigious += 1
        if tok in lex["Constraining"]:
            s.constraining += 1
    return s


# --------------------------------------------------------------------------- FinBERT


class FinBertUnavailable(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def _finbert_pipeline():
    try:
        import torch  # noqa: F401
        from transformers import pipeline  # heavy import, only when needed
    except ImportError as exc:  # pragma: no cover - depends on install
        raise FinBertUnavailable(
            "FinBERT needs the 'torch' and 'transformers' packages. Install them or "
            "turn FinBERT off; dictionary scores still work."
        ) from exc
    try:
        return pipeline("text-classification", model=config.FINBERT_MODEL, top_k=None, truncation=True, max_length=512)
    except Exception as exc:  # network / disk issues on first download
        raise FinBertUnavailable(f"Could not load FinBERT model '{config.FINBERT_MODEL}': {exc}") from exc


def finbert_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class SentenceScore:
    text: str
    positive: float
    negative: float
    neutral: float

    @property
    def score(self) -> float:
        return self.positive - self.negative


def finbert_sentences(sents: list[str], batch_size: int = 16) -> list[SentenceScore]:
    if not sents:
        return []
    pipe = _finbert_pipeline()
    results = pipe(sents, batch_size=batch_size)
    out = []
    for s, res in zip(sents, results):
        probs = {r["label"].lower(): float(r["score"]) for r in res}
        out.append(SentenceScore(s, probs.get("positive", 0.0), probs.get("negative", 0.0), probs.get("neutral", 0.0)))
    return out


# --------------------------------------------------------------------------- document level


@dataclass
class DocSentiment:
    section: str
    source_url: str
    n_sentences: int
    lm: dict
    finbert: dict | None = None
    top_positive: list[dict] = field(default_factory=list)
    top_negative: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def score_document(text: str, section: str, source_url: str, use_finbert: bool,
                   max_sentences: int = 600) -> DocSentiment:
    sents = split_sentences(text)
    lm = lm_score(" ".join(sents) if sents else text)
    doc = DocSentiment(section=section, source_url=source_url, n_sentences=len(sents), lm=lm.to_dict())

    scored: list[tuple[str, float]] = []
    if use_finbert and sents:
        sample = sents[:max_sentences]
        fb = finbert_sentences(sample)
        n = len(fb)
        doc.finbert = {
            "score": sum(x.score for x in fb) / n,
            "positive_share": sum(x.positive > max(x.negative, x.neutral) for x in fb) / n,
            "negative_share": sum(x.negative > max(x.positive, x.neutral) for x in fb) / n,
            "neutral_share": sum(x.neutral >= max(x.positive, x.negative) for x in fb) / n,
            "sentences_scored": n,
        }
        scored = [(x.text, x.score) for x in fb]
    else:
        # Evidence from per-sentence dictionary tone when FinBERT is off
        for s in sents:
            sc = lm_score(s)
            if sc.positive + sc.negative:
                scored.append((s, (sc.positive - sc.negative) / max(1, sc.words) * 10))
    scored.sort(key=lambda x: x[1])
    # Only clearly-signed sentences count as evidence
    doc.top_negative = [{"text": t, "score": round(v, 3)} for t, v in scored[:3] if v < -0.5]
    doc.top_positive = [{"text": t, "score": round(v, 3)} for t, v in reversed(scored[-3:]) if v > 0.5]
    return doc
