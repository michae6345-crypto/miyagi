#!/usr/bin/env python3
"""Capture protocol tests for miyagi-listen --stdin-only. No screen: in --stdin-only the helper writes a gray image of the
planned size instead of capturing. Checks the answer's fields, the file (JPEG, 0600, private 0700 folder), the cleanup
and the errors, the release command, the per-file expiry, and the engine's reader (shared/capture_file.py) on a real
file. Usage: test-capture.py <path to miyagi-listen>"""
import importlib.util, json, os, stat, subprocess, sys, tempfile, threading, time

BIN = sys.argv[1]
# The engine's reader, loaded by path (python -I: no sys.path tricks).
_spec = importlib.util.spec_from_file_location(
    "capture_file", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "shared", "capture_file.py"))
capture_file = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture_file)
failures = []
work = tempfile.mkdtemp(prefix="miyagi-capture-test-")
cap_dir = os.path.join(work, "caps")


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        failures.append(name)


class Helper:
    def __init__(self, **extra_env):
        env = dict(os.environ, MIYAGI_CAPTURE_DIR=cap_dir, **extra_env)
        self.p = subprocess.Popen([BIN, "--stdin-only"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
        self.events = []
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
                self.events.append(ev)

    def send(self, **cmd):
        self.p.stdin.write(json.dumps(cmd) + "\n")
        self.p.stdin.flush()

    def answer(self, cid, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                for e in self.events:
                    if e.get("type") == "capture" and e.get("id") == cid:
                        return e
            time.sleep(0.02)
        return None

    def close(self):
        self.p.stdin.close()
        try:
            self.p.wait(timeout=3)
            return True
        except subprocess.TimeoutExpired:
            self.p.kill()
            return False


def jpeg_size(path):
    """(w, h) from a JPEG's SOF marker."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(d):
        if d[i] != 0xFF:
            return None
        m = d[i + 1]
        n = int.from_bytes(d[i + 2:i + 4], "big")
        if m in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(d[i + 7:i + 9], "big"), int.from_bytes(d[i + 5:i + 7], "big")
        i += 2 + n
    return None


# A stale file from a helper that is gone (a pid that does not run) is deleted at startup. A file of a helper that is
# still running (here: this test's own pid stands in for the packaged app's helper) is never touched.
os.makedirs(cap_dir, mode=0o700, exist_ok=True)
stale = os.path.join(cap_dir, "cap-99999999-00000000-0000-0000-0000-000000000000.jpg")
open(stale, "wb").write(b"x")
other = os.path.join(cap_dir, f"cap-{os.getpid()}-00000000-0000-0000-0000-000000000001.jpg")
open(other, "wb").write(b"x")
h = Helper()

# --- a normal capture ---------------------------------------------------------------------------------------------
h.send(cmd="capture", id="c1", rect={"x": 100, "y": 80, "w": 300, "h": 200}, displayId=1)
a = h.answer("c1")
check("startup removed a dead helper's captures", not os.path.exists(stale))
check("startup kept a running helper's capture", os.path.exists(other))
check("capture answers with path, w, h, pxPerPoint, rect, displayId, ms",
      a is not None and all(k in a for k in ("path", "w", "h", "pxPerPoint", "rect", "displayId", "ms")) and "error" not in a, str(a))
if a and "path" in a:
    check("2x display, small box: native pixels", (a["w"], a["h"], a["pxPerPoint"]) == (600, 400, 2), str(a))
    check("rect is the box captured", a["rect"] == {"x": 100, "y": 80, "w": 300, "h": 200}, str(a["rect"]))
    st = os.stat(a["path"])
    check("file is 0600", stat.S_IMODE(st.st_mode) == 0o600, oct(st.st_mode))
    check("folder is 0700", stat.S_IMODE(os.stat(os.path.dirname(a["path"])).st_mode) == 0o700)
    check("file is a JPEG of the stated size", jpeg_size(a["path"]) == (600, 400), str(jpeg_size(a["path"])))
    check("name is cap-<helper pid>-<uuid>.jpg",
          os.path.basename(a["path"]).startswith(f"cap-{h.p.pid}-") and a["path"].endswith(".jpg"), a["path"])

# --- big box with margin: long edge 1092, margin clamped by the display ------------------------------------------------
h.send(cmd="capture", id="c2", rect={"x": 0, "y": 0, "w": 1400, "h": 700}, displayId=1, margin=0.15)
a = h.answer("c2")
if a and "path" in a:
    check("long edge capped at 1092", max(a["w"], a["h"]) == 1092 and jpeg_size(a["path"]) == (a["w"], a["h"]), str(a))
    r = a["rect"]
    check("margin clamped to the display", r["x"] == 0 and r["y"] == 0 and r["w"] <= 1512 and r["h"] <= 982, str(r))
    check("pxPerPoint = w / rect.w", abs(a["pxPerPoint"] - a["w"] / r["w"]) < 1e-9, str(a))
else:
    check("big capture answers", False, str(a))

# --- a second display with its own origin and scale ------------------------------------------------------------------
h.send(cmd="capture", id="c3", rect={"x": -1000, "y": 0, "w": 400, "h": 300}, displayId=7,
       simDisplay={"x": -1920, "y": -200, "w": 1920, "h": 1080, "scale": 1})
a = h.answer("c3")
check("second display: 1x pixels, displayId echoed", a is not None and (a.get("w"), a.get("h"), a.get("displayId")) == (400, 300, 7), str(a))
# displayId 0 ("the display under the region"): the answer names the display really used, never 0.
h.send(cmd="capture", id="c4", rect={"x": -1000, "y": 0, "w": 400, "h": 300}, displayId=0,
       simDisplay={"x": -1920, "y": -200, "w": 1920, "h": 1080, "scale": 1, "id": 2})
a = h.answer("c4")
check("displayId 0: captured on the display under the box, its id answered",
      a is not None and (a.get("w"), a.get("h"), a.get("displayId")) == (400, 300, 2)
      and a.get("rect") == {"x": -1000, "y": 0, "w": 400, "h": 300}, str(a))

# --- errors ---------------------------------------------------------------------------------------------------------
h.send(cmd="capture", id="e1", rect={"x": 0, "y": 0, "w": 0, "h": 10}, displayId=1)
a = h.answer("e1")
check("empty box -> error bad_rect", a is not None and a.get("error") == "bad_rect" and "path" not in a, str(a))
h.send(cmd="capture", id="e2", rect={"x": 5000, "y": 0, "w": 100, "h": 100}, displayId=1)
a = h.answer("e2")
check("off-screen box -> error bad_rect", a is not None and a.get("error") == "bad_rect", str(a))
h.send(cmd="capture", id="e3", displayId=1)
a = h.answer("e3")
check("no rect -> error bad_rect", a is not None and a.get("error") == "bad_rect", str(a))
h.send(cmd="capture", id="e4", rect={"x": 0, "y": 0, "w": 10, "h": 10}, displayId=-3)
a = h.answer("e4")
check("bad displayId -> error no_display", a is not None and a.get("error") == "no_display", str(a))
h.send(cmd="capture", id="bad id/..", rect={"x": 0, "y": 0, "w": 50, "h": 50}, displayId=1)
time.sleep(0.3)
with h.lock:
    check("a bad id gets no answer", not any(e.get("id") == "bad id/.." for e in h.events))

# --- release: by id, by path, before the capture is ready; only our own files ----------------------------------------
def cap_files():
    return sorted(f for f in os.listdir(cap_dir) if f.startswith("cap-"))


def gone_soon(path, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if not os.path.exists(path):
            return True
        time.sleep(0.02)
    return False


h.send(cmd="capture", id="r1", rect={"x": 10, "y": 10, "w": 50, "h": 50}, displayId=1)
a = h.answer("r1")
if a and "path" in a:
    h.send(cmd="capture-release", id="r1")
    check("release by id deletes the file", gone_soon(a["path"]), a["path"])
else:
    check("release capture answers", False, str(a))
h.send(cmd="capture", id="r2", rect={"x": 10, "y": 10, "w": 50, "h": 50}, displayId=1)
a = h.answer("r2")
if a and "path" in a:
    h.send(cmd="capture-release", path=a["path"])
    check("release by path deletes the file", gone_soon(a["path"]), a["path"])
outside = os.path.join(work, "cap-00000000-0000-0000-0000-000000000000.jpg")
open(outside, "wb").write(b"x")
odd = os.path.join(cap_dir, "notes.jpg")
open(odd, "wb").write(b"x")
h.send(cmd="capture-release", path=outside)
h.send(cmd="capture-release", path=odd)
h.send(cmd="capture-release", path=os.path.join(cap_dir, "..", os.path.basename(outside)))
h.send(cmd="capture-release", id="never-written")
time.sleep(0.3)
check("release never deletes a file outside the folder or with another name", os.path.exists(outside) and os.path.exists(odd))
os.unlink(outside)
os.unlink(odd)
before = cap_files()
h.send(cmd="capture-release", id="r3")
h.send(cmd="capture", id="r3", rect={"x": 10, "y": 10, "w": 50, "h": 50}, displayId=1)
check("released before ready: no answer", h.answer("r3", timeout=0.6) is None)
check("released before ready: no file left", cap_files() == before, str((before, cap_files())))

# --- the engine's reader on a real file: reads it, deletes it --------------------------------------------------------
h.send(cmd="capture", id="e2e", rect={"x": 100, "y": 80, "w": 300, "h": 200}, displayId=1)
a = h.answer("e2e")
if a and "path" in a:
    c = capture_file.take_capture({k: a[k] for k in ("path", "w", "h", "rect", "displayId")}, dirs=[cap_dir])
    check("engine reader accepts the helper's file", c is not None and c.jpeg[:2] == b"\xff\xd8" and (c.w, c.h) == (600, 400), str(c and (c.w, c.h)))
    check("engine reader deletes it", not os.path.exists(a["path"]))
    check("engine reader maps the crop centre", c is not None and capture_file.crop_to_screen(c, 300, 200, 20) == (250.0, 180.0, 10.0))
else:
    check("e2e capture answers", False, str(a))

# --- cleanup: never more than 8 files ------------------------------------------------------------------------------
for i in range(12):
    h.send(cmd="capture", id=f"k{i}", rect={"x": 10, "y": 10, "w": 40, "h": 40}, displayId=1)
check("all 12 answered", all(h.answer(f"k{i}") for i in range(12)))
files = [f for f in os.listdir(cap_dir) if f.startswith(f"cap-{h.p.pid}-")]
check("at most 8 capture files kept", len(files) <= 8, str(len(files)))
check("pruning never touched a running helper's capture", os.path.exists(other))
last = h.answer("k11")
check("the newest capture survives", last is not None and os.path.exists(last["path"]))

# --- capture events never break the push-to-talk events ------------------------------------------------------------
with h.lock:
    bad = [e for e in h.events if e.get("type") == "capture" and not e.get("id")]
check("every capture answer carries an id", not bad, str(bad))

# --- quit removes every capture ------------------------------------------------------------------------------------
check("stdin closing makes the helper exit", h.close())
left = [f for f in os.listdir(cap_dir) if f.startswith("cap-")]
check("quit removes this helper's captures, never a running helper's", left == [os.path.basename(other)], str(left))
os.unlink(other)

# --- expiry: every file goes after the TTL with no new capture (test knob: a 400 ms TTL) -------------------------------
h = Helper(MIYAGI_CAPTURE_TTL_MS="400")
h.send(cmd="capture", id="t1", rect={"x": 10, "y": 10, "w": 50, "h": 50}, displayId=1)
a = h.answer("t1")
if a and "path" in a:
    check("TTL: the file exists right after the answer", os.path.exists(a["path"]))
    time.sleep(0.15)
    check("TTL: still there before it expires", os.path.exists(a["path"]))
    check("TTL: gone after it expires, with no new capture", gone_soon(a["path"], timeout=2.0))
    check("TTL: the helper keeps running", h.p.poll() is None)
else:
    check("TTL capture answers", False, str(a))
h.send(cmd="capture", id="t2", rect={"x": 10, "y": 10, "w": 50, "h": 50}, displayId=1)
a = h.answer("t2")
if a and "path" in a:
    h.send(cmd="capture-release", id="t2")   # released early, then the timer fires on a missing file: harmless
    gone_soon(a["path"])
    time.sleep(0.6)
    check("TTL after a release is harmless", h.p.poll() is None and not os.path.exists(a["path"]))
check("second helper exits", h.close())

try:
    os.rmdir(cap_dir)
    os.rmdir(work)
except OSError:
    pass
print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
