#!/usr/bin/env bash
# Build miyagi and install it in /Applications, for using the real app every day on your own Mac (SHIP.md, "Daily use").
# Run from app/:
#
#   npm run install:local                      # ship build (dmg) → /Applications/miyagi.app
#   npm run install:local -- --dry-run         # print every step, change nothing (no build, no quit, no copy)
#   npm run install:local -- --skip-build      # install the dist/Miyagi-Mac.dmg that's already there
#   npm run install:local -- --open            # open miyagi when it's in place
#
# Switch the engine mode only (no build, no quit, no install, no backups touched; then quit and reopen miyagi):
#   npm run install:local -- --mode-only --engine dev              # YOUR engine on :8787 (Terminal, .env), never its own
#   npm run install:local -- --mode-only --engine dev --cloud off  # ...and no cloud token, so that engine uses .env keys
#   npm run install:local -- --mode-only --engine bundled          # back to what every user gets: inside engine + cloud
# (--skip-build with --engine or --cloud also only switches the mode; add --reinstall to install the dmg as well.)
# With a build (`npm run install:local -- --engine dev`) the mode is set after the install.
#
# What a full install does:
#   1. npm run ship:mac (bundle the engine, build, ad-hoc sign, dmg). Any extra ship option goes after --ship, e.g.
#      `-- --ship --universal`.
#   2. Copies miyagi.app out of the dmg (so you install exactly what users download) into /Applications/.miyagi.app.new
#      and checks its signature.
#   3. Quits miyagi: the installed app's main process and a dev copy (`npm run dev` Electron running this repo's app),
#      both with SIGTERM, which Electron turns into a normal quit (so the app stops the engine it started). No
#      AppleScript: no "wants access to control miyagi" Automation prompt, nothing that can hang a non-interactive shell.
#   4. Swaps it in with two renames on the same volume (never a half-copied app): the old one moves to
#      ~/miyagi/app-backups.noindex/miyagi-<date>.app (.noindex: Spotlight doesn't list backups). Keeps the last 2.
#   5. Strips quarantine (your own build) and registers it with Launch Services, so Spotlight and the Dock show the
#      bonsai and the name "miyagi" right away.
#   6. Prints which engine it will use and what to do about permissions (ad-hoc signed: see the end).
#
# It never touches ~/Applications (a dev launcher there keeps working), your engine, or VS Code.
set -euo pipefail
cd "$(dirname "$0")/.."

DRY=0; BUILD=1; OPEN=0; ENGINE=""; CLOUD=""; SHIP_ARGS=(); MODE_ONLY=0; REINSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --skip-build) BUILD=0 ;;
    --open) OPEN=1 ;;
    --mode-only) MODE_ONLY=1 ;;
    --reinstall) REINSTALL=1 ;;
    --engine) shift; ENGINE="${1:-}" ;;
    --engine=*) ENGINE="${1#--engine=}" ;;
    --cloud) shift; CLOUD="${1:-}" ;;
    --cloud=*) CLOUD="${1#--cloud=}" ;;
    --ship) shift; SHIP_ARGS=("$@"); break ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d'; exit 0 ;;
    *) echo "[install] unknown option: $1 (see --help)"; exit 1 ;;
  esac
  shift
done
case "$ENGINE" in ""|dev|bundled) ;; *) echo "[install] --engine dev | bundled"; exit 1 ;; esac
case "$CLOUD" in ""|on|off) ;; *) echo "[install] --cloud on | off"; exit 1 ;; esac
[ -z "$CLOUD" ] || [ "$ENGINE" = dev ] || [ "$CLOUD" = on ] || { echo "[install] --cloud off goes with --engine dev"; exit 1; }
# Switching the mode with --skip-build used to reinstall the same dmg and push a real backup out (KEEP=2): now it only
# switches the mode, unless --reinstall asks for the install too.
if [ "$MODE_ONLY" = 0 ] && [ "$BUILD" = 0 ] && [ "$REINSTALL" = 0 ] && { [ -n "$ENGINE" ] || [ -n "$CLOUD" ]; }; then MODE_ONLY=1; fi
if [ "$MODE_ONLY" = 1 ]; then
  [ -n "$ENGINE" ] || { echo "[install] switching the mode needs --engine dev | bundled (--cloud off goes with --engine dev)"; exit 1; }
  [ "$REINSTALL" = 0 ] || { echo "[install] --mode-only and --reinstall don't go together"; exit 1; }
  [ ${#SHIP_ARGS[@]} -eq 0 ] || { echo "[install] --mode-only builds nothing: drop --ship"; exit 1; }
fi

[ "$(uname)" = "Darwin" ] || { echo "[install] run this on a Mac"; exit 1; }

BUNDLE_ID="dev.sandhacks.miyagi"
DEST="/Applications/miyagi.app"
STAGE="/Applications/.miyagi.app.new"
DMG="dist/Miyagi-Mac.dmg"
BACKUPS="$HOME/miyagi/app-backups.noindex"
KEEP=2
USER_DATA="$HOME/Library/Application Support/miyagi"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
STAMP="$(date +%Y%m%d-%H%M%S)"
APP_DIR="$(pwd -P)"

say() { printf '[install] %s\n' "$*"; }
# Run a command, or only print it with --dry-run.
act() {
  if [ "$DRY" = 1 ]; then printf '[dry-run] would run:'; printf ' %q' "$@"; printf '\n'; else "$@"; fi
}

[ "$DRY" = 1 ] && say "dry run: nothing is built, quit, copied or deleted"

# --- engine mode (userData/engine.json, read by src/main/localEngine.ts on launch) ------------------------------------
write_mode() {
  local json="$1"
  if [ "$DRY" = 1 ]; then say "[dry-run] would write $USER_DATA/engine.json: $json"; return; fi
  mkdir -p "$USER_DATA"
  printf '%s\n' "$json" > "$USER_DATA/engine.json"
}
apply_mode() {
  case "$ENGINE" in
    dev)
      if [ "$CLOUD" = off ]; then write_mode '{"engine": "dev", "cloud": "off"}'; else write_mode '{"engine": "dev"}'; fi ;;
    bundled)
      if [ -f "$USER_DATA/engine.json" ]; then act rm -f "$USER_DATA/engine.json"; else say "  no engine.json: already bundled"; fi ;;
  esac
}
mode_report() {
  local mode="bundled" listener
  if [ "$ENGINE" = dev ]; then mode="dev"
  elif [ -z "$ENGINE" ] && [ -f "$USER_DATA/engine.json" ] && grep -q '"dev"' "$USER_DATA/engine.json"; then mode="dev"; fi
  listener="$(lsof -nP -iTCP:8787 -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -1 || true)"
  echo
  echo "Engine"
  if [ "$mode" = dev ]; then
    echo "  Mode: dev ($USER_DATA/engine.json$([ "$CLOUD" = off ] && echo ', cloud off')). miyagi only connects to the engine on :8787 and never starts its own."
    if [ -n "$listener" ]; then echo "  :8787 now: pid $listener, $(ps -o command= -p "$listener" | cut -c1-100)"
    else echo "  :8787 now: nothing. Start your dev engine in Terminal; the pill waits for it."; fi
    echo "  Back to what users get: npm run install:local -- --mode-only --engine bundled"
  else
    echo "  Mode: bundled (what every user gets): the engine inside the app, AI calls through the miyagi cloud."
    if [ -n "$listener" ]; then
      echo "  Note: :8787 is taken right now (pid $listener, $(ps -o command= -p "$listener" | cut -c1-80))."
      echo "  miyagi will use THAT engine and leave it running. To test what users get, stop it first."
    fi
    echo "  Use your dev engine instead: npm run install:local -- --mode-only --engine dev"
  fi
}
# The installed app's main process only: never a helper (Contents/Frameworks/...), the dev launcher in ~/Applications
# (also named miyagi) or a dev copy (Electron).
MAIN_RE='^/Applications/miyagi\.app/Contents/MacOS/miyagi( |$)'
running() { pgrep -f "$MAIN_RE" >/dev/null 2>&1; }

# --- mode only: no build, no quit, no install, the backups untouched ------------------------------------------------
if [ "$MODE_ONLY" = 1 ]; then
  say "switching the engine mode only (nothing is built, quit or installed; the backups stay as they are)"
  apply_mode
  mode_report
  echo
  if running; then
    echo "miyagi is running: quit it (menu bar tree > Quit miyagi, or Control-Option-Q) and reopen it to use the new mode."
  else
    echo "Open miyagi to use the new mode (if it was open, quit and reopen it)."
    if [ "$OPEN" = 1 ] && [ -d "$DEST" ]; then act open "$DEST"; fi
  fi
  exit 0
fi

# --- 1. build -------------------------------------------------------------------------------------------------------
if [ "$BUILD" = 1 ]; then
  say "1/6 ship build (a few minutes: engine, app, ad-hoc signature, dmg)"
  act bash scripts/ship-mac.sh ${SHIP_ARGS[@]+"${SHIP_ARGS[@]}"}
else
  say "1/6 build skipped: using $DMG"
fi
if [ "$DRY" = 0 ] && [ ! -f "$DMG" ]; then say "no $DMG: run without --skip-build"; exit 1; fi

# --- 2. copy the app out of the dmg ----------------------------------------------------------------------------------
say "2/6 copy miyagi.app out of $DMG → $STAGE"
[ -w /Applications ] || [ "$DRY" = 1 ] || { say "/Applications isn't writable for $(id -un): use an admin account"; exit 1; }
MNT=""
cleanup() {
  if [ -n "$MNT" ]; then hdiutil detach "$MNT" -quiet -force >/dev/null 2>&1 || true; rmdir "$MNT" 2>/dev/null || true; fi
  if [ "$DRY" = 0 ] && [ -e "$STAGE" ]; then rm -rf "$STAGE"; fi
}
trap cleanup EXIT
if [ "$DRY" = 1 ]; then
  act hdiutil attach "$DMG" -nobrowse -readonly -noautoopen -mountpoint "<tmp mount>"
  act ditto "<tmp mount>/miyagi.app" "$STAGE"
  act codesign --verify --deep --strict "$STAGE"
else
  MNT="$(mktemp -d /tmp/miyagi-dmg.XXXXXX)"
  hdiutil attach "$DMG" -nobrowse -readonly -noautoopen -mountpoint "$MNT" -quiet
  [ -d "$MNT/miyagi.app" ] || { say "no miyagi.app inside $DMG (productName?)"; exit 1; }
  rm -rf "$STAGE"
  ditto "$MNT/miyagi.app" "$STAGE"
  hdiutil detach "$MNT" -quiet; rmdir "$MNT" 2>/dev/null || true; MNT=""
  codesign --verify --deep --strict "$STAGE" || { say "the copied app's signature doesn't verify"; exit 1; }
  NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleName' "$STAGE/Contents/Info.plist")"
  [ "$NAME" = miyagi ] || { say "CFBundleName is '$NAME', expected 'miyagi'"; exit 1; }
fi

# --- 3. quit miyagi ----------------------------------------------------------------------------------------------------
say "3/6 quit miyagi (installed app and any dev copy of this repo's app)"
# SIGTERM to the main process: Electron turns it into a normal quit, so will-quit stops the engine the app started
# (never one you started in Terminal). No AppleScript, so no one-time Automation prompt for Terminal / VS Code.
if running; then
  act pkill -TERM -f "$MAIN_RE"
  if [ "$DRY" = 0 ]; then
    for _ in $(seq 1 20); do running || break; sleep 0.5; done
    if running; then
      # Its engine keeps running; the next launch recognizes it from the pid file and replaces it (localEngine step 7).
      say "  miyagi didn't quit in 10 s: stopping it (SIGKILL); the next launch replaces the engine it left"
      pkill -KILL -f "$MAIN_RE" || true
      sleep 1
    fi
  fi
else
  say "  the installed miyagi isn't running"
fi
# A dev copy: Electron started by electron-vite on this repo's app/ (or another worktree of it). Only its main process
# (no --type=, so not a renderer/GPU helper), only when its command line points at a miyagi app folder.
dev_pids() {
  local pid cmd
  for pid in $(pgrep -f 'Electron.app/Contents/MacOS/Electron' 2>/dev/null || true); do
    cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    case "$cmd" in
      *--type=*) ;;
      *sandhacks-tutor*|*miyagi*|*"$APP_DIR"*) echo "$pid" ;;
    esac
  done
}
DEV_PIDS="$(dev_pids)"
if [ -n "$DEV_PIDS" ]; then
  for pid in $DEV_PIDS; do
    say "  dev copy running (pid $pid): $(ps -o command= -p "$pid" | cut -c1-120)"
    act kill -TERM "$pid"
  done
else
  say "  no dev copy running"
fi

# --- 4. swap -----------------------------------------------------------------------------------------------------------
say "4/6 install → $DEST"
ASIDE="/Applications/.miyagi.app.old-$STAMP"
OLD=""
[ -e "$DEST" ] && OLD="$BACKUPS/miyagi-$STAMP.app"
if [ "$DRY" = 1 ]; then
  [ -n "$OLD" ] && act mv "$DEST" "$ASIDE"
  act mv "$STAGE" "$DEST"
  [ -n "$OLD" ] && act mkdir -p "$BACKUPS" && act mv "$ASIDE" "$OLD"
else
  # Two renames on one volume: /Applications never holds a half-copied app. If the second fails, put the old one back.
  [ -n "$OLD" ] && mv "$DEST" "$ASIDE"
  if ! mv "$STAGE" "$DEST"; then
    [ -n "$OLD" ] && mv "$ASIDE" "$DEST"
    say "couldn't move the new app into place; the old one is back"; exit 1
  fi
  if [ -n "$OLD" ]; then
    mkdir -p "$BACKUPS"
    mv "$ASIDE" "$OLD" || say "  couldn't move the old app to $BACKUPS; it's still at $ASIDE"
  fi
fi
[ -n "$OLD" ] && say "  previous app kept at $OLD"
# Keep the newest $KEEP backups (a dry run counts the one it would have added).
if [ -d "$BACKUPS" ]; then
  KEEP_NOW=$KEEP
  [ "$DRY" = 1 ] && [ -n "$OLD" ] && KEEP_NOW=$((KEEP - 1))
  # shellcheck disable=SC2012
  ls -1dt "$BACKUPS"/miyagi-*.app 2>/dev/null | tail -n +"$((KEEP_NOW + 1))" | while read -r b; do
    [ -n "$b" ] && act rm -rf "$b"
  done
fi

# --- 5. quarantine, Launch Services -----------------------------------------------------------------------------------
say "5/6 strip quarantine, register with Launch Services"
act xattr -dr com.apple.quarantine "$DEST"
[ -x "$LSREGISTER" ] && act "$LSREGISTER" -f "$DEST"

# --- engine mode (only when --engine was given) ------------------------------------------------------------------------
[ -z "$ENGINE" ] || apply_mode

# --- 6. report ---------------------------------------------------------------------------------------------------------
say "6/6 done$([ "$DRY" = 1 ] && echo ' (dry run)')"
if [ "$DRY" = 0 ]; then
  plist="$DEST/Contents/Info.plist"
  say "  $(/usr/libexec/PlistBuddy -c 'Print :CFBundleDisplayName' "$plist") $(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$plist"), $BUNDLE_ID, engine $(cat "$DEST/Contents/Resources/engine/VERSION" 2>/dev/null || echo '?')"
fi

mode_report
if [ -d "$HOME/Applications/miyagi.app" ]; then
  echo
  echo "Spotlight: ~/Applications/miyagi.app (your dev launcher) is also called miyagi. Spotlight lists both;"
  echo "  this script never touches it. Pick /Applications/miyagi.app, or rename the dev one (e.g. 'miyagi dev')."
fi

cat <<'EOF'

Permissions (miyagi is signed ad hoc, so macOS sees every rebuild as a new app)
  The first open asks for Screen Recording (and later Accessibility / Automation) for "miyagi". After a reinstall a
  switch can look ON in System Settings and still not work, because it belongs to the old build. Then:
    System Settings > Privacy & Security > Screen & System Audio Recording (macOS 15+; "Screen Recording" on 14):
      select miyagi, press -, then open miyagi again and allow it when asked. Same for Accessibility.
  Or reset only miyagi's grants from Terminal and let it ask again on the next open:
    tccutil reset ScreenCapture dev.sandhacks.miyagi
    tccutil reset Accessibility dev.sandhacks.miyagi
    tccutil reset AppleEvents dev.sandhacks.miyagi
  If macOS says to quit and reopen after granting: quit from the menu bar tree (Quit miyagi) or with Control-Option-Q.
  With the dev engine, Screen Recording belongs to the app that started that engine (Terminal or VS Code), not miyagi.
  A Developer ID signature fixes the re-asking for good (SHIP.md, Known gaps).
EOF
echo
if [ "$OPEN" = 1 ]; then
  act open "$DEST"
else
  echo "Open it: Spotlight (Cmd-Space) > miyagi, or Applications > miyagi."
fi
