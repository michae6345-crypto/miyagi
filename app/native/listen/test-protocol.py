#!/usr/bin/env python3
"""Protocol tests for miyagi-listen --stdin-only. No key tap, no mic, no prompts.
Drives sessions with the hidden {"cmd":"_simulate"} command. Usage: test-protocol.py <path to miyagi-listen>"""
import json, os, subprocess, sys, threading, time

BIN = sys.argv[1]
failures = []


class Helper:
    def __init__(self):
        self.p = subprocess.Popen([BIN, "--stdin-only"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.events = []
        self.t0 = time.time()
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                failures.append(f"non-JSON line: {line!r}")
                continue
            with self.lock:
                self.events.append((time.time() - self.t0, ev))

    def send(self, **cmd):
        self.p.stdin.write(json.dumps(cmd) + "\n")
        self.p.stdin.flush()

    def sim(self, state, **kw):
        self.send(cmd="_simulate", state=state, **kw)

    def mark(self):
        with self.lock:
            return len(self.events)

    def since(self, mark):
        with self.lock:
            return [e for _, e in self.events[mark:]]

    def timed_since(self, mark):
        with self.lock:
            return list(self.events[mark:])

    def wait(self, pred, timeout=6.0, mark=0):
        end = time.time() + timeout
        while time.time() < end:
            if pred(self.since(mark)):
                return True
            time.sleep(0.02)
        return False

    def close(self):
        self.p.stdin.close()
        try:
            self.p.wait(timeout=3)
            return True
        except subprocess.TimeoutExpired:
            self.p.kill()
            return False


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


def types(evs):
    return [(e["type"], e.get("state") or e.get("reason") or "") for e in evs]


def term(evs, sid):
    return [e for e in evs if e.get("id") == sid and e["type"] in ("final", "cancelled")]


def fresh(**cfg):
    h = Helper()
    h.send(cmd="config", enabled=True, chord="fn+control", minHoldMs=250, **cfg)
    assert h.wait(lambda e: any(x["type"] == "ready" for x in e)), "no ready event"
    assert h.wait(lambda e: any(x["type"] == "perm" for x in e)), "no perm event"
    return h


# --- startup ---------------------------------------------------------------------------------------------------
h = fresh()
ready = next(e for e in h.since(0) if e["type"] == "ready")
perm = next(e for e in h.since(0) if e["type"] == "perm")
check("ready has stt/locale/chord", ready["stt"] in ("speechanalyzer", "sfspeech", "none") and ready["locale"] == "en-US"
      and ready["chord"] == "fn+control", str(ready))
check("perm has mic/input/assets", set(perm) >= {"mic", "input", "assets"}, str(perm))

# --- repeated config must not make the helper repeat `ready` (the app answers ready with config: a loop otherwise) ------------
m = h.mark()
for _ in range(3):
    h.send(cmd="config", enabled=True, chord="fn+control", minHoldMs=250, maxHoldMs=60000, locale="en-US")
time.sleep(1.0)
check("same config again does not emit ready again", not any(e["type"] == "ready" for e in h.since(m)), str(h.since(m)))

# --- short hold -> cancelled short ---------------------------------------------------------------------------
m = h.mark()
h.sim("down"); time.sleep(0.08); h.sim("up")
h.wait(lambda e: any(x["type"] == "cancelled" for x in e), mark=m)
ev = h.since(m)
check("short hold: down, up, cancelled short, same id, no listening",
      types(ev) == [("ptt", "down"), ("ptt", "up"), ("cancelled", "short")] and len({e["id"] for e in ev}) == 1, str(ev))

# --- idempotent down ------------------------------------------------------------------------------------------
m = h.mark()
h.sim("down"); h.sim("down"); time.sleep(0.05)
check("second down while held is ignored", types(h.since(m)) == [("ptt", "down")], str(h.since(m)))
h.sim("up"); h.wait(lambda e: any(x["type"] == "cancelled" for x in e), mark=m)

# --- empty transcript -> cancelled empty -----------------------------------------------------------------------
m = h.mark()
h.sim("down", fakeText=""); time.sleep(0.45); h.sim("up")
h.wait(lambda e: any(x["type"] in ("final", "cancelled") and x.get("reason") != "short" for x in e), mark=m)
ev = h.since(m)
check("empty hold: listening, then cancelled empty (no final)",
      [t for t in types(ev)] == [("ptt", "down"), ("listening", ""), ("ptt", "up"), ("cancelled", "empty")], str(ev))

# --- normal final (fake STT) ----------------------------------------------------------------------------------
m = h.mark()
h.sim("down", fakeText="how do I import numpy"); time.sleep(0.45); h.sim("up")
h.wait(lambda e: any(x["type"] == "final" for x in e), mark=m)
ev = h.since(m)
fin = [e for e in ev if e["type"] == "final"]
check("fake STT: partial then final with the text, ids agree",
      [t for t, _ in types(ev)] == ["ptt", "listening", "partial", "ptt", "final"] and fin and fin[0]["text"] == "how do I import numpy"
      and len({e["id"] for e in ev}) == 1, str(ev))

# --- stale final carries the old id ---------------------------------------------------------------------------
m = h.mark()
h.sim("down", fakeText="first question", finalDelayMs=900); time.sleep(0.45); h.sim("up")
time.sleep(0.05)
h.sim("down", fakeText="second question"); time.sleep(0.45)
h.wait(lambda e: any(x["type"] == "final" and x["text"] == "first question" for x in e), mark=m)
h.sim("up")
h.wait(lambda e: any(x["type"] == "final" and x["text"] == "second question" for x in e), mark=m)
ev = h.since(m)
downs = [e for e in ev if e["type"] == "ptt" and e["state"] == "down"]
finals = [e for e in ev if e["type"] == "final"]
id1, id2 = (downs[0]["id"], downs[1]["id"]) if len(downs) == 2 else (None, None)
pos = {json.dumps(e): i for i, e in enumerate(ev)}
stale_after_new = (len(finals) == 2 and ev.index(finals[0]) > ev.index(downs[1]))
check("stale final arrives after the new down and carries the OLD id",
      id1 != id2 and stale_after_new and finals[0]["id"] == id1 and finals[0]["text"] == "first question"
      and finals[1]["id"] == id2, str(ev))

# --- final slower than 1.5 s: best partial is sent, and the late final is dropped ----------------------------------
m = h.mark()
h.sim("down", fakeText="slow one", finalDelayMs=4000); time.sleep(0.45)
h.sim("up"); t_up = time.time() - h.t0
h.wait(lambda e: any(x["type"] == "final" for x in e), mark=m)
tev = h.timed_since(m)
tf = next((t for t, e in tev if e["type"] == "final"), None)
check("slow final: best partial sent about 1.5 s after release",
      tf is not None and 1.3 <= tf - t_up <= 2.2, f"dt={None if tf is None else round(tf - t_up, 2)}")
time.sleep(0.2)
h.sim("down", fakeText="x"); h.sim("up")   # (short) just flush
time.sleep(0.4)

# --- keypress and esc abort; hold is then ignored until release ----------------------------------------------
for code, reason in ((0, "keypress"), (53, "esc")):
    m = h.mark()
    h.sim("down", fakeText="abort me"); time.sleep(0.45)
    h.sim("key", code=code); time.sleep(0.05)
    h.sim("down", fakeText="ignored")   # still held: ignored
    time.sleep(0.1)
    ev = h.since(m)
    cancelled = [e for e in ev if e["type"] == "cancelled"]
    check(f"keyDown code {code} during hold -> cancelled {reason}, and no second session",
          len(cancelled) == 1 and cancelled[0]["reason"] == reason and sum(1 for e in ev if e["type"] == "ptt") == 1, str(ev))
    h.sim("up"); time.sleep(0.1)
    m = h.mark(); h.sim("down", fakeText="after"); time.sleep(0.05)
    check(f"after release a new hold works again ({reason})", ("ptt", "down") in types(h.since(m)), str(h.since(m)))
    h.sim("up"); time.sleep(0.2)

# --- Fn / Globe / modifier keyDowns during the hold are not key presses (some keyboards report them) -----------
for code in (63, 179, 59, 62):
    m = h.mark()
    h.sim("down", fakeText="still talking"); time.sleep(0.45)
    h.sim("key", code=code); time.sleep(0.05)
    h.sim("up"); time.sleep(0.4)
    ev = h.since(m)
    check(f"keyDown code {code} (Fn/Globe/modifier) does not abort the hold",
          not any(e["type"] == "cancelled" and e["reason"] in ("keypress", "esc") for e in ev) and any(e["type"] == "final" for e in ev), str(ev))
    time.sleep(0.1)

# --- cancel command and disabling ----------------------------------------------------------------------------
m = h.mark()
h.sim("down", fakeText="cancel me"); time.sleep(0.45); h.send(cmd="cancel"); time.sleep(0.1)
check("cancel command ends the hold with cancelled esc", ("cancelled", "esc") in types(h.since(m)), str(h.since(m)))
h.sim("up"); time.sleep(0.1)
m = h.mark()
h.sim("down", fakeText="disable me"); time.sleep(0.45); h.send(cmd="config", enabled=False); time.sleep(0.1)
check("disabling mid-hold -> cancelled disabled", ("cancelled", "disabled") in types(h.since(m)), str(h.since(m)))
h.sim("up")
h.send(cmd="config", enabled=True); time.sleep(0.1)
m = h.mark(); h.sim("down"); time.sleep(0.05); h.sim("up"); time.sleep(0.1)
check("re-enabled works", ("cancelled", "short") in types(h.since(m)), str(h.since(m)))

# --- hold cap ---------------------------------------------------------------------------------------------------
h.send(cmd="config", enabled=True, maxHoldMs=700); time.sleep(0.1)
m = h.mark()
h.sim("down", fakeText="too long"); h.wait(lambda e: any(x["type"] == "cancelled" for x in e), mark=m, timeout=3)
check("hold past maxHoldMs -> cancelled timeout", ("cancelled", "timeout") in types(h.since(m)), str(h.since(m)))
h.sim("up"); time.sleep(0.1)
h.send(cmd="config", enabled=True, maxHoldMs=60000)

# --- real SpeechAnalyzer fed from a file through the session path -----------------------------------------------
if ready["stt"] == "speechanalyzer":
    wav = "/tmp/ptt-protocol.aiff"
    subprocess.run(["say", "-o", wav, "why is my TensorFlow loss NaN"], check=True)
    h.send(cmd="context", terms=["TensorFlow", "NaN"])
    m = h.mark()
    h.sim("down", file=wav); time.sleep(1.2); h.sim("up")
    h.wait(lambda e: any(x["type"] in ("final", "cancelled") and x.get("reason") != "short" for x in e), mark=m)
    fin = [e for e in h.since(m) if e["type"] == "final"]
    check("file-fed real STT through a session -> final mentions tensor flow",
          bool(fin) and "flow" in fin[0]["text"].lower(), str(h.since(m)))

    # release while the STT is still starting (minHold 0, release 5 ms after the mic opens)
    h.send(cmd="config", enabled=True, minHoldMs=0); time.sleep(0.1)
    m = h.mark()
    h.sim("down", file=wav); h.sim("up")
    ok = h.wait(lambda e: any(x["type"] in ("final", "cancelled") for x in e), mark=m, timeout=5)
    ev = h.since(m)
    ids = {e["id"] for e in ev}
    check("release during async STT start still ends the session exactly once",
          ok and len(ids) == 1 and len([e for e in ev if e["type"] in ("final", "cancelled")]) == 1
          and ("ptt", "up") in types(ev), str(ev))
    h.send(cmd="config", enabled=True, minHoldMs=250)
else:
    print("SKIP file-fed real STT (no speechanalyzer on this Mac)")

# --- every session event carries an id; closing stdin exits ------------------------------------------------------
sess_types = {"ptt", "listening", "partial", "final", "cancelled"}
bad = [e for _, e in h.events if e["type"] in sess_types and not e.get("id")]
check("every ptt/listening/partial/final/cancelled event carries an id", not bad, str(bad))
check("stdin closing makes the helper exit", h.close())

# --- SIGTERM -----------------------------------------------------------------------------------------------------
h2 = Helper()
h2.wait(lambda e: any(x["type"] == "ready" for x in e))
h2.p.terminate()
try:
    h2.p.wait(timeout=3); ok = True
except subprocess.TimeoutExpired:
    h2.p.kill(); ok = False
check("SIGTERM exits cleanly", ok and h2.p.returncode == 0, f"rc={h2.p.returncode}")

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
