"""Which PyPI packages the engine may install for a lesson (OWASP LLM06 / A08: no arbitrary code from a model).

A lesson graph, the setup check (Claude's tool list), a scaffold's requirements.txt or a tutorial's `pip install`
names the packages. Each name gets one verdict:

  allow    on the curated list (pip_packages.txt, a few hundred common tutorial packages): Install / Install all
  refuse   not on the list but one typo (Damerau-Levenshtein distance 1, or the same letters with separators moved)
           from a listed name: a likely typosquat ("reqeusts", "numpyy", "scikitlearn"); never installed by the
           engine, the learner is told which name it resembles
  confirm  any other valid name: installed only after its own confirm that shows the exact name and its pypi.org
           page, and never by Install all. A near miss that real projects use (two edits away, "pyautogen" next to
           pyautogui, or only a trailing version digit apart, "boto" next to boto3) is a confirm too, whose reason
           says which listed name it resembles (Verdict.near)
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


def _digit_suffix_only(a: str, b: str) -> bool:
    """boto / boto3, web3 / web: one name is the other plus trailing digits (a real project's major version)."""
    short, long_ = sorted((a, b), key=len)
    return long_.startswith(short) and long_[len(short):].isdigit()


def near_miss(name: str) -> tuple[str, bool] | None:
    """(the listed name `name` resembles, refused?) or None. refused: one typo away ("reqeusts", "numpyy") or the same
    letters with separators moved ("scikitlearn"). Not refused (a confirm that names the look-alike): two edits away
    ("pyautogen" / pyautogui) or only a trailing version digit apart ("boto" / boto3)."""
    near = typosquat_of(name)
    if near is None:
        return None
    n = normalize(name)
    d = damerau_levenshtein(n, near)
    if d == 1 and not _digit_suffix_only(n, near) or n.replace("-", "") == near.replace("-", ""):
        return near, True
    return near, False


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
    if miss := near_miss(name):
        near, refuse = miss
        if refuse:
            return Verdict(REFUSE, name, f"{name} looks like a misspelling of {near}", near=near)
        return Verdict(CONFIRM, name, f"{name} isn't on miyagi's list of common tutorial packages and looks a lot like "
                       f"{near}: make sure it's the one the tutorial means", near=near)
    return Verdict(CONFIRM, name, f"{name} isn't on miyagi's list of common tutorial packages")


# pip decodes a requirements file by its BOM, else by a PEP 263 `# coding: X` line in its first two lines, else the
# locale's encoding (pip._internal.req.req_file / utils.encoding). The engine accepts only a file every one of those
# reads the same way it does: plain ASCII, no BOM, no coding line, no line break but \n / \r\n.
_CODING = re.compile(rb"coding[:=]")
_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")


def decode_requirements(data: bytes | str) -> tuple[str | None, str | None]:
    """(text, None) for a requirements file pip reads exactly as the engine does; (None, why) otherwise: a BOM, a
    PEP 263 coding line in the first two lines, a byte outside printable ASCII + tab, or a line break other than \\n
    and \\r\\n (\\v, \\f, \\x1c-\\x1e, a lone \\r: str.splitlines() and pip split there, a card shows one line).
    A str (a scaffold's content, written as UTF-8) is checked as its UTF-8 bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8", "surrogatepass")
    if data.startswith(_BOMS):
        return None, "it starts with a byte-order mark (pip would read it in another encoding)"
    for line in data.split(b"\n")[:2]:
        if _CODING.search(line):
            return None, "it declares an encoding (pip would read it in that encoding)"
    for i, b in enumerate(data):
        if b == 0x0D and data[i + 1:i + 2] == b"\n" or b in (0x09, 0x0A) or 0x20 <= b < 0x7F:
            continue
        return None, (f"it has a non-ASCII byte (0x{b:02X})" if b >= 0x80
                      else f"it has a control character (0x{b:02X})")
    return data.decode("ascii"), None


def requirement_specs(text: str) -> list[str]:
    """The requirement specs of a requirements file every line of which requirements_problems() accepts, without
    their whitespace (`numpy >= 1.26` -> `numpy>=1.26`): what `pip install <specs>` gets in place of `-r <file>`, so
    pip never reads the file the card summarised."""
    out = []
    for raw in (text or "").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if line and not line.startswith(("#", "-")) and project_name(line):
            out.append("".join(line.split()))
    return out


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
