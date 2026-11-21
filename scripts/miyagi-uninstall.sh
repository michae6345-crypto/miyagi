#!/usr/bin/env bash
# miyagi-uninstall.sh: remove miyagi from this Mac for a truly clean reinstall test.
#
# Dry run by default: it only lists what it finds. Pass --yes to remove it.
# The list is DISTRIBUTION-PLAN.md section 5; the full test is docs/CLEAN-TEST.md.
#
#   scripts/miyagi-uninstall.sh                  # dry run: show what would go
#   scripts/miyagi-uninstall.sh --yes            # remove it
#   scripts/miyagi-uninstall.sh --yes --keep-lessons --keep-state
#
# What it never does:
#   - kill a process. It asks miyagi to quit (like ⌥Q) and stops if miyagi, anything on
#     port 8787, or anything with files open in an app data folder (the npm run dev app)
#     is still running, so a dev engine or dev app is never touched.
#   - remove an .app whose bundle id is not dev.sandhacks.miyagi (a dev launcher applet
#     named miyagi.app, for example).
#   - delete lessons. ~/miyagi/lessons is moved aside to ~/miyagi-lessons-<time> (or left
#     in place with --keep-lessons).
#   - delete ~/miyagi/state (lesson progress, history, mastery, the Continue list and
#     gemini_usage.json, the daily Gemini video counter). It is moved aside to
#     ~/miyagi-state-<time> (or left in place with --keep-state).
#   - touch ~/.cache/uv, ~/.local/share/uv, the Python or Jupyter VS Code extensions, or the
#     "Electron Safe Storage" keychain item (shared by every Electron app run from source).
#   - print a keychain secret. Keychain lookups read attributes only and their output is dropped.
#
# macOS only, bash 3.2 compatible (the one that ships with macOS). Run as yourself, not sudo.

set -u

BUNDLE_ID="dev.sandhacks.miyagi"
ENGINE_PORT=8787
EXT_ID="miyagi.companion"
# Names the app has run under: "Miyagi" (packaged: electron-builder productName), "miyagi",
# "miyagi-overlay" (npm run dev: package.json name).
APP_NAMES="miyagi Miyagi miyagi-overlay"
TCC_SERVICES="ScreenCapture Accessibility AppleEvents Microphone"

MODE="dry"
KEEP_LESSONS=0
KEEP_STATE=0

usage() {
  cat <<'EOF'
usage: miyagi-uninstall.sh [--dry-run | --yes] [--keep-lessons] [--keep-state]

Removes miyagi from this Mac so the next download starts from nothing:
the app, its data, its keychain item, the local engine, the VS Code
companion extension and the macOS permissions it was granted. Lessons and
engine state are moved aside, never deleted.

  --dry-run       list what would be removed and change nothing (default)
  --yes, -y       remove it
  --keep-lessons  leave ~/miyagi/lessons where it is (default: move it aside
                  to ~/miyagi-lessons-<time>, never delete it)
  --keep-state    leave ~/miyagi/state where it is: lesson progress, history,
                  mastery and today's Gemini usage (default: move it aside to
                  ~/miyagi-state-<time>, never delete it)
  -h, --help      this text

Full test procedure: docs/CLEAN-TEST.md
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|-n) MODE="dry" ;;
    --yes|-y) MODE="act" ;;
    --keep-lessons) KEEP_LESSONS=1 ;;
    --keep-state) KEEP_STATE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'miyagi-uninstall: unknown option %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

die() { printf 'miyagi-uninstall: %s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "this script is for macOS only."
[ "$(id -u)" -ne 0 ] || die "run it as yourself, not with sudo (it works on your home folder)."
case "${HOME:-}" in
  ""|"/") die "HOME is not set to a home folder." ;;
esac
[ -d "$HOME" ] || die "HOME ($HOME) is not a folder."

FOUND=0     # things found (dry run: things that would change)
CHANGED=0   # things removed or reset (--yes)
FAILED=0    # things that could not be removed (--yes)
SEEN=""     # device:inode of every path already handled (case-insensitive volumes)

section() { printf '\n== %s\n' "$*"; }
info()    { printf '   %s\n' "$*"; }
would()   { FOUND=$((FOUND + 1)); printf '   would %s\n' "$*"; }
did()     { CHANGED=$((CHANGED + 1)); printf '   done   %s\n' "$*"; }
failed()  { FAILED=$((FAILED + 1)); printf '   FAILED %s\n' "$*"; }
nothing() { printf '   nothing to do: %s\n' "$*"; }
tilde()   { case "$1" in "$HOME"/*) printf '~/%s' "${1#"$HOME"/}" ;; *) printf '%s' "$1" ;; esac; }

# A path is removable only when it is inside $HOME (and not $HOME itself or a top-level
# Library folder), or it is the app bundle in /Applications.
safe_target() {
  p="$1"
  case "$p" in
    *"/../"*|*"/./"*|*/..|*/.) return 1 ;;
  esac
  case "$p" in
    /Applications/miyagi.app|/Applications/Miyagi.app) return 0 ;;
    "$HOME"/Library) return 1 ;;
    "$HOME"/Library/?*/?*) return 0 ;;
    "$HOME"/Library/*) return 1 ;;
    "$HOME"/?*) return 0 ;;
  esac
  return 1
}

# Returns 0 the first time a path (by device and inode) is seen, 1 after that.
first_sight() {
  key=$(stat -f '%d:%i' "$1" 2>/dev/null) || return 0
  case " $SEEN " in *" $key "*) return 1 ;; esac
  SEEN="$SEEN $key"
  return 0
}

size_of() { du -sh "$1" 2>/dev/null | awk '{print $1}'; }

# remove PATH: delete a file or folder if it exists.
remove() {
  p="$1"
  [ -e "$p" ] || [ -L "$p" ] || return 0
  first_sight "$p" || return 0
  shown=$(tilde "$p")
  if ! safe_target "$p"; then
    failed "refusing to remove $shown (outside the allowed places)"
    return 0
  fi
  if [ "$MODE" = "dry" ]; then
    would "remove $shown ($(size_of "$p"))"
  elif rm -rf -- "$p" 2>/dev/null && [ ! -e "$p" ]; then
    did "removed $shown"
  else
    failed "could not remove $shown (check its owner, or remove it in Finder)"
  fi
}

# bundle_id_of APP: the CFBundleIdentifier in APP's Info.plist, or nothing.
# PlistBuddy prints "File Doesn't Exist, Will Create: ..." on stdout for a missing
# plist, so its output is used only when it succeeds.
bundle_id_of() {
  [ -f "$1/Contents/Info.plist" ] || return 0
  out=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null) \
    && printf '%s' "$out"
}

# is_disk_image VOL: 0 when the mounted volume VOL comes from a disk image (hdiutil).
# An external drive or other volume that happens to be called miyagi is not one.
is_disk_image() {
  hdiutil info 2>/dev/null | awk -F '\t' -v v="$1" '$NF == v { found = 1 } END { exit !found }'
}

# move_aside PATH NAME KEEP FLAG: move PATH to ~/miyagi-NAME-<time> (never delete it), or
# leave it in place when KEEP is 1 (FLAG names the option that did that).
move_aside() {
  src="$1"; name="$2"; keep="$3"; flag="$4"
  [ -d "$src" ] || return 0
  if [ "$keep" -eq 1 ]; then
    info "kept $(tilde "$src") in place ($flag)"
    return 0
  fi
  dest="$HOME/miyagi-$name-$(date +%Y%m%d-%H%M%S)"
  if [ "$MODE" = "dry" ]; then
    would "move $(tilde "$src") aside to $(tilde "$dest") ($(size_of "$src"), not deleted)"
  elif mv -- "$src" "$dest" 2>/dev/null; then
    did "moved $(tilde "$src") to $(tilde "$dest")"
  else
    failed "could not move $(tilde "$src") aside"
  fi
}

# remove_app PATH: remove an .app bundle only when it is the miyagi app ($BUNDLE_ID).
# Anything else that happens to be called miyagi.app (a dev launcher applet, for
# example) is kept.
remove_app() {
  p="$1"
  [ -e "$p" ] || [ -L "$p" ] || return 0
  id=$(bundle_id_of "$p")
  if [ "$id" = "$BUNDLE_ID" ]; then
    remove "$p"
  else
    first_sight "$p" || return 0
    info "kept $(tilde "$p") (not the miyagi app: bundle id ${id:-none})"
  fi
}

# rmdir_if_empty PATH: tidy a parent folder once its contents are gone.
rmdir_if_empty() {
  [ "$MODE" = "act" ] || return 0
  [ -d "$1" ] || return 0
  if rmdir "$1" 2>/dev/null; then info "removed empty $(tilde "$1")"; fi
}

app_pids() { pgrep -f '/[Mm]iyagi\.app/Contents/MacOS/' 2>/dev/null; }
port_pids() { lsof -nP -iTCP:"$ENGINE_PORT" -sTCP:LISTEN -t 2>/dev/null | sort -u; }
# userdata_pids NAME: pids with a file open in ~/Library/Application Support/NAME. This also
# catches the dev app (npm run dev runs Electron.app, which app_pids does not match).
userdata_pids() {
  d="$HOME/Library/Application Support/$1"
  [ -d "$d" ] || return 0
  lsof -t +D "$d" 2>/dev/null | sort -u
}
show_pids() { for pid in "$@"; do info "pid $pid: $(ps -o command= -p "$pid" 2>/dev/null | cut -c1-140)"; done; }

if [ "$MODE" = "dry" ]; then
  printf 'miyagi-uninstall: DRY RUN, nothing will change. Run with --yes to remove.\n'
else
  printf 'miyagi-uninstall: removing miyagi from this Mac.\n'
fi

# ---------------------------------------------------------------------------------------
section "1. Processes"
pids=$(app_pids)
if [ -n "$pids" ]; then
  if [ "$MODE" = "dry" ]; then
    would "ask miyagi to quit (the same as ⌥Q):"
    show_pids $pids
  else
    info "asking miyagi to quit (the same as ⌥Q)..."
    osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
    i=0
    while [ -n "$(app_pids)" ] && [ $i -lt 15 ]; do sleep 1; i=$((i + 1)); done
    if [ -n "$(app_pids)" ]; then
      show_pids $(app_pids)
      die "miyagi is still running. Quit it with ⌥Q (or from its menu), then run this again. Nothing was removed."
    fi
    did "miyagi quit"
  fi
else
  nothing "miyagi is not running"
fi

pids=$(port_pids)
if [ -n "$pids" ] && [ "$MODE" = "act" ]; then
  # The app's own engine can take a few seconds to exit after the app quits.
  i=0
  while [ -n "$(port_pids)" ] && [ $i -lt 10 ]; do sleep 1; i=$((i + 1)); done
  pids=$(port_pids)
fi
if [ -n "$pids" ]; then
  if [ "$MODE" = "dry" ]; then
    FOUND=$((FOUND + 1))
    info "BLOCKER: something listens on port $ENGINE_PORT, so a reinstalled miyagi would use it"
    info "instead of its own engine. Stop it yourself before --yes (this script never kills it):"
    show_pids $pids
  else
    info "something still listens on port $ENGINE_PORT:"
    show_pids $pids
    die "stop that process yourself (this script never kills processes), then run this again. Nothing was removed."
  fi
else
  info "port $ENGINE_PORT is free"
fi

# Anything still using an app data folder (the dev app from npm run dev, for example) would
# lose its keys.bin and its keychain key while running. Same rule as port 8787: never kill.
ud_seen=""
for name in $APP_NAMES; do
  shown="~/Library/Application Support/$name"
  # miyagi and Miyagi are one folder on a case-insensitive volume: check it once.
  key=$(stat -f '%d:%i' "$HOME/Library/Application Support/$name" 2>/dev/null) || continue
  case " $ud_seen " in *" $key "*) continue ;; esac
  ud_seen="$ud_seen $key"
  pids=$(userdata_pids "$name")
  if [ -n "$pids" ] && [ "$MODE" = "act" ]; then
    # Give an app that was just asked to quit a few seconds to close its files.
    i=0
    while [ -n "$(userdata_pids "$name")" ] && [ $i -lt 5 ]; do sleep 1; i=$((i + 1)); done
    pids=$(userdata_pids "$name")
  fi
  if [ -z "$pids" ]; then
    info "$shown is not in use"
    continue
  fi
  if [ "$MODE" = "dry" ]; then
    FOUND=$((FOUND + 1))
    info "BLOCKER: $shown is in use, so --yes would remove it under a running app."
    info "Quit miyagi (packaged or npm run dev) with ⌥Q first (this script never kills it):"
    show_pids $pids
  else
    info "these processes still have files open in $shown:"
    show_pids $pids
    die "quit miyagi (packaged or npm run dev) with ⌥Q yourself (this script never kills processes), then run this again. Nothing was removed."
  fi
done

# ---------------------------------------------------------------------------------------
section "2. Permissions and login item (before the app goes, while macOS still knows its id)"
for svc in $TCC_SERVICES; do
  if [ "$MODE" = "dry" ]; then
    info "would reset the $svc permission for $BUNDLE_ID (tccutil reset)"
  elif err=$(tccutil reset "$svc" "$BUNDLE_ID" 2>&1 >/dev/null); then
    did "reset the $svc permission"
  else
    case "$err" in
      *"No such bundle identifier"*) nothing "$svc: macOS no longer knows $BUNDLE_ID (app already gone)" ;;
      *) failed "could not reset $svc (remove miyagi in System Settings > Privacy & Security > $svc)" ;;
    esac
  fi
done
if [ "$MODE" = "dry" ]; then
  info "would remove the \"miyagi\" login item if \"Open at login\" was on"
else
  # macOS may ask once to let Terminal control System Events; declining only skips this.
  out=$(osascript -e 'tell application "System Events"
      set n to 0
      repeat with nm in {"miyagi", "Miyagi"}
        if exists login item nm then
          delete login item nm
          set n to n + 1
        end if
      end repeat
      return n
    end tell' 2>/dev/null) || out=""
  case "$out" in
    ""|0) nothing "no miyagi login item found by System Events" ;;
    *) did "removed the miyagi login item" ;;
  esac
fi
info "check System Settings > General > Login Items: no miyagi entry should remain"

# ---------------------------------------------------------------------------------------
section "3. App"
# Each .app goes only if its bundle id is $BUNDLE_ID (see remove_app).
remove_app "/Applications/miyagi.app"
remove_app "/Applications/Miyagi.app"
remove_app "$HOME/Applications/miyagi.app"
remove_app "$HOME/Applications/Miyagi.app"
for vol in /Volumes/[Mm]iyagi*; do
  [ -d "$vol" ] || continue
  if ! is_disk_image "$vol"; then
    info "kept $vol mounted (not a disk image)"
  elif [ "$MODE" = "dry" ]; then
    would "eject the mounted disk image $vol"
  elif hdiutil detach "$vol" -quiet 2>/dev/null; then
    did "ejected $vol"
  else
    failed "could not eject $vol (eject it in Finder)"
  fi
done
if [ -d "$HOME/Downloads" ]; then
  while IFS= read -r f; do
    case "$f" in
      *.[Aa][Pp][Pp]) remove_app "$f" ;;
      *) remove "$f" ;;
    esac
  done < <(
    find "$HOME/Downloads" -maxdepth 1 -iname 'miyagi*' \
      \( -iname '*.zip' -o -iname '*.dmg' -o -iname '*.app' \) 2>/dev/null)
fi

# ---------------------------------------------------------------------------------------
section "4. App data (keys.bin, install.bin, prefs, caches, logs)"
for name in $APP_NAMES; do
  remove "$HOME/Library/Application Support/$name"
  remove "$HOME/Library/Caches/$name"
  remove "$HOME/Library/Logs/$name"
done
for p in "$HOME/Library/Caches/$BUNDLE_ID"* "$HOME/Library/HTTPStorages/$BUNDLE_ID"* \
         "$HOME/Library/Saved Application State/$BUNDLE_ID"*; do
  remove "$p"
done
# cfprefsd caches preferences in memory: clear the domain first, then the file.
if defaults read "$BUNDLE_ID" >/dev/null 2>&1; then
  if [ "$MODE" = "dry" ]; then
    would "clear the preferences domain $BUNDLE_ID (defaults delete)"
  elif defaults delete "$BUNDLE_ID" >/dev/null 2>&1; then
    did "cleared the preferences domain $BUNDLE_ID"
  else
    failed "could not clear the preferences domain $BUNDLE_ID"
  fi
fi
for p in "$HOME/Library/Preferences/$BUNDLE_ID"*.plist; do
  remove "$p"
done

# ---------------------------------------------------------------------------------------
section "5. Keychain (safeStorage key that encrypts keys.bin and install.bin)"
kc_found=0
for name in $APP_NAMES; do
  svc="$name Safe Storage"
  # find-generic-password without -g or -w reads attributes only; output dropped anyway.
  security find-generic-password -s "$svc" >/dev/null 2>&1 || continue
  kc_found=1
  if [ "$MODE" = "dry" ]; then
    would "delete the keychain item \"$svc\""
    continue
  fi
  i=0
  while security find-generic-password -s "$svc" >/dev/null 2>&1 && [ $i -lt 5 ]; do
    security delete-generic-password -s "$svc" >/dev/null 2>&1 || break
    i=$((i + 1))
  done
  if security find-generic-password -s "$svc" >/dev/null 2>&1; then
    failed "could not delete the keychain item \"$svc\" (delete it in Keychain Access)"
  else
    did "deleted the keychain item \"$svc\""
  fi
done
[ $kc_found -eq 1 ] || nothing "no miyagi Safe Storage item in the login keychain"
info "kept \"Electron Safe Storage\" (shared by every Electron app run from source)"

# ---------------------------------------------------------------------------------------
section "6. Engine and state"
remove "$HOME/miyagi/engine"
remove "$HOME/.miyagi/tiger-spool"
remove "$HOME/.cache/sandhacks-tutor/tts"
# state: lesson progress (current.json, graph-<lessonId>.json), history.json, mastery.json,
# the Continue list (recent.json) and gemini_usage.json (the daily Gemini video cap).
move_aside "$HOME/miyagi/state" state "$KEEP_STATE" --keep-state
move_aside "$HOME/miyagi/lessons" lessons "$KEEP_LESSONS" --keep-lessons
if [ -n "${MIYAGI_STATE_DIR:-}" ]; then
  info "note: MIYAGI_STATE_DIR is set to $MIYAGI_STATE_DIR; that folder is left alone"
fi
if [ -n "${MIYAGI_LESSONS_DIR:-}" ]; then
  info "note: MIYAGI_LESSONS_DIR is set to $MIYAGI_LESSONS_DIR; that folder is left alone"
fi
rmdir_if_empty "$HOME/miyagi"
rmdir_if_empty "$HOME/.miyagi"
rmdir_if_empty "$HOME/.cache/sandhacks-tutor"

# ---------------------------------------------------------------------------------------
section "7. VS Code companion extension ($EXT_ID)"
CODE=""
for c in "$(command -v code 2>/dev/null)" \
         "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
         "$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"; do
  if [ -n "$c" ] && [ -x "$c" ]; then CODE="$c"; break; fi
done
ext_dirs=0
for d in "$HOME/.vscode/extensions/$EXT_ID"-*; do
  [ -e "$d" ] && ext_dirs=1
done
if [ $ext_dirs -eq 1 ]; then
  if [ -n "$CODE" ]; then
    if [ "$MODE" = "dry" ]; then
      would "run: code --uninstall-extension $EXT_ID"
    elif "$CODE" --uninstall-extension "$EXT_ID" >/dev/null 2>&1; then
      did "uninstalled $EXT_ID from VS Code"
    else
      info "VS Code could not uninstall $EXT_ID; removing its folder instead"
    fi
  else
    info "VS Code's command line tool was not found; removing the extension folder directly"
  fi
  for d in "$HOME/.vscode/extensions/$EXT_ID"-*; do remove "$d"; done
  [ "$MODE" = "dry" ] || info "reload any open VS Code window so it forgets the extension"
else
  nothing "$EXT_ID is not installed"
fi
info "kept the Python and Jupyter extensions"

# ---------------------------------------------------------------------------------------
section "8. Kept on purpose"
info "~/.cache/uv and ~/.local/share/uv (other projects use them; the new bundle does not)"
info "the Python and Jupyter VS Code extensions"
info "\"Electron Safe Storage\" in the keychain"

printf '\n'
if [ "$MODE" = "dry" ]; then
  if [ $FOUND -eq 0 ] && [ $FAILED -eq 0 ]; then
    printf 'Dry run: this Mac is already clean of miyagi.\n'
  else
    printf 'Dry run: %d item(s) would change. Nothing was changed.\n' "$FOUND"
    printf 'Run again with --yes to remove them. Next: docs/CLEAN-TEST.md\n'
  fi
  [ $FAILED -eq 0 ] || exit 1
  exit 0
fi
printf 'Done: %d item(s) removed or reset, %d failed.\n' "$CHANGED" "$FAILED"
printf 'Run it again (dry run) to confirm nothing is left. Next: docs/CLEAN-TEST.md\n'
[ $FAILED -eq 0 ] || exit 1
exit 0
