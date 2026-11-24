#!/usr/bin/env bash
# EarningsPulse launcher for macOS and Linux.
#
#   ./start.sh            set up on first run (a few minutes), then open the dashboard
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
LOG_DIR="$APP_DIR/data/logs"
mkdir -p "$LOG_DIR"

if [ -t 1 ]; then
  bold=$'\033[1m'; dim=$'\033[2m'; violet=$'\033[38;5;135m'; green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'; off=$'\033[0m'
else
  bold=""; dim=""; violet=""; green=""; yellow=""; red=""; off=""
fi
say()  { printf '%s\n' "${violet}▸${off} $*"; }
ok()   { printf '%s\n' "${green}✔${off} $*"; }
warn() { printf '%s\n' "${yellow}!${off} $*"; }
die()  { printf '%s\n' "${red}✖ $*${off}" >&2; exit 1; }
step() { printf '\n%s\n' "${bold}${violet}[$1/5]${off} ${bold}$2${off}"; }

# Questions come from the keyboard even when this script is piped in (curl ... | bash)
ask() { # ask "question" default -> echoes answer
  local reply=""
  if { : > /dev/tty; } 2>/dev/null; then
    printf '%s' "$1" > /dev/tty
    IFS= read -r reply < /dev/tty || reply=""
  fi
  printf '%s' "${reply:-$2}"
}

fmt_time() { local s=$1; if [ "$s" -ge 60 ]; then printf '%dm %02ds' $((s / 60)) $((s % 60)); else printf '%ds' "$s"; fi; }

# run_task "label" logfile [progress-command] -- command...
# Runs a command with its output going to a log file, while showing a live
# spinner, elapsed time and (optionally) a progress note such as "212 / 440 MB".
run_task() {
  local label="$1" log="$2" progress_cmd="$3"; shift 4
  local start=$SECONDS i=0 note="" rc=0
  local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  "$@" > "$log" 2>&1 < /dev/null &
  local pid=$!
  if [ -t 1 ]; then
    while kill -0 "$pid" 2>/dev/null; do
      [ -n "$progress_cmd" ] && note="$(eval "$progress_cmd" 2>/dev/null || true)"
      printf '\r\033[K  %s %s %s' "${violet}${frames[i++ % 10]}${off}" "$label" "${dim}$(fmt_time $((SECONDS - start)))${note:+ · $note}${off}"
      sleep 0.25
    done
  else
    printf '  … %s\n' "$label"
  fi
  wait "$pid" || rc=$?
  if [ "$rc" -eq 0 ]; then
    printf '\r\033[K  %s %s %s\n' "${green}✔${off}" "$label" "${dim}($(fmt_time $((SECONDS - start))))${off}"
  elif [ -n "${QUIET_FAIL:-}" ]; then
    printf '\r\033[K  %s %s\n' "${yellow}↻${off}" "$label: not available, trying another source"
  else
    printf '\r\033[K  %s %s\n' "${red}✖${off}" "$label failed. Last lines of $log:"
    tail -n 15 "$log" | sed 's/^/      /'
  fi
  return "$rc"
}

printf '\n%s\n%s\n' "${bold}${violet}📈 EarningsPulse${off}" "Sentiment & health from every quarterly result"

# ---------------------------------------------------------------- 1. Python 3.10+
step 1 "Python"
find_python() {
  for cmd in python3.13 python3.12 python3.11 python3.10 python3.14 python3 python; do
    if command -v "$cmd" >/dev/null 2>&1 &&
       "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$cmd"; return 0
    fi
  done
  return 1
}

if [ -x "$VENV/bin/python" ]; then
  ok "Using the app's environment ($("$VENV/bin/python" --version 2>&1))"
else
  USE_UV=0
  if PY="$(find_python)"; then
    ok "Found $("$PY" --version 2>&1)"
  else
    warn "Python 3.10 or newer was not found."
    answer="$(ask "  Install Python automatically with uv (a small, trusted installer from astral.sh)? [Y/n] " "y")"
    case "$answer" in
      [nN]*) die "Install Python 3.12 from https://www.python.org/downloads/ and run this script again." ;;
    esac
    if ! command -v uv >/dev/null 2>&1; then
      run_task "Installing uv" "$LOG_DIR/uv.log" "" -- sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
      export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi
    command -v uv >/dev/null 2>&1 || die "uv could not be installed. Install Python 3.12 from python.org instead."
    USE_UV=1
  fi
  if [ "$USE_UV" = 1 ]; then
    run_task "Creating the app's private environment (with Python 3.12)" "$LOG_DIR/venv.log" "" -- \
      uv venv --python 3.12 --seed "$VENV" || die "Could not create the environment."
  else
    run_task "Creating the app's private environment (.venv)" "$LOG_DIR/venv.log" "" -- \
      "$PY" -m venv "$VENV" || die "Could not create the environment. On Debian/Ubuntu run: sudo apt install python3-venv"
  fi
fi
PYV="$VENV/bin/python"

# ---------------------------------------------------------------- 2. packages (only when they change)
step 2 "App packages"
FINBERT_CHOICE_FILE="$VENV/.finbert"
if [ ! -f "$FINBERT_CHOICE_FILE" ]; then
  choice="${EARNINGSPULSE_FINBERT:-}"
  if [ -z "$choice" ]; then
    echo "  FinBERT is an AI model that reads every sentence for tone (more accurate)."
    echo "  It downloads about 400 MB once. You can add or switch models later in the app."
    echo "  Without it the app uses the finance dictionary only (faster setup, still useful)."
    choice="$(ask "  Include FinBERT? [Y/n] " "y")"
  fi
  case "$choice" in [nN]*) echo no > "$FINBERT_CHOICE_FILE" ;; *) echo yes > "$FINBERT_CHOICE_FILE" ;; esac
fi
FINBERT="$(cat "$FINBERT_CHOICE_FILE")"

req_hash() {
  "$PYV" - "$FINBERT" <<'PY'
import hashlib, sys
h = hashlib.sha256(sys.argv[1].encode())
for f in ("requirements.txt",):
    with open(f, "rb") as fh:
        h.update(fh.read())
print(h.hexdigest())
PY
}
PIP=("$PYV" -m pip install --disable-pip-version-check --progress-bar off)
STAMP="$VENV/.installed"
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$(req_hash)" ]; then
  ok "Already installed"
else
  "$PYV" -m pip install --quiet --upgrade pip > /dev/null 2>&1 || true
  run_task "Installing app packages (~150 MB, usually 1-3 minutes)" "$LOG_DIR/pip-app.log" \
    "grep -c '^Collecting' '$LOG_DIR/pip-app.log' | sed 's/$/ packages fetched/'" -- \
    "${PIP[@]}" -r requirements.txt || die "Package install failed (full log: $LOG_DIR/pip-app.log)"
  req_hash > "$STAMP"
fi

# ---------------------------------------------------------------- 3. FinBERT model (once)
step 3 "FinBERT model"
MODEL_STAMP="$VENV/.model-finbert-onnx"   # ONNX model via the registry (replaces the old PyTorch download)
if [ "$FINBERT" != yes ]; then
  ok "Skipped (dictionary scoring only). Run 'rm .venv/.finbert && ./start.sh' to add it later."
elif [ -f "$MODEL_STAMP" ]; then
  ok "Already downloaded"
else
  MODEL_LOG="$LOG_DIR/finbert-model.log"
  run_task "Downloading the FinBERT model (~400 MB, one time)" "$MODEL_LOG" \
    "tr '\\r' '\\n' < '$MODEL_LOG' | grep -o '[0-9]* / [0-9]* MB' | tail -1" -- \
    "$PYV" -m earnings_sentiment models download finbert && touch "$MODEL_STAMP" \
    || warn "The model could not be downloaded now; you can download it later from the app."
fi

# ---------------------------------------------------------------- 4. SEC identity (.env, never committed)
step 4 "Your SEC identity"
if [ -n "${SEC_USER_AGENT:-}" ] || grep -qs '^SEC_USER_AGENT=..*@' .env; then
  ok "Already set (stored in .env on this computer)"
else
  echo "  The SEC asks every app that downloads filings to identify itself with a name and e-mail."
  echo "  It is only sent to sec.gov and saved in .env on this computer (you can also type it in the app)."
  ua="$(ask "  Your name and e-mail (e.g. Jane Doe jane@example.com), or Enter to skip: " "")"
  if [ -n "$ua" ]; then
    printf 'SEC_USER_AGENT="%s"\n' "$ua" >> .env
    ok "Saved to .env"
  else
    ok "Skipped: you can enter it in the app's sidebar"
  fi
fi

# ---------------------------------------------------------------- 5. launch
step 5 "Starting the dashboard"
port="${EARNINGSPULSE_PORT:-8501}"
port_busy() { "$PYV" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', $1))==0 else 1)"; }
while port_busy "$port"; do port=$((port + 1)); done
URL="http://localhost:$port"
APP_LOG="$LOG_DIR/app.log"

# Headless: Streamlit never shows its own first-run e-mail prompt; we open the browser ourselves.
"$PYV" -m streamlit run app.py --server.port "$port" --server.headless true \
  --browser.gatherUsageStats false --server.fileWatcherType none > "$APP_LOG" 2>&1 < /dev/null &
APP_PID=$!
stop_app() {
  printf '\n'; say "Stopping EarningsPulse ..."
  kill "$APP_PID" 2>/dev/null || true; wait "$APP_PID" 2>/dev/null || true
  ok "Stopped. Start it again any time with: $APP_DIR/start.sh"
  exit 0
}
trap stop_app INT TERM

wait_ready() {
  for _ in $(seq 1 240); do
    kill -0 "$APP_PID" 2>/dev/null || return 1
    "$PYV" -c "import urllib.request,sys; urllib.request.urlopen('$URL/_stcore/health', timeout=1)" 2>/dev/null && return 0
    sleep 0.5
  done
  return 1
}
run_task "Launching on $URL" "$LOG_DIR/launch.log" "" -- wait_ready || {
  printf '%s\n' "${red}✖ The dashboard did not start. Last lines of $APP_LOG:${off}"
  tail -n 20 "$APP_LOG" | sed 's/^/      /'
  kill "$APP_PID" 2>/dev/null || true
  exit 1
}

if [ -z "${EARNINGSPULSE_NO_BROWSER:-}" ]; then
  if command -v open >/dev/null 2>&1 && [ "$(uname -s)" = Darwin ]; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi

printf '\n%s\n' "${bold}${green}✔ EarningsPulse is running →  ${URL}${off}"
[ -z "${EARNINGSPULSE_NO_BROWSER:-}" ] && echo "  It should have opened in your browser; if not, open the link above."
echo "  Keep this window open while you use it. Press Ctrl+C to stop."
echo "  ${dim}App log: $APP_LOG${off}"
wait "$APP_PID" || true
