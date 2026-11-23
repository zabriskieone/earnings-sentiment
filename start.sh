#!/usr/bin/env bash
# EarningsPulse launcher for macOS and Linux.
#
#   ./start.sh            set up on first run (a minute or two), then open the dashboard
#
# Every later run starts in a few seconds. Optional settings (for automation):
#   EARNINGSPULSE_FINBERT=yes|no   skip the FinBERT question
#   EARNINGSPULSE_PORT=8501        preferred port (the next free one is used if busy)
#   EARNINGSPULSE_NO_BROWSER=1     don't open a browser window
#   SEC_USER_AGENT="Name email"    skip the name/e-mail question
set -euo pipefail

cd "$(dirname "$0")"
APP_DIR="$(pwd)"
VENV="$APP_DIR/.venv"

bold=$'\033[1m'; violet=$'\033[38;5;135m'; green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'; off=$'\033[0m'
say()  { printf '%s\n' "${violet}▸${off} $*"; }
ok()   { printf '%s\n' "${green}✔${off} $*"; }
warn() { printf '%s\n' "${yellow}!${off} $*"; }
die()  { printf '%s\n' "${red}✖ $*${off}" >&2; exit 1; }

# Questions must come from the keyboard even when this script is piped in (curl ... | bash)
ask() { # ask "question" default -> echoes answer
  local reply=""
  if { : > /dev/tty; } 2>/dev/null; then   # a keyboard is attached
    printf '%s' "$1" > /dev/tty
    IFS= read -r reply < /dev/tty || reply=""
  fi
  printf '%s' "${reply:-$2}"
}

printf '\n%s\n%s\n\n' "${bold}${violet}📈 EarningsPulse${off}" "Sentiment & health from every quarterly result"

# ---------------------------------------------------------------- 1. Python 3.10+
find_python() {
  for cmd in python3.13 python3.12 python3.11 python3.10 python3.14 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1 &&
       "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$cmd"; return 0
    fi
  done
  return 1
}

USE_UV=0
if [ ! -x "$VENV/bin/python" ]; then
  if PY="$(find_python)"; then
    ok "Found $("$PY" --version 2>&1)"
  else
    warn "Python 3.10 or newer was not found."
    answer="$(ask "  Install Python automatically with uv (a small, trusted installer from astral.sh)? [Y/n] " "y")"
    case "$answer" in
      [nN]*) die "Install Python 3.12 from https://www.python.org/downloads/ and run this script again." ;;
    esac
    if ! command -v uv >/dev/null 2>&1; then
      say "Installing uv ..."
      curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
      export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi
    command -v uv >/dev/null 2>&1 || die "uv could not be installed. Install Python 3.12 from python.org instead."
    USE_UV=1
  fi

  say "Creating a private Python environment in .venv (first run only) ..."
  if [ "$USE_UV" = 1 ]; then
    uv venv --python 3.12 --seed "$VENV" >/dev/null
  else
    "$PY" -m venv "$VENV" || die "Could not create the environment. On Debian/Ubuntu run: sudo apt install python3-venv"
  fi
fi
PYV="$VENV/bin/python"

# ---------------------------------------------------------------- 2. packages (only when requirements change)
FINBERT_CHOICE_FILE="$VENV/.finbert"
if [ ! -f "$FINBERT_CHOICE_FILE" ]; then
  choice="${EARNINGSPULSE_FINBERT:-}"
  if [ -z "$choice" ]; then
    echo
    say "FinBERT is an AI model that reads every sentence for tone (more accurate)."
    echo "  It adds about 2 GB of downloads now, plus a 440 MB model the first time you use it."
    echo "  Without it the app uses the finance dictionary only (faster, still useful)."
    choice="$(ask "  Include FinBERT? [Y/n] " "y")"
  fi
  case "$choice" in [nN]*) echo no > "$FINBERT_CHOICE_FILE" ;; *) echo yes > "$FINBERT_CHOICE_FILE" ;; esac
fi
FINBERT="$(cat "$FINBERT_CHOICE_FILE")"

req_hash() {
  "$PYV" - "$FINBERT" <<'PY'
import hashlib, sys
h = hashlib.sha256(sys.argv[1].encode())
for f in ("requirements.txt", "requirements-finbert.txt"):
    with open(f, "rb") as fh:
        h.update(fh.read())
print(h.hexdigest())
PY
}
STAMP="$VENV/.installed"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$(req_hash)" ]; then
  say "Installing packages (first run or after an update; this can take a few minutes) ..."
  "$PYV" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
  "$PYV" -m pip install --quiet --disable-pip-version-check -r requirements.txt || die "Package install failed (see messages above)."
  if [ "$FINBERT" = yes ]; then
    say "Installing FinBERT support (PyTorch + transformers) ..."
    if [ "$(uname -s)" = Linux ]; then  # CPU-only build is ~1.5 GB smaller on Linux
      "$PYV" -m pip install --quiet --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu \
        || "$PYV" -m pip install --quiet --disable-pip-version-check torch
    fi
    "$PYV" -m pip install --quiet --disable-pip-version-check -r requirements-finbert.txt \
      || warn "FinBERT could not be installed; the app will use dictionary scoring."
  fi
  req_hash > "$STAMP"
  ok "Packages ready"
fi

# ---------------------------------------------------------------- 3. SEC identity (.env, never committed)
if [ -z "${SEC_USER_AGENT:-}" ] && ! grep -qs '^SEC_USER_AGENT=..*@' .env; then
  echo
  say "The SEC asks every app that downloads filings to identify itself with a name and e-mail."
  echo "  It is only sent to sec.gov and saved in .env on this computer (you can also type it in the app)."
  ua="$(ask "  Your name and e-mail (e.g. Jane Doe jane@example.com), or Enter to skip: " "")"
  if [ -n "$ua" ]; then
    printf 'SEC_USER_AGENT="%s"\n' "$ua" >> .env
    ok "Saved to .env"
  fi
fi

# ---------------------------------------------------------------- 4. launch
port="${EARNINGSPULSE_PORT:-8501}"
port_busy() { "$PYV" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', $1))==0 else 1)"; }
while port_busy "$port"; do port=$((port + 1)); done
URL="http://localhost:$port"

headless=false
[ -n "${EARNINGSPULSE_NO_BROWSER:-}" ] && headless=true
printf '\n%s\n' "${bold}${green}✔ EarningsPulse is starting: ${URL}${off}"
echo "  Your browser will open automatically. Press Ctrl+C here to stop the app."
echo
exec "$PYV" -m streamlit run app.py --server.port "$port" --server.headless "$headless" \
  --browser.gatherUsageStats false --server.fileWatcherType none
