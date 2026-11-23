#!/usr/bin/env bash
# EarningsPulse one-line installer for macOS and Linux:
#
#   curl -fsSL https://raw.githubusercontent.com/zabriskieone/earnings-sentiment/main/install.sh | bash
#
# Downloads (or updates) the app in ~/EarningsPulse, then runs start.sh, which
# sets everything up and opens the dashboard in your browser.
# Change the folder with:  ... | EARNINGSPULSE_DIR=/path/you/like bash
set -euo pipefail

REPO="${EARNINGSPULSE_REPO:-https://github.com/zabriskieone/earnings-sentiment}"
BRANCH="${EARNINGSPULSE_BRANCH:-main}"
DIR="${EARNINGSPULSE_DIR:-$HOME/EarningsPulse}"

violet=$'\033[38;5;135m'; green=$'\033[32m'; red=$'\033[31m'; off=$'\033[0m'
say() { printf '%s\n' "${violet}▸${off} $*"; }

if [ -d "$DIR/.git" ]; then
  say "Updating EarningsPulse in $DIR ..."
  git -C "$DIR" pull --ff-only --quiet || say "Could not update (local changes?); starting the version you have."
elif [ -f "$DIR/start.sh" ]; then
  say "Using the existing copy in $DIR"
elif command -v git >/dev/null 2>&1; then
  say "Downloading EarningsPulse to $DIR ..."
  git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$DIR"
else
  say "Downloading EarningsPulse to $DIR (git not found, using a plain download) ..."
  mkdir -p "$DIR"
  curl -fsSL "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$DIR" --strip-components 1
fi

[ -f "$DIR/start.sh" ] || { printf '%s\n' "${red}✖ Download failed: $DIR/start.sh not found${off}" >&2; exit 1; }
chmod +x "$DIR/start.sh" "$DIR/Start EarningsPulse.command" 2>/dev/null || true
printf '%s\n' "${green}✔${off} Installed in $DIR. Next time, run: $DIR/start.sh"
exec bash "$DIR/start.sh"
