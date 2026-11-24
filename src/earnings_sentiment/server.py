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

from . import __version__, charts, config, explain, logos, models
from .analysis import SECTIONS, Analysis, analyze
from .edgar import EdgarClient, EdgarError
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
    theme: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/api/settings", dependencies=auth)
def get_settings() -> dict:
    s = models.load_settings()
    ua = sec_user_agent()
    return {"sec_user_agent": ua, "sec_user_agent_valid": config.valid_user_agent(ua),
            "theme": s.get("theme", "system"), "active_model": models.active_model(),
            "data_dir": str(config.DATA_DIR)}


@app.put("/api/settings", dependencies=auth)
def put_settings(body: SettingsIn) -> dict:
    changes = {}
    if body.sec_user_agent is not None:
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
        job.analysis = analyze(job.req.ticker, max(4, min(12, job.req.quarters)),
                               use_finbert=(mid != "dictionary"), model_id=None if mid in (None, "dictionary") else mid,
                               user_agent=sec_user_agent(), progress=progress)
        job.status, job.progress, job.message = "done", 1.0, "Done"
    except EdgarError as exc:
        job.status, job.error = "error", str(exc)
    except Exception as exc:  # report, don't crash the engine
        job.status, job.error = "error", f"Unexpected problem while analysing: {exc}"


@app.post("/api/analyses", dependencies=auth)
def start_analysis(body: AnalysisIn) -> dict:
    if not config.valid_user_agent(sec_user_agent()):
        raise HTTPException(400, "Add your name and e-mail in Settings first (the SEC requires it).")
    job = Job(body)
    with _jobs_lock:
        _jobs[job.id] = job
        while len(_jobs) > 12:
            _jobs.popitem(last=False)
    threading.Thread(target=_run_job, args=(job,), daemon=True, name=f"analysis-{job.id}").start()
    return {"job_id": job.id}


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
    print(f"EarningsPulse engine {__version__} on http://127.0.0.1:{args.port} (data: {config.DATA_DIR})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
