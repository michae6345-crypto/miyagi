#!/usr/bin/env bash
# Pure unit tests for the release tail (Tail.swift). Compiles Tail.swift with tests/tail/main.swift only: no mic, no key
# tap, no Speech, no permissions, nothing on screen. Mac only.
set -euo pipefail
[ "$(uname)" = "Darwin" ] || { echo "[listen] not a Mac: skipping"; exit 0; }
cd "$(dirname "$0")"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
xcrun swiftc -swift-version 5 Tail.swift tests/tail/main.swift -o "$TMP/tail-tests"
"$TMP/tail-tests"
