#!/usr/bin/env bash
# The "mac" release's notes, as ship-mac.sh --publish writes them (gh release edit mac --notes-file).
# Prints to stdout; changes nothing. The update card reads the same release (features/updates/manifest.ts readRelease):
# the version from the title ("miyagi <version>") or the Version line, the plain lines as notes.
#
#   bash scripts/release-notes.sh <version> <build sha>
set -euo pipefail
VERSION="${1:?version, e.g. 0.1.1}"
BUILD="${2:?build sha, e.g. 1d453ca0}"
case "$VERSION" in *[!0-9A-Za-z.-]*) echo "[notes] bad version: $VERSION" >&2; exit 1 ;; esac
case "$BUILD" in *[!0-9a-f]*) echo "[notes] bad build sha: $BUILD" >&2; exit 1 ;; esac

cat <<EOF
Open the DMG and drag miyagi to Applications.
If macOS stops it: System Settings, Privacy & Security, Open Anyway.
No setup needed. The engine is inside the app.

Version: $VERSION
Build $BUILD
EOF
