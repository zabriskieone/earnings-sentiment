"""Plain-English help: how to read each chart, and a glossary of terms.

Written for someone who has never read an earnings report. Each chart guide
answers four questions: what is this, how do I read it, what does good look
like, and which terms do I need.
"""

from __future__ import annotations

CHART_GUIDES: dict[str, dict] = {
    "revenue": {
        "title": "Revenue & net income",
        "what": "How much the company sold each quarter (revenue) and how much of that it kept as profit after "
                "every cost and tax (net income).",
        "read": "Each tall capsule is one quarter's revenue; the faint track behind it just sets the scale. The "
                "thin orange bar inside is net income. The darker capsule is the latest quarter.",
        "good": "Capsules growing over time, and the orange bar staying a healthy share of the capsule. Compare a "
                "quarter with the same quarter a year earlier: many companies (Apple included) sell far more in "
                "the holiday quarter, so a drop right after it is normal.",
        "terms": ["Revenue", "Net income", "Fiscal quarter"],
    },
    "growth": {
        "title": "Year-on-year growth",
        "what": "How much revenue and earnings per share changed compared with the same quarter one year earlier.",
        "read": "Each point is a percentage change. Above the 0% line means growth, below it means shrinkage. "
                "The pill marks the latest quarter.",
        "good": "Lines staying above zero. Sudden spikes are often one-off effects (a tax charge or gain a year "
                "earlier), so check the filing before reading too much into them.",
        "terms": ["YoY", "Diluted EPS"],
    },
    "margins": {
        "title": "Margins",
        "what": "The share of every dollar of revenue the company keeps at three levels: after making the product "
                "(gross), after running the business (operating), and after everything including tax (net).",
        "read": "Higher lines are better. The gap between lines shows where money goes: gross to operating is "
                "spending on research, sales and admin; operating to net is mostly tax and interest.",
        "good": "Stable or rising lines. A falling gross margin can mean rising costs or price pressure.",
        "terms": ["Gross margin", "Operating margin", "Net margin", "bps"],
    },
    "cash": {
        "title": "Cash generation & buybacks",
        "what": "Cash actually coming in from the business, what is left after investment, and how much was spent "
                "buying back the company's own shares.",
        "read": "Three bars per quarter: operating cash flow (violet), free cash flow (orange) and buybacks (teal).",
        "good": "Free cash flow consistently positive and close to net income. Buybacks larger than free cash "
                "flow for long periods would need to be funded from savings or debt.",
        "terms": ["Operating cash flow", "Free cash flow", "Buybacks"],
    },
    "balance": {
        "title": "Balance sheet",
        "what": "Whether the company holds more cash and investments than it owes (net cash), and how its debt "
                "is changing.",
        "read": "The teal area is net cash: above zero means cash exceeds debt. The dotted orange line is total debt.",
        "good": "Net cash steady or rising, debt steady or falling. Large cash-rich companies often carry debt "
                "on purpose because borrowing is cheap, so look at the trend rather than the level.",
        "terms": ["Net cash", "Total debt"],
    },
    "tone": {
        "title": "Management tone index",
        "what": "How positive or cautious management's own language was in the quarterly report (MD&A) and the "
                "earnings press release.",
        "read": "Bars above the middle line lean positive; bars below lean negative. The scale runs from -1 "
                "(very negative) to +1 (very positive). The darker bar is the latest quarter.",
        "good": "The change matters more than the level. A tone that drops while the numbers still look fine can "
                "be an early warning; a rising tone suggests management is more confident.",
        "terms": ["Tone index", "MD&A", "FinBERT", "Loughran-McDonald dictionary"],
    },
    "tone_sources": {
        "title": "Tone by document & method",
        "what": "The tone index broken into its parts: each document, scored by each method.",
        "read": "Press releases usually score higher because companies write them to highlight good news. MD&A "
                "dictionary scores are often below zero even for healthy companies, because words like "
                "'decline' and 'risk' are common in neutral disclosure.",
        "good": "Compare each line with its own history. When the methods agree on a change, it is more reliable.",
        "terms": ["FinBERT", "Loughran-McDonald dictionary", "MD&A", "Press release (8-K)"],
    },
    "lm_mdna": {
        "title": "Cautious language",
        "what": "The share of words in the MD&A that signal uncertainty, negativity or legal matters, counted with "
                "a finance-specific word list.",
        "read": "Each line is a percentage of all words. For example 1.3% uncertainty means about 13 in every "
                "1,000 words are words like 'may', 'approximately' or 'uncertain'.",
        "good": "Flat or falling lines. A jump in uncertainty words often comes with new risks or a less "
                "predictable outlook.",
        "terms": ["Loughran-McDonald dictionary", "Uncertainty words", "Litigious words"],
    },
    "risk_length": {
        "title": "Risk-factor section length",
        "what": "How many words the company spends describing what could go wrong.",
        "read": "Orange bars are annual reports (10-K), which list every risk. Violet bars are quarterly reports "
                "(10-Q), which only list changes, so they are much shorter or nearly empty.",
        "good": "Compare like with like: annual with annual. A clearly longer section usually means new risks "
                "were added.",
        "terms": ["Risk factors", "10-K", "10-Q"],
    },
    "changes": {
        "title": "What changed in the words (Changes tab)",
        "what": "Every sentence of a quarter's MD&A or risk factors, matched against an earlier report: new "
                "sentences, sentences that were reworded, and sentences that were dropped.",
        "read": "Figures, dates and punctuation are ignored, so 'sales rose 5%' becoming 'sales rose 9%' counts as "
                "carried over. Green rows are new, amber rows were reworded (struck-through words were removed, "
                "highlighted words added) and red rows were dropped. Tags show cautionary words (negative, uncertain, "
                "legal, constraining) from the Loughran-McDonald dictionary; 'Notable only' keeps those rows.",
        "good": "Compare with the same quarter a year ago: it pairs a 10-Q with a 10-Q and a 10-K with a 10-K. A "
                "heavy rewrite, or many new cautionary sentences, is worth reading closely. Research (Cohen, Malloy "
                "and Nguyen, 'Lazy Prices', Journal of Finance 2020) found that companies that change their report "
                "wording a lot tend to underperform afterwards.",
        "terms": ["MD&A", "Risk factors", "Lazy Prices"],
    },
    "gauge": {
        "title": "Health score",
        "what": "A single 0-100 score summarising the company's financial strength in the latest quarter.",
        "read": "It is the average of five pillars (growth, profitability, cash generation, liquidity and "
                "leverage). 75+ is Strong, 55-74 Healthy, 40-54 Mixed, below 40 Weak.",
        "good": "Higher is better, but compare a company with its own history first: the thresholds are general "
                "rules of thumb, not tuned for each industry.",
        "terms": ["Health score", "TTM"],
    },
    "pillars": {
        "title": "Health pillars",
        "what": "The five parts of the health score, each scored 0-100.",
        "read": "Longer bars are stronger. The faint track shows the full 100.",
        "good": "No single pillar far below the rest. A low liquidity score with strong cash generation (as with "
                "Apple) usually reflects a deliberate choice to keep little idle cash, not a problem.",
        "terms": ["Growth", "Profitability", "Liquidity", "Leverage", "Current ratio", "Debt to equity"],
    },
    "fscore": {
        "title": "Piotroski F-Score",
        "what": "Nine yes/no checks of whether the company's fundamentals are improving compared with a year earlier.",
        "read": "One point per check passed, so the scale is 0-9. The Health tab lists every check.",
        "good": "7-9 is strong, 4-6 average, 0-3 weak. It measures improvement, so a great company can still "
                "score lower in a flat year.",
        "terms": ["Piotroski F-Score", "Return on assets"],
    },
    "health": {
        "title": "Health over time",
        "what": "How the overall health score moved quarter by quarter.",
        "read": "Click a pillar name below the chart to add its line; click again to hide it.",
        "good": "A steady or rising line. A falling line points you to the pillar that weakened.",
        "terms": ["Health score"],
    },
}

GLOSSARY: dict[str, str] = {
    "Lazy Prices": "A 2020 study by Cohen, Malloy and Nguyen (Journal of Finance) showing that most reports repeat "
                   "last year's wording, and that firms which change it substantially tend to see weaker returns "
                   "and news afterwards. The Changes tab shows those edits.",
    "10-K": "The annual report every US-listed company files with the SEC. It covers the full fiscal year and "
            "lists every major risk.",
    "10-Q": "The quarterly report filed for the first three quarters of the fiscal year. Shorter than a 10-K.",
    "Press release (8-K)": "On results day, companies file a form 8-K with the SEC. Its Exhibit 99.1 is the earnings "
                           "press release: the headline numbers and management's quotes.",
    "MD&A": "Management's Discussion and Analysis: the section of the 10-Q/10-K where management explains the "
            "results in its own words. The main source for tone.",
    "Risk factors": "The section of a filing that lists what could hurt the business.",
    "SEC EDGAR": "The US Securities and Exchange Commission's public database of company filings. Every figure "
                 "here comes from it.",
    "XBRL": "Machine-readable tags attached to the numbers in a filing, which let software read the figures "
            "reliably.",
    "Fiscal quarter": "A company's own three-month reporting period. Apple's fiscal year ends in late September, "
                      "so its Q1 is the October-December holiday quarter.",
    "Revenue": "Total money from sales before any costs. Also called sales or the top line.",
    "Net income": "Profit left after all costs, interest and taxes. Also called earnings or the bottom line.",
    "Diluted EPS": "Earnings per share: net income divided by the number of shares, counting stock options and "
                   "other awards that could become shares.",
    "YoY": "Year-on-year: compared with the same quarter one year earlier. Fairer than comparing with the "
           "previous quarter when sales are seasonal.",
    "QoQ": "Quarter-on-quarter: compared with the quarter just before.",
    "TTM": "Trailing twelve months: the sum of the last four quarters. Smooths out seasonal ups and downs.",
    "Gross margin": "Revenue minus the direct cost of making the products, as a share of revenue.",
    "Operating margin": "Profit from running the business (after research, sales and admin costs), as a share of "
                        "revenue.",
    "Net margin": "Net income as a share of revenue.",
    "bps": "Basis points: hundredths of a percentage point. A margin moving from 47.2% to 47.9% is +70 bps.",
    "Operating cash flow": "Cash actually generated by the business in the period, which can differ from accounting "
                           "profit.",
    "Free cash flow": "Operating cash flow minus capital expenditure (spending on buildings, equipment, data "
                      "centres). The cash truly available to return to shareholders or save.",
    "Buybacks": "Money spent repurchasing the company's own shares, which spreads future profits across fewer shares.",
    "Net cash": "Cash plus marketable securities, minus all debt. Positive means the company could repay all debt "
                "from savings.",
    "Total debt": "Long-term debt, the current portion of long-term debt, and short-term commercial paper.",
    "Current ratio": "Short-term assets divided by short-term liabilities. Above 1 means short-term bills are "
                     "covered by short-term assets.",
    "Debt to equity": "Total debt divided by shareholders' equity. Lower means less reliance on borrowing.",
    "Return on assets": "Net income divided by total assets: how efficiently the company turns what it owns into "
                        "profit.",
    "Tone index": "This app's headline sentiment number: the average tone of the MD&A and the press release, "
                  "from -1 (negative) to +1 (positive).",
    "FinBERT": "A language model trained on financial text (Araci, 2019). It reads each sentence in context and "
               "rates it positive, negative or neutral.",
    "Loughran-McDonald dictionary": "Word lists built specifically for financial filings (Loughran & McDonald, "
                                    "2011). Unlike general dictionaries, it does not treat words like 'liability' "
                                    "or 'tax' as negative.",
    "Uncertainty words": "Words signalling imprecision or doubt, such as 'may', 'approximately', 'believe'.",
    "Litigious words": "Words related to legal matters, such as 'lawsuit', 'plaintiff', 'regulation'.",
    "Health score": "This app's 0-100 summary of financial strength, averaging five pillars. See the methodology "
                    "document for the exact thresholds.",
    "Growth": "Health pillar: revenue and EPS growth year-on-year.",
    "Profitability": "Health pillar: operating and net margins (TTM).",
    "Liquidity": "Health pillar: ability to pay short-term bills (current ratio and cash cover).",
    "Leverage": "Health pillar: how much debt the company carries relative to equity and cash flow.",
    "Piotroski F-Score": "Nine yes/no checks of improving fundamentals (Piotroski, 2000), scored 0-9.",
}

KPI_HELP = {
    "Revenue": "Total sales in the latest quarter, with the change versus the same quarter last year. The small "
               "chart shows the last quarters.",
    "Diluted EPS": "Profit per share in the latest quarter, versus the same quarter last year.",
    "Gross margin": "Share of revenue left after the direct cost of the products; the change is in percentage "
                    "points versus a year ago.",
    "Free cash flow (TTM)": "Cash left after investment over the last twelve months, versus the twelve months "
                            "before.",
    "Tone index": "Management's tone from -1 (negative) to +1 (positive), versus the same quarter last year.",
    "Health score": "Overall financial strength, 0-100, versus a year ago.",
}


def guide_markdown(key: str) -> str:
    g = CHART_GUIDES.get(key)
    if not g:
        return ""
    terms = "\n".join(f"- **{t}**: {GLOSSARY[t]}" for t in g.get("terms", []) if t in GLOSSARY)
    return (
        f"**What it shows**  \n{g['what']}\n\n"
        f"**How to read it**  \n{g['read']}\n\n"
        f"**What good looks like**  \n{g['good']}"
        + (f"\n\n**Terms**\n{terms}" if terms else "")
    )


def guide_html(key: str) -> str:
    """Same content for the HTML report, as a collapsible note."""
    import html as _h

    g = CHART_GUIDES.get(key)
    if not g:
        return ""
    return (
        '<details class="howto"><summary>How to read this chart</summary>'
        f"<p><b>What it shows.</b> {_h.escape(g['what'])}</p>"
        f"<p><b>How to read it.</b> {_h.escape(g['read'])}</p>"
        f"<p><b>What good looks like.</b> {_h.escape(g['good'])}</p></details>"
    )
