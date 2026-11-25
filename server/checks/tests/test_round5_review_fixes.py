"""Regression tests for the review of the round-5 step-check fixes: the hole count looks at the body the step names,
a brace inside quotes is not expanded, and .gitignore negations and nested files are read as git reads them.
Offline: no model, no network."""
from __future__ import annotations

import json

from server.checks import RunContext, blocks, evaluate_gate
from server.checks.evaluator import _git_ignores, _ignore_rules
from server.checks.model_files import _hole_count_claims


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _body(name, holes, box=(60.0, 40.0, 5.0)):
    return {"name": name, "tip": "Pocket", "features": [{"name": "Pad", "type": "PartDesign::Pad", "Length": 5.0}],
            "shape": {"valid": True, "bound_box": list(box), "holes": holes}}


_HOLE = {"diameter": 4.0, "center": [10.0, 20.0], "through": True}
_TWO = [_HOLE, {**_HOLE, "center": [50.0, 20.0]}]


def test_hole_count_only_on_the_body_the_step_names():
    text = "Pocket two 4 mm holes through the Plate"
    doc = {"bodies": [_body("Plate", _TWO), _body("Lid", [], box=(80.0, 50.0, 3.0))]}
    assert _hole_count_claims(text, doc) == []
    doc["bodies"][0]["shape"]["holes"] = [_HOLE]
    claims = _hole_count_claims(text, doc)
    assert len(claims) == 1 and claims[0].startswith("Plate has 1 hole")


def test_hole_count_with_no_body_named_reads_the_bodies_that_have_holes():
    text = "Pocket two 4 mm holes through it"
    doc = {"bodies": [_body("Plate", _TWO), _body("Lid", [], box=(80.0, 50.0, 3.0))]}
    assert _hole_count_claims(text, doc) == []
    # no body has a hole yet: the largest one is the part the step cuts
    doc["bodies"][0]["shape"]["holes"] = []
    claims = _hole_count_claims(text, doc)
    assert len(claims) == 1 and claims[0].startswith("Lid has 0 holes")


def test_a_quoted_brace_is_one_word():
    assert blocks._command_words("""echo '{"a":1,"b":2}'""") == ["echo", '{"a":1,"b":2}']
    assert blocks._command_words("git log '--pretty=format:{%h,%s}'") == ["git", "log", "--pretty=format:{%h,%s}"]
    assert blocks._command_words(r"echo \{a,b\}") == ["echo", "{a,b}"]
    assert blocks._command_words('echo "x{a,b}" y{c,d}') == ["echo", "x{a,b}", "yc", "yd"]
    assert blocks._command_words("FOO=1 sudo mkdir -p a/{x,y}") == ["mkdir", "-p", "a/x", "a/y"]


def test_gitignore_negation_and_nested_files(tmp_path):
    (tmp_path / "r" / ".git").mkdir(parents=True)
    _write(tmp_path, "r/.gitignore", "*.log\n!keep.log\nbuild/\n/top.txt\n")
    _write(tmp_path, "r/sub/.gitignore", "local.cfg\n")
    rules = _ignore_rules(str(tmp_path))[str(tmp_path / "r")]
    assert _git_ignores(rules, "debug.log") and _git_ignores(rules, "a/b/debug.log")
    assert not _git_ignores(rules, "keep.log") and not _git_ignores(rules, "a/keep.log")
    assert _git_ignores(rules, "build/out.js") and not _git_ignores(rules, "build")
    assert _git_ignores(rules, "top.txt") and not _git_ignores(rules, "a/top.txt")
    # a subfolder's .gitignore reaches only the files under that folder
    assert _git_ignores(rules, "sub/local.cfg") and _git_ignores(rules, "sub/x/local.cfg")
    assert not _git_ignores(rules, "local.cfg") and not _git_ignores(rules, "other/local.cfg")


def test_a_commit_of_a_file_gitignore_lets_back_in(tmp_path):
    step = {"id": "s", "instructions": "Stage the logs you keep and commit them.",
            "targets": [{"app": "Terminal", "match": "git commit -m \"Keep logs\""}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "committed", "app": "Terminal",
                        "pattern": r"\]\s+Keep\s+logs"}]}
    _write(tmp_path, "c/.gitignore", "*.log\n!keep.log\n")
    _write(tmp_path, "c/sub/.gitignore", "local.cfg\n")
    rows = ["me@mac c % git commit -m \"Keep logs\"", "[main 8c9d0e1] Keep logs",
            " create mode 100644 {path}", "me@mac c % "]

    def term(path):
        return {"Terminal": [r.format(path=path) for r in rows]}

    assert _gate(step, workdir=str(tmp_path), screen=term("keep.log"))["passed"]
    assert _gate(step, workdir=str(tmp_path), screen=term("local.cfg"))["passed"]
    assert not _gate(step, workdir=str(tmp_path), screen=term("debug.log"))["passed"]
    assert not _gate(step, workdir=str(tmp_path), screen=term("sub/local.cfg"))["passed"]


def test_scene_file_with_two_bodies_passes_the_gate(tmp_path):
    step = {"id": "s", "title": "", "instructions": "Pocket two 4 mm holes through the Plate.",
            "checks": [{"id": "c", "type": "file_contains", "label": "Pocket added", "file": "s.scene.json",
                        "pattern": r'"type":\s*"PartDesign::Pocket"'}]}
    plate = _body("Plate", _TWO)
    plate["features"].append({"name": "Pocket", "type": "PartDesign::Pocket", "Type": "ThroughAll"})
    _write(tmp_path, "s.scene.json", json.dumps({"bodies": [plate, _body("Lid", [], box=(80.0, 50.0, 3.0))]}))
    assert _gate(step, workdir=str(tmp_path))["passed"]
