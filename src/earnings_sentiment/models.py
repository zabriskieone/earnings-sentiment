"""Sentiment model registry: catalogue, downloads, storage and ONNX inference.

Models are full-precision ONNX exports of Hugging Face models, built and verified
by tools/export_models.py and published as assets of a GitHub release. They run
with onnxruntime + tokenizers (no PyTorch), entirely on this computer.

Layout on disk (DATA_DIR/models):
    <id>/model.onnx, <id>/tokenizer.json, <id>/config.json, <id>/installed.json
"""

from __future__ import annotations

import functools
import hashlib
import json
import shutil
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import requests

from . import config

RELEASE_TAG = "models-v1"
RELEASE_BASE = f"https://github.com/zabriskieone/earnings-sentiment/releases/download/{RELEASE_TAG}"
DEFAULT_MODEL = "finbert"

# Shown before the online manifest has been fetched (sizes are approximate there)
BUILTIN_CATALOG = [
    {"id": "finbert", "name": "FinBERT", "repo": "ProsusAI/finbert", "recommended": True,
     "tagline": "Balanced, general financial text", "best_for": "A reliable default for MD&A and press releases",
     "description": "BERT further trained on financial text and fine-tuned on Financial PhraseBank news "
                    "sentences. The well-established baseline (Araci, 2019).",
     "paper": "https://arxiv.org/abs/1908.10063", "license": "See model card (ProsusAI/finbert)",
     "size_bytes": 405_800_000, "sentences_per_sec_ref": 99},
    {"id": "finbert-tone", "name": "FinBERT-tone", "repo": "yiyanghkust/finbert-tone", "recommended": False,
     "tagline": "Closest to filings: trained on 10-K/10-Q text",
     "best_for": "Reading the formal language of 10-Q and 10-K reports",
     "description": "Pre-trained on corporate 10-K/10-Q reports, earnings call transcripts and analyst reports; "
                    "fine-tuned on 10,000 analyst-report sentences (Huang, Wang & Yang).",
     "paper": "https://huggingface.co/yiyanghkust/finbert-tone", "license": "See model card (yiyanghkust/finbert-tone)",
     "size_bytes": 408_000_000, "sentences_per_sec_ref": 99},
    {"id": "distilroberta-fin", "name": "DistilRoBERTa Fast",
     "repo": "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis", "recommended": False,
     "tagline": "Fastest; lighter on older Macs", "best_for": "Quick scans and Intel Macs",
     "description": "Distilled RoBERTa (82M parameters) fine-tuned on Financial PhraseBank news sentences. Apache-2.0.",
     "paper": "https://huggingface.co/mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis",
     "license": "Apache-2.0", "size_bytes": 305_600_000, "sentences_per_sec_ref": 200},
]


class ModelError(RuntimeError):
    pass


# --------------------------------------------------------------------------- settings
def _settings_path() -> Path:
    return config.DATA_DIR / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(**changes) -> dict:
    s = load_settings()
    s.update(changes)
    _settings_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = _settings_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
    tmp.replace(_settings_path())
    return s


# --------------------------------------------------------------------------- catalogue
def models_dir() -> Path:
    d = config.DATA_DIR / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest_cache() -> Path:
    return models_dir() / "models.json"


def fetch_manifest(force: bool = False) -> list[dict]:
    """Release manifest (exact sizes + checksums), cached for a day."""
    path = _manifest_cache()
    if path.exists() and not force and time.time() - path.stat().st_mtime < 86400:
        return json.loads(path.read_text())["models"]
    resp = requests.get(f"{RELEASE_BASE}/models.json", timeout=20)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data))
    return data["models"]


def catalog() -> list[dict]:
    """Catalogue merged with the release manifest when available."""
    entries = {m["id"]: dict(m) for m in BUILTIN_CATALOG}
    try:
        for m in fetch_manifest():
            entries.setdefault(m["id"], {}).update(m)
    except (requests.RequestException, ValueError, KeyError):
        pass  # offline: built-in info is enough to list models
    return list(entries.values())


def model_info(model_id: str) -> dict:
    for m in catalog():
        if m["id"] == model_id:
            return m
    raise ModelError(f"Unknown model '{model_id}'")


def is_installed(model_id: str) -> bool:
    d = models_dir() / model_id
    return all((d / f).exists() for f in ("model.onnx", "tokenizer.json", "config.json", "installed.json"))


def installed_models() -> list[str]:
    return [m["id"] for m in BUILTIN_CATALOG if is_installed(m["id"])]


def active_model() -> str | None:
    """The model the user picked, if it is installed; else any installed model."""
    chosen = load_settings().get("active_model", DEFAULT_MODEL)
    if chosen == "none":
        return None
    if is_installed(chosen):
        return chosen
    inst = installed_models()
    return inst[0] if inst else None


def set_active(model_id: str | None) -> None:
    if model_id and not is_installed(model_id):
        raise ModelError(f"{model_id} is not downloaded yet")
    save_settings(active_model=model_id or "none")
    load_model.cache_clear()


def display_name(model_id: str | None) -> str:
    if not model_id:
        return "Loughran-McDonald dictionary"
    return next((m["name"] for m in BUILTIN_CATALOG if m["id"] == model_id), model_id)


# --------------------------------------------------------------------------- downloads
@dataclass
class DownloadState:
    model_id: str
    total: int = 0
    done: int = 0
    status: str = "queued"  # queued | downloading | verifying | installing | done | error | cancelled
    error: str = ""
    started: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event)

    def to_dict(self) -> dict:
        elapsed = max(0.001, time.time() - self.started)
        rate = self.done / elapsed
        return {"model_id": self.model_id, "total": self.total, "done": self.done, "status": self.status,
                "error": self.error, "progress": (self.done / self.total) if self.total else 0.0,
                "bytes_per_sec": rate, "eta_sec": ((self.total - self.done) / rate) if rate > 0 and self.total else None}


_downloads: dict[str, DownloadState] = {}
_dl_lock = threading.Lock()


def download_status(model_id: str) -> dict | None:
    st = _downloads.get(model_id)
    return st.to_dict() if st else None


def download(model_id: str, progress: Callable[[DownloadState], None] | None = None,
             state: DownloadState | None = None) -> None:
    """Download, verify (SHA-256) and install a model. Blocking; safe to run in a thread."""
    info = next((m for m in fetch_manifest() if m["id"] == model_id), None)
    if not info:
        raise ModelError(f"'{model_id}' is not in the published model list")
    st = state or DownloadState(model_id)
    st.total = int(info["size_bytes"])
    target = models_dir() / model_id
    part = models_dir() / f"{model_id}.zip.part"
    try:
        st.status = "downloading"
        sha = hashlib.sha256()
        with requests.get(f"{RELEASE_BASE}/{info['file']}", stream=True, timeout=30) as resp:
            resp.raise_for_status()
            with part.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if st.cancel.is_set():
                        st.status = "cancelled"
                        return
                    fh.write(chunk)
                    sha.update(chunk)
                    st.done += len(chunk)
                    if progress:
                        progress(st)
        st.status = "verifying"
        if sha.hexdigest() != info["sha256"]:
            raise ModelError("Checksum mismatch: the download was corrupted. Please try again.")
        st.status = "installing"
        staging = models_dir() / f"{model_id}.staging"
        shutil.rmtree(staging, ignore_errors=True)
        with zipfile.ZipFile(part) as z:
            for name in z.namelist():  # only the three expected files, never paths outside the folder
                if name not in ("model.onnx", "tokenizer.json", "config.json"):
                    raise ModelError(f"Unexpected file in model archive: {name}")
            z.extractall(staging)
        (staging / "installed.json").write_text(json.dumps({"sha256": info["sha256"], "installed_at": time.time()}))
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
        st.status = "done"
        if progress:
            progress(st)
    except Exception as exc:
        st.status = "error"
        st.error = str(exc)
        raise
    finally:
        part.unlink(missing_ok=True)


def start_download(model_id: str) -> dict:
    """Start a background download (used by the app)."""
    with _dl_lock:
        cur = _downloads.get(model_id)
        if cur and cur.status in ("queued", "downloading", "verifying", "installing"):
            return cur.to_dict()
        st = DownloadState(model_id)
        _downloads[model_id] = st

    def run():
        try:
            download(model_id, state=st)
        except Exception:
            pass  # recorded in st.error

    threading.Thread(target=run, daemon=True, name=f"download-{model_id}").start()
    return st.to_dict()


def cancel_download(model_id: str) -> None:
    st = _downloads.get(model_id)
    if st:
        st.cancel.set()


def remove(model_id: str) -> None:
    load_model.cache_clear()
    shutil.rmtree(models_dir() / model_id, ignore_errors=True)


def disk_usage(model_id: str) -> int:
    d = models_dir() / model_id
    return sum(f.stat().st_size for f in d.glob("*") if f.is_file()) if d.exists() else 0


# --------------------------------------------------------------------------- inference
@dataclass
class Probabilities:
    positive: float
    negative: float
    neutral: float


class OnnxSentimentModel:
    def __init__(self, model_id: str):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        d = models_dir() / model_id
        if not is_installed(model_id):
            raise ModelError(f"Model '{model_id}' is not downloaded")
        self.id = model_id
        self.cfg = json.loads((d / "config.json").read_text())
        self.labels: list[str] = self.cfg["labels"]
        self.inputs: list[str] = self.cfg["inputs"]
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(d / "model.onnx"), sess_options=opts,
                                            providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self.tok.enable_truncation(int(self.cfg.get("max_length", 512)))
        pad = self.cfg.get("pad_id")
        self.tok.enable_padding(pad_id=0 if pad is None else int(pad))

    def predict(self, texts: list[str], batch_size: int = 16) -> list[Probabilities]:
        out: list[Probabilities] = []
        idx = {lbl: i for i, lbl in enumerate(self.labels)}
        for i in range(0, len(texts), batch_size):
            encs = self.tok.encode_batch(texts[i:i + batch_size])
            arrays = {"input_ids": [e.ids for e in encs], "attention_mask": [e.attention_mask for e in encs],
                      "token_type_ids": [e.type_ids for e in encs]}
            feed = {n: np.asarray(arrays[n], dtype=np.int64) for n in self.inputs}
            logits = self.session.run(None, feed)[0]
            e = np.exp(logits - logits.max(axis=-1, keepdims=True))
            probs = e / e.sum(axis=-1, keepdims=True)
            for row in probs:
                out.append(Probabilities(float(row[idx["positive"]]), float(row[idx["negative"]]),
                                         float(row[idx["neutral"]])))
        return out


@functools.lru_cache(maxsize=2)
def load_model(model_id: str) -> OnnxSentimentModel:
    return OnnxSentimentModel(model_id)
