"""Server-side lesson checks (lesson_safety.py, lesson_patterns.py) and LESSON_AUTO_APPROVE_VALIDATED, offline.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import copy
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

CLOUD = Path(__file__).resolve().parents[1]
ADMIN_TOKEN = "miyagi-tests-admin-0123456789-abcdefghijklmnop"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
VID = "dQw4w9WgXcQ"

CLEAN = {
    "title": "Train a tiny CNN",
    "files": ["train.py"],
    "sources": [{"id": "v", "type": "video", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}],
    "steps": [
        {"id": "s1", "title": "Write the model", "file": "src/model.py", "start": 0, "end": 60,
         "run_command": "python train.py",
         "targets": [{"app": "Code", "file": "src/model.py", "match": "class Net(nn.Module)"}],
         "checks": [{"id": "c1", "type": "screen_contains", "pattern": r"def\s+forward\s*\("},
                    {"id": "c2", "type": "metric_threshold", "metric_pattern": r"loss[=:]\s*(?P<value>\d+\.?\d*)",
                     "op": "<", "value": 1.0}],
         "precision_checks": [{"id": "p1", "type": "file_contains", "file": "src/model.py", "pattern": r"import\s+torch"}]},
    ],
}


def with_step(**changes) -> dict:
    lesson = copy.deepcopy(CLEAN)
    lesson["steps"][0].update(changes)
    return lesson


# The engine's own lists (server/safety/tests/test_patterns.py on integration/live): refused and kept patterns.
CATASTROPHIC = [r"(?:a?){30}a{30}", r"(a{1,32}){1,32}$", r".*.*.*.*.*=", r"\s*\s*\s*\s*\s*x$",
                r"\d+\.?\d*\.?\d*\.?\d*\.?\d*\.?\d*z", r"\w*\w*\w*!", r"(x+)+y", r"(a|aa)+$", r"(a|a?)+$", r"(\d+){3}",
                r"(a*)*$", r"(?:(?:a+)?)+", r"(\w+\s?)+$", r"(?:\s*\w*)+x", r"(?:x{1,9}){1,9}", r"(?:a|b|ab)+c",
                r"[\s\S]*[\s\S]*!", r".*.*=", r"\S*\S*x", r"(?s).*.*!", r".{0,500}.{0,500}.{0,500}!", r"abc.*.*.*=",
                r"(?i)[a-z]*[A-Z]*[a-z]*!"]
LESSON_PATTERNS = [
    r"\d+\.?\d*", r"loss[=:]\s*(?P<value>\d+\.?\d*)", r"(\d{1,3}\.){3}\d{1,3}", r"def\s+\w+\s*\(",
    r"\[\s*-\s*1\.[0O]\s*,?\s*-?\s*[0O]\.[0O]\s*,?\s*1\.[0O]\s*\]", r"\d+/\d+\s*\S*\s*\d+ms/step|Epoch|ms/step",
    r"useEffect\(|\[\s*\]\s*\)\s*;?\s*\n?.*useEffect", r"print\(.*\)", r"(\w+\.)?\w+\(",
    r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", r"Epoch\s+(?P<step>\d+).*loss[=:]\s*(?P<value>[\d.]+)",
    r"Usage:\s*\S+.*\[PATH\]", r"\bimport\s+numpy\s+as\s+np\b", r"name.{0,3}:.{0,3}\S+.{0,40}modified",
]


@pytest.fixture
def mods(monkeypatch):
    monkeypatch.syspath_prepend(str(CLOUD))
    for mod in ("lesson_safety", "lesson_patterns"):
        sys.modules.pop(mod, None)
    return importlib.import_module("lesson_safety"), importlib.import_module("lesson_patterns")


@pytest.mark.parametrize("pattern", CATASTROPHIC)
def test_catastrophic_patterns_are_refused(mods, pattern):
    assert mods[1].static_problem(pattern)


@pytest.mark.parametrize("pattern", LESSON_PATTERNS)
def test_real_lesson_patterns_pass(mods, pattern):
    assert mods[1].static_problem(pattern) is None


def test_pattern_basics(mods):
    p = mods[1]
    assert p.static_problem("a" * 401) and p.static_problem(None) and p.static_problem("(unclosed").startswith("invalid")
    assert p.static_problem(r"[a-z]+[A-Z]+[a-z]+!") is None and p.static_problem(r"[a-z]+[A-Z]+[a-z]+!", re.IGNORECASE)


def test_clean_lesson_has_no_problems(mods):
    assert mods[0].review(CLEAN) == []


@pytest.mark.parametrize("lesson,needle", [
    (with_step(file=".git/hooks/pre-commit"), ".git/"),
    (with_step(file="node_modules/x/index.js"), "node_modules/"),
    (with_step(file="Venv/bin/activate"), "Venv/"),
    (with_step(file="a\\b.py"), "POSIX"),
    (with_step(files=["ok.py", "../escape.py"]), "unsafe path"),
    (with_step(targets=[{"file": "/etc/passwd", "match": "x"}]), "absolute"),
    (with_step(targets=[{"match": r"(x+)+y"}]), "nested repetition"),
    (with_step(targets=[{"match": "x"}] * 25), "over 24"),
    (with_step(checks=[{"id": "c", "type": "screen_contains", "pattern": r"(a|aa)+$"}]), "c: pattern"),
    (with_step(checks=[{"id": "c", "type": "screen_contains", "pattern": "(unclosed"}]), "invalid pattern"),
    (with_step(checks=[{"id": "c", "type": "metric_threshold", "metric_pattern": r".*.*="}]), "metric_pattern"),
    (with_step(precision_checks=[{"id": "p", "type": "file_exists", "file": "~/x"}]), "home"),
    (with_step(checks=[{"id": f"c{i}", "type": "screen_contains", "pattern": "x"} for i in range(25)]), "over 24"),
    ({**CLEAN, "sources": [{"id": "v", "url": "http://example.com"}]}, "not https"),
    ({**CLEAN, "files": ["../x"]}, "goes up"),
    ({**CLEAN, "lesson": {"workdir": "/Users/x"}}, "workdir"),
])
def test_engine_repairs_are_problems(mods, lesson, needle):
    problems = mods[0].review(lesson)
    assert problems and any(needle in p for p in problems), problems


def test_a_target_match_may_be_literal_text(mods):
    assert mods[0].review(with_step(targets=[{"match": "print(("}])) == []


def test_pattern_budget_per_lesson(mods):
    steps = [{"id": f"s{i}", "title": "t", "checks": [{"id": f"c{j}", "type": "screen_contains", "pattern": "x"}
                                                        for j in range(20)]} for i in range(21)]
    assert any("over 400" in p for p in mods[0].review({"title": "t", "steps": steps}))


# --------------------------------------------------------------------------- LESSON_AUTO_APPROVE_VALIDATED end to end

@pytest.fixture
def make_cloud(tmp_path, monkeypatch):
    clients = []

    def make(**env):
        base = {"ADMIN_TOKEN": ADMIN_TOKEN, "DB_PATH": str(tmp_path / "miyagi.db"),
                "ANTHROPIC_API_KEY": "fake-upstream-key", "UPSTREAM_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages",
                "FREE_LESSON_BUILDS_PER_MONTH": "10", "LESSON_AUTO_APPROVE_VALIDATED": "1", "LESSON_AUTO_APPROVE_N": "0"}
        for k, v in {**base, **env}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.syspath_prepend(str(CLOUD))
        for mod in ("app", "store", "lesson_safety", "lesson_patterns"):
            sys.modules.pop(mod, None)
        app_mod = importlib.import_module("app")
        from fastapi.testclient import TestClient

        client = TestClient(app_mod.app)
        client.__enter__()
        clients.append(client)
        return client, app_mod

    yield make
    for c in clients:
        c.__exit__(None, None, None)
    for mod in ("app", "store", "lesson_safety", "lesson_patterns"):
        sys.modules.pop(mod, None)


def install(client) -> dict:
    r = client.post("/v1/install", json={"app": "test", "os": "darwin", "arch": "arm64"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def share(client, h, lesson, vid=VID, schema=1):
    assert client.post(f"/v1/lessons/{vid}/build", headers=h).status_code == 200
    return client.put(f"/v1/lessons/{vid}", headers=h, content=json.dumps({"schema": schema, "lesson": lesson}))


def served(client, h, vid=VID):
    r = client.get(f"/v1/lessons/{vid}?schema=1", headers=h)
    return r.json()["lesson"] if r.status_code == 200 else None


def test_a_lesson_that_passes_is_approved_and_served_to_everyone(make_cloud):
    client, _ = make_cloud()
    builder, learner = install(client), install(client)
    r = share(client, builder, CLEAN)
    assert r.status_code == 201 and r.json()["status"] == "approved" and r.json()["problems"] == []
    assert served(client, learner) == CLEAN
    # a second, different upload for the same video does not replace the served one
    other = with_step(title="Something else")
    r = share(client, install(client), other)
    assert r.json()["status"] == "pending" and served(client, learner) == CLEAN


def test_a_lesson_that_fails_stays_pending(make_cloud):
    client, _ = make_cloud()
    builder = install(client)
    bad = with_step(checks=[{"id": "c", "type": "screen_contains", "pattern": r"(x+)+y"}])
    r = share(client, builder, bad)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert any("nested repetition" in p for p in r.json()["problems"])
    assert served(client, install(client)) is None
    pending = client.get("/admin/lessons/pending", headers=ADMIN).json()["pending"]
    assert len(pending) == 1 and pending[0]["problems"]
    # an operator can still approve it after reading it
    r = client.post(f"/admin/lessons/{VID}/approve", headers=ADMIN, json={"hash": pending[0]["hash"]})
    assert r.status_code == 200 and served(client, builder) == bad


def test_auto_approve_off_keeps_everything_pending(make_cloud):
    client, _ = make_cloud(LESSON_AUTO_APPROVE_VALIDATED="0")
    r = share(client, install(client), CLEAN)
    assert r.json()["status"] == "pending" and served(client, install(client)) is None


def test_revoke_sticks(make_cloud):
    client, app_mod = make_cloud()
    builder = install(client)
    assert share(client, builder, CLEAN).json()["status"] == "approved"
    r = client.post(f"/admin/lessons/{VID}/revoke", headers=ADMIN, json={})
    assert r.status_code == 200 and r.json() == {"video_id": VID, "revoked": [1], "status": "revoked"}
    assert served(client, builder) is None
    # the same uploader re-uploading, the same lesson from someone else, or a tweaked one: none is auto-approved
    r = client.put(f"/v1/lessons/{VID}", headers=builder, content=json.dumps({"schema": 1, "lesson": CLEAN}))
    assert r.json()["status"] == "pending"
    assert share(client, install(client), CLEAN).json()["status"] == "pending"
    assert share(client, install(client), with_step(title="tweaked")).json()["status"] == "pending"
    assert served(client, builder) is None
    statuses = {r["status"] for r in app_mod.store._q("SELECT status FROM lesson_candidates WHERE video_id = ?", (VID,))}
    assert "revoked" in statuses and "approved" not in statuses
    # the revocation survives a restart and the original uploader deleting their account
    assert client.post("/v1/account/delete", headers=builder, json={}).status_code == 200
    client2, _ = make_cloud()
    assert share(client2, install(client2), CLEAN).json()["status"] == "pending"
    assert served(client2, install(client2)) is None
    usage = client2.get("/admin/usage", headers=ADMIN).json()["lessons"]
    assert usage["cached"] == 0
    # an operator's explicit approve still serves one
    pending = client2.get("/admin/lessons/pending", headers=ADMIN).json()["pending"]
    r = client2.post(f"/admin/lessons/{VID}/approve", headers=ADMIN, json={"hash": pending[0]["hash"]})
    assert r.status_code == 200 and served(client2, install(client2)) is not None


def test_revoke_one_schema_and_bad_input(make_cloud):
    client, _ = make_cloud(LESSON_SCHEMAS="1,2")
    h = install(client)
    assert share(client, h, CLEAN, schema=1).json()["status"] == "approved"
    assert share(client, h, CLEAN, schema=2).json()["status"] == "approved"
    r = client.post(f"/admin/lessons/{VID}/revoke", headers=ADMIN, json={"schema": 2})
    assert r.json()["revoked"] == [2]
    assert client.get(f"/v1/lessons/{VID}?schema=1", headers=h).status_code == 200
    assert client.get(f"/v1/lessons/{VID}?schema=2", headers=h).status_code == 404
    assert client.post(f"/admin/lessons/{VID}/revoke").status_code == 401
    assert client.post("/admin/lessons/too-short/revoke", headers=ADMIN, json={}).status_code == 400
    # no body at all revokes every schema
    assert client.post(f"/admin/lessons/{VID}/revoke", headers=ADMIN).json()["revoked"] == [1]
