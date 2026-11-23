"""Extract analysable narrative text from SEC filing HTML.

* 10-Q: Part I, Item 2 (MD&A) and Part II, Item 1A (Risk Factors)
* 10-K: Item 7 (MD&A) and Item 1A (Risk Factors)
* 8-K Exhibit 99.1: the earnings press release

Numeric tables are dropped: dictionary and FinBERT scoring are designed for
prose, and tables of figures would only add noise.
"""

from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_APOS = "['’`]"

SECTION_PATTERNS = {
    ("10-Q", "mdna"): (
        rf"Item\s*2\s*\.?\s*[-–—:]?\s*Management{_APOS}?s\s+Discussion",
        r"Item\s*3\s*\.?\s*[-–—:]?\s*Quantitative|Item\s*4\s*\.?\s*[-–—:]?\s*Controls",
    ),
    ("10-K", "mdna"): (
        rf"Item\s*7\s*\.?\s*[-–—:]?\s*Management{_APOS}?s\s+Discussion",
        r"Item\s*7A\s*\.?\s*[-–—:]?\s*Quantitative|Item\s*8\s*\.?\s*[-–—:]?\s*Financial\s+Statements",
    ),
    ("10-Q", "risk"): (
        r"Item\s*1A\s*\.?\s*[-–—:]?\s*Risk\s+Factors",
        r"Item\s*2\s*\.?\s*[-–—:]?\s*Unregistered|Item\s*3\s*\.?\s*[-–—:]?\s*Defaults|Item\s*5\s*\.?\s*[-–—:]?\s*Other\s+Information|Item\s*6\s*\.?\s*[-–—:]?\s*Exhibits",
    ),
    ("10-K", "risk"): (
        r"Item\s*1A\s*\.?\s*[-–—:]?\s*Risk\s+Factors",
        r"Item\s*1B\s*\.?\s*[-–—:]?\s*Unresolved|Item\s*1C\s*\.?\s*[-–—:]?\s*Cybersecurity|Item\s*2\s*\.?\s*[-–—:]?\s*Properties",
    ),
}


def _is_numeric_table(table) -> bool:
    text = table.get_text(" ", strip=True)
    if not text:
        return True
    digits = sum(ch.isdigit() for ch in text)
    letters = sum(ch.isalpha() for ch in text)
    return digits > 0.12 * max(1, digits + letters) or letters < 200


def html_to_text(html: str, drop_numeric_tables: bool = True) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    for tag in soup.find_all(re.compile(r"^ix:header$", re.I)):
        tag.decompose()
    for tag in soup.find_all(style=re.compile(r"display:\s*none", re.I)):
        tag.decompose()
    if drop_numeric_tables:
        for table in soup.find_all("table"):
            if _is_numeric_table(table):
                table.decompose()
    # Keep block boundaries so sentences don't run into headings
    for br in soup.find_all(["br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4"]):
        br.append("\n")
    text = soup.get_text(" ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def extract_section(text: str, form: str, section: str) -> str:
    """Return the longest span between a start heading and the *nearest* end heading.

    In the table of contents the next heading follows within a few characters,
    so those spans are tiny and lose to the real section body.
    """
    base_form = "10-K" if form.startswith("10-K") else "10-Q"
    start_pat, end_pat = SECTION_PATTERNS[(base_form, section)]
    starts = [m.end() for m in re.finditer(start_pat, text, re.I)]
    ends = [m.start() for m in re.finditer(end_pat, text, re.I)]
    best = ""
    for s in starts:
        following = [e for e in ends if e > s]
        candidate = text[s : following[0]] if following else text[s : s + 150000]
        if len(candidate) > len(best):
            best = candidate
    return best.strip()


def clean_press_release(text: str) -> str:
    """Trim the boilerplate tail (safe-harbor / forward-looking language)."""
    cut = re.search(r"(This press release contains forward-looking statements|Forward-Looking Statements|Safe Harbor)", text, re.I)
    if cut and cut.start() > 500:
        text = text[: cut.start()]
    return text.strip()


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])|\n+")


def sentences(text: str, min_words: int = 6, max_chars: int = 1200) -> list[str]:
    """Split into prose sentences, dropping headings, page footers and fragments."""
    out = []
    for raw in _SENT_SPLIT.split(text):
        s = raw.strip()
        if not s:
            continue
        words = re.findall(r"[A-Za-z][A-Za-z'’-]+", s)
        if len(words) < min_words:
            continue
        alpha = sum(ch.isalpha() for ch in s)
        if alpha < 0.6 * len(s.replace(" ", "")):
            continue
        out.append(s[:max_chars])
    return out
