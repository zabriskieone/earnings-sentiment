"""Company logos for the dashboard and reports.

Logos are downloaded once per ticker from Financial Modeling Prep's public image
URL (no account or key needed; only the ticker symbol is sent), cached on disk
and embedded as data URIs so reports work offline. When no logo is available
the company gets a gradient monogram tile instead.
"""

from __future__ import annotations

import base64
import html
import time
from pathlib import Path

import requests

from . import config
from .theme import GRADIENT

LOGO_URL = "https://financialmodelingprep.com/image-stock/{ticker}.png"
MISSING_RETRY_DAYS = 7


def _cache_dir() -> Path:
    d = Path(config.CACHE_DIR) / "logos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logo_png(ticker: str, timeout: float = 6.0) -> bytes | None:
    """PNG bytes of the company logo, or None if there isn't one."""
    t = ticker.upper().replace("/", "-")
    path = _cache_dir() / f"{t}.png"
    missing = _cache_dir() / f"{t}.missing"
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    if missing.exists() and (time.time() - missing.stat().st_mtime) < MISSING_RETRY_DAYS * 86400:
        return None
    try:
        resp = requests.get(LOGO_URL.format(ticker=t), timeout=timeout,
                            headers={"User-Agent": "EarningsPulse/1.0"})
        data = resp.content
        if resp.status_code == 200 and data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 200:
            path.write_bytes(data)
            return data
        missing.touch()
    except requests.RequestException:
        pass  # offline: show the monogram, try again next time
    return None


def logo_data_uri(ticker: str) -> str | None:
    data = logo_png(ticker)
    return f"data:image/png;base64,{base64.b64encode(data).decode()}" if data else None


def monogram(ticker: str) -> str:
    letters = "".join(ch for ch in ticker.upper() if ch.isalpha())[:2] or ticker[:2].upper()
    return letters


def logo_html(ticker: str, size: int = 56, radius: int = 16) -> str:
    """Logo on a white tile, or a gradient monogram tile when no logo exists."""
    uri = logo_data_uri(ticker)
    common = (f"width:{size}px;height:{size}px;border-radius:{radius}px;flex:0 0 auto;"
              "display:grid;place-items:center;box-shadow:0 6px 18px rgba(15,13,31,0.25);")
    if uri:
        pad = max(6, size // 7)
        return (f'<div class="ep-logo-tile" style="{common}background:#fff;padding:{pad}px;">'
                f'<img src="{uri}" alt="{html.escape(ticker)} logo" '
                f'style="max-width:100%;max-height:100%;object-fit:contain;"></div>')
    g0, g1, g2 = GRADIENT
    return (f'<div class="ep-logo-tile" style="{common}background:linear-gradient(135deg,#c4b5fd,#f0abfc);'
            f'color:{g0};font-weight:800;font-size:{int(size * 0.36)}px;letter-spacing:-0.02em;">'
            f"{html.escape(monogram(ticker))}</div>")
