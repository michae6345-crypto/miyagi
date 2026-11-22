#!/usr/bin/env bash
# Build one release of the Mac app for one arch: the dmg, the update zip, its blockmap and latest-mac.yml, signed with a
# Developer ID and notarized when an identity is given, else ad hoc ("unsigned"). The release workflow
# (.github/workflows/release.yml) runs it once per arch; it also runs on a Mac by hand (RELEASING.md). Run from app/:
#
#   bash scripts/release-mac.sh --arch arm64            # ad hoc → dist/release/
#   bash scripts/release-mac.sh --arch x64              # Intel (needs an Intel Mac or Rosetta for the Python precompile)
#   MIYAGI_SIGN_IDENTITY="Developer ID Application: Name (TEAMID)" APPLE_ID=… APPLE_APP_SPECIFIC_PASSWORD=… \
#     APPLE_TEAM_ID=… bash scripts/release-mac.sh --arch arm64   # Developer ID + hardened runtime + notarized + stapled
#
# Same steps as ship-mac.sh (engine bundle, push-to-talk helper, app, dmg recompressed to ULMO), with three differences:
#   - the helper plists are fixed in an afterPack hook (scripts/release-after-pack.cjs), so a real signature covers them;
#   - with MIYAGI_SIGN_IDENTITY, electron-builder signs (hardened runtime, build/entitlements.mac.plist) and notarizes
#     and staples the app; this script then signs, notarizes and staples the dmg. Without it: ad hoc, like ship-mac.sh;
#   - electron-builder also makes the update zip and latest-mac.yml (electron-updater's feed; the app itself still reads
#     the GitHub release, src/main/features/updates.ts).
# Names: arm64 keeps Miyagi-Mac.dmg (what the site and the in-app update card link to); x64 is Miyagi-Mac-x64.dmg. Zips
# carry the arch (Miyagi-Mac-arm64.zip, Miyagi-Mac-x64.zip): electron-updater picks the file by "arm64" in its name.
#
# Env: MIYAGI_ENGINE_REF (default origin/integration/live), MIYAGI_DMG_FORMAT (ULMO), MIYAGI_UPDATE_FEED_URL (the
#      generic feed URL electron-builder records; latest-mac.yml itself only names files), MIYAGI_RELEASE_OUT
#      (dist/release). Writes dist/release/<files> and dist/release/build-<arch>.json (what was built and how).
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(uname)" = "Darwin" ] || { echo "[release] run this on a Mac (codesign, hdiutil, notarytool)"; exit 1; }

ARCH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --arch) ARCH="${2:-}"; shift 2 ;;
    --arch=*) ARCH="${1#--arch=}"; shift ;;
    *) echo "[release] unknown option: $1"; exit 1 ;;
  esac
done
case "$ARCH" in arm64|x64) ;; *) echo "[release] --arch arm64 or --arch x64"; exit 1 ;; esac

FORMAT="${MIYAGI_DMG_FORMAT:-ULMO}"
case "$FORMAT" in ULMO|ULFO|UDZO) ;; *) echo "[release] MIYAGI_DMG_FORMAT=$FORMAT: use ULMO, ULFO or UDZO"; exit 1 ;; esac
OUT="${MIYAGI_RELEASE_OUT:-dist/release}"
FEED="${MIYAGI_UPDATE_FEED_URL:-https://github.com/adrian-erlikhman/miyagi/releases/latest/download}"
VERSION="$(node -p "require('./package.json').version")"
if [ "$ARCH" = arm64 ]; then DMG_NAME="Miyagi-Mac.dmg"; else DMG_NAME="Miyagi-Mac-$ARCH.dmg"; fi

IDENTITY="${MIYAGI_SIGN_IDENTITY:-}"
SIGNED=0
if [ -n "$IDENTITY" ]; then
  SIGNED=1
  for v in APPLE_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_TEAM_ID; do
    [ -n "${!v:-}" ] || { echo "[release] MIYAGI_SIGN_IDENTITY is set but $v isn't: a signed build must be notarized"; exit 1; }
  done
  # electron-builder wants the name without the "Developer ID Application: " prefix (it refuses the prefix).
  QUALIFIER="${IDENTITY#Developer ID Application: }"
else
  # Never pick up a certificate from the build machine's keychain by accident.
  export CSC_IDENTITY_AUTO_DISCOVERY=false
fi
echo "[release] miyagi $VERSION $ARCH, $([ $SIGNED = 1 ] && echo "Developer ID ($QUALIFIER)" || echo "ad hoc (unsigned)")"

echo "[release] 1/6 engine → build/engine (Python $ARCH)"
MIYAGI_PY_ARCH="$ARCH" node scripts/bundle-engine.mjs

echo "[release] 2/6 push-to-talk helper → build/helpers/miyagi-listen"
bash native/listen/build.sh --force

echo "[release] 3/6 app"
# Stale files from an earlier run would pass the checks below.
rm -rf dist/mac dist/mac-* dist/Miyagi-Mac* dist/latest-mac.yml "$OUT"
mkdir -p "$OUT"
npx electron-vite build
PACK=(--mac --dir "--$ARCH" --publish never "-c.afterPack=scripts/release-after-pack.cjs")
if [ $SIGNED = 1 ]; then
  # Signs every nested binary (bundled Python included) with hardened runtime, then notarizes and staples the .app
  # (@electron/notarize reads APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID).
  PACK+=("-c.forceCodeSigning=true" "-c.mac.identity=$QUALIFIER" "-c.mac.hardenedRuntime=true"
         "-c.mac.entitlements=build/entitlements.mac.plist" "-c.mac.entitlementsInherit=build/entitlements.mac.plist")
fi
npx electron-builder "${PACK[@]}"

APP="$(find dist -maxdepth 2 -name '*.app' -type d -not -path "$OUT/*" | head -1)"
[ -n "$APP" ] || { echo "[release] no .app in dist/"; exit 1; }
[ -x "$APP/Contents/Resources/helpers/miyagi-listen" ] || { echo "[release] miyagi-listen isn't inside $APP"; exit 1; }
[ -f "$APP/Contents/Resources/engine/VERSION" ] || { echo "[release] the engine isn't inside $APP (extraResources?)"; exit 1; }
[ -d "$APP/Contents/Resources/engine/python" ] || { echo "[release] the bundled Python isn't inside $APP"; exit 1; }

echo "[release] 4/6 check the signature"
if [ $SIGNED = 1 ]; then
  codesign --verify --deep --strict --verbose=2 "$APP"
  codesign -dv --verbose=2 "$APP" 2>&1 | grep -E '^(Authority|TeamIdentifier|Runtime|Timestamp)' || true
  xcrun stapler validate "$APP"
  spctl --assess --type execute -vv "$APP"
else
  # Ad hoc, exactly as ship-mac.sh (resetAdHocDarwinSignature already re-sealed it after the fuses; this seals the
  # whole bundle again, nested helpers included, the same way the builds people use today are sealed).
  codesign --force --deep -s - "$APP"
  codesign --verify --deep --strict "$APP"
fi

echo "[release] 5/6 dmg + update zip + latest-mac.yml"
# --prepackaged: package the app checked above as is (no re-pack, no re-sign). The generic publish config only makes
# electron-builder write latest-mac.yml and the zip blockmap; --publish never uploads nothing.
TARGETS=(--mac dmg zip "--$ARCH" --prepackaged "$APP" --publish never
         "-c.publish.provider=generic" "-c.publish.url=$FEED"
         "-c.mac.artifactName=Miyagi-Mac-\${arch}.\${ext}" "-c.dmg.artifactName=${DMG_NAME%.dmg}.\${ext}")
npx electron-builder "${TARGETS[@]}"
DMG="dist/$DMG_NAME"
ZIP="dist/Miyagi-Mac-$ARCH.zip"
for f in "$DMG" "$ZIP" "$ZIP.blockmap" dist/latest-mac.yml; do
  [ -f "$f" ] || { echo "[release] electron-builder made no $f"; exit 1; }
done
if [ "$FORMAT" != ULFO ]; then
  hdiutil convert "$DMG" -format "$FORMAT" -o "$DMG.$FORMAT.dmg" -quiet
  mv -f "$DMG.$FORMAT.dmg" "$DMG"
fi
hdiutil verify "$DMG" -quiet

if [ $SIGNED = 1 ]; then
  echo "[release] 6/6 sign, notarize and staple the dmg"
  codesign --force --sign "$IDENTITY" --timestamp "$DMG"
  xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --password "$APPLE_APP_SPECIFIC_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" --wait --timeout 60m
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
  spctl --assess --type open --context context:primary-signature -vv "$DMG"
else
  echo "[release] 6/6 dmg not signed (ad hoc build): first open needs Privacy & Security › Open Anyway"
fi

mv "$DMG" "$ZIP" "$ZIP.blockmap" "$OUT/"
mv dist/latest-mac.yml "$OUT/latest-mac-$ARCH.yml"
ENGINE="$(cat "$APP/Contents/Resources/engine/VERSION")"
node -e '
  const [out, arch, version, signed, engine, dmg] = process.argv.slice(1)
  require("node:fs").writeFileSync(`${out}/build-${arch}.json`, JSON.stringify({ version, arch, signed: signed === "1", engine, dmg }, null, 2) + "\n")
' "$OUT" "$ARCH" "$VERSION" "$SIGNED" "$ENGINE" "$DMG_NAME"
( cd "$OUT" && shasum -a 256 "$DMG_NAME" "Miyagi-Mac-$ARCH.zip" "Miyagi-Mac-$ARCH.zip.blockmap" > "SHA256SUMS-$ARCH.txt" )
ls -lh "$OUT"
echo "[release] done: miyagi $VERSION $ARCH, engine $ENGINE, $([ $SIGNED = 1 ] && echo signed + notarized || echo unsigned)"
