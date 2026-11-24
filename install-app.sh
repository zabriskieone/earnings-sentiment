#!/usr/bin/env bash
# Install (or update) the EarningsPulse Mac app from the latest GitHub release:
#
#   curl -fsSL https://raw.githubusercontent.com/zabriskieone/earnings-sentiment/main/install-app.sh | bash
#
# Puts EarningsPulse.app in /Applications (or ~/Applications if that isn't
# writable) and opens it. To remove it:  ... | bash -s -- --uninstall
set -euo pipefail

REPO="${EARNINGSPULSE_REPO:-zabriskieone/earnings-sentiment}"
APP="EarningsPulse.app"

if [ -t 1 ]; then
  bold=$'\033[1m'; violet=$'\033[38;5;135m'; green=$'\033[32m'; red=$'\033[31m'; off=$'\033[0m'
else
  bold=""; violet=""; green=""; red=""; off=""
fi
say() { printf '%s\n' "${violet}▸${off} $*"; }
ok()  { printf '%s\n' "${green}✔${off} $*"; }
die() { printf '%s\n' "${red}✖ $*${off}" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || die "This installer is for macOS. On Linux or Windows, see the README (install.sh / install.ps1)."

if [ -w /Applications ]; then DEST=/Applications; else DEST="$HOME/Applications"; mkdir -p "$DEST"; fi

if [ "${1:-}" = "--uninstall" ]; then
  osascript -e 'quit app "EarningsPulse"' >/dev/null 2>&1 || true
  rm -rf "/Applications/$APP" "$HOME/Applications/$APP"
  ok "Removed EarningsPulse. Your data (filings cache, models, settings) is kept in"
  echo "  ~/Library/Application Support/EarningsPulse. Delete that folder to remove it too."
  exit 0
fi

printf '\n%s\n\n' "${bold}${violet}📈 EarningsPulse${off} for Mac"

case "$(uname -m)" in
  arm64) ARCH=arm64; KIND="Apple silicon" ;;
  x86_64) ARCH=x64; KIND="Intel" ;;
  *) die "Unsupported processor: $(uname -m)" ;;
esac

say "Finding the latest release for $KIND Macs ..."
JSON="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest")" || die "Could not reach GitHub. Check your internet connection."
URL="$(printf '%s' "$JSON" | grep -o "\"browser_download_url\": *\"[^\"]*_${ARCH}\.app\.zip\"" | head -1 | sed 's/.*"\(https[^"]*\)"/\1/')"
TAG="$(printf '%s' "$JSON" | grep -o '"tag_name": *"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
[ -n "$URL" ] || die "No $KIND build found in the latest release ($TAG)."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
say "Downloading EarningsPulse $TAG ..."
curl -fL --progress-bar "$URL" -o "$TMP/app.zip" || die "Download failed."

say "Installing to $DEST ..."
osascript -e 'quit app "EarningsPulse"' >/dev/null 2>&1 || true
ditto -x -k "$TMP/app.zip" "$TMP/unpacked"
[ -d "$TMP/unpacked/$APP" ] || die "The download did not contain $APP."
rm -rf "${DEST:?}/$APP"
mv "$TMP/unpacked/$APP" "$DEST/$APP"
# Files fetched with curl are not quarantined, but clear the flag in case an older copy was
xattr -dr com.apple.quarantine "$DEST/$APP" 2>/dev/null || true

ok "Installed EarningsPulse $TAG in $DEST"
say "Opening it now. Next time, find it in Launchpad or Spotlight (⌘ Space, type EarningsPulse)."
open "$DEST/$APP"
