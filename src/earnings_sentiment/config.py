"""Runtime configuration.

Everything user-specific comes from environment variables (or a local `.env`
file) so nothing personal is ever committed to the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader (KEY=VALUE lines) so we avoid an extra dependency."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# SEC asks every automated client to identify itself with a name and contact
# e-mail: https://www.sec.gov/os/accessing-edgar-data
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "").strip()

# SEC fair-access limit is 10 requests/second; we stay well below it.
SEC_MIN_INTERVAL_SECONDS = 0.15

# Everything the app writes (downloads cache, models, settings). The desktop app
# points this at ~/Library/Application Support/EarningsPulse.
DATA_DIR = Path(os.environ.get("EARNINGSPULSE_DATA_DIR", PROJECT_ROOT / "data"))
CACHE_DIR = Path(os.environ.get("EARNINGS_CACHE_DIR", DATA_DIR / "cache"))
SNAPSHOT_DIR = Path(os.environ.get("EARNINGS_SNAPSHOT_DIR", PROJECT_ROOT / "snapshots"))

# Company-level JSON (filing list, XBRL facts) changes when new filings land,
# so it is refreshed after this many hours. Individual filings never change.
COMPANY_DATA_TTL_HOURS = 12



# Bump when the scoring logic changes so cached sentiment is recomputed.
SENTIMENT_VERSION = "3"


def valid_user_agent(ua: str) -> bool:
    """SEC wants a name plus a contact e-mail; require at least an '@'."""
    return bool(ua) and "@" in ua and len(ua.split()) >= 2
