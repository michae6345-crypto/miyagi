#!/usr/bin/env bash
# Offline self-test for miyagi-listen. No mic, no key tap, no permission prompts, no network.
#   1. builds the helper
#   2. speaks each line of phrases.tsv to a file with `say -o` (silent), transcribes it with and without --terms,
#      prints word accuracy (1 - word error rate, case and punctuation ignored)
#   3. runs the stdin-only protocol tests (test-protocol.py)
# Usage: native/listen/test.sh [--protocol-only] [--accuracy-only]
set -euo pipefail
cd "$(dirname "$0")"
./build.sh
BIN="$PWD/../../build/helpers/miyagi-listen"
WORK="${TMPDIR:-/tmp}/miyagi-listen-test"; mkdir -p "$WORK"

if [ "${1:-}" != "--protocol-only" ]; then
  echo "== accuracy (SpeechAnalyzer, files from say -o) =="
  : > "$WORK/results.tsv"
  n=0
  while IFS=$'\t' read -r phrase terms; do
    [ -n "$phrase" ] || continue
    n=$((n+1))
    f="$WORK/ptt-$n.aiff"
    say -o "$f" "$phrase"
    plain="$("$BIN" --transcribe-file "$f")"
    withterms="$("$BIN" --transcribe-file "$f" --terms "$terms")"
    speechterms="$("$BIN" --transcribe-file "$f" --terms "$terms" --module speech)"
    printf '%s\t%s\t%s\t%s\n' "$phrase" "$plain" "$withterms" "$speechterms" >> "$WORK/results.tsv"
  done < phrases.tsv
  python3 -I - "$WORK/results.tsv" <<'PY'
import json, re, sys
def words(s): return re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("-", " ")).split()
def dist(a, b):
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (x != y))
    return d[-1]
tot = {"no terms": [0, 0], "terms (auto)": [0, 0], "terms, SpeechTranscriber only": [0, 0]}
for line in open(sys.argv[1]):
    ref, a, b, c = line.rstrip("\n").split("\t")
    r = words(ref)
    row = [ref]
    for key, raw in (("no terms", a), ("terms (auto)", b), ("terms, SpeechTranscriber only", c)):
        txt = json.loads(raw).get("text", "") if raw.startswith("{") else ""
        h = words(txt); e = dist(r, h)
        tot[key][0] += e; tot[key][1] += len(r)
        row.append(f"{txt!r} ({max(len(r)-e,0)}/{len(r)})")
    print(" | ".join(row))
for k, (e, n) in tot.items():
    print(f"word accuracy {k:30}: {100*(1-e/n):.1f}%  ({e} errors / {n} words)")
PY
fi

if [ "${1:-}" != "--accuracy-only" ]; then
  echo "== protocol (--stdin-only) =="
  python3 -I test-protocol.py "$BIN"
fi

if [ "${1:-}" != "--accuracy-only" ]; then
  # --screens only reads NSScreen (no permissions, no prompts, no tap, no mic).
  echo "== screens (--screens) =="
  "$BIN" --screens | python3 -I -c '
import json, sys
s = json.loads(sys.stdin.readline())["screens"]
assert isinstance(s, list) and s, "no screens"
def rect(r): return all(isinstance(r[k], (int, float)) for k in ("x", "y", "w", "h"))
for e in s:
    assert isinstance(e["id"], int), "id"
    assert rect(e["frame"]) and rect(e["visible"]), "rects"
    assert isinstance(e["safeTop"], (int, float)) and e["safeTop"] >= 0, "safeTop"
    for k in ("auxLeft", "auxRight"):
        assert e[k] is None or isinstance(e[k], (int, float)), k
    assert isinstance(e["scale"], (int, float)) and e["scale"] > 0, "scale"
    assert isinstance(e["builtin"], bool), "builtin"
print("screens ok:", len(s), "display(s)")
'
fi
