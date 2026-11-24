"""Command line: save a dated snapshot of the analysis into the repo.

    python -m earnings_sentiment snapshot AAPL
    python -m earnings_sentiment snapshot AAPL MSFT --quarters 8 --no-finbert

Writes snapshots/<TICKER>/<FYyyyy-Qn>/{summary.json, report.html, report.pdf}
and updates snapshots/<TICKER>/history.csv - commit these to git after each
results day so the repository's history shows how every quarter was read.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time

from . import config
from .analysis import analyze
from .edgar import EdgarError
from .narrative import build_insights, verdict
from .report import build_html, build_pdf

HISTORY_FIELDS = [
    "quarter", "period_end", "form", "revenue", "revenue_yoy", "eps_diluted", "gross_margin",
    "operating_margin", "fcf", "tone_index", "mdna_finbert", "press_finbert", "mdna_lm_tone",
    "mdna_uncertainty_pct", "health_score", "health_band", "piotroski", "verdict", "analysed_at",
]


def _num(v):
    try:
        f = float(v)
        return "" if f != f else round(f, 6)
    except (TypeError, ValueError):
        return ""


def snapshot(ticker: str, quarters: int, use_finbert: bool) -> str:
    def progress(p: float, msg: str) -> None:
        print(f"  [{p:5.0%}] {msg}", file=sys.stderr)

    a = analyze(ticker, quarters, use_finbert=use_finbert, progress=progress)
    out_dir = config.SNAPSHOT_DIR / a.company.ticker / a.latest.fq.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(a.to_summary(), indent=2, default=str), encoding="utf-8")
    (out_dir / "report.html").write_text(build_html(a, offline=False), encoding="utf-8")
    (out_dir / "report.pdf").write_bytes(build_pdf(a))

    # history.csv: one row per quarter, refreshed from this run
    hist_path = config.SNAPSHOT_DIR / a.company.ticker / "history.csv"
    existing: dict[str, dict] = {}
    if hist_path.exists():
        with hist_path.open(encoding="utf-8") as fh:
            existing = {r["quarter"]: r for r in csv.DictReader(fh)}
    st = a.sentiment_table()
    fin = a.financials
    v = verdict(build_insights(a))[0]
    for q in a.quarters:
        lbl = q.fq.label
        f = fin.loc[lbl] if lbl in fin.index else {}
        s = st.loc[lbl] if lbl in st.index else {}
        existing[lbl] = {
            "quarter": lbl, "period_end": q.period_end.isoformat(), "form": q.filing.form,
            "revenue": _num(f.get("revenue")), "revenue_yoy": _num(f.get("revenue_yoy")),
            "eps_diluted": _num(f.get("eps_diluted")), "gross_margin": _num(f.get("gross_margin")),
            "operating_margin": _num(f.get("operating_margin")), "fcf": _num(f.get("fcf")),
            "tone_index": _num(s.get("tone_index")), "mdna_finbert": _num(s.get("mdna_finbert")),
            "press_finbert": _num(s.get("press_finbert")), "mdna_lm_tone": _num(s.get("mdna_lm_tone")),
            "mdna_uncertainty_pct": _num(s.get("mdna_unc_pct")),
            "health_score": _num((q.health or {}).get("overall")), "health_band": (q.health or {}).get("band", ""),
            "piotroski": (q.fscore or {}).get("score", ""),
            "verdict": v if q is a.latest else existing.get(lbl, {}).get("verdict", ""),
            "analysed_at": a.generated_at,
        }
    with hist_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HISTORY_FIELDS)
        w.writeheader()
        for lbl in sorted(existing, key=lambda s: (int(s[2:6]), int(s[-1]))):
            w.writerow({k: existing[lbl].get(k, "") for k in HISTORY_FIELDS})
    for warning in a.warnings:
        print(f"  note: {warning}", file=sys.stderr)
    return str(out_dir)


def models_cmd(action: str, model_id: str | None) -> int:
    from . import models

    if action == "list":
        active = models.active_model()
        for m in models.catalog():
            state = "installed" if models.is_installed(m["id"]) else "not downloaded"
            mark = "*" if m["id"] == active else " "
            print(f"{mark} {m['id']:18s} {m['name']:20s} {m['size_bytes'] / 1e6:5.0f} MB  {state:15s} {m['tagline']}")
        print("\n* = active model.  Download: python -m earnings_sentiment models download <id>")
        return 0
    if not model_id:
        print("Please give a model id (see: models list)", file=sys.stderr)
        return 2
    if action == "download":
        last = [0.0]

        def show(st):
            if time.time() - last[0] > 0.2 or st.status == "done":
                last[0] = time.time()
                pct = st.done / st.total if st.total else 0
                print(f"\r  {models.display_name(model_id)}: {st.done / 1e6:5.0f} / {st.total / 1e6:.0f} MB "
                      f"({pct:4.0%})", end="", flush=True)

        models.download(model_id, progress=show)
        print()
        if not models.load_settings().get("active_model"):
            models.set_active(model_id)
        print(f"Installed {models.display_name(model_id)}.")
    elif action == "use":
        models.set_active(None if model_id == "none" else model_id)
        print(f"Active model: {models.display_name(models.active_model())}")
    elif action == "remove":
        models.remove(model_id)
        print(f"Removed {model_id}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="earnings_sentiment", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("snapshot", help="analyse tickers and save reports under snapshots/")
    sp.add_argument("tickers", nargs="+")
    sp.add_argument("--quarters", type=int, default=8, help="number of recent quarters (default 8)")
    sp.add_argument("--no-finbert", action="store_true", help="dictionary scoring only (fast, no model download)")
    mp = sub.add_parser("models", help="list, download, select or remove sentiment models")
    mp.add_argument("action", choices=["list", "download", "use", "remove"])
    mp.add_argument("model_id", nargs="?", help="e.g. finbert, finbert-tone, distilroberta-fin, or 'none'")
    args = parser.parse_args(argv)

    if args.cmd == "models":
        return models_cmd(args.action, args.model_id)

    status = 0
    for t in args.tickers:
        print(f"Analysing {t.upper()} ...", file=sys.stderr)
        try:
            path = snapshot(t, args.quarters, not args.no_finbert)
            print(f"Saved {path}")
        except EdgarError as exc:
            print(f"Error for {t}: {exc}", file=sys.stderr)
            status = 1
    return status
