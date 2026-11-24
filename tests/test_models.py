"""Model registry tests (offline: downloads are served from a local zip)."""

import hashlib
import io
import json
import zipfile

import pytest

from earnings_sentiment import config, models


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class _Resp:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        for i in range(0, len(self.data), chunk_size):
            yield self.data[i:i + chunk_size]


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    models.load_model.cache_clear()
    good = _zip({"model.onnx": b"x" * 1000, "tokenizer.json": b"{}", "config.json": json.dumps({"labels": []}).encode()})
    manifest = [{"id": "finbert", "file": "finbert.zip", "size_bytes": len(good),
                 "sha256": hashlib.sha256(good).hexdigest()}]
    served = {"data": good}
    monkeypatch.setattr(models, "fetch_manifest", lambda force=False: manifest)
    monkeypatch.setattr(models.requests, "get", lambda url, **kw: _Resp(served["data"]))
    return manifest, served


def test_download_verifies_and_installs(registry):
    seen = []
    models.download("finbert", progress=lambda st: seen.append(st.status))
    assert models.is_installed("finbert")
    assert "done" in seen
    assert models.active_model() == "finbert"  # default choice once installed
    models.set_active(None)
    assert models.active_model() is None
    models.remove("finbert")
    assert not models.is_installed("finbert")


def test_corrupted_download_is_rejected(registry):
    _, served = registry
    served["data"] = served["data"][:-10] + b"0123456789"
    with pytest.raises(models.ModelError, match="Checksum"):
        models.download("finbert")
    assert not models.is_installed("finbert")
    assert not list(models.models_dir().glob("*.part"))


def test_archive_with_unexpected_paths_is_rejected(registry):
    manifest, served = registry
    evil = _zip({"model.onnx": b"x", "../../escape.txt": b"nope", "config.json": b"{}", "tokenizer.json": b"{}"})
    served["data"] = evil
    manifest[0].update(size_bytes=len(evil), sha256=hashlib.sha256(evil).hexdigest())
    with pytest.raises(models.ModelError, match="Unexpected file"):
        models.download("finbert")
    assert not models.is_installed("finbert")


def test_cannot_activate_missing_model(registry):
    with pytest.raises(models.ModelError):
        models.set_active("finbert-tone")


def test_display_names():
    assert models.display_name("finbert-tone") == "FinBERT-tone"
    assert models.display_name(None) == "Loughran-McDonald dictionary"
