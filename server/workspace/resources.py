"""The tutorial's own materials: find them (video description + step-graph sources) and download them
into `<lesson folder>/tutorial/` when the learner presses Download.

    found = find_resources(graph)            # [{name, url, kind, fetch}] (one watch-page fetch, cached per video)
    saved = download_resources(graph)        # [{name, url, kind, path, bytes} | {..., path: None, error}]
    summary(saved)                           # "Saved 3 files to …/tutorial" or NO_RESOURCES

Recognised: GitHub repos (zip from codeload: no git, so no hooks), GitHub/raw file links, Colab notebooks
(GitHub-backed -> raw .ipynb; Drive-backed -> Drive download), gists (via the API), and direct data/code
files (.csv .tsv .json .jsonl .parquet .xlsx .txt .ipynb .py .zip). Everything else (socials, playlists,
papers, sponsors) is ignored. Each download is capped at MIYAGI_DOWNLOAD_MAX_MB (50); zips are
extracted with path-escape and symlink guards, file and size caps. Nothing downloaded is ever executed,
imported or installed, and no file gets an executable bit.

Every fetch goes through server.netsafe (claude/eng-keys-ssrf): the description is written by the video's uploader,
so a link like https://evil.example/data.csv could redirect to http://192.168.1.1/ or http://169.254.169.254/ (or be
https://10.0.0.5/x.zip outright) and have the router's or a metadata service's answer saved into tutorial/. Each hop
must be a public http(s) host (resolved and checked, the peer address checked after connecting), at most 3 redirects,
and each fetch has a deadline (DOWNLOAD_DEADLINE_S for a file, a few timeouts for the watch page).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

import httpx

from server import netsafe

from . import paths

log = logging.getLogger("server.workspace")

NO_RESOURCES = "No downloadable code linked from this video"
MAX_BYTES = int(float(os.environ.get("MIYAGI_DOWNLOAD_MAX_MB", "50")) * 1024 * 1024)
MAX_UNZIPPED = 4 * MAX_BYTES
MAX_ZIP_FILES = 5000
MAX_RESOURCES = 8
DOWNLOAD_TIMEOUT_S = 60
DOWNLOAD_DEADLINE_S = 600  # one file (up to MAX_BYTES) start to finish
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
FILE_EXT = {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx", ".txt", ".ipynb", ".py", ".zip", ".r", ".sql", ".md"}
_URL = re.compile(r"https?://[^\s<>\"'()\[\]{}]+")
_GH_RESERVED = {"sponsors", "orgs", "settings", "features", "marketplace", "topics", "about", "login", "join", "pricing",
                "collections", "explore", "notifications", "apps", "site", "security", "enterprise", "readme"}
_NAME = re.compile(r"[^A-Za-z0-9._-]+")


# --------------------------------------------------------------------------- finding links

def _clean(url: str) -> str:
    return url.rstrip(".,;:!?)]}>'\"")


def classify(url: str) -> dict | None:
    """One link -> {name, url, kind (repo|notebook|gist|file), fetch} or None if it isn't tutorial material."""
    url = _clean(url)
    try:
        u = urlparse(url)
    except ValueError:
        return None
    host = (u.hostname or "").lower().removeprefix("www.")
    parts = [p for p in u.path.split("/") if p]
    if host == "github.com" and len(parts) >= 2 and parts[0].lower() not in _GH_RESERVED:
        owner, repo = parts[0], parts[1].removesuffix(".git")
        if not re.fullmatch(r"[\w.-]+", owner) or not re.fullmatch(r"[\w.-]+", repo):
            return None
        if len(parts) >= 5 and parts[2] in ("blob", "raw"):  # one file
            path = "/".join(parts[4:])
            return {"name": PurePosixPath(path).name, "url": url, "kind": "notebook" if path.endswith(".ipynb") else "file",
                    "fetch": f"https://raw.githubusercontent.com/{owner}/{repo}/{parts[3]}/{path}", "repo": f"{owner}/{repo}"}
        ref = parts[3] if len(parts) >= 4 and parts[2] == "tree" else "HEAD"
        return {"name": f"{owner}-{repo}", "url": url, "kind": "repo", "repo": f"{owner}/{repo}",
                "fetch": f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"}
    if host == "raw.githubusercontent.com" and len(parts) >= 4:
        name = parts[-1]
        return {"name": name, "url": url, "kind": "notebook" if name.endswith(".ipynb") else "file", "fetch": url,
                "repo": f"{parts[0]}/{parts[1]}"}
    if host == "colab.research.google.com":
        if len(parts) >= 6 and parts[0] == "github" and parts[3] == "blob":
            owner, repo, ref, path = parts[1], parts[2], parts[4], "/".join(parts[5:])
            return {"name": PurePosixPath(path).name, "url": url, "kind": "notebook", "repo": f"{owner}/{repo}",
                    "fetch": f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"}
        if len(parts) >= 2 and parts[0] == "drive" and re.fullmatch(r"[\w-]{10,}", parts[1]):
            return {"name": f"colab-{parts[1][:12]}.ipynb", "url": url, "kind": "notebook",
                    "fetch": f"https://drive.google.com/uc?export=download&id={parts[1]}"}
        return None
    if host == "gist.github.com" and parts:
        gid = parts[-1]
        if re.fullmatch(r"[0-9a-f]{6,}", gid):
            return {"name": f"gist-{gid[:10]}", "url": url, "kind": "gist", "fetch": f"https://api.github.com/gists/{gid}"}
        return None
    if host in ("drive.google.com", "docs.google.com") and (m := re.search(r"/d/([\w-]{10,})", u.path) or None):
        fid = m.group(1)
        if host == "docs.google.com" and "/spreadsheets/" in u.path:
            return {"name": f"sheet-{fid[:10]}.csv", "url": url, "kind": "file",
                    "fetch": f"https://docs.google.com/spreadsheets/d/{fid}/export?format=csv"}
        if host == "drive.google.com":
            return {"name": f"drive-{fid[:10]}", "url": url, "kind": "file", "fetch": f"https://drive.google.com/uc?export=download&id={fid}"}
        return None
    if host == "drive.google.com" and (fid := (parse_qs(u.query).get("id") or [""])[0]) and re.fullmatch(r"[\w-]{10,}", fid):
        return {"name": f"drive-{fid[:10]}", "url": url, "kind": "file", "fetch": f"https://drive.google.com/uc?export=download&id={fid}"}
    ext = PurePosixPath(u.path).suffix.lower()
    if u.scheme == "https" and ext in FILE_EXT and host and not host.endswith(("youtube.com", "youtu.be")):
        return {"name": PurePosixPath(u.path).name, "url": url, "kind": "notebook" if ext == ".ipynb" else "file", "fetch": url}
    return None


def extract_links(text: str) -> list[str]:
    return [_clean(m) for m in _URL.findall(text or "")]


def fetch_description(video_id: str, *, client: httpx.Client | None = None) -> str:
    """The video's full description from its watch page ("" if unavailable)."""
    c = client or netsafe.sync_client(headers=UA, timeout=10)
    try:
        html = netsafe.get_sync(f"https://www.youtube.com/watch?v={video_id}", client=c, timeout=10,
                                max_bytes=netsafe.PAGE_MAX_BYTES).text
    except httpx.HTTPError as e:
        log.warning("description for %s: %s", video_id, e)
        return ""
    finally:
        if client is None:
            c.close()
    m = re.search(r'"shortDescription":\s?"((?:[^"\\]|\\.)*)"', html)
    try:
        return json.loads(f'"{m.group(1)}"') if m else ""
    except ValueError:
        return ""


def _video_id(graph: dict) -> str | None:
    for s in graph.get("sources") or []:
        if v := (s.get("videoId") or paths.video_id(s.get("url", ""))):
            return v
    return None


def _cache_file(graph: dict) -> Path:
    vid = _video_id(graph)
    key = f"video-{vid}" if vid else "lesson-" + hashlib.sha1(paths.folder_name(graph).encode()).hexdigest()[:12]
    return paths.lessons_root() / ".miyagi-state" / "resources" / f"{re.sub(r'[^A-Za-z0-9_-]', '_', key)}.json"


def find_resources(lesson: dict, *, description: str | None = None, client: httpx.Client | None = None,
                   use_cache: bool = True) -> list[dict]:
    """The tutorial's downloadable materials. Reads the step graph's sources (repo/notebook links), any
    `description` in the graph, and the video description (passed in, or fetched once and cached per video)."""
    cache = _cache_file(lesson)
    if use_cache and description is None and cache.exists():
        try:
            return json.loads(cache.read_text())
        except ValueError:
            pass
    texts = [s.get("url", "") for s in lesson.get("sources") or [] if s.get("kind") != "video"]
    texts += [s.get("description", "") for s in lesson.get("sources") or []]
    texts.append((paths.lesson_meta(lesson) or {}).get("description", ""))
    if description is None and (vid := _video_id(lesson)):
        description = fetch_description(vid, client=client)
    texts.append(description or "")
    found: list[dict] = []
    seen: set[str] = set()
    for t in texts:
        for url in extract_links(t):
            r = classify(url)
            if r is None:
                continue
            key = r.get("repo") if r["kind"] == "repo" else r["fetch"]
            if key in seen:
                continue
            seen.add(key)
            found.append(r)
    repos = {r["repo"] for r in found if r["kind"] == "repo"}
    # a file inside a repo we download whole is already covered
    found = [r for r in found if r["kind"] == "repo" or r.get("repo") not in repos][:MAX_RESOURCES]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(found, indent=1))
    return found


# --------------------------------------------------------------------------- downloading

class TooLarge(Exception):
    pass


def _get(client: httpx.Client, url: str) -> tuple[bytes, dict]:
    """One file through netsafe (redirects by hand, every hop a public host), capped at MAX_BYTES."""
    try:
        r = netsafe.get_sync(url, client=client, timeout=DOWNLOAD_TIMEOUT_S, max_bytes=MAX_BYTES,
                             deadline=DOWNLOAD_DEADLINE_S)
    except netsafe.BodyTooLarge:
        raise TooLarge(f"larger than {MAX_BYTES // 2**20} MB") from None
    r.raise_for_status()
    return r.content, {k.lower(): v for k, v in r.headers.items()}


def _safe_name(name: str) -> str:
    n = _NAME.sub("_", name).strip("._") or "download"
    return n[:120]


def _write(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    dest.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)  # never executable


def _extract_zip(data: bytes, dest: Path) -> int:
    """Extract a GitHub zip into dest (drops the `<repo>-<ref>/` top folder). Returns the number of files."""
    root = dest.resolve()
    n = total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                continue  # symlinks could point outside the folder
            parts = PurePosixPath(info.filename).parts
            rel = PurePosixPath(*parts[1:]) if len(parts) > 1 else PurePosixPath(parts[0])
            if not rel.parts or ".." in rel.parts or rel.is_absolute() or ".git" in rel.parts:
                continue
            target = (root / rel).resolve()
            if root not in target.parents:
                continue
            n += 1
            total += info.file_size
            if n > MAX_ZIP_FILES or total > MAX_UNZIPPED:
                raise TooLarge("archive too large to unpack")
            _write(target, z.read(info))
    return n


def _download_one(r: dict, out: Path, client: httpx.Client) -> dict:
    res = {"name": r["name"], "url": r["url"], "kind": r["kind"], "path": None}
    try:
        if r["kind"] == "repo":
            dest = out / _safe_name(r["name"])
            if dest.is_dir() and any(dest.iterdir()):
                return {**res, "path": str(dest), "cached": True}
            data, _ = _get(client, r["fetch"])
            res["files"] = _extract_zip(data, dest)
            res["bytes"] = len(data)
            res["path"] = str(dest)
        elif r["kind"] == "gist":
            meta = json.loads(_get(client, r["fetch"])[0])
            dest = out / _safe_name(r["name"])
            count = 0
            for f in (meta.get("files") or {}).values():
                body = f.get("content")
                if body is None or f.get("truncated"):
                    body = _get(client, f["raw_url"])[0].decode("utf-8", "replace")
                _write(dest / _safe_name(f.get("filename") or "file"), body.encode())
                count += 1
            res.update(path=str(dest), files=count)
        else:
            dest = out / _safe_name(r["name"])
            if dest.exists():
                return {**res, "path": str(dest), "cached": True}
            data, headers = _get(client, r["fetch"])
            if "text/html" in headers.get("content-type", "") and not r["name"].endswith((".html", ".htm")):
                raise ValueError("the link returned a web page (sign-in or confirmation needed): open it in the browser")
            if r["kind"] == "notebook" and not data.lstrip().startswith(b"{"):
                raise ValueError("not a notebook file (the link may need sign-in)")
            if "drive.google.com" in r["fetch"]:  # Drive/Colab: use the file's real name when the server gives it
                m = re.search(r'filename="([^"]+)"', headers.get("content-disposition", ""))
                if m:
                    real = _safe_name(m.group(1))
                    if r["kind"] == "notebook" and not real.endswith(".ipynb"):
                        real += ".ipynb"
                    dest = out / real
                    res["name"] = real
            _write(dest, data)
            res.update(path=str(dest), bytes=len(data))
    except (httpx.HTTPError, TooLarge, ValueError, zipfile.BadZipFile, OSError, KeyError) as e:
        res["error"] = str(e)[:200] or type(e).__name__
    return res


def download_resources(lesson: dict, *, folder: Path | str | None = None, description: str | None = None,
                       client: httpx.Client | None = None, resources: list[dict] | None = None) -> list[dict]:
    """Download the tutorial's materials into `<folder>/tutorial/`. ONLY on the learner's Download press.

    folder defaults to the lesson's folder (~/miyagi/lessons/<slug>-<hash>). Returns one entry per resource:
    {name, url, kind, path, bytes?|files?, cached?} or {..., path: None, error}. [] = nothing linked
    (show NO_RESOURCES). Already-downloaded resources are reused."""
    c = client or netsafe.sync_client(headers=UA, timeout=DOWNLOAD_TIMEOUT_S)
    try:
        found = resources if resources is not None else find_resources(lesson, description=description, client=c)
        if not found:
            return []
        base = Path(folder).expanduser() if folder else paths.lessons_root() / paths.folder_name(lesson)
        hero = paths.hero_workdir(lesson)
        if hero is not None and base.resolve() == hero:  # never drop downloads into the repo's demo folder
            base = paths.lessons_root() / paths.folder_name(lesson)
        out = base / "tutorial"
        out.mkdir(parents=True, exist_ok=True)
        results = [_download_one(r, out, c) for r in found]
    finally:
        if client is None:
            c.close()
    log.info("download_resources -> %s", [(r["name"], bool(r.get("path")), r.get("error")) for r in results])
    return results


def summary(results: list[dict]) -> str:
    """One line for a card: what was saved where, what failed, or NO_RESOURCES."""
    if not results:
        return NO_RESOURCES + "."
    ok = [r for r in results if r.get("path")]
    bad = [r for r in results if not r.get("path")]
    parts = []
    if ok:
        where = str(Path(ok[0]["path"]).parent).replace(str(Path.home()), "~")
        parts.append(f"Saved {', '.join(r['name'] for r in ok)} to {where}.")
    if bad:
        parts.append("Couldn't download " + "; ".join(f"{r['name']} ({r.get('error', 'failed')})" for r in bad) + ".")
    return " ".join(parts)
