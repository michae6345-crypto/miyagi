#!/usr/bin/env bash
# Developer ID signing and notarization for the Mac build. ship-mac.sh calls it only when MIYAGI_DEVID is set;
# without it the build stays ad hoc (or MIYAGI_SIGN_ID), exactly as before. SHIP.md, "Signed release".
#
#   scripts/sign-mac.sh order    <app>          # print the inside-out signing order (no codesign; used by the test)
#   scripts/sign-mac.sh app      <app>          # sign every Mach-O and bundle inside-out, then the app (hardened runtime)
#   scripts/sign-mac.sh dmg      <dmg>          # sign the disk image
#   scripts/sign-mac.sh notarize <dmg> [<app>]  # submit, wait, staple the dmg (and the app), verify; fails on rejection
#   scripts/sign-mac.sh has-notary              # exit 0 when notary credentials are set
#
# Env:
#   MIYAGI_DEVID             "Developer ID Application: Name (TEAMID)" (security find-identity -v -p codesigning)
#   MIYAGI_NOTARY_PROFILE    a notarytool keychain profile (xcrun notarytool store-credentials <name> ...), or
#   APPLE_API_KEY            path to the App Store Connect API key (AuthKey_XXXX.p8), with
#   APPLE_API_KEY_ID         its key id and
#   APPLE_API_ISSUER         its issuer id (the same names electron-builder uses)
#   MIYAGI_ENTITLEMENTS      entitlements plist (default build/entitlements.mac.plist)
set -euo pipefail
cd "$(dirname "$0")/.."

ENTITLEMENTS="${MIYAGI_ENTITLEMENTS:-build/entitlements.mac.plist}"
say() { echo "[sign] $*"; }
die() { echo "[sign] ERROR: $*" >&2; exit 1; }

# First four bytes of a Mach-O: thin 32/64-bit in either byte order, or a fat (universal) binary. `od` rather than
# `file` so the order can be checked on Linux CI too. cafebabe is also a Java class file; the app ships none.
is_macho() {
  local magic
  magic="$(od -An -tx1 -N4 "$1" 2>/dev/null | tr -d ' \n')"
  case "$magic" in feedface|feedfacf|cefaedfe|cffaedfe|cafebabe|bebafeca) return 0 ;; *) return 1 ;; esac
}

# Everything to sign before the app itself, deepest path first: loose Mach-O files (Python's .so/.dylib and
# bin/python3.12, miyagi-listen, Electron's dylibs and crashpad handler), then the bundles that hold them
# (Electron Framework.framework, the helper .apps). A file inside a bundle is always deeper than the bundle, so each
# bundle is sealed after its contents. Symlinks are skipped (Versions/Current, python3 -> python3.12, the framework's
# top-level links): codesign signs what they point to.
order() {
  local app="${1%/}" f
  [ -d "$app" ] || die "no app at $app"
  {
    while IFS= read -r -d '' f; do
      is_macho "$f" && printf '%s\n' "$f"
    done < <(find "$app/Contents" -type f -print0)
    find "$app/Contents" -type d \( -name '*.app' -o -name '*.framework' -o -name '*.appex' -o -name '*.xpc' \) -print
  } | awk -F/ '{ print NF "\t" $0 }' | sort -t$'\t' -k1,1nr -k2,2 | cut -f2-
  printf '%s\n' "$app"
}

need_id() {
  [ -n "${MIYAGI_DEVID:-}" ] || die "MIYAGI_DEVID is not set"
  [ -f "$ENTITLEMENTS" ] || die "no entitlements at $ENTITLEMENTS"
  grep -qF "\"$MIYAGI_DEVID\"" <<<"$(security find-identity -v -p codesigning)" \
    || die "\"$MIYAGI_DEVID\" isn't a valid signing identity in the keychain (security find-identity -v -p codesigning)"
}

sign_one() {
  local extra=()
  # miyagi-listen keeps the identifier native/listen/build.sh gave it (TCC remembers the mic grant by it).
  case "$1" in */helpers/miyagi-listen) extra=(--identifier dev.sandhacks.miyagi.listen) ;; esac
  codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" "${extra[@]+"${extra[@]}"}" \
    -s "$MIYAGI_DEVID" "$1"
}

sign_app() {
  local app="${1%/}" n=0 p
  need_id
  say "signing $app inside-out as $MIYAGI_DEVID"
  while IFS= read -r p; do
    sign_one "$p" || die "codesign failed on $p"
    n=$((n + 1))
  done < <(order "$app")
  say "signed $n items"
  codesign --verify --deep --strict --verbose=2 "$app"
  # Hardened runtime on the main binary (flags=0x10000(runtime)), or notarization rejects it.
  # Capture first: with pipefail, `codesign | grep -q` fails when grep exits early and codesign gets SIGPIPE.
  local info; info=$(codesign -dv "$app" 2>&1 || true)
  grep -q 'flags=.*runtime' <<<"$info" || die "$app isn't signed with the hardened runtime"
}

sign_dmg() {
  need_id
  codesign --force --timestamp -s "$MIYAGI_DEVID" "$1"
  codesign --verify --strict "$1"
}

has_notary() {
  [ -n "${MIYAGI_NOTARY_PROFILE:-}" ] && return 0
  [ -n "${APPLE_API_KEY:-}" ] && [ -n "${APPLE_API_KEY_ID:-}" ] && [ -n "${APPLE_API_ISSUER:-}" ]
}

notary_auth() {
  if [ -n "${MIYAGI_NOTARY_PROFILE:-}" ]; then
    NOTARY_AUTH=(--keychain-profile "$MIYAGI_NOTARY_PROFILE")
  elif has_notary; then
    [ -f "$APPLE_API_KEY" ] || die "APPLE_API_KEY=$APPLE_API_KEY: no such file (it's the path to AuthKey_XXXX.p8)"
    NOTARY_AUTH=(--key "$APPLE_API_KEY" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER")
  else
    die "no notary credentials: set MIYAGI_NOTARY_PROFILE, or APPLE_API_KEY + APPLE_API_KEY_ID + APPLE_API_ISSUER"
  fi
}

json_field() { node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(String(JSON.parse(s)[process.argv[1]]??""))}catch{}})' "$1"; }

notarize() {
  local dmg="$1" app="${2:-}" out id status
  [ -f "$dmg" ] || die "no file at $dmg"
  notary_auth
  say "notarizing $dmg (uploads to Apple, usually 2-15 minutes)"
  out="$(xcrun notarytool submit "$dmg" "${NOTARY_AUTH[@]}" --wait --output-format json)" || true
  id="$(printf '%s' "$out" | json_field id)"
  status="$(printf '%s' "$out" | json_field status)"
  say "submission ${id:-?}: ${status:-no status}"
  if [ "$status" != "Accepted" ]; then
    echo "$out" >&2
    if [ -n "$id" ]; then
      echo "[sign] ---- notarytool log $id ----" >&2
      xcrun notarytool log "$id" "${NOTARY_AUTH[@]}" >&2 || true
    fi
    die "notarization ${status:-failed} for $dmg. Nothing was published."
  fi
  xcrun stapler staple "$dmg"
  xcrun stapler validate "$dmg"
  # The dmg's ticket also covers the app inside it, so the app can carry its own ticket (for the --zip download).
  if [ -n "$app" ]; then
    xcrun stapler staple "$app" || say "WARNING: couldn't staple $app (the dmg is stapled; a zip of this app would need Gatekeeper's online check)"
    codesign --verify --deep --strict "$app"
  fi
  spctl -a -vvv -t install "$dmg"
  [ -z "$app" ] || spctl -a -vvv -t exec "$app"
  say "notarized and stapled: $dmg"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  order) order "${1:?app path}" ;;
  app) sign_app "${1:?app path}" ;;
  dmg) sign_dmg "${1:?dmg path}" ;;
  notarize) notarize "${1:?dmg path}" "${2:-}" ;;
  has-notary) has_notary ;;
  *) sed -n '2,/^set -euo/p' "$0" | sed '$d'; exit 1 ;;
esac
