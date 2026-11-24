"""Regression tests for the round-4 review: rules added in round 4 that failed steps the learner had finished.
Offline: no model, no network."""
from __future__ import annotations

from server.checks import RunContext, blocks, evaluate_gate


def _gate(step, **ctx):
    return evaluate_gate(step, RunContext(**ctx))


def _term(*rows):
    return {"Terminal": list(rows)}


def _scaffold_step(text):
    return {"id": "s", "title": "Scaffold", "instructions": text, "targets": [{"app": "Terminal", "match": "npm run dev"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Dev server ready", "app": "Terminal",
                        "pattern": r"[Rr]eady\s+in"}]}


def test_create_next_apps_yes_no_prompts_are_not_the_steps_options():
    step = _scaffold_step("Run npx create-next-app@latest shop and choose TypeScript, Tailwind and the App Router, "
                          "then npm run dev.")
    rows = ["me@mac p % npx create-next-app@latest shop",
            "✔ Would you like to use TypeScript? … No / Yes", "✔ Would you like to use ESLint? … No / Yes",
            "✔ Would you like to use Tailwind CSS? … No / Yes",
            "✔ Would you like your code inside a `src/` directory? … No / Yes",
            "✔ Would you like to use App Router? (recommended) … No / Yes",
            "me@mac p % npm run dev", "  ▲ Next.js 15.0.3", " ✓ Ready in 1342ms"]
    assert _gate(step, screen=_term(*rows))["passed"]


def test_a_prompt_the_step_makes_no_choice_for_takes_any_answer():
    rows = ["me@mac p % npm create vite@latest", "✔ Project name: … my-app", "✔ Select a framework: › React",
            "✔ Select a variant: › TypeScript + SWC", "me@mac p % npm run dev", "VITE v5.4.10  ready in 188 ms"]
    assert _gate(_scaffold_step("Run npm create vite@latest my-app choosing React, then npm run dev."),
                 screen=_term(*rows))["passed"]
    # a variant the step does choose, answered with another, is still another template
    gate = _gate(_scaffold_step("Run npm create vite@latest my-app choosing React and JavaScript, then npm run dev."),
                 screen=_term(*rows))
    assert not gate["passed"] and "TypeScript + SWC" in gate["checks"][-1]["detail"]


def test_keyframe_frame_numbers_are_not_the_render_range(tmp_path):
    step = {"id": "s", "title": "Render the bounce", "instructions": "Key the ball's Location at frame 1 and at frame "
            "48, go to frame 24 and key it on the floor, then Render > Render Animation.", "checks": [
                {"id": "c", "type": "file_exists", "label": "MP4 saved", "file": "bounce.mp4"}]}
    (tmp_path / "0001-0250.mp4").write_text("ftyp")
    assert _gate(step, workdir=str(tmp_path))["passed"]
    # the same keys with an end frame the render doesn't reach: still another render
    step["instructions"] = "Key the ball at frame 1 and at frame 48, set the End frame to 48, then Render Animation."
    gate = _gate(step, workdir=str(tmp_path))
    assert not gate["passed"] and "1-250" in gate["checks"][0]["detail"]


def test_revert_and_cherry_pick_take_the_commit_by_any_name():
    assert blocks.runs("git revert 3f2a1b9c", "git revert HEAD")
    assert blocks.runs("git revert HEAD", "git revert 3f2a1b9c")
    assert blocks.runs("git cherry-pick 9c8d7e6", "git cherry-pick add-syrup")
    assert blocks.runs("git rebase 5d6e7f8a", "git rebase main")  # main's tip by its hash
    assert not blocks.runs("git merge main", "git merge add-waffles")  # a branch the other way round still isn't
    step = {"id": "s", "run_command": "git revert HEAD", "targets": [{"app": "Terminal", "match": "git revert HEAD"}],
            "checks": [{"id": "c", "type": "screen_contains", "label": "Revert committed", "app": "Terminal",
                        "pattern": r"Revert\s+\""}]}
    rows = ["me@mac c % git revert 3f2a1b9c --no-edit", "[main 7a8b9c0] Revert \"Add syrup\"",
            " 1 file changed, 2 deletions(-)", "me@mac c % "]
    assert _gate(step, screen=_term(*rows))["passed"]
