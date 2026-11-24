# Methodology

This document explains exactly how every number in the dashboard and reports is
produced, with references so each step can be checked. The goal is
**traceability**: any figure can be followed back to a specific SEC filing.

> Hobby research tool. Automated text and ratio analysis of public filings is a
> starting point for your own reading, not investment advice.

---

## 1. Data sources

| Data | Source | Notes |
|---|---|---|
| Company list (ticker → CIK) | `https://www.sec.gov/files/company_tickers.json` | Only companies that file with the US SEC |
| Filing history | `https://data.sec.gov/submissions/CIK##########.json` | 10-Q, 10-K, 8-K; older pages read when needed |
| Financial statements | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | XBRL facts as tagged by the company |
| Narrative text | The 10-Q / 10-K primary document, and Exhibit 99.1 of the Item 2.02 8-K | Downloaded from `www.sec.gov/Archives` |
| Company logos (display only) | `https://financialmodelingprep.com/image-stock/<TICKER>.png` | Only the ticker is sent; cached in `data/cache/logos`; monogram fallback. Logos are trademarks of their owners |

SEC API documentation: <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>.

**Fair access.** SEC limits automated clients to 10 requests per second and asks
each client to declare a User-Agent containing a name and contact e-mail
(<https://www.sec.gov/os/accessing-edgar-data>). The app throttles itself to at
most about 6–7 requests per second, caches every download on disk, and reads the
User-Agent from the `SEC_USER_AGENT` setting or the sidebar. Nothing personal is
stored in the repository.

**Scope.** Companies that file 10-Q/10-K reports. Foreign private issuers file
20-F/6-K, which are not supported yet.

---

## 2. Which quarters are analysed

1. Every 10-Q and 10-K with a period-of-report date is mapped to a **fiscal
   quarter** using the company's fiscal-year-end (from SEC's submissions data).
   52/53-week calendars are handled by snapping the period end to the nearest
   month (e.g. a period ending 1 July counts as the June quarter).
2. If a quarter was re-filed, the most recent filing is used.
3. The latest *N* quarters (4–12, default 8) are analysed.
4. The **earnings press release** for a quarter is the first 8-K containing
   **Item 2.02 (Results of Operations and Financial Condition)** filed within 70
   days after the quarter ended. Exhibit 99.1 of that 8-K is the press release.

---

## 3. Financial figures

Quarterly values come from the XBRL company facts.

* **Income-statement and cash-flow items** (revenue, net income, operating cash
  flow, ...) are reported as 3-month and/or year-to-date amounts. Direct 3-month
  values are used when present; otherwise the quarter is derived by subtracting
  consecutive year-to-date values that share the same start date (e.g. Q2 =
  6-month − 3-month).
* **Fourth quarter**: 10-K filings report the full year, so Q4 = full year −
  nine months. Diluted EPS for Q4 is derived the same way, which is a close
  approximation because share counts differ slightly between periods.
* **Balance-sheet items** (cash, debt, equity, ...) are point-in-time values at
  the quarter end.
* **Restatements**: when the same period is reported in several filings, the most
  recently filed value is used.
* **Tag changes**: companies switch XBRL tags over time (for example
  `SalesRevenueNet` → `RevenueFromContractWithCustomerExcludingAssessedTax`), so
  each metric has a list of fallback tags (`financials.py → METRICS`).

Derived metrics: gross/operating/net margin, free cash flow (operating cash flow
− capital expenditure), total debt (long-term + current debt + commercial paper),
net cash (cash + all marketable securities − total debt), current ratio,
debt/equity, trailing-twelve-month (TTM) sums, and quarter-on-quarter (QoQ) and
year-on-year (YoY) growth. Year-on-year comparisons are matched by fiscal
quarter, not by row position, so a missing quarter never shifts the comparison.

**Why YoY matters more than QoQ**: many businesses are seasonal (Apple's December
quarter includes the holiday season), so the "what changed" summary reports both
but treats YoY as the fairer comparison.

**Known gap**: segment and geographic revenue are tagged with XBRL *dimensions*,
which the company-facts API does not include. These are not shown yet.

---

## 4. Text extraction

| Section | 10-Q | 10-K |
|---|---|---|
| MD&A | Part I, Item 2 | Item 7 |
| Risk factors | Part II, Item 1A | Item 1A |

Steps:

1. Convert HTML to text; remove scripts, hidden XBRL headers and **numeric
   tables** (tables where digits make up more than 12% of characters). Tables of
   figures are not prose and would distort word-based scores.
2. Locate the section between its heading and the next item heading. Every
   start heading is paired with the nearest following end heading, and the
   longest span wins, which skips the table of contents.
3. Split into sentences and drop fragments (fewer than 6 words, or mostly
   non-letters, e.g. page footers).
4. Press releases: the forward-looking-statements boilerplate at the end is
   removed.

Headings are matched loosely: some filings split a word across HTML tags (Microsoft's
"RI SK FACTORS"), so stray spaces inside heading words are tolerated.

A 10-Q risk-factor section that only says "no material changes" is short by
design. The summary reports this, and risk sections are compared with the same
quarter a year earlier (the same form type), because 10-K sections list every
risk while 10-Q sections list only changes.

---

## 5. Sentiment

### 5.1 Loughran-McDonald dictionary (always on)

General-purpose sentiment dictionaries misclassify many finance words. "Liability",
"tax" and "cost" are not negative in a 10-K. Loughran and McDonald built word
lists specifically for financial filings.

* Loughran, T. & McDonald, B. (2011). *When Is a Liability Not a Liability?
  Textual Analysis, Dictionaries, and 10-Ks.* Journal of Finance 66(1), 35–65.
  <https://doi.org/10.1111/j.1540-6261.2010.01625.x>
* Word lists: <https://sraf.nd.edu/loughranmcdonald-master-dictionary/>

Computed per document:

* counts of **Positive, Negative, Uncertainty, Litigious, Constraining** words;
* each as a **% of all words**;
* **net tone** = (positive − negative) / (positive + negative), from −1 to +1.

Following Loughran & McDonald (2011), a positive word preceded within three words
by a negation (*no, not, none, neither, never, nobody*) is not counted as
positive.

**Which word list.** By default the app uses the copy of the master dictionary
bundled with the MIT-licensed `pysentiment2` package, so it works offline. To use
the latest official version, download it from the Notre Dame site above and save
it as `data/LoughranMcDonald_MasterDictionary_<year>.csv`. The app picks it up
automatically, and the source in use is printed on every report. Note that the
official dictionary is free for academic use and requires a licence for
commercial use.

Note: MD&A net tone is usually *negative* even for healthy companies, because
words such as "decline", "loss" and "adverse" are common in neutral disclosure.
Track the **change** over time, not the absolute level.

### 5.2 FinBERT (optional, default on when installed)

* Araci, D. (2019). *FinBERT: Financial Sentiment Analysis with Pre-trained
  Language Models.* <https://arxiv.org/abs/1908.10063>
* Model: `ProsusAI/finbert` on Hugging Face — <https://huggingface.co/ProsusAI/finbert>

FinBERT reads each sentence in context and outputs P(positive), P(negative) and
P(neutral). Per document:

* **FinBERT score** = mean over sentences of P(positive) − P(negative), from −1 to +1;
* share of sentences classified positive / negative / neutral;
* the most positive and most negative sentences are kept as **evidence**, shown
  only if clearly signed (score beyond ±0.5).

FinBERT is applied to the MD&A and the press release. It is not applied to risk
factors, because those are negative by design and the dictionary's uncertainty
and litigious measures say more about them. Up to 600 sentences per document are
scored, which covers the whole MD&A of most filings. The model is downloaded
once (about 440 MB) and runs on CPU.

### 5.3 Tone index (headline number)

**Tone index** = mean of the MD&A score and the press-release score, using
FinBERT when available and LM net tone otherwise. The method in use is printed
next to every tone figure. Scores from different methods are never mixed in one
index.

### 5.4 Why MD&A tone is informative

MD&A tone has been shown to carry information about future performance beyond
the reported numbers:

* Li, F. (2010). *The Information Content of Forward-Looking Statements in
  Corporate Filings—A Naïve Bayesian Machine Learning Approach.* Journal of
  Accounting Research 48(5), 1049–1102.
  <https://doi.org/10.1111/j.1475-679X.2010.00382.x>
* Survey of methods and pitfalls: Loughran, T. & McDonald, B. (2016). *Textual
  Analysis in Accounting and Finance: A Survey.* Journal of Accounting Research
  54(4), 1187–1230. <https://doi.org/10.1111/1475-679X.12123>

---

## 6. Financial health

### 6.1 Scorecard (0–100)

Five pillars, each the average of two metrics. Each metric is scaled linearly
between a *weak* value (score 0) and a *strong* value (score 100) and clamped.

| Pillar | Metric | Weak → 0 | Strong → 100 |
|---|---|---|---|
| Growth | Revenue growth YoY | −10% | +15% |
| Growth | Diluted EPS growth YoY | −20% | +20% |
| Profitability | Operating margin (TTM) | 0% | 30% |
| Profitability | Net margin (TTM) | 0% | 25% |
| Cash generation | FCF margin (TTM) | 0% | 25% |
| Cash generation | FCF / net income (TTM) | 0.5× | 1.2× |
| Liquidity | Current ratio | 0.5 | 2.0 |
| Liquidity | (Cash + all marketable securities) / current liabilities | 0.2 | 1.5 |
| Leverage | Total debt / equity | 3.0 | 0.3 |
| Leverage | Total debt / operating cash flow (TTM, years) | 5.0 | 0.5 |

Overall score = mean of the available pillars. Bands: **Strong** ≥ 75,
**Healthy** ≥ 55, **Mixed** ≥ 40, **Weak** < 40.

These thresholds are **generic rules of thumb chosen for transparency**, not
industry benchmarks. A bank, a utility and a software company have very
different "normal" ratios. They live in `src/earnings_sentiment/health.py →
THRESHOLDS` so you can tune them for your portfolio.

Long-term marketable securities are included in liquidity because, for
cash-rich companies, they are mostly high-grade bonds that can be sold quickly.
For Apple this makes a large difference: its current ratio is about 1.0, but
including all securities roughly doubles the cash cover.

### 6.2 Piotroski F-Score (0–9)

* Piotroski, J. (2000). *Value Investing: The Use of Historical Financial
  Statement Information to Separate Winners from Losers.* Journal of Accounting
  Research 38 (Supplement), 1–41. <https://doi.org/10.2307/2672906>

Nine pass/fail signals. The original uses annual data; here they are computed on
a **trailing-twelve-month** basis against the same TTM one year earlier, so the
score refreshes every quarter:

1. Positive return on assets (TTM net income / assets a year ago)
2. Positive operating cash flow (TTM)
3. Return on assets improved
4. Operating cash flow > net income (earnings quality)
5. Long-term debt / assets decreased
6. Current ratio improved
7. No net new shares issued
8. Gross margin improved
9. Asset turnover improved

If a signal's inputs are missing it is reported as "n/a" and the score shows
`score / available`.

---

## 7. "What changed" summary

Rule-based statements, each tied to a number shown elsewhere:

* revenue and EPS growth (YoY and QoQ);
* gross and operating margin change, called out when ≥ 50 basis points;
* TTM free cash flow and its ratio to net income;
* net-cash change versus a year ago; buybacks;
* tone change versus last quarter and a year ago, called out when ≥ 0.05;
* uncertainty-word share in MD&A versus a year ago, called out when the relative
  change is ≥ 15%;
* risk-factor section length versus a year ago (≥ 15%), or "no material changes";
* health-score change, called out when ≥ 3 points.

**Overall direction** counts positive and negative signals: **Improving** if
positives exceed negatives by 3 or more, **Deteriorating** if the reverse, else
**Stable / mixed**.

---

## 8. Text changes (Changes tab)

The MD&A or risk-factor section of a filing is split into sentences and matched
against the same section of an earlier filing (the same fiscal quarter a year
before by default, so a 10-Q is compared with a 10-Q and a 10-K with a 10-K).

1. **Normalise** each sentence: lower case, punctuation removed, and numbers,
   percentages, years and dates replaced by placeholders. "Net sales rose 8% in
   2025" and "Net sales rose 12% in 2026" become the same sentence, so routine
   figure updates do not count as changes.
2. **Exact matches** after normalisation are *carried over*.
3. Remaining sentences are compared word by word (`difflib.SequenceMatcher`);
   the best pairs with similarity ≥ 0.72 are *reworded*. A rewording that
   changes at most two words and adds no cautionary language is *minor*.
4. Unmatched sentences in the new filing are *new*; unmatched sentences in the
   old filing were *dropped*.

Each new or reworded sentence is tagged with the Loughran-McDonald categories it
contains (negative, uncertainty, litigious, constraining, positive) and, for the
MD&A, scored by the active tone model. *Notable* rows contain cautionary words or
have a model tone of at least ±0.5.

The share of sentences new or substantively reworded is described as light
(< 20%), usual (20–55%) or heavy (≥ 55%). These bands were calibrated on Apple
and Microsoft 10-Q/10-K filings from 2025–26, where year-on-year MD&A changes
ranged from about 30% to 52%; they are a rough guide, not a statistical test.

Why it matters: Cohen, Malloy & Nguyen, "Lazy Prices", *Journal of Finance*
75(3), 2020, pp. 1371–1415 (<https://doi.org/10.1111/jofi.12885>) found that most
reports repeat the previous year's wording, and that firms which change it
substantially see lower future returns and more negative news.

## 9. Comparing companies

Fiscal years differ, so each quarter is placed in the **calendar quarter that
contains its midpoint** (period end minus 45 days). Apple's quarter ending 26 Sep
and Microsoft's ending 30 Sep both fall in Jul–Sep; NVIDIA's quarter ending in late
July (May–July) falls in Apr–Jun. The head-to-head table uses each company's
latest analysed quarter and stars the strongest value per row (lowest for debt to
equity, ignoring negative equity).

## 10. Limitations

* Word counts and language models measure *how management writes*, which
  companies manage carefully. Treat tone as one signal among many.
* XBRL tagging varies between companies. Unusual tags may leave some metrics
  blank ("n/a") rather than guessed.
* Q4 values are derived (full year − nine months) and can differ slightly from
  figures a company quotes in its press release.
* Earnings-call transcripts are not included (licensing). The prepared remarks
  and analyst Q&A often carry the strongest tone signal.
* Scorecard thresholds are generic; compare a company with its own history first.
