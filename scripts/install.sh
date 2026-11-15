#!/usr/bin/env bash
# Miyagi installer for macOS: the engine (Python 3.12 via uv), the Miyagi app, and, if you say yes,
# the VS Code companion extension. Needs no git, Node or Python beforehand. Makes no paid API calls.
#
#   curl -fsSL https://raw.githubusercontent.com/michae6345-crypto/sandhacks-tutor/integration/live/scripts/install.sh | bash
#   scripts/install.sh               # from a clone: uses that checkout in place (no download)
#   scripts/install.sh --dry-run     # print every step, change nothing
#   scripts/install.sh --help
#
# Where things go:
#   ~/miyagi/engine/        src/ (engine source), venv/ (Python + deps), bin/miyagi-engine (start it), logs/
#   /Applications/Miyagi.app   (~/Applications if /Applications isn't writable)
#   ~/miyagi/lessons/       your lesson folders (made by the engine, not by this script)
#
# API keys never go in a file: paste them in Miyagi's Settings, which keeps them in the macOS Keychain.
# Re-run the same command to update. Uninstall: docs/INSTALL.md.
set -euo pipefail

MIYAGI_REPO="${MIYAGI_REPO:-michae6345-crypto/sandhacks-tutor}"
MIYAGI_REF="${MIYAGI_REF:-integration/live}"
MIYAGI_HOME="${MIYAGI_HOME:-$HOME/miyagi/engine}"
MIYAGI_APP_URL="${MIYAGI_APP_URL:-https://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.zip}"
APP_BUNDLE_ID="dev.sandhacks.miyagi"   # app/electron-builder.yml appId
PY_VERSION="3.12"

DRY=0 YES=0 DO_APP=1 DO_VSCODE=1 DO_START=1 SRC_ARG="" APP_ZIP=""

say()  { printf '\033[1m[miyagi]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[miyagi]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[miyagi]\033[0m %s\n' "$*" >&2; exit 1; }
# Every change goes through run: --dry-run prints it instead.
run()  { if [ "$DRY" = 1 ]; then printf '  would run:'; printf ' %q' "$@"; printf '\n'; else "$@"; fi; }

# Questions read the keyboard, not stdin (stdin is the script itself under `curl | bash`).
# No keyboard (CI, a pipe): the answer is no, unless --yes.
ask() {
  local reply=""
  if [ "$YES" = 1 ]; then return 0; fi
  if [ "$DRY" = 1 ]; then printf '  would ask: %s [Y/n]\n' "$1"; return 0; fi
  if ! (: </dev/tty) 2>/dev/null; then return 1; fi
  printf '\033[1m[miyagi]\033[0m %s [Y/n] ' "$1" >/dev/tty
  IFS= read -r reply </dev/tty || reply="n"
  case "$reply" in ""|y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

usage() {
  sed -n '2,16p' "${BASH_SOURCE[0]:-/dev/null}" 2>/dev/null | sed 's/^# \{0,1\}//' || true
  cat <<'EOF'

Options:
  --dry-run        print every step, change nothing
  -y, --yes        yes to every question (VS Code extension, start now)
  --no-app         engine only (you already have Miyagi.app, or build it yourself)
  --no-vscode      don't offer the VS Code extension
  --no-start       don't offer to start Miyagi at the end
  --app-zip PATH   install the app from a Miyagi-Mac.zip you already have (e.g. from CI)
  --src DIR        use an engine checkout on disk instead of downloading one
  --ref REF        branch to download (default: integration/live)
Environment: MIYAGI_HOME, MIYAGI_REPO, MIYAGI_REF, MIYAGI_APP_URL, MIYAGI_APP_DIR.
EOF
}

# ---------------------------------------------------------------------------------------------------
# 0. This Mac

check_mac() {
  [ "$(uname -s)" = "Darwin" ] || die "This installer is for macOS. Windows: see docs/INSTALL.md (Windows section)."
  local v major
  v="$(sw_vers -productVersion 2>/dev/null || echo 0)"
  major="${v%%.*}"
  [ "${major:-0}" -ge 12 ] || die "Miyagi needs macOS 12 or newer (this Mac has $v)."
  ARCH="$(uname -m)"
  # A Terminal running under Rosetta says x86_64 on Apple Silicon: ask the hardware.
  if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = 1 ]; then ARCH=arm64; fi
  for t in curl tar ditto zip; do command -v "$t" >/dev/null || die "missing '$t' (part of macOS)"; done
  say "macOS $v on $ARCH"
}

# ---------------------------------------------------------------------------------------------------
# 1. uv (installs Python 3.12 and the engine's packages; ~30 MB, no admin rights)

find_uv() {
  UV=""
  local c
  for c in "$(command -v uv 2>/dev/null || true)" "$MIYAGI_HOME/bin/uv" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -n "$c" ] && [ -x "$c" ]; then UV="$c"; return 0; fi
  done
  return 1
}

ensure_uv() {
  if find_uv; then say "uv: $UV"; return; fi
  say "installing uv (Astral's Python manager) into $MIYAGI_HOME/bin (no shell profile changes)"
  if [ "$DRY" = 1 ]; then
    printf '  would run: curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=%q UV_NO_MODIFY_PATH=1 sh\n' "$MIYAGI_HOME/bin"
    UV="$MIYAGI_HOME/bin/uv"
    return
  fi
  mkdir -p "$MIYAGI_HOME/bin"
  curl -LsSf https://astral.sh/uv/install.sh |
    env UV_INSTALL_DIR="$MIYAGI_HOME/bin" UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
  find_uv || die "uv didn't install. Install it yourself (https://docs.astral.sh/uv/) and re-run."
  say "uv: $UV"
}

# ---------------------------------------------------------------------------------------------------
# 2. Engine source: this checkout, --src, or a download of $MIYAGI_REF

script_checkout() {
  # The checkout this script sits in, if it was run from a file (not piped from curl).
  local self="${BASH_SOURCE[0]:-}"
  [ -n "$self" ] && [ -f "$self" ] || return 1
  local root
  root="$(cd "$(dirname "$self")/.." && pwd)"
  [ -f "$root/server/pyproject.toml" ] && [ -f "$root/scripts/miyagi-engine.sh" ] || return 1
  printf '%s\n' "$root"
}

fetch_tarball() {
  # $1 = output file. Public repo: plain curl. Private repo: your `gh` login, if you have access.
  local out="$1" url="https://codeload.github.com/$MIYAGI_REPO/tar.gz/refs/heads/$MIYAGI_REF"
  if curl -fsSL --retry 2 -o "$out" "$url" 2>/dev/null; then return 0; fi
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    say "the repo isn't public; downloading with your GitHub login (gh)"
    gh api "repos/$MIYAGI_REPO/tarball/$MIYAGI_REF" >"$out" 2>/dev/null && [ -s "$out" ] && return 0
  fi
  return 1
}

ensure_source() {
  if [ -n "$SRC_ARG" ]; then
    SRC="$(cd "$SRC_ARG" && pwd)" || die "--src $SRC_ARG: no such folder"
    [ -f "$SRC/server/pyproject.toml" ] || die "--src $SRC: not a Miyagi checkout (no server/pyproject.toml)"
    say "engine source: $SRC (in place)"
    return
  fi
  if SRC="$(script_checkout)"; then
    say "engine source: this checkout, $SRC (in place)"
    return
  fi
  SRC="$MIYAGI_HOME/src"
  say "downloading the engine ($MIYAGI_REPO @ $MIYAGI_REF) into $SRC"
  if [ "$DRY" = 1 ]; then
    printf '  would download: https://codeload.github.com/%s/tar.gz/refs/heads/%s\n' "$MIYAGI_REPO" "$MIYAGI_REF"
    return
  fi
  mkdir -p "$MIYAGI_HOME"
  local tgz new="$MIYAGI_HOME/src.new"
  tgz="$(mktemp "${TMPDIR:-/tmp}/miyagi-src.XXXXXX")"
  fetch_tarball "$tgz" || {
    rm -f "$tgz"
    die "Couldn't download $MIYAGI_REPO@$MIYAGI_REF. While the repo is private: get access, run 'gh auth login', and re-run (or clone it and run scripts/install.sh from the clone)."
  }
  rm -rf "$new" && mkdir -p "$new"
  tar -xzf "$tgz" -C "$new" --strip-components 1
  rm -f "$tgz"
  [ -f "$new/server/pyproject.toml" ] || die "the download has no server/pyproject.toml (wrong ref?)"
  # Swap in the new source. The venv lives outside src/, so it survives (editable install = same path).
  rm -rf "$MIYAGI_HOME/src.old"
  [ -d "$SRC" ] && mv "$SRC" "$MIYAGI_HOME/src.old"
  mv "$new" "$SRC"
  # The engine caches built lessons, searches and transcripts in src/demo/cache: keep the learner's
  # (rebuilding a lesson costs API calls). -n: files that come with the new source win. macOS cp -n
  # exits 1 whenever it skips a file, so its status means nothing here.
  if [ -d "$MIYAGI_HOME/src.old/demo/cache" ]; then
    mkdir -p "$SRC/demo/cache"
    cp -Rn "$MIYAGI_HOME/src.old/demo/cache/." "$SRC/demo/cache/" 2>/dev/null || true
  fi
  rm -rf "$MIYAGI_HOME/src.old"
  printf 'repo=%s\nref=%s\ninstalled=%s\n' "$MIYAGI_REPO" "$MIYAGI_REF" "$(date -u +%Y-%m-%dT%H:%MZ)" >"$MIYAGI_HOME/VERSION"
}

# ---------------------------------------------------------------------------------------------------
# 3. Python 3.12 venv with the engine (+ the `tut` CLI)

ensure_venv() {
  VENV="$MIYAGI_HOME/venv"
  if [ ! -x "$VENV/bin/python" ]; then
    say "creating $VENV (Python $PY_VERSION; uv downloads it if this Mac doesn't have it)"
    run "$UV" venv --quiet --python "$PY_VERSION" "$VENV"
  fi
  say "installing the engine's packages (first time: about a minute)"
  local args=(-e "$SRC/server")
  [ -f "$SRC/cli/pyproject.toml" ] && args+=(-e "$SRC/cli")
  run "$UV" pip install --quiet --python "$VENV/bin/python" "${args[@]}"
  if [ "$DRY" = 0 ]; then
    "$VENV/bin/python" -c "import server, fastapi, uvicorn, anthropic, Quartz, Vision" ||
      die "the engine's packages didn't import; re-run, or see docs/INSTALL.md (Troubleshooting)"
  fi
}

# ---------------------------------------------------------------------------------------------------
# 4. bin/miyagi-engine: one command that starts the engine (Terminal now; Miyagi.app later)

write_launcher() {
  local bin="$MIYAGI_HOME/bin/miyagi-engine"
  say "writing $bin"
  if [ "$DRY" = 1 ]; then printf '  would write: %s (starts %s/scripts/miyagi-engine.sh on 127.0.0.1:8787)\n' "$bin" "$SRC"; return; fi
  mkdir -p "$MIYAGI_HOME/bin" "$MIYAGI_HOME/logs"
  cat >"$bin" <<EOF
#!/usr/bin/env bash
# Starts the Miyagi engine on ws://127.0.0.1:8787 (this Mac only). Written by scripts/install.sh;
# re-run the installer to update. Run it in Terminal, or let Miyagi.app start it.
set -euo pipefail
MIYAGI_HOME=$(printf '%q' "$MIYAGI_HOME")
SRC=$(printf '%q' "$SRC")
# Apps opened from Finder get a bare PATH: add where VS Code's \`code\`, Homebrew, uv and python live.
for d in "\$MIYAGI_HOME/bin" "\$HOME/.local/bin" /usr/local/bin /opt/homebrew/bin \\
         "/Applications/Visual Studio Code.app/Contents/Resources/app/bin" \\
         "\$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin"; do
  if [ -d "\$d" ]; then case ":\$PATH:" in *":\$d:"*) ;; *) PATH="\$d:\$PATH" ;; esac; fi
done
export PATH
# Started by the app (no terminal): write to logs/engine.log instead.
if [ ! -t 1 ]; then
  mkdir -p "\$MIYAGI_HOME/logs"
  exec >>"\$MIYAGI_HOME/logs/engine.log" 2>&1
  echo "--- \$(date '+%F %T') engine start"
fi
export PYTHON="\$MIYAGI_HOME/venv/bin/python"
export TUT_ENV="\${TUT_ENV:-\$MIYAGI_HOME/engine.env}"   # optional non-secret settings; keys live in the app
export ENGINE_HOST="\${ENGINE_HOST:-127.0.0.1}"          # this Mac only
export LESSON_ENGINE="\${LESSON_ENGINE:-claude}"         # lessons from the transcript with Claude (Gemini off)
export MIYAGI_EDITOR="\${MIYAGI_EDITOR:-vscode}"
exec "\$SRC/scripts/miyagi-engine.sh" "\$@"
EOF
  chmod +x "$bin"
  if [ ! -f "$MIYAGI_HOME/engine.env" ]; then
    cat >"$MIYAGI_HOME/engine.env" <<'EOF'
# Optional engine settings (read by bin/miyagi-engine). Not for API keys: put those in Miyagi's Settings
# (press ⌥Space and type "settings"), which keeps them in the macOS Keychain.
# Examples:
# DEMO=1                      # cached demo lesson, no API calls
# MIYAGI_LESSONS_DIR=${HOME}/code/miyagi-lessons
EOF
  fi
}

# ---------------------------------------------------------------------------------------------------
# 5. Miyagi.app

bundle_id() { /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null || true; }

install_app() {
  local dir="${MIYAGI_APP_DIR:-}"
  if [ -z "$dir" ]; then
    if [ -w /Applications ]; then dir=/Applications; else dir="$HOME/Applications"; fi
  fi
  APP="$dir/Miyagi.app"
  # APFS ignores case: an unrelated "miyagi.app" here IS this path. Only ever replace our own app.
  if [ -e "$APP" ]; then
    local id; id="$(bundle_id "$APP")"
    if [ "$id" != "$APP_BUNDLE_ID" ]; then
      warn "$APP is a different app (bundle id '${id:-none}'); leaving it alone. Use MIYAGI_APP_DIR=<folder> to install elsewhere."
      APP=""; return
    fi
    if pgrep -f "$APP/Contents/MacOS/" >/dev/null 2>&1; then
      warn "Miyagi is running. Quit it (⌥Q) and re-run to update the app; keeping the current one."
      return
    fi
  fi

  local tmp zip
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/miyagi-app.XXXXXX")"
  if [ -n "$APP_ZIP" ]; then
    zip="$APP_ZIP"; [ -f "$zip" ] || die "--app-zip $zip: no such file"
    say "installing the app from $zip"
  else
    zip="$tmp/Miyagi-Mac.zip"
    say "downloading the app: $MIYAGI_APP_URL"
    if [ "$DRY" = 1 ]; then
      if curl -fsIL -o /dev/null "$MIYAGI_APP_URL" 2>/dev/null; then echo "  (published: yes)"; else echo "  (published: NOT YET, the real run would skip the app)"; fi
      printf '  would install: %s\n' "$APP"; rm -rf "$tmp"; return
    fi
    if ! curl -fsSL --retry 2 -o "$zip" "$MIYAGI_APP_URL"; then
      rm -rf "$tmp"
      warn "The Mac app isn't downloadable yet ($MIYAGI_APP_URL)."
      warn "Get Miyagi-Mac.zip from the team and re-run with --app-zip <file>, or build it: cd \"$SRC/app\" && npm ci && npm run dist:mac"
      APP=""; return
    fi
  fi
  if [ "$DRY" = 1 ]; then printf '  would install: %s\n' "$APP"; rm -rf "$tmp"; return; fi

  ditto -x -k "$zip" "$tmp/x"
  # CI artifacts wrap the zip in another zip: unwrap once.
  local inner; inner="$(find "$tmp/x" -maxdepth 2 -name '*.zip' | head -1)"
  [ -n "$inner" ] && ditto -x -k "$inner" "$tmp/x"
  local new; new="$(find "$tmp/x" -maxdepth 3 -name 'Miyagi.app' -type d | head -1)"
  [ -n "$new" ] || { rm -rf "$tmp"; die "no Miyagi.app inside $zip"; }
  [ "$(bundle_id "$new")" = "$APP_BUNDLE_ID" ] || { rm -rf "$tmp"; die "$zip doesn't hold Miyagi (bundle id $(bundle_id "$new"))"; }
  local archs; archs="$(lipo -archs "$new/Contents/MacOS/Miyagi" 2>/dev/null || echo "")"
  case " $archs " in
    *" $ARCH "*) ;;
    *) rm -rf "$tmp"
       warn "This Miyagi build is for '$archs' and this Mac is $ARCH. Ask for a universal build (docs/DISTRIBUTION.md)."
       APP=""; return ;;
  esac
  mkdir -p "$dir"
  rm -rf "$APP"
  ditto "$new" "$APP"
  rm -rf "$tmp"
  say "app: $APP"
}

# ---------------------------------------------------------------------------------------------------
# 6. VS Code companion (asks first)

find_code_cli() {
  local c
  for c in "$(command -v code 2>/dev/null || true)" \
           "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
           "$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"; do
    if [ -n "$c" ] && [ -x "$c" ]; then printf '%s\n' "$c"; return 0; fi
  done
  return 1
}

install_vscode_ext() {
  local code
  if ! code="$(find_code_cli)"; then
    say "VS Code isn't installed: Miyagi offers it when a lesson needs it. Re-run this installer afterwards to add the companion."
    return
  fi
  if ! ask "Add the Miyagi Companion to VS Code? It lets Miyagi read your editor and terminal exactly and open files at the right line (localhost only)."; then
    say "skipped the VS Code companion (re-run the installer to add it)"
    return
  fi
  local tmp vsix
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/miyagi-vsix.XXXXXX")"
  vsix="$tmp/miyagi-companion.vsix"
  if [ "$DRY" = 1 ]; then
    printf '  would run: %q %q && %q --install-extension %q --force\n' "$SRC/scripts/package-vscode-ext.sh" "$vsix" "$code" "$vsix"
    rm -rf "$tmp"; return
  fi
  if [ -f "$SRC/scripts/package-vscode-ext.sh" ] &&
     bash "$SRC/scripts/package-vscode-ext.sh" "$vsix" >/dev/null &&
     "$code" --install-extension "$vsix" --force >/dev/null 2>&1; then
    say "VS Code companion installed (reload open VS Code windows: Cmd+Shift+P → Developer: Reload Window)"
  else
    local ver; ver="$(plutil -extract version raw -o - "$SRC/vscode-ext/package.json" 2>/dev/null || echo 0.0.1)"
    warn "code --install-extension failed; copying it into ~/.vscode/extensions instead"
    rm -rf "$HOME/.vscode/extensions/miyagi.companion-$ver"
    mkdir -p "$HOME/.vscode/extensions"
    cp -R "$SRC/vscode-ext" "$HOME/.vscode/extensions/miyagi.companion-$ver"
    rm -rf "$HOME/.vscode/extensions/miyagi.companion-$ver/test"
  fi
  rm -rf "$tmp"
}

# ---------------------------------------------------------------------------------------------------

next_steps() {
  local bin="$MIYAGI_HOME/bin/miyagi-engine" title="Miyagi is installed."
  if [ "$DRY" = 1 ]; then title="Dry run done. After a real run:"; fi
  cat <<EOF

$(printf '\033[1m')$title$(printf '\033[0m')
  1. Start the engine in Terminal (leave the window open):   "$bin"
     The first time, macOS asks to let Terminal record the screen: allow it in
     System Settings › Privacy & Security › Screen & System Audio Recording, quit Terminal, and run it again.
  2. Open Miyagi${APP:+ ($APP)}. It lives under the notch (no Dock icon).
  3. Settings opens by itself: paste your Anthropic API key (https://console.anthropic.com). Bright Data is optional.
  4. Press ⌥Space and type what you want to learn.
Full guide and troubleshooting: docs/INSTALL.md
EOF
}

main() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) DRY=1 ;;
      -y|--yes) YES=1 ;;
      --no-app) DO_APP=0 ;;
      --no-vscode) DO_VSCODE=0 ;;
      --no-start) DO_START=0 ;;
      --app-zip) APP_ZIP="${2:?--app-zip needs a file}"; shift ;;
      --src) SRC_ARG="${2:?--src needs a folder}"; shift ;;
      --ref) MIYAGI_REF="${2:?--ref needs a branch}"; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown option: $1 (try --help)" ;;
    esac
    shift
  done
  [ "$DRY" = 1 ] && say "dry run: nothing will change"
  APP=""

  check_mac
  ensure_uv
  ensure_source
  ensure_venv
  write_launcher
  if [ "$DO_APP" = 1 ]; then install_app; fi
  if [ "$DO_VSCODE" = 1 ]; then install_vscode_ext; fi
  next_steps

  if [ "$DO_START" = 1 ] && [ "$DRY" = 0 ] && ask "Start Miyagi now?"; then
    if lsof -nP -iTCP:8787 -sTCP:LISTEN >/dev/null 2>&1; then
      say "an engine is already running on :8787"
      [ -n "$APP" ] && open "$APP"
      return
    fi
    [ -n "$APP" ] && open "$APP"
    say "starting the engine here (Ctrl+C stops it)"
    exec "$MIYAGI_HOME/bin/miyagi-engine"
  fi
}

# Everything runs from here, so a half-downloaded `curl | bash` does nothing.
main "$@"
