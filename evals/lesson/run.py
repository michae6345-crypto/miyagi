"""Build every lesson in videos.json LIVE with server.lesson.build_lesson and grade it.

    python evals/lesson/run.py                 # build all (one subprocess per video, in parallel), then grade
    python evals/lesson/run.py --only rust-cli # build one
    python evals/lesson/run.py --grade-only    # re-grade evals/lesson/results/*.json without building
    python evals/lesson/run.py --src DIR       # import `server` from another checkout (e.g. E2's branch tip)
    python evals/lesson/run.py --out DIR       # write results elsewhere (e.g. results-<sha>/ to compare runs)
    python evals/lesson/run.py --saved-captions evals/lesson/results  # YouTube 429s captions: reuse saved real ones

Nothing is read from or written to demo/cache: build_lesson(..., cache=False) is the builder's bypass
(no cache read, video pass forced, no cache write). Each video gets its own empty workdir, as a learner
starting a new project would. Each build runs in its own process because the builder records the
serving model in module globals (gemini.last_model / claude.last_model), which concurrent builds in
one process would overwrite.

Outputs (evals/lesson/results/): <id>.json = {meta, graph, error}, <id>.transcript.json = captions used
for spot-checking, grades.json = automatic grades (see grade.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "results"
VIDEOS = json.loads((HERE / "videos.json").read_text())["videos"]
BUILD_TIMEOUT_S = 900


def _env_file() -> str | None:
    """The repo's .env, or the main checkout's when running from a worktree (never printed)."""
    for p in (REPO / ".env", REPO.parents[2] / ".env" if REPO.parent.name == "worktrees" else None):
        if p and p.is_file():
            return str(p)
    return None


def _use_saved_captions(transcript, vid: dict, saved_dir: Path, meta: dict) -> None:
    """Opt-in (--saved-captions DIR): when the live caption fetch fails (YouTube 429s this IP), feed the
    Claude path the REAL captions an earlier run of this eval saved (DIR/<id>.transcript.json), plus the
    live title/description/chapters from the watch page. Recorded in meta["captions"]; never invents text."""
    import httpx

    live = transcript.fetch_video_info

    async def fetch(video_id: str) -> dict:
        try:
            return await live(video_id)
        except RuntimeError as e:
            saved = json.loads((saved_dir / f"{vid['id']}.transcript.json").read_text())
            async with httpx.AsyncClient(headers=transcript._HEADERS, timeout=30, follow_redirects=True) as c:
                page = (await c.get(transcript.WATCH_URL.format(vid=video_id))).text
            vd = (transcript._player_response(page) or {}).get("videoDetails") or {}
            desc = vd.get("shortDescription", "")
            meta["captions"] = f"saved by an earlier run ({saved_dir.name}/); live fetch failed: {str(e)[:160]}"
            return {"video_id": video_id, "title": vd.get("title") or saved["title"], "description": desc,
                    "length_s": saved.get("length_s"), "chapters": transcript.parse_chapters(desc) or saved.get("chapters", []),
                    "transcript": saved["transcript"], "sources": {"metadata": "youtube.com", "transcript": "saved captions (eval)"},
                    "errors": [str(e)[:300]]}

    transcript.fetch_video_info = fetch  # builder calls transcript.fetch_video_info at build time


def build_one(vid: dict, src: Path, saved_captions: Path | None = None) -> dict:
    """Runs in a child process: one live build, returns {meta, graph, error}."""
    sys.path.insert(0, str(src))
    import logging

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format=f"[{vid['id']}] %(levelname)s %(name)s: %(message)s")
    from server.lesson import build_lesson, transcript  # noqa: E402

    meta: dict = {"id": vid["id"], "url": vid["url"], "goal": vid["goal"], "src": str(src), "engine_env": os.environ.get("LESSON_ENGINE", "claude")}  # unset = the Claude-only default (D1)
    if saved_captions:
        _use_saved_captions(transcript, vid, saved_captions, meta)
    graph, error = None, None
    with tempfile.TemporaryDirectory(prefix=f"lesson-eval-{vid['id']}-") as wd:
        t0 = time.time()
        try:
            graph = asyncio.run(build_lesson(vid["url"], vid["goal"], wd, cache=False))
        except Exception as e:  # noqa: BLE001  record every failure, the eval grades it
            error = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}"
        meta["wall_s"] = round(time.time() - t0, 1)
        meta["workdir"] = "(fresh empty temp dir)"
    if graph:
        b = graph.get("build") or {}
        meta["model"] = b.get("model")
        video_model = str((b.get("model") or {}).get("video", ""))
        meta["path"] = "gemini" if video_model.startswith("gemini") else "claude" if video_model.startswith("claude") else "unknown"
        meta["fallback_notes"] = b.get("warnings", [])[:3]
    # Transcript for spot-checking (same fetcher the Claude path uses; independent of which engine ran).
    try:
        info = asyncio.run(transcript.fetch_video_info(vid["url"].split("v=")[1][:11]))
        (OUT / f"{vid['id']}.transcript.json").write_text(json.dumps(
            {k: info[k] for k in ("video_id", "title", "length_s", "chapters", "transcript", "sources")}, indent=1))
        meta["length_s"] = info.get("length_s")
    except Exception as e:  # noqa: BLE001
        meta["transcript_error"] = str(e)[:300]
    return {"meta": meta, "graph": graph, "error": error}


def child(vid_id: str, src: Path, saved_captions: Path | None = None) -> int:
    vid = next(v for v in VIDEOS if v["id"] == vid_id)
    res = build_one(vid, src, saved_captions)
    (OUT / f"{vid_id}.json").write_text(json.dumps(res, indent=1))
    print(f"[{vid_id}] done in {res['meta'].get('wall_s')}s path={res['meta'].get('path')} error={bool(res['error'])}", file=sys.stderr)
    return 0


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append", help="video id(s) to build")
    ap.add_argument("--src", default=str(REPO), help="checkout to import `server` from (default: this repo)")
    ap.add_argument("--out", default=str(OUT), help="results folder (default: evals/lesson/results)")
    ap.add_argument("--saved-captions", metavar="DIR", help="if the live caption fetch fails, use captions an earlier run saved in DIR (labelled in meta)")
    ap.add_argument("--grade-only", action="store_true")
    ap.add_argument("--child", help=argparse.SUPPRESS)
    a = ap.parse_args()
    OUT = Path(a.out).resolve()
    OUT.mkdir(exist_ok=True)
    if env := _env_file():
        os.environ.setdefault("TUT_ENV", env)  # server.lesson loads keys from $TUT_ENV first
    src = Path(a.src).resolve()
    saved = Path(a.saved_captions).resolve() if a.saved_captions else None
    if a.child:
        return child(a.child, src, saved)
    if not a.grade_only:
        ids = a.only or [v["id"] for v in VIDEOS]
        procs = {i: subprocess.Popen([sys.executable, __file__, "--child", i, "--src", str(src), "--out", str(OUT)] + (["--saved-captions", str(saved)] if saved else []),
                                     stdout=subprocess.DEVNULL, stderr=open(OUT / f"{i}.log", "w")) for i in ids}
        for i, p in procs.items():
            try:
                p.wait(timeout=BUILD_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                p.kill()
                (OUT / f"{i}.json").write_text(json.dumps({"meta": {"id": i, "wall_s": BUILD_TIMEOUT_S}, "graph": None, "error": f"timeout after {BUILD_TIMEOUT_S}s"}))
    sys.path.insert(0, str(src))
    from grade import grade_all  # noqa: E402  (evals/lesson/grade.py)

    grades = grade_all(OUT, VIDEOS)
    (OUT / "grades.json").write_text(json.dumps(grades, indent=1))
    for g in grades:
        print(f"{g['id']:16} auto={g['auto_score']:>4}  steps={g.get('steps')}  path={g.get('path')}  wall={g.get('wall_s')}s  {('ERROR ' + g['error'][:80]) if g.get('error') else ''}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
