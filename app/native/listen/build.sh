#!/usr/bin/env bash
# Build miyagi-listen (the push-to-talk helper) into app/build/helpers/miyagi-listen and ad-hoc sign it.
# Command Line Tools only: `xcrun swiftc`, no Xcode, no packages. Universal (arm64 + x86_64) when both link; if x86_64
# fails (e.g. SpeechAnalyzer linking) it says so and ships arm64 only. Mac only: elsewhere it exits 0 and does nothing.
#
#   native/listen/build.sh            # incremental: skips when the binary is newer than every source
#   native/listen/build.sh --force
#   MIYAGI_LISTEN_ARCHS="arm64" native/listen/build.sh   # force a subset
set -euo pipefail
[ "$(uname)" = "Darwin" ] || { echo "[listen] not a Mac: skipping miyagi-listen"; exit 0; }
cd "$(dirname "$0")"
OUT="../../build/helpers"
BIN="$OUT/miyagi-listen"
SRC=(main.swift Session.swift KeyTap.swift Mic.swift Transcriber.swift Permissions.swift Screens.swift Windows.swift CaptureMath.swift Capture.swift)
ARCHS="${MIYAGI_LISTEN_ARCHS:-arm64 x86_64}"

if [ "${1:-}" != "--force" ] && [ -f "$BIN" ]; then
  newer="$(find "${SRC[@]}" Info.plist build.sh -newer "$BIN" 2>/dev/null | head -1)"
  if [ -z "$newer" ]; then echo "[listen] $BIN is up to date"; exit 0; fi
fi

mkdir -p "$OUT"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
built=()
for arch in $ARCHS; do
  echo "[listen] swiftc $arch"
  if xcrun swiftc -O -swift-version 5 -target "$arch-apple-macos13.0" "${SRC[@]}" -o "$TMP/miyagi-listen-$arch" \
       -framework Speech -framework AVFoundation -framework CoreGraphics -framework CoreMedia -framework AppKit \
       -framework ScreenCaptureKit -framework ImageIO \
       -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker Info.plist 2> "$TMP/err-$arch"; then
    built+=("$TMP/miyagi-listen-$arch")
  else
    echo "[listen] $arch failed:"; cat "$TMP/err-$arch"
    [ "$arch" = arm64 ] && exit 1
    echo "[listen] continuing without $arch"
  fi
done
[ "${#built[@]}" -gt 0 ] || { echo "[listen] nothing built"; exit 1; }
if [ "${#built[@]}" -gt 1 ]; then lipo -create "${built[@]}" -output "$BIN"; else cp "${built[0]}" "$BIN"; fi
chmod +x "$BIN"
codesign -s - --force --identifier dev.sandhacks.miyagi.listen "$BIN"
echo "[listen] built $BIN: $(lipo -archs "$BIN")"
