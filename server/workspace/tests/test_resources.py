"""find_resources / download_resources with a mocked HTTP transport (no network)."""

from __future__ import annotations

import io
import json
import os
import stat
import zipfile

import httpx
import pytest

from server.workspace import (
    NO_RESOURCES,
    download_resources,
    download_summary,
    find_resources,
)
from server.workspace import resources as R
from server.workspace.setup import setup_card
from server.workspace.tests.test_workspace import load

KARPATHY_DESC = """We build a Generatively Pretrained Transformer (GPT)...

Links:
- Google colab for the video: https://colab.research.google.com/drive/1JMLa53HDuA-i7ZBmqV7ZnA3c_fvtXnx-?usp=sharing
- GitHub repo for the video: https://github.com/karpathy/ng-video-lecture
- Playlist of the whole Zero to Hero series so far: https://www.youtube.com/watch?v=VMj-3S1tku0&list=PLAqhIrjkxbuWI23v9cThsA9GvCAUhRvKZ
- nanoGPT repo: https://github.com/karpathy/nanoGPT
- my website: https://karpathy.ai
- my twitter: https://twitter.com/karpathy
- our Discord channel: https://discord.gg/3zy8kqD9Cp
- Attention is All You Need paper: https://arxiv.org/abs/1706.03762
- see https://github.com/karpathy/nanoGPT/blob/master/train.py for the full trainer.
"""


def graph(vid="kCc8FmEb1nY"):
    return {"lesson": {"id": f"lesson-{vid}", "title": "Let's build GPT"},
            "sources": [{"id": "src1", "kind": "video", "title": "t", "url": f"https://www.youtube.com/watch?v={vid}", "videoId": vid}],
            "steps": []}


def gh_zip(top: str, files: dict[str, bytes], symlink: str | None = None, evil: bool = False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(f"{top}/{name}")
            info.external_attr = (0o100755 << 16)  # executable in the archive: must not stay executable
            z.writestr(info, data)
        if symlink:
            info = zipfile.ZipInfo(f"{top}/link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, symlink)
        if evil:
            z.writestr(f"{top}/../../escape.txt", b"x")
            z.writestr(f"{top}/.git/config", b"[core]")
    return buf.getvalue()


NOTEBOOK = json.dumps({"cells": [], "nbformat": 4}).encode()


def transport(routes: dict[str, httpx.Response], hits: list[str]):
    def handler(req: httpx.Request) -> httpx.Response:
        hits.append(str(req.url))
        for prefix, resp in routes.items():
            if str(req.url).startswith(prefix):
                return resp
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIYAGI_LESSONS_DIR", str(tmp_path / "lessons"))


def test_find_karpathy_links_only_materials():
    found = find_resources(graph(), description=KARPATHY_DESC)
    assert [(r["kind"], r["name"]) for r in found] == [
        ("notebook", "colab-1JMLa53HDuA-.ipynb"), ("repo", "karpathy-ng-video-lecture"), ("repo", "karpathy-nanoGPT")]
    # the blob link into nanoGPT is covered by the repo download; socials/papers/playlist ignored
    assert found[2]["fetch"] == "https://codeload.github.com/karpathy/nanoGPT/zip/HEAD"


def test_find_fetches_description_once_and_caches(tmp_path):
    hits: list[str] = []
    page = '... "shortDescription":"Code: https://github.com/a/b\\nData: https://ex.com/d.csv" ...'
    c = transport({"https://www.youtube.com/watch": httpx.Response(200, text=page)}, hits)
    assert [r["name"] for r in find_resources(graph("abcdefghijk"), client=c)] == ["a-b", "d.csv"]
    assert [r["name"] for r in find_resources(graph("abcdefghijk"), client=c)] == ["a-b", "d.csv"]
    assert len(hits) == 1


def test_no_links_means_no_resources_message():
    assert find_resources(graph("zzzzzzzzzzz"), description="Follow me on https://twitter.com/x") == []
    assert download_resources(graph("zzzzzzzzzzz"), description="nothing here") == []
    assert download_summary([]) == NO_RESOURCES + "." == "No downloadable code linked from this video."


def test_download_repo_notebook_and_data(tmp_path):
    hits: list[str] = []
    z = gh_zip("ng-video-lecture-master", {"gpt.py": b"print('hi')\n", "input.txt": b"First Citizen:\n"},
               symlink="/etc/passwd", evil=True)
    c = transport({
        "https://codeload.github.com/karpathy/ng-video-lecture/zip/HEAD": httpx.Response(200, content=z),
        "https://drive.google.com/uc": httpx.Response(200, content=NOTEBOOK, headers={
            "content-type": "application/octet-stream", "content-disposition": 'attachment; filename="gpt-dev.ipynb"'}),
        "https://ex.com/d.csv": httpx.Response(200, text="a,b\n1,2\n", headers={"content-type": "text/csv"}),
    }, hits)
    desc = ("https://colab.research.google.com/drive/1JMLa53HDuA-i7ZBmqV7ZnA3c_fvtXnx- "
            "https://github.com/karpathy/ng-video-lecture https://ex.com/d.csv")
    folder = tmp_path / "lesson"
    out = download_resources(graph(), folder=folder, description=desc, client=c)
    by = {r["kind"]: r for r in out}
    tut = folder / "tutorial"
    assert by["notebook"]["name"] == "gpt-dev.ipynb" and (tut / "gpt-dev.ipynb").read_bytes() == NOTEBOOK
    repo = tut / "karpathy-ng-video-lecture"
    assert sorted(p.name for p in repo.iterdir()) == ["gpt.py", "input.txt"]  # no symlink, no .git, no escape
    assert not (tmp_path / "escape.txt").exists() and not (folder / "escape.txt").exists()
    assert not os.access(repo / "gpt.py", os.X_OK)  # never executable
    assert (tut / "d.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    s = download_summary(out)
    assert s.startswith("Saved gpt-dev.ipynb, karpathy-ng-video-lecture, d.csv to ") and s.endswith("/lesson/tutorial.")
    # second press: everything reused, only the (cheap) single files are skipped too
    hits.clear()
    again = download_resources(graph(), folder=folder, description=desc, client=c)
    assert all(r.get("cached") for r in again if r["kind"] == "repo") and not any("codeload" in h for h in hits)


def test_size_cap_and_html_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MAX_BYTES", 100)
    hits: list[str] = []
    c = transport({
        "https://ex.com/big.csv": httpx.Response(200, content=b"x" * 500),
        "https://drive.google.com/uc": httpx.Response(200, text="<html>Sign in</html>", headers={"content-type": "text/html"}),
    }, hits)
    out = download_resources(graph(), folder=tmp_path, client=c,
                             description="https://ex.com/big.csv https://colab.research.google.com/drive/1JMLa53HDuA-i7ZBmqV7ZnA3c_fvtXnx-")
    errs = {r["name"]: r.get("error", "") for r in out}
    assert "larger than" in errs["big.csv"] and "web page" in errs["colab-1JMLa53HDuA-.ipynb"]
    assert all(r["path"] is None for r in out) and "Couldn't download" in download_summary(out)


def test_gist(tmp_path):
    hits: list[str] = []
    meta = {"files": {"a.py": {"filename": "a.py", "content": "x = 1\n"}, "../evil sh": {"filename": "../evil sh", "content": "rm\n"}}}
    c = transport({"https://api.github.com/gists/d4dee566867f8291f086": httpx.Response(200, json=meta)}, hits)
    out = download_resources(graph(), folder=tmp_path, client=c, description="https://gist.github.com/karpathy/d4dee566867f8291f086")
    g = tmp_path / "tutorial" / "gist-d4dee56686"
    assert out[0]["files"] == 2 and sorted(p.name for p in g.iterdir()) == ["a.py", "evil_sh"]


def test_default_folder_is_the_lesson_folder(tmp_path):
    c = transport({"https://ex.com/d.csv": httpx.Response(200, text="a\n")}, [])
    out = download_resources(graph(), client=c, description="https://ex.com/d.csv")
    assert out[0]["path"].startswith(str(tmp_path / "lessons")) and "/tutorial/d.csv" in out[0]["path"]


def test_setup_card_offers_download(monkeypatch):
    monkeypatch.setattr("server.workspace.editor.editor_id", lambda: "vscode")
    items = [{"tool": "vscode", "label": "Visual Studio Code", "kind": "editor", "why": "x", "needed": True, "installed": True,
              "ok": True, "version": "1", "min_version": "", "install": {"method": "brew_cask", "command": "c", "url": "u"}}]
    res = find_resources(graph(), description=KARPATHY_DESC)
    card = setup_card(items, resources=res)
    assert "download" in card["actions"] and card["setup"]["actionLabels"]["download"] == "Download tutorial files"
    assert "karpathy-ng-video-lecture" in card["body"] and len(card["setup"]["resources"]) == 3
    assert "download" not in setup_card(items)["actions"]


def test_react_cached_lesson_graph_sources_are_scanned():
    g = load("516197461c0dacf3.json")
    g["sources"].append({"id": "src2", "kind": "repo", "title": "code", "url": "https://github.com/someone/react-food"})
    assert [r["name"] for r in find_resources(g, description="")] == ["someone-react-food"]


def test_hero_downloads_go_to_lessons_root_not_the_repo(tmp_path):
    from server.workspace.paths import HERO_WORKDIR_DEFAULT
    hero = load("aebc6b8fba02dac5.json")
    c = transport({"https://ex.com/d.csv": httpx.Response(200, text="a\n")}, [])
    out = download_resources(hero, folder=HERO_WORKDIR_DEFAULT, client=c, description="https://ex.com/d.csv")
    assert out[0]["path"].startswith(str(tmp_path / "lessons")) and not (HERO_WORKDIR_DEFAULT / "tutorial").exists()
