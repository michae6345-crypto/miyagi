"""Regression tests for the second round-4 review: correct work the round-4 fixes failed (an option's value read as
the merged branch, a dev server restarted after an error, a frame rate read as the render's length, a TypeScript
generic call), and a push of another branch hiding a failed push. Offline: no model, no network."""
from __future__ import annotations

from server.checks import RunContext, blocks, evaluate_gate


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


# -- merge / rebase options that take a value ------------------------------------------------------------------------

def test_a_merge_options_value_is_not_the_merged_branch():
    target = "git merge add-waffles"
    assert blocks.runs('git merge -m "Merge add-waffles" add-waffles', target)
    assert blocks.runs("git merge -X theirs add-waffles", target)
    assert blocks.runs("git merge -s ours add-waffles", target)
    assert blocks.runs("git merge --no-ff -m x add-waffles", target)
    assert blocks.runs("git merge --strategy-option theirs origin/add-waffles", target)
    # the branch is still read past the options: the other way round is still another merge
    assert not blocks.runs('git merge -m "Merge main" main', target)
    assert not blocks.runs("git merge -X theirs main", target)
    assert blocks.runs("git rebase --onto main feature", "git rebase feature")
    assert not blocks.runs("git rebase --onto feature main", "git rebase feature")


def test_a_merge_with_a_message_passes_the_merge_step():
    step = {"id": "s", "run_command": "git merge add-waffles",
            "targets": [{"app": "Terminal", "match": "git merge add-waffles"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Merged", "app": "Terminal",
                        "pattern": r"Merge made by|Fast-forward"}]}
    rows = ['me@mac c % git merge -m "Merge add-waffles" add-waffles', "Merge made by the 'ort' strategy.",
            " waffles.md | 3 +++", "me@mac c % "]
    assert _gate(step, screen=_term(*rows))["passed"]
    rows = ["me@mac c % git merge -X theirs add-waffles", "Merge made by the 'ort' strategy.", "me@mac c % "]
    assert _gate(step, screen=_term(*rows))["passed"]


# -- a dev server restarted after an error ----------------------------------------------------------------------------

_DEV_STEP = {"id": "s", "run_command": "npm run dev", "targets": [{"app": "Terminal", "match": "npm run dev"}],
             "checks": [{"id": "c", "type": "screen_absent", "label": "No compile errors in the terminal",
                         "app": "Terminal", "pattern": r"ERR!|Failed\s+to\s+compile"}]}
_BROKEN = ["me@mac a % npm run dev", "VITE v5.4.10  ready in 296 ms",
           "4:31:52 PM [vite] Internal server error: /a/src/App.jsx: Unterminated JSX contents. (8:4)", "^C"]


def test_a_dev_server_restarted_cleanly_after_an_error():
    clean = ["me@mac a % npm run dev", "VITE v5.4.10  ready in 210 ms", "  ➜  Local:   http://localhost:5173/"]
    assert _gate(_DEV_STEP, screen=_term(*_BROKEN, *clean))["passed"]
    yarn = ["me@mac a % yarn dev", "VITE v5.4.10  ready in 210 ms"]  # restarted through another runner
    assert _gate(_DEV_STEP, screen=_term(*_BROKEN, *yarn))["passed"]


def test_a_dev_server_error_still_fails_when_the_server_was_not_restarted():
    other = ["me@mac a % npm run build", "vite v5.4.10 building for production..."]
    assert not _gate(_DEV_STEP, screen=_term(*_BROKEN, *other))["passed"]
    restarted_broken = [*_BROKEN[:3], "^C", *_BROKEN[:3]]  # restarted, and the newest run shows the error again
    assert not _gate(_DEV_STEP, screen=_term(*restarted_broken))["passed"]


# -- a frame rate is not the render's length -------------------------------------------------------------------------

def _render_step(text):
    return {"id": "s", "title": "Render the animation", "instructions": text, "checks": [
        {"id": "c", "type": "file_exists", "label": "MP4 saved", "file": "bounce.mp4"}]}


def test_frames_per_second_is_not_the_frame_range(tmp_path):
    _write(tmp_path, "0001-0250.mp4", "ftyp")
    step = _render_step("Set the frame rate to 24 frames per second, then Render Animation.")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    step = _render_step("Give the jump 12 frames of anticipation, then Render Animation.")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    step = _render_step("Key the ball every 10 frames, then Render Animation.")
    assert _gate(step, workdir=str(tmp_path))["passed"]


def test_a_render_length_in_frames_is_still_read(tmp_path):
    _write(tmp_path, "0001-0048.mp4", "ftyp")
    step = _render_step("Render 96 frames of animation at 24 frames per second.")
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "1-48" in gate["checks"][0]["detail"]
    _write(tmp_path, "0001-0096.mp4", "ftyp")
    assert _gate(step, workdir=str(tmp_path))["passed"]


# -- a called name with TypeScript type arguments ---------------------------------------------------------------------

def _called(file, pattern, label):
    return {"id": "s", "checks": [{"id": "c", "type": "file_contains", "label": label, "file": file,
                                   "pattern": pattern}]}


def test_a_typescript_generic_call_is_a_call(tmp_path):
    step = _called("Counter.tsx", "useState", "useState called")
    _write(tmp_path, "Counter.tsx", "const [n, setN] = useState<number>(0);\n")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _write(tmp_path, "Counter.tsx", "const [m, setM] = useState<Map<string, number>>(new Map());\n")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    _write(tmp_path, "Counter.tsx", "import { useState } from 'react';\nconst f = useState;\n")
    assert not _gate(step, workdir=str(tmp_path))["passed"]


def test_an_optional_chained_call_is_a_call(tmp_path):
    step = _called("Form.tsx", "onSave", "onSave called")
    _write(tmp_path, "Form.tsx", "props.onSave?.(value);\n")
    assert _gate(step, workdir=str(tmp_path))["passed"]


# -- a push of another branch does not get past a failed push ---------------------------------------------------------

_PUSH_STEP = {"id": "s", "run_command": "git push origin main",
              "targets": [{"app": "Terminal", "match": "git push origin main"}],
              "checks": [{"id": "c", "type": "screen_absent", "label": "No Git errors", "app": "Terminal",
                          "pattern": r"error:|! \[rejected\]"}]}
_PUSH_FAILED = ["me@mac c % git push origin main", " ! [rejected]        main -> main (fetch first)",
                "error: failed to push some refs to 'github.com:ada/cookbook.git'"]


def test_a_push_of_another_branch_does_not_hide_a_failed_push():
    feature = ["me@mac c % git push origin feature", " * [new branch]      feature -> feature", "me@mac c % "]
    assert not _gate(_PUSH_STEP, screen=_term(*_PUSH_FAILED, *feature))["passed"]
    again = ["me@mac c % git pull --rebase origin main", "Successfully rebased and updated refs/heads/main.",
             "me@mac c % git push -u origin main", "   a1b2c3d..d4e5f6a  main -> main", "me@mac c % "]
    assert _gate(_PUSH_STEP, screen=_term(*_PUSH_FAILED, *again))["passed"]
