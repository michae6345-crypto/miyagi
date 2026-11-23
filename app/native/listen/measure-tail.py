#!/usr/bin/env python3
"""Replays release-tail policies on timed transcripts from tests/tailmeasure (see measure-tail.sh).

Each run has the recognizer's text changes timed against release (ms; negative = while the keys were held), the time its
finish() returned (finishMs) and the final text. A policy picks when the words go; the words sent are the final if it
came by then, else the text at that moment (Tail.pick). Word loss = words of the final missing from what was sent
(edit distance, case and punctuation ignored; "dropped" counts only words short). tail_swift mirrors Tail.swift: keep
the two in step.
Usage: measure-tail.py runs.jsonl"""
import json, re, sys

MAX_MS, CEILING_MS = 1000, 1500  # Tail.maxMs, Tail.ceilingMs


def cap_ms(queued_ms):
    """Tail.capMs: the warm cap, plus a quarter of the audio that was queued and flushed at once, at most the ceiling."""
    return min(CEILING_MS, MAX_MS + queued_ms // 4)


def words(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("-", " ")).split()


def dist(a, b):
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, y in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (x != y))
    return d[-1]


def text_at(run, t):
    txt = ""
    for ms, s in run["events"]:
        if ms <= t:
            txt = s
    return txt


def fixed(T):
    def pick(run):
        if run["finishMs"] <= T:
            return run["finishMs"], run["final"]
        return T, text_at(run, T)
    return pick


def settled(min_ms, settle_ms):
    """Rejected: the final; else from min_ms on, once the text moved during the tail and then held still settle_ms; else
    the cap. Checked every 25 ms."""
    def pick(run):
        cap = cap_ms(run["audioMs"] if run["mode"] == "cold" else 0)
        t = 0
        while True:
            if run["finishMs"] <= t:
                return run["finishMs"], run["final"]
            changes = [ms for ms, _ in run["events"] if 0 <= ms <= t]
            last = changes[-1] if changes else None
            if t >= cap or (t >= min_ms and last is not None and t - last >= settle_ms):
                return t, text_at(run, t)
            t += 25
    return pick


def tail_swift(run):
    """Tail.swift: the final the moment it comes; else the best text at the cap (1000 ms, plus a quarter of the audio
    queued during a cold start and flushed at once, at most 1500 ms)."""
    cap = cap_ms(run["audioMs"] if run["mode"] == "cold" else 0)
    if run["finishMs"] <= cap:
        return run["finishMs"], run["final"]
    return cap, text_at(run, cap)


def loss(run, sent):
    return dist(words(run["final"]), words(sent))


def slowed(run, k):
    """The same run on a Mac k times slower after release (a busy machine, a model still loading): every text change
    and the final after release come k times later. A sensitivity check; nothing is run under load."""
    return {**run, "finishMs": int(run["finishMs"] * k), "events": [[ms * k if ms >= 0 else ms, s] for ms, s in run["events"]]}


def main():
    runs = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
    groups = {}
    for r in runs:
        groups.setdefault(f'{r["mode"]} pad {r["padMs"]} ms', []).append(r)
    policies = [("flat 300 ms (first cut)", fixed(300)), ("300 ms, then settled 150 ms", settled(300, 150)),
                ("300 ms, then settled 300 ms", settled(300, 300)), ("flat 1500 ms (before Nov 22)", fixed(1500)),
                ("final, else cap (Tail.swift)", tail_swift)]
    for g, rs in list(groups.items()):
        if g.startswith("warm pad 0") or g.startswith("cold"):
            for k in (3, 5, 8, 10):
                groups[f"{g}, {k}x slower after release"] = [slowed(r, k) for r in rs]
    for g, rs in groups.items():
        fin = sorted(r["finishMs"] for r in rs)
        post = [[ms for ms, _ in r["events"] if ms >= 0] for r in rs]
        gap = max(max([b - a for a, b in zip(p, p[1:])] or [0]) for p in post)
        held = sum(1 for r in rs if words(text_at(r, -1)) != words(r["final"]))
        print(f"\n== {g}: {len(rs)} clips, finish() after release: median {fin[len(fin)//2]} ms, max {fin[-1]} ms; "
              f"text incomplete at release in {held}/{len(rs)}; longest still gap between changes after release {gap} ms ==")
        for name, pol in policies:
            lost, dropped, clips, waits = 0, 0, 0, []
            for r in rs:
                at, sent = pol(r)
                e = loss(r, sent)
                lost += e; clips += e > 0; waits.append(at)
                dropped += max(0, len(words(r["final"])) - len(words(sent)))
            waits.sort()
            nw = sum(len(words(r["final"])) for r in rs)
            print(f"  {name:30} words lost {lost:3}/{nw} ({dropped:3} dropped) in {clips:2} clips; "
                  f"wait median {waits[len(waits)//2]} ms, max {waits[-1]} ms")


main()
