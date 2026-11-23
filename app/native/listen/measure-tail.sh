#!/usr/bin/env bash
# Offline word-loss measurement for the release tail (Tail.swift). No mic, no key tap, no prompts, nothing on screen,
# nothing played aloud: `say -o` writes each phrase to a file, the real Transcriber (SpeechAnalyzer, macOS 26) reads
# it (tests/tailmeasure), and measure-tail.py replays tail policies on the timed text. Mac only.
#   native/listen/measure-tail.sh [voices...]     default voices: Samantha Daniel Fred
#   MIYAGI_TAIL_KEEP=runs.jsonl native/listen/measure-tail.sh    also keep the timed runs
set -euo pipefail
[ "$(uname)" = "Darwin" ] || { echo "[listen] not a Mac: skipping"; exit 0; }
cd "$(dirname "$0")"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
xcrun swiftc -O -swift-version 5 -target "$(uname -m)-apple-macos13.0" Transcriber.swift Tail.swift tests/tailmeasure/main.swift \
  -framework Speech -framework AVFoundation -o "$TMP/tail-measure"
VOICES=("$@"); [ "${#VOICES[@]}" -gt 0 ] || VOICES=(Samantha Daniel Fred)
files=()
n=0
for v in "${VOICES[@]}"; do
  while IFS=$'\t' read -r phrase _; do
    [ -n "$phrase" ] || continue
    n=$((n+1)); f="$TMP/clip-$n.aiff"
    say -v "$v" -o "$f" "$phrase" 2>/dev/null || continue
    files+=("$f")
  done < <(cat phrases.tsv tests/tailmeasure/long.tsv)
done
: > "$TMP/runs.jsonl"
for pad in 0 200; do "$TMP/tail-measure" warm "$pad" "${files[@]}" >> "$TMP/runs.jsonl"; done
"$TMP/tail-measure" cold 0 "${files[@]}" >> "$TMP/runs.jsonl"
[ -z "${MIYAGI_TAIL_KEEP:-}" ] || cp "$TMP/runs.jsonl" "$MIYAGI_TAIL_KEEP"   # keep the timed runs to replay more policies
python3 -I measure-tail.py "$TMP/runs.jsonl"
