"""Which PyPI packages the engine may install for a lesson (OWASP LLM06 / A08: no arbitrary code from a model).

A lesson graph, the setup check (Claude's tool list), a scaffold's requirements.txt or a tutorial's `pip install`
names the packages. Each name gets one verdict:

  allow    on the curated list (pip_packages.txt, a few hundred common tutorial packages): Install / Install all
  refuse   not on the list but within Damerau-Levenshtein distance 1-2 of a listed name: a likely typosquat
           ("reqeusts", "numpyy"); never installed by the engine, the learner is told which name it resembles
  confirm  any other valid name: installed only after its own confirm that shows the exact name and its pypi.org
           page, and never by Install all
  invalid  not a PyPI project name at all (a URL, a path, a flag, a VCS spec, a local archive such as x.tar.gz or
           x.whl that pip would build from the folder): refused

The list is static and reviewed; nothing a model says changes it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LIST_FILE = Path(__file__).with_name("pip_packages.txt")
_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$")
_SPEC = re.compile(r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(\[[A-Za-z0-9_,.\- ]*\])?\s*"
                   r"((?:[<>=!~]=?|===)\s*[A-Za-z0-9.*+!_-]+(?:\s*,\s*(?:[<>=!~]=?|===)\s*[A-Za-z0-9.*+!_-]+)*)?\s*$")
ALLOW, CONFIRM, REFUSE, INVALID = "allow", "confirm", "refuse", "invalid"
# pip treats a name ending in one of these as a LOCAL FILE when it exists in the folder, and builds a local sdist by
# running its setup.py (pip's own ARCHIVE_EXTENSIONS, plus .egg): never a PyPI name
ARCHIVE_SUFFIXES = (".zip", ".whl", ".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz", ".tar.xz", ".txz", ".tlz",
                    ".tar.lz", ".tar.lzma", ".egg")


@dataclass(frozen=True)
class Verdict:
    kind: str  # allow | confirm | refuse | invalid
    name: str  # the PEP 503 normalised project name ("" when invalid)
    reason: str = ""
    near: str | None = None  # refuse: the listed name it resembles

    @property
    def url(self) -> str:
        return pypi_url(self.name) if self.name else ""

    @property
    def ok(self) -> bool:
        return self.kind == ALLOW


def normalize(name: str) -> str:
    """PEP 503: lower case, runs of -, _ and . become one -."""
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def pypi_url(name: str) -> str:
    return f"https://pypi.org/project/{normalize(name)}/"


@lru_cache(maxsize=1)
def curated() -> frozenset[str]:
    try:
        lines = LIST_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(normalize(ln.split("#", 1)[0]) for ln in lines if ln.split("#", 1)[0].strip())


def project_name(spec: str) -> str | None:
    """The project name of a requirement spec (`numpy`, `pandas>=2`, `uvicorn[standard]==0.30`), or None when it is
    not a plain PyPI requirement (a URL, a path, a flag, `git+...`, an environment marker)."""
    s = (spec or "").strip()
    if not s or "://" in s or s.startswith(("-", ".", "/", "~")) or ";" in s or "@" in s:
        return None
    m = _SPEC.match(s)
    if not m or m.group(1).lower().endswith(ARCHIVE_SUFFIXES):  # evil.tar.gz: a local archive, not a project
        return None
    return normalize(m.group(1))


def damerau_levenshtein(a: str, b: str, limit: int = 3) -> int:
    """Optimal string alignment distance (insert, delete, substitute, swap neighbours); stops counting at `limit`."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) >= limit:
        return limit
    prev2: list[int] | None = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) >= limit:
            return limit
        prev2, prev = prev, cur
    return min(prev[-1], limit)


def typosquat_of(name: str) -> str | None:
    """The listed name `name` looks like a misspelling of, else None. Distance 1 for names of 3+ characters, distance 2
    for names of 6+ (shorter names are 2 edits away from too many real projects)."""
    n = normalize(name)
    listed = curated()
    if not n or n in listed:
        return None
    best: tuple[int, str] | None = None
    for cand in listed:
        if abs(len(cand) - len(n)) > 2:
            continue
        d = damerau_levenshtein(n, cand)
        if d == 1 and min(len(n), len(cand)) >= 3 or d == 2 and min(len(n), len(cand)) >= 6:
            if best is None or (d, cand) < best:
                best = (d, cand)
    if best is None:
        # "py-torch", "scikitlearn": the same letters as a listed name with separators moved
        flat = n.replace("-", "")
        for cand in sorted(listed):
            if cand.replace("-", "") == flat:
                return cand
    return best[1] if best else None


def verdict(spec: str) -> Verdict:
    """The install verdict for one requirement spec or bare name."""
    name = project_name(spec)
    if name is None or not _NAME.match(name):
        return Verdict(INVALID, "", f"{(spec or '').strip()[:60]!r} is not a PyPI package name")
    if name in curated():
        return Verdict(ALLOW, name)
    if near := typosquat_of(name):
        return Verdict(REFUSE, name, f"{name} looks like a misspelling of {near}", near=near)
    return Verdict(CONFIRM, name, f"{name} isn't on miyagi's list of common tutorial packages")


def requirements_problems(text: str) -> list[str]:
    """Why a requirements.txt may not be installed by the engine: option lines (`-i`, `--index-url`, `-e`, `-r`),
    VCS / URL / path requirements, and typosquats. [] = every line is a plain requirement."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            out.append(f"option line {line[:60]!r}")
            continue
        if "://" in line or line.lower().startswith(("git+", "hg+", "svn+", "bzr+")) or "@" in line:
            out.append(f"URL / VCS requirement {line[:60]!r}")
            continue
        v = verdict(line)
        if v.kind == INVALID:
            out.append(v.reason)
        elif v.kind == REFUSE:
            out.append(v.reason)
    return out


def requirements_to_confirm(text: str) -> list[Verdict]:
    """The CONFIRM verdicts of a requirements.txt (names off the curated list), in order, each name once: `pip install
    -r` is never run for the learner while it lists one (each needs its own confirm with its pypi.org page)."""
    out: dict[str, Verdict] = {}
    for raw in (text or "").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        v = verdict(line)
        if v.kind == CONFIRM:
            out.setdefault(v.name, v)
    return list(out.values())


def requirement_names(text: str) -> list[str]:
    """The project names a requirements.txt lists (for a confirm card)."""
    names = []
    for raw in (text or "").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if line and not line.startswith(("#", "-")) and (n := project_name(line)):
            names.append(n)
    return names
