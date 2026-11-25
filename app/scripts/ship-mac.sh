#!/usr/bin/env bash
# Build the one-download Mac app (the app + the engine inside it) as a one-click disk image, Miyagi-Mac.dmg:
# open it, drag miyagi onto Applications. Run on a Mac, from app/:
#
#   npm run ship:mac                    # build + ad-hoc sign + dmg  → app/dist/Miyagi-Mac.dmg
#   npm run ship:mac -- --zip           # also app/dist/Miyagi-Mac.zip (what install.sh --app still downloads)
#   npm run ship:mac -- --universal     # Apple silicon + Intel (bigger download)
#   npm run ship:mac -- --x64           # Intel only → app/dist/Miyagi-Mac-x64.dmg (never the Apple silicon name)
#   npm run ship:mac -- --publish       # also upload to the "mac" release (needs `gh auth login` + write access) and
#                                       # set its title and notes, which is where the update card reads the version
#
# Env: MIYAGI_ENGINE_REF (default origin/integration/live), MIYAGI_RELEASE_REPO (default adrian-erlikhman/miyagi),
#      MIYAGI_DMG_FORMAT (default ULMO = lzma, macOS 10.15+; ULFO = lzfse, the format electron-builder writes).
# See app/SHIP.md for the whole flow and how to test it before you publish, app/SIZE.md for what makes it this big.
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(uname)" = "Darwin" ] || { echo "[ship] run this on a Mac (it signs and packs with codesign / hdiutil)"; exit 1; }

ARCH="--arm64"; PUBLISH=0; ZIP=0
for a in "$@"; do
  case "$a" in
    --universal) ARCH="--universal" ;;
    --x64) ARCH="--x64" ;;
    --zip) ZIP=1 ;;
    --publish) PUBLISH=1 ;;
    *) echo "[ship] unknown option: $a"; exit 1 ;;
  esac
done
REPO="${MIYAGI_RELEASE_REPO:-adrian-erlikhman/miyagi}"
FORMAT="${MIYAGI_DMG_FORMAT:-ULMO}"
case "$FORMAT" in ULMO|ULFO|UDZO) ;; *) echo "[ship] MIYAGI_DMG_FORMAT=$FORMAT: use ULMO, ULFO or UDZO"; exit 1 ;; esac
# Names (RELEASING.md, .github/scripts/release-notes.mjs): Miyagi-Mac.dmg is the Apple silicon download, the one the
# site and the in-app update card link to (a universal build runs there too). An Intel-only build is Miyagi-Mac-x64.dmg,
# so it can never replace the download Apple silicon Macs get.
if [ "$ARCH" = "--x64" ]; then NAME=Miyagi-Mac-x64; else NAME=Miyagi-Mac; fi
DMG="dist/$NAME.dmg"
ZIPFILE="dist/$NAME.zip"

echo "[ship] 1/5 engine → build/engine"
node scripts/bundle-engine.mjs

echo "[ship] 1b/5 push-to-talk helper → build/helpers/miyagi-listen (signed here, before electron-builder seals the app)"
bash native/listen/build.sh

echo "[ship] 2/5 app"
# A stale .app from another arch would be picked up below.
rm -rf dist/mac dist/mac-* dist/Miyagi-Mac*
npx electron-vite build
npx electron-builder --mac --dir "$ARCH" --publish never

APP="$(find dist -maxdepth 2 -name '*.app' -type d | head -1)"
[ -n "$APP" ] || { echo "[ship] no .app in dist/"; exit 1; }
[ -x "$APP/Contents/Resources/helpers/miyagi-listen" ] || { echo "[ship] miyagi-listen isn't inside $APP (extraResources helpers?)"; exit 1; }
[ -f "$APP/Contents/Resources/engine/install.sh" ] || { echo "[ship] the engine isn't inside $APP (extraResources?)"; exit 1; }

echo "[ship] 3/5 ad-hoc sign $APP"
# electron-builder renames the helper apps ("miyagi Helper (Renderer)") but leaves CFBundleName "Electron Helper …",
# which crash reports and some process lists show. Match it to the display name before signing, so nothing says Electron.
for helper in "$APP"/Contents/Frameworks/*Helper*.app; do
  plist="$helper/Contents/Info.plist"
  [ -f "$plist" ] || continue
  shown="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleDisplayName' "$plist" 2>/dev/null || basename "$helper" .app)"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName $shown" "$plist"
done
# Before the dmg: the image carries the signed app. No Developer ID yet (SHIP.md, Known gaps).
codesign --force --deep -s - "$APP"
codesign --verify --deep --strict "$APP"

echo "[ship] 4/5 dmg ($FORMAT)"
# electron-builder lays the image out (art, icon positions, Applications link: electron-builder.yml `dmg`) as ULFO,
# the strongest format it accepts. hdiutil then recompresses the same image, layout included, to lzma.
npx electron-builder --mac dmg "$ARCH" --prepackaged "$APP" --publish never "-c.dmg.artifactName=$NAME.\${ext}"
[ -f "$DMG" ] || { echo "[ship] electron-builder made no $DMG"; exit 1; }
if [ "$FORMAT" != ULFO ]; then
  hdiutil convert "$DMG" -format "$FORMAT" -o "$DMG.$FORMAT.dmg" -quiet
  mv -f "$DMG.$FORMAT.dmg" "$DMG"
fi
hdiutil verify "$DMG" -quiet
ls -lh "$DMG"

if [ "$ZIP" = 1 ]; then
  echo "[ship] 5/5 zip"
  ditto -c -k --keepParent "$APP" "$ZIPFILE"
  ls -lh "$ZIPFILE"
else
  echo "[ship] 5/5 zip skipped (--zip makes $ZIPFILE too)"
fi
echo "[ship] app on disk: $(du -sh "$APP" | cut -f1), engine inside: $(cat "$APP/Contents/Resources/engine/VERSION")"

if [ "$PUBLISH" = 1 ]; then
  echo "[ship] uploading to $REPO release 'mac'"
  gh release upload mac "$DMG" --clobber --repo "$REPO"
  if [ "$ARCH" = "--x64" ]; then
    # The release's title, notes and Miyagi-Mac.zip belong to the Apple silicon build: an Intel upload leaves them alone.
    echo "[ship] uploaded $NAME.dmg only. The update card offers it to Intel Macs once OFFICIAL_ASSETS.mac lists it (manifest.ts)."
  else
    if [ -f "$ZIPFILE" ]; then
      gh release upload mac "$ZIPFILE" --clobber --repo "$REPO"
    else
      echo "[ship] note: no zip uploaded, so install.sh --app (it downloads Miyagi-Mac.zip) keeps the old build. Add --zip to refresh it."
    fi
    # The in-app update card reads the version from the release title ("miyagi 0.2.0"), then a "Version:" line, and
    # shows the notes' plain lines as "What's new" (manifest.ts). Without them it finds no version and offers nothing.
    VERSION="$(node -p "require('./package.json').version")"
    SHA="$(shasum -a 256 "$DMG" | cut -d' ' -f1)"
    NOTES=(rolling --version "$VERSION" --sha256 "$SHA" --unsigned)
    [ -f RELEASE-NOTES.txt ] && NOTES+=(--notes RELEASE-NOTES.txt)
    node ../.github/scripts/release-notes.mjs "${NOTES[@]}" > dist/ROLLING.md
    TITLE="$(node ../.github/scripts/release-notes.mjs title --version "$VERSION" --unsigned)"
    gh release edit mac --title "$TITLE" --notes-file dist/ROLLING.md --repo "$REPO"
    echo "[ship] release 'mac' is now \"$TITLE\". The update card offers it only to apps older than $VERSION: bump version in package.json for every build you publish."
  fi
fi
echo "[ship] done. Test it (SHIP.md, 'Test before you publish') before anyone downloads it."
