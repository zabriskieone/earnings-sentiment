"""Local engine for the EarningsPulse desktop app.

A small HTTP API on 127.0.0.1 that the app's interface calls. It wraps the same
analysis code as the command line and the browser version.

    python -m earnings_sentiment.server --port 8765 --token <secret>

Security: binds to 127.0.0.1 only, and every /api call except /api/health must
carry the per-launch token (header X-EP-Token) that the desktop app generates,
so other local programs or web pages cannot drive it.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import shutil
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from . import __version__, changes, charts, compare, config, explain, logos, models, watchlist
from .analysis import SECTIONS, Analysis, analyze
from .edgar import FACTS_URL, EdgarClient, EdgarError
from .health import METRIC_LABELS
from .narrative import build_insights, verdict
from .report import build_html, build_pdf, data_table, kpis, metric_value

app = FastAPI(title="EarningsPulse engine", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
                   "http://localhost:1420", "http://127.0.0.1:1420"],
    allow_methods=["*"], allow_headers=["*"],
)
TOKEN = os.environ.get("EARNINGSPULSE_TOKEN", "")


def require_token(x_ep_token: str = Header(default="")) -> None:
    if TOKEN and not secrets.compare_digest(x_ep_token, TOKEN):
        raise HTTPException(status_code=401, detail="Missing or invalid app token")


auth = [Depends(require_token)]


def clean(obj: Any) -> Any:
    """Make results JSON-safe (NaN/inf -> null, numpy/pandas -> Python)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        try:
            return clean(obj.item())
        except (ValueError, AttributeError):
            pass
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


# --------------------------------------------------------------------------- settings
def sec_user_agent() -> str:
    return (models.load_settings().get("sec_user_agent") or config.SEC_USER_AGENT or "").strip()


class SettingsIn(BaseModel):
    sec_user_agent: str | None = None
    sec_name: str | None = None
    sec_email: str | None = None
    theme: str | None = None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def split_identity(ua: str) -> tuple[str, str]:
    """'Jane Doe jane@example.com' -> ('Jane Doe', 'jane@example.com')."""
    parts = ua.split()
    email = next((p for p in reversed(parts) if "@" in p), "")
    name = " ".join(p for p in parts if p != email)
    return name, email


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/api/settings", dependencies=auth)
def get_settings() -> dict:
    s = models.load_settings()
    ua = sec_user_agent()
    name, email = split_identity(ua)
    return {"sec_user_agent": ua, "sec_user_agent_valid": config.valid_user_agent(ua),
            "sec_name": name, "sec_email": email,
            "theme": s.get("theme", "system"), "active_model": models.active_model(),
            "data_dir": str(config.DATA_DIR)}


@app.put("/api/settings", dependencies=auth)
def put_settings(body: SettingsIn) -> dict:
    changes = {}
    if body.sec_name is not None or body.sec_email is not None:
        name = " ".join((body.sec_name or "").split())
        email = (body.sec_email or "").strip()
        if not name:
            raise HTTPException(400, "Please enter your name.")
        if not EMAIL_RE.match(email):
            raise HTTPException(400, "Please enter a valid e-mail address, e.g. jane@example.com.")
        changes["sec_user_agent"] = f"{name} {email}"
    elif body.sec_user_agent is not None:
        ua = body.sec_user_agent.strip()
        if ua and not config.valid_user_agent(ua):
            raise HTTPException(400, "Enter your name and e-mail, e.g. 'Jane Doe jane@example.com'")
        changes["sec_user_agent"] = ua
    if body.theme in ("light", "dark", "system"):
        changes["theme"] = body.theme
    models.save_settings(**changes)
    return get_settings()


# --------------------------------------------------------------------------- companies
_companies: list[dict] = []


@app.get("/api/companies", dependencies=auth)
def companies(q: str = Query("", max_length=60), limit: int = 12) -> list[dict]:
    global _companies
    ua = sec_user_agent()
    if not config.valid_user_agent(ua):
        raise HTTPException(400, "Add your name and e-mail in Settings first (the SEC requires it).")
    if not _companies:
        seen, out = set(), []
        for c in EdgarClient(ua).company_list():
            if c.ticker not in seen:
                seen.add(c.ticker)
                out.append({"ticker": c.ticker, "name": c.name, "cik": c.cik})
        _companies = out
    ql = q.strip().lower()
    if not ql:
        return _companies[:limit]
    starts = [c for c in _companies if c["ticker"].lower().startswith(ql)]
    names = [c for c in _companies if ql in c["name"].lower() and c not in starts]
    exact = [c for c in starts if c["ticker"].lower() == ql]
    return (exact + [c for c in starts if c not in exact] + names)[:limit]


@app.get("/api/logo/{ticker}", dependencies=auth)
def logo(ticker: str) -> Response:
    data = logos.logo_png(ticker)
    if not data:
        return JSONResponse({"monogram": logos.monogram(ticker)}, status_code=404)
    return Response(data, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


# --------------------------------------------------------------------------- analyses
class AnalysisIn(BaseModel):
    ticker: str
    quarters: int = 8
    model_id: str | None = None  # None -> active model; "dictionary" -> no neural model
    refresh: bool = False  # re-download SEC financial data first (a new filing just arrived)


class Job:
    def __init__(self, req: AnalysisIn):
        self.id = uuid.uuid4().hex[:12]
        self.req = req
        self.status = "running"
        self.progress = 0.0
        self.message = "Starting"
        self.error = ""
        self.analysis: Analysis | None = None
        self.started = time.time()


_jobs: "OrderedDict[str, Job]" = OrderedDict()
_jobs_lock = threading.Lock()


def _run_job(job: Job) -> None:
    def progress(p: float, msg: str) -> None:
        job.progress, job.message = min(1.0, p), msg

    try:
        mid = job.req.model_id
        if job.req.refresh:
            client = EdgarClient(sec_user_agent())
            client.get_json(FACTS_URL.format(cik=client.lookup(job.req.ticker).cik), ttl_hours=0)
        job.analysis = analyze(job.req.ticker, max(4, min(12, job.req.quarters)),
                               use_finbert=(mid != "dictionary"), model_id=None if mid in (None, "dictionary") else mid,
                               user_agent=sec_user_agent(), progress=progress)
        job.status, job.progress, job.message = "done", 1.0, "Done"
        _record_history(job)
    except EdgarError as exc:
        job.status, job.error = "error", str(exc)
    except Exception as exc:  # report, don't crash the engine
        job.status, job.error = "error", f"Unexpected problem while analysing: {exc}"


@app.post("/api/analyses", dependencies=auth)
def start_analysis(body: AnalysisIn) -> dict:
    if not config.valid_user_agent(sec_user_agent()):
        raise HTTPException(400, "Add your name and e-mail in Settings first (the SEC requires it).")
    return {"job_id": _start_job(body).id}


def _start_job(req: AnalysisIn) -> Job:
    job = Job(req)
    with _jobs_lock:
        _jobs[job.id] = job
        while len(_jobs) > 16:
            _jobs.popitem(last=False)
    threading.Thread(target=_run_job, args=(job,), daemon=True, name=f"analysis-{job.id}").start()
    return job


def _job(job_id: str) -> Job:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Analysis not found (the app may have restarted)")
    return job


@app.get("/api/analyses/{job_id}", dependencies=auth)
def analysis_status(job_id: str) -> dict:
    job = _job(job_id)
    return {"job_id": job.id, "status": job.status, "progress": job.progress, "message": job.message,
            "error": job.error, "elapsed": time.time() - job.started}


def _done(job_id: str) -> Analysis:
    job = _job(job_id)
    if job.status != "done" or not job.analysis:
        raise HTTPException(409, "Analysis is not finished")
    return job.analysis


@app.get("/api/analyses/{job_id}/result", dependencies=auth)
def analysis_result(job_id: str, theme: str = "light") -> dict:
    a = _done(job_id)
    mode = "dark" if theme == "dark" else "light"
    insights = build_insights(a)
    v_label, v_detail = verdict(insights)
    figs = {k: json.loads(f.to_json()) for k, f in charts.all_charts(a, mode).items()}
    h = a.latest.health or {"metrics": {}, "metric_scores": {}}
    evidence = []
    for q in reversed(a.quarters):
        evidence.append({"quarter": q.fq.label, "docs": [
            {"section": sec, "label": SECTIONS[sec], "n_sentences": d["n_sentences"], "lm": d["lm"],
             "model_score": (d.get("finbert") or {}).get("score"), "top_positive": d.get("top_positive", []),
             "top_negative": d.get("top_negative", []), "source_url": d["source_url"]}
            for sec, d in q.docs.items()]})
    return clean({
        "company": {"ticker": a.company.ticker, "name": a.company.name, "cik": a.company.cik},
        "latest": {"label": a.latest.fq.label, "period_end": a.latest.period_end, "form": a.latest.filing.form,
                   "filed": a.latest.filing.filing_date},
        "quarters": len(a.quarters),
        "method": {"model_id": a.model_id, "model_name": a.model_name, "used_model": a.used_finbert,
                   "dictionary_source": a.dictionary_source},
        "generated_at": a.generated_at,
        "kpis": [k | {"help": explain.KPI_HELP.get(k["name"], "")} for k in kpis(a)],
        "sparks": charts.sparkline_series(a),
        "verdict": {"label": v_label, "detail": v_detail},
        "insights": [{"area": i.area, "text": i.text, "signal": i.signal} for i in insights],
        "charts": figs,
        "table": data_table(a),
        "scorecard": [{"metric": label, "value": metric_value(k, h["metrics"].get(k)),
                       "score": h["metric_scores"].get(k)} for k, label in METRIC_LABELS.items()],
        "fscore": a.latest.fscore,
        "evidence": evidence,
        "sources": a.sources(),
        "warnings": a.warnings,
    })


@app.get("/api/analyses/{job_id}/changes", dependencies=auth)
def analysis_changes(job_id: str, quarter: str = "", vs: str = Query("yoy", pattern="^(prev|yoy)$"),
                     section: str = Query("mdna", pattern="^(mdna|risk)$")) -> dict:
    """New, removed and reworded sentences in a quarter's MD&A or risk factors vs an earlier filing."""
    a = _done(job_id)
    label = quarter or a.latest.fq.label
    try:
        out = changes.compare(a, label, vs, section, sec_user_agent())
    except KeyError:
        raise HTTPException(404, f"{label} is not part of this analysis")
    except EdgarError as exc:
        raise HTTPException(502, str(exc))
    return clean(out | {"options": changes.options(a)})


@app.get("/api/analyses/{job_id}/report.html", dependencies=auth)
def report_html(job_id: str) -> Response:
    a = _done(job_id)
    name = f"{a.company.ticker}_{a.latest.fq.slug}_report.html"
    return Response(build_html(a, offline=True), media_type="text/html",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/analyses/{job_id}/report.pdf", dependencies=auth)
def report_pdf(job_id: str) -> Response:
    a = _done(job_id)
    name = f"{a.company.ticker}_{a.latest.fq.slug}_report.pdf"
    return Response(build_pdf(a), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/analyses/{job_id}/data.csv", dependencies=auth)
def report_csv(job_id: str) -> Response:
    a = _done(job_id)
    buf = io.StringIO()
    pd.DataFrame(data_table(a)).to_csv(buf, index=False)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{a.company.ticker}_quarters.csv"'})


@app.post("/api/analyses/{job_id}/export", dependencies=auth)
def export(job_id: str, kind: str = Query("pdf", pattern="^(pdf|html|csv)$")) -> dict:
    """Save a report into ~/Downloads (desktop app) and return its path."""
    from pathlib import Path

    a = _done(job_id)
    base = f"{a.company.ticker}_{a.latest.fq.slug}"
    folder = Path.home() / "Downloads"
    folder.mkdir(parents=True, exist_ok=True)
    if kind == "pdf":
        path, data = folder / f"{base}_report.pdf", build_pdf(a)
    elif kind == "html":
        path, data = folder / f"{base}_report.html", build_html(a, offline=True).encode("utf-8")
    else:
        buf = io.StringIO()
        pd.DataFrame(data_table(a)).to_csv(buf, index=False)
        path, data = folder / f"{a.company.ticker}_quarters.csv", buf.getvalue().encode("utf-8")
    n = 1
    while path.exists():  # never overwrite an earlier export
        path = path.with_name(f"{path.stem.split(' (')[0]} ({n}){path.suffix}")
        n += 1
    path.write_bytes(data)
    return {"path": str(path)}


# --------------------------------------------------------------------------- recent analyses
def _history_path():
    return config.DATA_DIR / "history.json"


def load_history() -> list[dict]:
    try:
        return json.loads(_history_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def snapshot(a: Analysis) -> dict:
    """Headline numbers for one analysis, used by Recent analyses and the Portfolio table."""
    def num(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(v) or math.isinf(v) else v

    lbl, ya = a.latest.fq.label, a.latest.fq.year_ago().label
    st, ht, fin = a.sentiment_table(), a.health_table(), a.financials
    col = lambda df, row, c: num(df.loc[row, c]) if (not df.empty and row in df.index and c in df.columns) else None
    tone, tone_ya = col(st, lbl, "tone_index"), col(st, ya, "tone_index")
    health, health_ya = col(ht, lbl, "overall"), col(ht, ya, "overall")
    return {
        "ticker": a.company.ticker, "name": a.company.name, "model_name": a.model_name, "latest": lbl,
        "period_end": a.latest.period_end, "form": a.latest.filing.form, "filed": a.latest.filing.filing_date,
        "verdict": verdict(build_insights(a))[0], "health": health, "band": (a.latest.health or {}).get("band"),
        "health_change": health - health_ya if health is not None and health_ya is not None else None,
        "tone": tone, "tone_change": tone - tone_ya if tone is not None and tone_ya is not None else None,
        "revenue": col(fin, lbl, "revenue"), "revenue_yoy": col(fin, lbl, "revenue_yoy"),
        "eps_yoy": col(fin, lbl, "eps_diluted_yoy"), "gross_margin": col(fin, lbl, "gross_margin"),
        "fscore": (a.latest.fscore or {}).get("score"),
    }


def _record_history(job: "Job") -> None:
    a = job.analysis
    if not a:
        return
    try:
        entry = clean(snapshot(a) | {"quarters": job.req.quarters, "model_id": job.req.model_id,
                                     "analysed_at": time.time()})
        hist = [h for h in load_history() if not (h["ticker"] == entry["ticker"] and h.get("model_id") == entry["model_id"])]
        hist.insert(0, entry)
        _history_path().write_text(json.dumps(hist[:60], indent=1), encoding="utf-8")
    except Exception:
        pass  # history is a convenience; never fail an analysis over it


@app.get("/api/history", dependencies=auth)
def history() -> list[dict]:
    return load_history()


@app.delete("/api/history", dependencies=auth)
def clear_history() -> dict:
    _history_path().unlink(missing_ok=True)
    return {"ok": True}


# --------------------------------------------------------------------------- storage
MOVABLE = ("cache", "models", "summaries", "settings.json", "history.json", "watchlist.json", "alerts.json")


def _size(path) -> int:
    from pathlib import Path

    p = Path(path)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


@app.get("/api/storage", dependencies=auth)
def storage() -> dict:
    d = config.DATA_DIR
    return {"data_dir": str(d), "sizes": {
        "filings": _size(d / "cache"), "models": _size(d / "models"),
        "summaries": _size(d / "summaries"), "logs": _size(d / "logs"),
    }}


@app.post("/api/storage/clear-cache", dependencies=auth)
def clear_cache() -> dict:
    """Delete downloaded filings (they are fetched again when needed). Models are kept."""
    shutil.rmtree(config.DATA_DIR / "cache", ignore_errors=True)
    global _companies
    _companies = []
    return storage()


class MoveIn(BaseModel):
    target: str
    remove_old: bool = True


@app.post("/api/storage/move", dependencies=auth)
def move_storage(body: MoveIn) -> dict:
    """Copy filings, models, summaries and settings into <chosen folder>/EarningsPulse.

    The desktop app then records the new location and restarts so the engine uses it.
    Only EarningsPulse's own files are ever copied or removed.
    """
    from pathlib import Path

    chosen = Path(body.target).expanduser()
    if not chosen.is_dir():
        raise HTTPException(400, "That folder does not exist.")
    dest = chosen if chosen.name == "EarningsPulse" else chosen / "EarningsPulse"
    src = config.DATA_DIR
    if dest.resolve() == src.resolve():
        return {"data_dir": str(dest), "moved": False}
    if src.resolve() in dest.resolve().parents:
        raise HTTPException(400, "Choose a folder outside the current data folder.")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        probe = dest / ".write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        raise HTTPException(400, "EarningsPulse cannot write to that folder. Choose another one.")
    needed = sum(_size(src / n) for n in MOVABLE)
    if shutil.disk_usage(dest).free < needed * 1.1:
        raise HTTPException(400, f"Not enough free space there ({needed / 1e9:.1f} GB needed).")
    for name in MOVABLE:
        s, t = src / name, dest / name
        if s.is_dir():
            shutil.copytree(s, t, dirs_exist_ok=True)
        elif s.is_file():
            shutil.copy2(s, t)
    if body.remove_old:
        for name in MOVABLE:
            p = src / name
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                p.unlink(missing_ok=True)
    return {"data_dir": str(dest), "moved": True}


# --------------------------------------------------------------------------- models
@app.get("/api/models", dependencies=auth)
def list_models() -> dict:
    active = models.active_model()
    out = []
    for m in models.catalog():
        out.append(m | {"installed": models.is_installed(m["id"]), "active": m["id"] == active,
                        "disk_bytes": models.disk_usage(m["id"]), "download": models.download_status(m["id"])})
    return {"models": out, "active": active, "active_name": models.display_name(active)}


@app.post("/api/models/{model_id}/download", dependencies=auth)
def download_model(model_id: str) -> dict:
    models.model_info(model_id)  # 404-like error for unknown ids
    return models.start_download(model_id)


@app.delete("/api/models/{model_id}/download", dependencies=auth)
def cancel_model_download(model_id: str) -> dict:
    models.cancel_download(model_id)
    return {"ok": True}


@app.post("/api/models/{model_id}/activate", dependencies=auth)
def activate_model(model_id: str) -> dict:
    try:
        models.set_active(None if model_id == "dictionary" else model_id)
    except models.ModelError as exc:
        raise HTTPException(400, str(exc))
    return list_models()


@app.delete("/api/models/{model_id}", dependencies=auth)
def delete_model(model_id: str) -> dict:
    models.remove(model_id)
    return list_models()


@app.exception_handler(models.ModelError)
def model_error(_, exc: models.ModelError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


# --------------------------------------------------------------------------- guide
@app.get("/api/guide", dependencies=auth)
def guide() -> dict:
    return {"charts": explain.CHART_GUIDES, "glossary": explain.GLOSSARY, "kpi_help": explain.KPI_HELP}


# --------------------------------------------------------------------------- watchlist & alerts
def _watch_client() -> EdgarClient | None:
    ua = sec_user_agent()
    return EdgarClient(ua) if config.valid_user_agent(ua) else None


def _auto_analyse(item: dict) -> str | None:
    """A watched company filed a new 10-Q/10-K: analyse it now so it is ready when the user looks."""
    prev = next((h for h in load_history() if h["ticker"] == item["ticker"]), None)
    req = AnalysisIn(ticker=item["ticker"], quarters=(prev or {}).get("quarters", 8), refresh=True)
    return _start_job(req).id


checker = watchlist.Checker(_watch_client, _auto_analyse)


class WatchIn(BaseModel):
    ticker: str


@app.get("/api/watchlist", dependencies=auth)
def get_watchlist() -> dict:
    hist: dict[str, dict] = {}
    for h in load_history():  # newest first: keep each company's latest analysis
        hist.setdefault(h["ticker"], h)
    items = []
    wl = watchlist.load()
    for i in wl:
        h = hist.get(i["ticker"]) or {}
        snap = {k: h.get(k) for k in ("verdict", "health", "band", "health_change", "tone", "tone_change", "revenue",
                                      "revenue_yoy", "eps_yoy", "gross_margin", "fscore", "latest", "period_end",
                                      "analysed_at", "quarters", "model_name")}
        items.append({k: v for k, v in i.items() if k != "seen"} | snap
                     | {"batch": batch.state.get(i["ticker"])})
    # companies are checked when added, too
    last = max([checker.last_run or 0] + [i.get("last_checked") or 0 for i in wl]) or None
    return clean({"items": items, "checking": checker.running, "last_run": last, "error": checker.last_error,
                  "batch": batch.summary(),
                  "next_run": (last + watchlist.CHECK_EVERY_SECONDS) if last else None,
                  "unread": sum(1 for a in watchlist.alerts() if not a["read"])})


@app.post("/api/watchlist", dependencies=auth)
def add_watch(body: WatchIn) -> dict:
    client = _watch_client()
    if client is None:
        raise HTTPException(400, "Add your name and e-mail in Settings first (the SEC requires it).")
    try:
        return clean({k: v for k, v in watchlist.add(client, body.ticker).items() if k != "seen"})
    except EdgarError as exc:
        raise HTTPException(404, str(exc))


class BulkIn(BaseModel):
    tickers: list[str]


@app.post("/api/watchlist/bulk", dependencies=auth)
def add_watch_bulk(body: BulkIn) -> dict:
    """Add many tickers at once (pasted from a spreadsheet or a list)."""
    client = _watch_client()
    if client is None:
        raise HTTPException(400, "Add your name and e-mail in Settings first (the SEC requires it).")
    added, failed = [], []
    for raw in dict.fromkeys(t.strip().upper().lstrip("$") for t in body.tickers if t.strip()):
        try:
            added.append(watchlist.add(client, raw)["ticker"])
        except Exception as exc:
            failed.append({"ticker": raw, "error": str(exc)})
    return {"added": added, "failed": failed}


class Batch:
    """Analyse several companies one after another (kind to SEC's rate limit and to the CPU)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.queue: list[str] = []
        self.state: dict[str, dict] = {}  # ticker -> {status: queued|running|done|error, job_id, error}
        self.thread: threading.Thread | None = None

    def add(self, tickers: list[str]) -> None:
        with self.lock:
            if not self.thread or not self.thread.is_alive():  # a new run: forget the last run's results
                self.state = {t: v for t, v in self.state.items() if v["status"] in ("queued", "running")}
            for t in tickers:
                if t not in self.queue and (self.state.get(t) or {}).get("status") not in ("queued", "running"):
                    self.queue.append(t)
                    self.state[t] = {"status": "queued"}
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, daemon=True, name="portfolio-batch")
                self.thread.start()

    def cancel(self) -> None:
        with self.lock:
            for t in self.queue:
                self.state.pop(t, None)
            self.queue.clear()

    def summary(self) -> dict:
        with self.lock:
            vals = list(self.state.values())
        return {"queued": sum(v["status"] == "queued" for v in vals), "running": sum(v["status"] == "running" for v in vals),
                "done": sum(v["status"] == "done" for v in vals), "errors": sum(v["status"] == "error" for v in vals)}

    def _run(self) -> None:
        while True:
            with self.lock:
                if not self.queue:
                    return
                t = self.queue.pop(0)
                self.state[t] = {"status": "running"}
            prev = next((h for h in load_history() if h["ticker"] == t), None)
            job = Job(AnalysisIn(ticker=t, quarters=(prev or {}).get("quarters", 8)))
            with _jobs_lock:
                _jobs[job.id] = job
            _run_job(job)
            with self.lock:
                self.state[t] = {"status": job.status, "job_id": job.id, "error": job.error}


batch = Batch()


class BatchIn(BaseModel):
    tickers: list[str] | None = None  # None: every followed company
    stale_only: bool = False          # only companies never analysed or with a newer filing


@app.post("/api/portfolio/analyse", dependencies=auth)
def portfolio_analyse(body: BatchIn) -> dict:
    if not config.valid_user_agent(sec_user_agent()):
        raise HTTPException(400, "Add your name and e-mail in Settings first (the SEC requires it).")
    hist: dict[str, dict] = {}
    for h in load_history():
        hist.setdefault(h["ticker"], h)
    tickers = body.tickers or [i["ticker"] for i in watchlist.load()]
    if body.stale_only:
        def stale(t: str) -> bool:
            h, item = hist.get(t), next((i for i in watchlist.load() if i["ticker"] == t), None)
            if not h:
                return True
            lf = (item or {}).get("last_filing") or {}
            return lf.get("kind") == "report" and str(lf.get("filed", "")) > str(h.get("filed", ""))
        tickers = [t for t in tickers if stale(t)]
    batch.add([t.upper() for t in tickers])
    return {"queued": tickers} | batch.summary()


@app.delete("/api/portfolio/analyse", dependencies=auth)
def portfolio_cancel() -> dict:
    batch.cancel()
    return batch.summary()


@app.delete("/api/watchlist/{ticker}", dependencies=auth)
def remove_watch(ticker: str) -> dict:
    watchlist.remove(ticker)
    return {"ok": True}


@app.post("/api/watchlist/check", dependencies=auth)
def check_watchlist() -> dict:
    if checker.running:
        return {"new": [], "busy": True}
    return clean({"new": checker.run_now(), "busy": False})


@app.get("/api/alerts", dependencies=auth)
def get_alerts() -> list[dict]:
    out = []
    for a in watchlist.alerts():
        job = _jobs.get(a.get("job_id") or "")
        out.append(a | {"job_status": job.status if job else None})
    return clean(out)


class ReadIn(BaseModel):
    id: str | None = None  # None marks every alert read


@app.post("/api/alerts/read", dependencies=auth)
def read_alerts(body: ReadIn) -> dict:
    watchlist.mark_read(body.id)
    return {"ok": True}


@app.delete("/api/alerts", dependencies=auth)
def clear_alerts() -> dict:
    watchlist.clear_alerts()
    return {"ok": True}


# --------------------------------------------------------------------------- compare companies
class CompareIn(BaseModel):
    tickers: list[str]


class CompareJob:
    def __init__(self, tickers: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.tickers = tickers
        self.status, self.progress, self.message, self.error = "running", 0.0, "Starting", ""
        self.job_ids: list[str] = []


_compares: "OrderedDict[str, CompareJob]" = OrderedDict()


def _latest_done_job(ticker: str) -> Job | None:
    done = [j for j in _jobs.values() if j.status == "done" and j.analysis and j.analysis.company.ticker == ticker]
    return max(done, key=lambda j: j.started) if done else None


def _run_compare(cj: CompareJob) -> None:
    try:
        for n, t in enumerate(cj.tickers):
            job = _latest_done_job(t)
            if job is None:
                prev = next((h for h in load_history() if h["ticker"] == t), None)
                job = Job(AnalysisIn(ticker=t, quarters=(prev or {}).get("quarters", 8),
                                     model_id=(prev or {}).get("model_id")))
                with _jobs_lock:
                    _jobs[job.id] = job
                cj.message = f"Analysing {t}"
                base = n / len(cj.tickers)
                # mirror the analysis progress into the comparison's progress
                stop = threading.Event()

                def mirror(j=job, b=base):
                    while not stop.wait(0.3):
                        cj.progress = b + j.progress / len(cj.tickers)
                threading.Thread(target=mirror, daemon=True).start()
                _run_job(job)
                stop.set()
                if job.status != "done":
                    raise EdgarError(f"{t}: {job.error}")
            cj.job_ids.append(job.id)
            cj.progress = (n + 1) / len(cj.tickers)
        cj.status, cj.message = "done", "Done"
    except Exception as exc:
        cj.status, cj.error = "error", str(exc)


@app.post("/api/compare", dependencies=auth)
def start_compare(body: CompareIn) -> dict:
    tickers = list(dict.fromkeys(t.strip().upper() for t in body.tickers if t.strip()))
    if not 2 <= len(tickers) <= 3:
        raise HTTPException(400, "Pick two or three companies to compare.")
    if not config.valid_user_agent(sec_user_agent()):
        raise HTTPException(400, "Add your name and e-mail in Settings first (the SEC requires it).")
    cj = CompareJob(tickers)
    _compares[cj.id] = cj
    while len(_compares) > 8:
        _compares.popitem(last=False)
    threading.Thread(target=_run_compare, args=(cj,), daemon=True, name=f"compare-{cj.id}").start()
    return {"compare_id": cj.id}


def _compare_job(cid: str) -> CompareJob:
    cj = _compares.get(cid)
    if not cj:
        raise HTTPException(404, "Comparison not found (the app may have restarted)")
    return cj


@app.get("/api/compare/{cid}", dependencies=auth)
def compare_status(cid: str) -> dict:
    cj = _compare_job(cid)
    return {"compare_id": cj.id, "tickers": cj.tickers, "status": cj.status, "progress": cj.progress,
            "message": cj.message, "error": cj.error}


@app.get("/api/compare/{cid}/result", dependencies=auth)
def compare_result(cid: str, theme: str = "light") -> dict:
    cj = _compare_job(cid)
    if cj.status != "done":
        raise HTTPException(409, "Comparison is not finished")
    analyses = [_done(j) for j in cj.job_ids]
    out = compare.build(analyses, "dark" if theme == "dark" else "light", [snapshot(a) for a in analyses])
    out["job_ids"] = dict(zip(cj.tickers, cj.job_ids))
    return clean(out)


# --------------------------------------------------------------------------- entry point
def _exit_with_parent() -> None:
    """Stop the engine if the desktop app that started it goes away (crash, force quit)."""
    parent = os.getppid()

    def watch() -> None:
        while True:
            time.sleep(1.5)
            if os.getppid() != parent:  # re-parented: the app is gone
                os._exit(0)

    threading.Thread(target=watch, daemon=True, name="parent-watch").start()


def main(argv: list[str] | None = None) -> None:
    global TOKEN
    import uvicorn

    ap = argparse.ArgumentParser(description="EarningsPulse local engine")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=os.environ.get("EARNINGSPULSE_TOKEN", ""))
    args = ap.parse_args(argv)
    TOKEN = args.token
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if os.environ.get("EARNINGSPULSE_WATCH_PARENT"):
        _exit_with_parent()
    checker.start()
    print(f"EarningsPulse engine {__version__} on http://127.0.0.1:{args.port} (data: {config.DATA_DIR})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
