#!/usr/bin/env bash
# Build the one-download Mac app (the app + the engine inside it) and zip it as Miyagi-Mac.zip.
# Run on a Mac, from app/:
#
#   npm run ship:mac                    # build + ad-hoc sign + zip  → app/dist/Miyagi-Mac.zip
#   npm run ship:mac -- --universal     # Apple silicon + Intel (bigger download)
#   npm run ship:mac -- --publish       # also upload it to the "mac" release (needs `gh auth login` + write access)
#
# Env: MIYAGI_ENGINE_REF (default origin/integration/live), MIYAGI_RELEASE_REPO (default adrian-erlikhman/miyagi).
# See app/SHIP.md for the whole flow and how to test it before you publish.
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(uname)" = "Darwin" ] || { echo "[ship] run this on a Mac (it signs and zips with codesign / ditto)"; exit 1; }

ARCH="--arm64"; PUBLISH=0
for a in "$@"; do
  case "$a" in
    --universal) ARCH="--universal" ;;
    --x64) ARCH="--x64" ;;
    --publish) PUBLISH=1 ;;
    *) echo "[ship] unknown option: $a"; exit 1 ;;
  esac
done
REPO="${MIYAGI_RELEASE_REPO:-adrian-erlikhman/miyagi}"

echo "[ship] 1/4 engine → build/engine"
node scripts/bundle-engine.mjs

echo "[ship] 2/4 app"
npx electron-vite build
npx electron-builder --mac --dir "$ARCH"

APP="$(find dist -maxdepth 2 -name '*.app' -type d | head -1)"
[ -n "$APP" ] || { echo "[ship] no .app in dist/"; exit 1; }
[ -f "$APP/Contents/Resources/engine/install.sh" ] || { echo "[ship] the engine isn't inside $APP (extraResources?)"; exit 1; }

echo "[ship] 3/4 ad-hoc sign $APP"
codesign --force --deep -s - "$APP"

echo "[ship] 4/4 zip"
rm -f dist/Miyagi-Mac.zip
ditto -c -k --keepParent "$APP" dist/Miyagi-Mac.zip
ls -lh dist/Miyagi-Mac.zip
echo "[ship] engine inside: $(cat "$APP/Contents/Resources/engine/VERSION")"

if [ "$PUBLISH" = 1 ]; then
  echo "[ship] uploading to $REPO release 'mac'"
  gh release upload mac dist/Miyagi-Mac.zip --clobber --repo "$REPO"
fi
echo "[ship] done. Test it (SHIP.md, 'Test before you publish') before anyone downloads it."
