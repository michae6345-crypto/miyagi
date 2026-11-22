"""The hero workdir (demo/pinn-lab) must keep hitting its cached lesson, or the demo runs a live paid build.

A stray file in demo/pinn-lab changes the workdir fingerprint (folder name + file names + printed metric
names), so cache_key and find_cached both miss. This pins the folder to the hero cache.
"""

import json

from server.lesson import builder
from server.lesson.workdir import scan

HERO_DIR = builder.REPO_ROOT / "demo" / "pinn-lab"
HERO_CACHE = builder.CACHE_DIR / "aebc6b8fba02dac5.json"  # PINN diffusion (AXXnSzmpyoI)


def test_hero_workdir_fingerprint_matches_cached_lesson():
    cached = json.loads(HERO_CACHE.read_text(encoding="utf-8"))
    info = scan(str(HERO_DIR))
    assert builder.workdir_fingerprint(str(HERO_DIR), info) == cached["build"]["workdir_fp"], (
        f"demo/pinn-lab files changed ({sorted(info.files)}): the hero lesson would miss its cache"
    )


def test_hero_workdir_finds_cached_lesson():
    cached = json.loads(HERO_CACHE.read_text(encoding="utf-8"))
    vid = cached["sources"][0]["videoId"]
    found = builder.find_cached(vid, str(HERO_DIR), scan(str(HERO_DIR)))
    assert found is not None, "no cached lesson for the hero workdir: the demo would build live"
    hit = json.loads(found.read_text(encoding="utf-8"))
    assert hit["build"]["workdir_fp"] == cached["build"]["workdir_fp"]
