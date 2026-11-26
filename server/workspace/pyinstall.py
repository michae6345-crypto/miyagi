"""pip into a lesson's .venv: which package really, which Python it needs, progress, and what a failure means.

User test (MacBook Neo, fresh install, Nov 25): TensorFlow "doesn't install properly". What the installer did:
  - `pip install --progress-bar off --retries 2 --timeout 30 tensorflow`: a ~224 MB wheel with no output for minutes
    (it looked stuck), a 30 s read stall on a slow link failed the whole install, and nothing retried it;
  - a tutorial's `tensorflow-macos` / `tensorflow-metal` went to pip as named: tensorflow-macos 2.16.2 is an empty shim
    pinning tensorflow==2.16.2 (cp39-cp312 only), and tensorflow-metal 1.2.0 (the last release, Jan 2025, cp39-cp312)
    fails `import tensorflow` with "Symbol not found" in libmetal_plugin.dylib on TensorFlow 2.20+ (Apple developer
    forum threads 803658 / 802833), so an install that "worked" left a TensorFlow that can't import;
  - the check after the install imported every package in one probe with a 45 s budget: a cold `import tensorflow` on
    a low-end Mac can take longer, the row came back "unknown" and the install was reported as failed with "the tool
    still isn't found (open a new terminal / check PATH)";
  - pip's own error went to the card as its last "error" line, with no hint of the real cause.

This module holds the pure parts (no subprocess): plan_package, python_ok, explain_failure, parse_progress. setup.py
runs pip with them.

Facts (PyPI JSON API, checked Nov 25 2026; re-check https://pypi.org/pypi/tensorflow/json when a release lands):
  tensorflow 2.21.0 (2026-03-06): macOS wheels only macosx_12_0_arm64, cp310-cp313, ~224 MB; requires-python >=3.10.
  tensorflow 2.20.0: arm64 cp39-cp313. 2.17-2.19: arm64 cp39-cp312. 2.16.2: the last macOS x86_64 wheels (cp39-cp312).
  tensorflow-cpu: no macOS wheels at all. tensorflow-macos 2.16.2: shim for tensorflow==2.16.2 (arm64).
  tensorflow-metal 1.2.0: cp39-cp312 arm64; works with TensorFlow <= 2.19 only (forum reports, not Apple docs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PyVer = tuple[int, int]

# Python versions with a TensorFlow wheel on macOS, by CPU (the newest release that has one is what pip picks).
TF_PYTHONS: dict[str, tuple[PyVer, PyVer]] = {"arm64": ((3, 9), (3, 13)), "x86_64": ((3, 9), (3, 12))}
TF_LATEST = "2.21"
# Packages whose wheels limit which Python a new lesson .venv may be made from.
PY_CONSTRAINED = frozenset({"tensorflow", "tensorflow-macos", "tensorflow-cpu", "tensorflow-metal"})
# Big downloads: longer budgets, and they get the slow-download wording.
HEAVY = {"tensorflow": 224, "torch": 80, "jaxlib": 80, "jax": 80, "opencv-python": 40, "pyspark": 320}
# What pip prints for a download in raw mode (pip >= 24.1, --progress-bar raw): "Progress 1234 of 5678"
_RAW = re.compile(r"^Progress (\d+) of (\d+)$")
_DOWNLOADING = re.compile(r"^\s*Downloading\s+(?:https?://\S+/)?(?P<file>[\w.\-+%]+?)(?:\s+\((?P<size>[\d.]+)\s*(?P<unit>[kMG]B)\))?\s*$")
_COLLECTING = re.compile(r"^\s*Collecting\s+(?P<name>[A-Za-z0-9][\w.\-]*)")
_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)")


def norm(spec: str) -> str:
    m = _NAME.match((spec or "").strip())
    return m.group(1).lower().replace("_", "-") if m else ""


def fmt(v: PyVer) -> str:
    return f"{v[0]}.{v[1]}"


@dataclass
class Plan:
    """What to pip-install for one setup row. package "" = install nothing (error says why, skip=True: fine to skip)."""
    package: str
    note: str = ""
    error: str = ""
    code: str = ""
    skip: bool = False
    heavy_mb: int = 0
    needs: tuple[PyVer, PyVer] | None = None


def tf_range(machine: str | None) -> tuple[PyVer, PyVer]:
    return TF_PYTHONS.get("x86_64" if (machine or "").lower() in ("x86_64", "amd64", "i386") else "arm64")


def python_ok(package: str, py: PyVer | None, machine: str | None = None) -> bool:
    """Does `package` have a wheel for this Python on this Mac? Unknown Python or package: True (pip decides)."""
    name = norm(package)
    if py is None or name not in PY_CONSTRAINED:
        return True
    lo, hi = tf_range(machine)
    if name == "tensorflow-metal":
        hi = min(hi, (3, 12))
    return lo <= py <= hi


def plan_package(spec: str, *, py: PyVer | None = None, machine: str | None = None, system: str = "Darwin") -> Plan:
    """The pip requirement to really install for a setup row's `spec` (already validated by setup.pip_requirement).
    Retired / Mac-less TensorFlow names become `tensorflow`; tensorflow-metal is never installed (it breaks TF >= 2.20's
    import); a Python with no TensorFlow wheel is refused before a 224 MB download, with the versions that work."""
    name = norm(spec)
    rest = spec.strip()[len(name):] if spec.strip().lower().replace("_", "-").startswith(name) else ""
    mac = system == "Darwin"
    if mac and name == "tensorflow-metal":
        return Plan("", skip=True, code="skipped_incompatible",
                    error="Skipped: GPU add-on incompatible, runs on CPU. tensorflow-metal's last release breaks "
                          f"`import tensorflow` on TensorFlow 2.20 and newer; TensorFlow {TF_LATEST} runs on the CPU "
                          "without it, which is fine for this lesson.")
    note = ""
    if mac and name in ("tensorflow-macos", "tensorflow-cpu"):
        intel = (machine or "").lower() in ("x86_64", "amd64", "i386")
        note = (f"{name} has no build for Intel Macs: installing plain tensorflow (2.16.2 is its last Intel Mac build)."
                if intel else
                f"{name} is the old Mac name (or has no Mac build): installing plain tensorflow, which has Apple-silicon "
                "builds.")
        name, rest = "tensorflow", ""  # an old tutorial's floor (tensorflow-macos>=2.9) means nothing for tensorflow
    pkg = name + rest if name else spec
    plan = Plan(pkg, note=note, heavy_mb=HEAVY.get(name, 0))
    if name == "tensorflow" and mac:
        plan.needs = tf_range(machine)
        if py is not None and not python_ok("tensorflow", py, machine):
            lo, hi = plan.needs
            chip = "Intel Macs" if plan.needs == TF_PYTHONS["x86_64"] else "Apple-silicon Macs"
            plan.package = ""
            plan.code = "python_version"
            plan.error = (f"TensorFlow has no build for Python {fmt(py)} on {chip} (it supports Python {fmt(lo)} to "
                          f"{fmt(hi)}). This lesson's .venv uses Python {fmt(py)}.")
    return plan


# --------------------------------------------------------------------------- progress

@dataclass
class Progress:
    """Folds pip's output into {phase, package, done, total} for the setup gate's row ("Downloading tensorflow 41%")."""
    phase: str = "starting"  # starting | resolving | downloading | installing | verifying
    package: str = ""
    done: int = 0
    total: int = 0
    files: list[str] = field(default_factory=list)

    def feed(self, line: str) -> bool:
        """True when the line changed what the row shows."""
        s = (line or "").strip()
        if m := _RAW.match(s):
            done, total = int(m.group(1)), int(m.group(2))
            changed = done != self.done or total != self.total or self.phase != "downloading"
            self.phase, self.done, self.total = "downloading", done, total
            return changed
        if m := _COLLECTING.match(s):
            self.phase, self.package = "resolving", m.group("name")
            return True
        if m := _DOWNLOADING.match(s):
            self.phase, self.done, self.total = "downloading", 0, _bytes(m.group("size"), m.group("unit"))
            self.files.append(m.group("file"))
            return True
        if s.startswith("Installing collected packages"):
            self.phase, self.done, self.total = "installing", 0, 0
            return True
        return False

    def payload(self) -> dict:
        out: dict = {"phase": self.phase}
        if self.package:
            out["package"] = self.package
        if self.total:
            out["bytes"], out["totalBytes"] = self.done, self.total
            out["pct"] = max(0, min(100, round(100 * self.done / self.total)))
        return out


def _bytes(size: str | None, unit: str | None) -> int:
    if not size:
        return 0
    try:
        return int(float(size) * {"kB": 1e3, "MB": 1e6, "GB": 1e9}.get(unit or "MB", 1e6))
    except ValueError:
        return 0


def parse_progress(line: str) -> tuple[int, int] | None:
    m = _RAW.match((line or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def pip_version_ok_for_raw(version_text: str) -> bool:
    """`pip --version` output -> does it take --progress-bar raw (pip 24.1+)?"""
    m = re.search(r"pip (\d+)\.(\d+)", version_text or "")
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (24, 1)


def pip_supports_resume(version_text: str) -> bool:
    """`pip --version` output -> does it take --resume-retries (pip 25.1+: resumes a broken download)?"""
    m = re.search(r"pip (\d+)\.(\d+)", version_text or "")
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (25, 1)


# --------------------------------------------------------------------------- failures

NETWORK = "network"
TIMEOUT = "timeout"
NO_WHEEL = "no_wheel"
DISK = "disk_full"
CONFLICT = "conflict"
BUILD = "build_failed"
PERMISSION = "permission"
BROKEN_IMPORT = "broken_import"
CANCELLED = "cancelled"
UNKNOWN = "unknown"
RETRYABLE = (NETWORK, TIMEOUT)

_RULES: list[tuple[str, re.Pattern]] = [
    (DISK, re.compile(r"No space left on device|\[Errno 28\]", re.IGNORECASE)),
    (TIMEOUT, re.compile(r"Read timed out|ReadTimeoutError|timed out$|IncompleteRead|Connection broken", re.IGNORECASE)),
    (NETWORK, re.compile(r"NewConnectionError|Name or service not known|nodename nor servname|Temporary failure in name "
                         r"resolution|Network is unreachable|Failed to establish a new connection|ConnectTimeout|"
                         r"Could not resolve host|ConnectionResetError|SSLError|ProxyError|"
                         r"THESE PACKAGES DO NOT MATCH THE HASHES", re.IGNORECASE)),
    (NO_WHEEL, re.compile(r"No matching distribution found|Could not find a version that satisfies|"
                          r"requires a different Python|is not a supported wheel on this platform", re.IGNORECASE)),
    (CONFLICT, re.compile(r"ResolutionImpossible|conflicting dependencies|Cannot install .* because these package "
                          r"versions have conflicting", re.IGNORECASE)),
    (BUILD, re.compile(r"Failed building wheel|subprocess-exited-with-error|metadata-generation-failed|"
                       r"error: command .*clang", re.IGNORECASE)),
    (PERMISSION, re.compile(r"Permission denied|\[Errno 13\]|EnvironmentError: \[Errno 1\]", re.IGNORECASE)),
]


def classify(text: str, exit_code: int | None = None) -> str:
    if exit_code == 124:
        return TIMEOUT
    for code, rx in _RULES:
        if rx.search(text or ""):
            return code
    return UNKNOWN


def explain_failure(text: str, *, package: str, exit_code: int | None = None, py: PyVer | None = None,
                    machine: str | None = None, attempts: int = 1) -> tuple[str, str]:
    """pip's output -> (code, one or two calm sentences the card can show). The raw log stays for "Show details"."""
    code = classify(text, exit_code)
    name = norm(package) or package or "the package"
    tries = f" (tried {attempts} times)" if attempts > 1 else ""
    if code == TIMEOUT and exit_code == 124:
        return code, (f"Installing {name} took too long and was stopped{tries}. On a slow connection it can take a while: "
                      "press Retry, or try on a faster network.")
    if code == TIMEOUT:
        return code, (f"The download of {name} kept stalling{tries}. Your connection may be slow or dropping: "
                      "press Retry, or try on a faster network.")
    if code == NETWORK:
        return code, f"Couldn't reach the Python package index to download {name}{tries}. Check your connection, then Retry."
    if code == DISK:
        return code, f"Your Mac ran out of disk space while installing {name}. Free up a few GB, then Retry."
    if code == NO_WHEEL:
        pyv = f"Python {fmt(py)}" if py else "this Python"
        if norm(package) in ("tensorflow", "tensorflow-macos", "tensorflow-cpu"):
            lo, hi = tf_range(machine)
            return code, (f"TensorFlow has no build for {pyv} on this Mac (it supports Python {fmt(lo)} to {fmt(hi)}).")
        return code, f"{name} has no ready-made build for {pyv} on this Mac."
    if code == CONFLICT:
        return code, f"{name} needs versions of other packages that clash with ones already in this lesson's .venv."
    if code == BUILD:
        return code, f"{name} had to be compiled from source on this Mac and the build failed."
    if code == PERMISSION:
        return code, f"Miyagi wasn't allowed to write into the lesson's .venv while installing {name}."
    last = _last_error_line(text)
    return code, (f"Installing {name} failed: {last}" if last else f"Installing {name} failed.")


def broken_import_hint(detail: str) -> str:
    """A package that installed but fails to import: what to do about the known cases."""
    if "libmetal_plugin" in (detail or "") or "tensorflow-plugins" in (detail or ""):
        return ("TensorFlow installed but won't import: the tensorflow-metal add-on in this .venv doesn't match it. "
                "Run `pip uninstall tensorflow-metal` in the lesson's terminal, then Retry.")
    return ""


def _last_error_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    errs = [ln for ln in lines if re.search(r"error|fail|denied|not found", ln, re.IGNORECASE)]
    return (errs[-1] if errs else (lines[-1] if lines else ""))[:240]
