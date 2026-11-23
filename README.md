# 📈 EarningsPulse

**Sentiment & health from every quarterly result.**

[![tests](https://github.com/zabriskieone/earnings-sentiment/actions/workflows/tests.yml/badge.svg)](https://github.com/zabriskieone/earnings-sentiment/actions/workflows/tests.yml)

EarningsPulse is an interactive dashboard that reads every quarterly result a company
files with the US SEC and shows:

* **Management tone**: is the language in the MD&A and the earnings press release
  getting more positive or more cautious? Scored with the Loughran-McDonald finance
  dictionary and (optionally) the FinBERT language model.
* **Financial trends**: revenue, EPS, margins, cash flow and balance sheet, each
  compared with the **previous quarter** and the **same quarter last year**.
* **Financial health**: a transparent 0–100 scorecard plus the Piotroski F-Score.
* **What changed**: a plain-English summary of the latest quarter with an overall
  *Improving / Stable / Deteriorating* call.
* **Downloadable report** in HTML (interactive charts, works offline) or PDF,
  plus CSV/JSON data.

Search **any company that files 10-Q/10-K reports with the SEC**, then press
*Analyse*. Every figure links back to the filing it came from.

![Dashboard overview](docs/images/dashboard-overview.png)

> **Disclaimer**: a hobby research tool. Automated text and ratio analysis of
> public filings is not investment advice. Verify figures against the linked
> filings.

---

## Quick start

### Mac or Linux: one command

Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/zabriskieone/earnings-sentiment/main/install.sh | bash
```

That's it. It downloads EarningsPulse to `~/EarningsPulse`, sets everything up, asks two quick questions
(include the FinBERT AI model? your name and e-mail for the SEC) and opens the dashboard at
<http://localhost:8501>. The first run takes a few minutes; after that it starts in seconds.

**Next time:** double-click **`Start EarningsPulse.command`** in the `EarningsPulse` folder (first time:
right-click it, choose *Open*, then *Open* again so macOS allows it), or run `~/EarningsPulse/start.sh`.
Running the one-liner again also updates the app to the latest version.

### Windows: one command

Open **PowerShell** and paste:

```powershell
irm https://raw.githubusercontent.com/zabriskieone/earnings-sentiment/main/install.ps1 | iex
```

Needs Python 3.10+ from [python.org](https://www.python.org/downloads/windows/) (tick *Add python.exe to PATH*).
Next time, double-click **`start.bat`** in `%USERPROFILE%\EarningsPulse`.

> Prefer to look before you run? Both installers are short and readable:
> [`install.sh`](install.sh), [`install.ps1`](install.ps1), [`start.sh`](start.sh), [`start.bat`](start.bat).
> Or download the repo (green **Code → Download ZIP**) and double-click the start file yourself.

**What the installer does**
- uses your Python 3.10+, or offers to install one automatically with [uv](https://docs.astral.sh/uv/) if you have none (Mac/Linux);
- keeps everything inside the app folder (`.venv`), so nothing else on your computer changes;
- saves your SEC name and e-mail in `.env` on your computer only (never uploaded);
- only reinstalls packages when an update changes them.

To remove EarningsPulse, delete the `EarningsPulse` folder.

### Docker (alternative)

```bash
git clone https://github.com/zabriskieone/earnings-sentiment.git && cd earnings-sentiment && docker compose up --build
```

Then open <http://localhost:8501>. For a smaller image without FinBERT:
`docker compose build --build-arg WITH_FINBERT=false`.

### Manual setup (developers)

```bash
python -m venv .venv && source .venv/bin/activate
```
```bash
pip install -r requirements.txt -r requirements-finbert.txt
```
```bash
streamlit run app.py
```

### New to earnings reports?

Open the **Guide** tab in the app for a plain-English primer and glossary, or click **How to read this chart**
under any chart.

---

## How long does an analysis take?

| | First run | Repeat run |
|---|---|---|
| Dictionary only, 8 quarters | ~20–40 s (downloads ~30 filings from SEC) | ~2 s (disk cache) |
| With FinBERT, 8 quarters | + ~30–60 s on a laptop CPU (+ one-time model download) | ~2 s |

SEC downloads and sentiment scores are cached in `data/cache/`, so only new
filings are fetched after each results day.

---

## Tracking your portfolio over time (git workflow)

After a company reports, save a dated snapshot and commit it (run these from the app folder; `.venv/bin/python`
is the environment the installer created, or use `python` if you set things up manually):

```bash
.venv/bin/python -m earnings_sentiment snapshot AAPL
```
```bash
git add snapshots && git commit -m "AAPL FY2026 Q4 results snapshot"
```

This writes:

```
snapshots/AAPL/
├── history.csv                # one row per quarter: revenue, margins, tone, health, verdict
└── FY2026-Q4/
    ├── summary.json           # every score + links to the source filings
    ├── report.html            # the full report
    └── report.pdf
```

Several tickers at once: `.venv/bin/python -m earnings_sentiment snapshot AAPL MSFT NVDA`.
Over time, `git log -p snapshots/AAPL/history.csv` shows exactly how each quarter
was read when it came out.

---

## What's inside

![Landing page](docs/images/dashboard-landing.png)

Use the ☀️/🌙 icon at the top right to switch between light and dark mode.

![Health tab in light mode](docs/images/dashboard-health-light.png)

| Tab | Shows |
|---|---|
| **Overview** | KPIs with YoY change, "what changed" bullets, revenue and tone charts |
| **Financials** | Revenue/net income, YoY growth, margins, cash flow and buybacks, net cash vs debt, quarterly table |
| **Sentiment** | Tone index, tone by document and method, LM word categories, risk-factor length, and the **evidence sentences** behind each score |
| **Health** | Pillar scores, health trend, Piotroski F-Score with every signal |
| **Guide** | A primer for beginners, every chart explained, and a searchable glossary |
| **Sources & method** | Links to every filing used and a method summary |

**Data sources (all free and official)**

* SEC EDGAR APIs — <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
* 10-Q / 10-K: MD&A and Risk Factors sections
* 8-K Item 2.02, Exhibit 99.1: earnings press release
* Company logos: Financial Modeling Prep public image URL, by ticker (`financialmodelingprep.com/image-stock/<TICKER>.png`). Only the ticker is sent, logos are cached locally, and a monogram tile is shown when none exists

**Methods** (full details and formulas in [docs/METHODOLOGY.md](docs/METHODOLOGY.md))

* Loughran & McDonald (2011), *Journal of Finance* 66(1) — finance sentiment word lists. <https://doi.org/10.1111/j.1540-6261.2010.01625.x>
* Araci (2019), *FinBERT* — <https://arxiv.org/abs/1908.10063>, model [`ProsusAI/finbert`](https://huggingface.co/ProsusAI/finbert)
* Piotroski (2000), *Journal of Accounting Research* 38 — F-Score. <https://doi.org/10.2307/2672906>
* Li (2010), *Journal of Accounting Research* 48(5) — MD&A tone predicts future performance. <https://doi.org/10.1111/j.1475-679X.2010.00382.x>

---

## Project layout

```
install.sh / install.ps1       one-line installers (Mac/Linux, Windows)
start.sh / start.bat           launchers (also "Start EarningsPulse.command" for macOS Finder)
app.py                         Streamlit dashboard
src/earnings_sentiment/
  edgar.py                     SEC client (rate-limited, disk-cached)
  periods.py                   fiscal-quarter mapping (52/53-week years)
  financials.py                XBRL facts -> quarterly table (Q4 derivation, TTM, YoY)
  textextract.py               MD&A / risk-factor / press-release extraction
  sentiment.py                 Loughran-McDonald + FinBERT scoring
  health.py                    scorecard + Piotroski F-Score
  analysis.py                  orchestration
  narrative.py                 "what changed" rules
  charts.py                    Plotly charts
  explain.py                   "how to read" guides and glossary
  logos.py                     company logos with monogram fallback
  theme.py                     EarningsPulse look, light/dark palettes
  report.py                    HTML + PDF reports
  cli.py                       `snapshot` command
tests/                         offline unit tests (pytest)
snapshots/                     committed quarterly snapshots
docs/METHODOLOGY.md            how every number is computed, with references
```

Run the tests: `pip install -r requirements-dev.txt && pytest`.

---

## Hosting it later (optional)

The app runs unchanged on hosted platforms if you want a public URL:

* **Hugging Face Spaces** (free CPU tier: 2 vCPU, 16 GB RAM, sleeps after 48 h idle)
  has enough memory for FinBERT. Create a *Docker* Space and push this repository;
  set `SEC_USER_AGENT` as a Space secret.
  Docs: <https://huggingface.co/docs/hub/en/spaces-overview>
* **Streamlit Community Cloud**: free, but its memory limit (about 1–2.7 GB) is tight
  for FinBERT. Use it with `requirements.txt` only (dictionary mode).
  Docs: <https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app>

---

## Limitations

* US SEC filers with 10-Q/10-K only (no 20-F/6-K foreign issuers yet).
* Segment and regional revenue are not yet extracted (they need XBRL dimensions).
* Earnings-call transcripts are not included (licensing).
* Health thresholds are generic; tune `THRESHOLDS` in `health.py` for your sectors.

## License

MIT — see [LICENSE](LICENSE). The Loughran-McDonald word lists are © their authors.
The bundled copy comes from the MIT-licensed `pysentiment2` package. The official
dictionary is free for academic use, and commercial use needs a licence from the
authors.
