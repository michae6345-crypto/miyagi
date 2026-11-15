"""server.screen.target: Haiku set-of-marks picker, fully OFFLINE (stub client, recorded fixtures).

What these tests can and can't say:
- They check the pipeline around the model: the candidate set (is the right target offered as a
  mark? are breadcrumb / tab bar / hover tooltip / side panel never offered?), the image (crop,
  size, tags), the request (model, tokens, no sampling params), and how an answer maps back to a
  spotlight rect (merge, confidence floor, cache, budget, timeout, bad JSON).
- They can't measure Haiku's own pick accuracy: the stub answers with the id a perfect picker would
  give (found from the ground truth), or with a canned answer.

`test_offline_accuracy_report` prints the table (pytest -s).
"""
import asyncio
import base64
import io
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image

from server.screen import match as M
from server.screen import target as T
from server.screen.types import Rect, ScreenObservation

FIX = Path(__file__).resolve().parent.parent / "fixtures"
TAB = re.compile(r"^\W{0,2}[\w.-]+\.[A-Za-z]\w{0,7}(?:\s+(?:\d{1,3}|[•●○xX×✕]))*\W{0,2}$")   # an editor tab


def _load(name):
    obs = ScreenObservation.from_dict(json.loads((FIX / f"{name}.ocr.json").read_text()))
    return Image.open(FIX / f"{name}.png"), obs


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)     # never a real call from these tests
    monkeypatch.delenv("MIYAGI_VISION_MAX_CALLS_PER_MIN", raising=False)
    monkeypatch.delenv("MIYAGI_VISION_MIN_CONF", raising=False)
    T.reset()
    yield
    T.reset()


class Stub:
    """AsyncAnthropic look-alike: `.with_options(...).messages.create(**kw)`."""

    def __init__(self, answer='{"ids": [], "confidence": 0.9, "why": "x"}', delay=0.0, exc=None,
                 stop_reason="end_turn"):
        self.answer, self.delay, self.exc, self.stop_reason = answer, delay, exc, stop_reason
        self.calls: list[dict] = []
        self.options: list[dict] = []
        self.messages = self

    def with_options(self, **kw):
        self.options.append(kw)
        return self

    async def create(self, **kw):
        self.calls.append(kw)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        text = self.answer(kw) if callable(self.answer) else self.answer
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=self.stop_reason,
                               usage=SimpleNamespace(input_tokens=2000, output_tokens=25))


def run(coro):
    return asyncio.run(coro)


def ans(ids, conf=0.9, why="ok"):
    return json.dumps({"ids": ids, "confidence": conf, "why": why})


# ---------------------------------------------------------------------- labelled cases

def row(cy, h=18.0):
    """Truth: the editor row centred at `cy`."""
    return ("row", cy, h)


def box(x, y, w, h):
    """Truth: this small target (a line / an icon, not a region): the pick must contain its centre
    and stay small (at most 4x its size each way)."""
    return ("box", Rect(x, y, w, h))


def region(name):
    return ("region", name)


CASES = [
    # fixture, intent, truth (None = nothing on screen matches: the only right answer is no box)
    ("vscode_window_calc_clean", "the line where the learner types `def add(a, b):` in calculator.py", row(188)),
    ("vscode_window_calc_clean", "line 6 of calculator.py, the blank line after add()", row(224)),
    ("vscode_window_calc_clean", "the Terminal menu in the menu bar", region("terminal_menu")),
    ("vscode_window_calc_clean", "the VS Code integrated terminal panel", None),
    ("vscode_window_calc_hover", "the line `def subtract(a, b):` in calculator.py", row(260)),
    ("vscode_window_calc_hover", "the line `print(add(2, 3))` in calculator.py", row(530)),
    ("vscode_fullscreen_scrolled", "the line where `pde_residual` is defined", row(138)),
    ("vscode_fullscreen_scrolled", "the VS Code integrated terminal panel", region("terminal")),
    ("vscode_fullscreen_scrolled", "the terminal line with the command the learner ran",
     box(310, 832, 340, 22)),
    ("vscode_fullscreen_top", "the line where the learner types `def sample_collocation(n: int):`", row(660)),
    ("vscode_fullscreen_top", "the blank line 40 under `return x, t`", row(768)),
    ("vscode_fullscreen_top", "the Run button", None),
    ("vscode_terminal_flat", "the line `return u_t + beta * u_x` in pinn_convection.py", row(589)),
    ("vscode_terminal_flat", "the VS Code integrated terminal panel", None),
    # Michael's real screen: calculator.py with 4 short lines -> Vision reads no line numbers
    ("vscode_lesson_calculator", "the line where the learner types `print(add(2, 3))` in calculator.py",
     row(249, 22)),
    ("vscode_lesson_calculator", "the Run button", box(1400, 112, 26, 24)),
    ("vscode_lesson_calculator", "the VS Code integrated terminal panel", None),
]


def _matches(c: T.Cand, truth) -> bool:
    kind = truth[0]
    if kind == "row":
        _, cy, h = truth
        return c.kind in ("code", "blank") and abs(c.rect.cy - cy) <= h / 2
    if kind == "region":
        return c.kind == "region" and c.text == truth[1]
    r = truth[1]   # a panel region never counts as this small target; a control region (run ▷) may
    return c.rect.contains_point(r.cx, r.cy) and (c.kind != "region" or c.rect.w * c.rect.h <= 16 * r.w * r.h)


def _truth_id(cands, truth) -> int | None:
    hits = [c for c in cands if _matches(c, truth)]
    return hits[0].id if len(hits) == 1 else None


def _rect_ok(rect: dict, truth) -> bool:
    r = Rect.from_any(rect)
    kind = truth[0]
    if kind == "row":
        _, cy, h = truth
        return abs(r.cy - cy) <= h / 2 and r.h <= 2.5 * h
    if kind == "region":
        return True
    t = truth[1]
    return r.contains_point(t.cx, t.cy) and r.w <= 4 * t.w + 20 and r.h <= 4 * t.h


@pytest.mark.parametrize("name,intent,truth", CASES, ids=[f"{c[0]}:{c[1][:30]}" for c in CASES])
def test_case(name, intent, truth):
    frame, obs = _load(name)
    cands = T.build_candidates(obs, "Code")
    if truth is None:
        # a right picker has nothing to choose; when it says so, no box
        stub = Stub(ans([], 0.95, "not on screen"))
        assert run(T.pick_target(frame, obs, intent, client=stub)) is None
        if "terminal panel" in intent:
            assert not any(c.kind == "region" and c.text == "terminal" for c in cands)
            assert not any(c.region == "terminal" for c in cands)
        if "Run button" in intent:
            assert not any(c.kind == "toolbar" or c.text == "run_button" for c in cands)
        return
    tid = _truth_id(cands, truth)
    assert tid is not None, f"target not offered exactly once as a mark:\n{T.listing(cands)}"
    stub = Stub(ans([tid], 0.9))
    res = run(T.pick_target(frame, obs, intent, client=stub))
    assert res is not None and res["box_ids"] == [tid]
    assert _rect_ok(res["rect"], truth), res
    assert f"\n{tid} [" in stub.calls[0]["messages"][0]["content"][1]["text"]


def _offline_report() -> dict:
    rows, offered, mapped, none_ok = [], 0, 0, 0
    targets = [c for c in CASES if c[2] is not None]
    for name, intent, truth in CASES:
        T.reset()
        frame, obs = _load(name)
        cands = T.build_candidates(obs, "Code")
        if truth is None:
            res = run(T.pick_target(frame, obs, intent, client=Stub(ans([], 0.95))))
            ok = res is None
            none_ok += ok
            rows.append((name, intent, "none", "-", "ok" if ok else "BOX"))
            continue
        tid = _truth_id(cands, truth)
        offered += tid is not None
        res = run(T.pick_target(frame, obs, intent, client=Stub(ans([tid], 0.9)))) if tid else None
        ok = bool(res) and _rect_ok(res["rect"], truth)
        mapped += ok
        rows.append((name, intent, tid, len(cands), "ok" if ok else "MISS"))
    return {"cases": len(CASES), "targets": len(targets), "offered": offered, "mapped": mapped,
            "none_cases": len(CASES) - len(targets), "none_ok": none_ok, "rows": rows}


def test_offline_accuracy_report(capsys):
    rep = _offline_report()
    with capsys.disabled():
        print(f"\noffline: target offered as a mark {rep['offered']}/{rep['targets']}, "
              f"id->rect exact {rep['mapped']}/{rep['targets']}, "
              f"nothing-to-box cases with no box {rep['none_ok']}/{rep['none_cases']}")
        for r in rep["rows"]:
            print("  ", r)
    assert rep["offered"] == rep["targets"] and rep["mapped"] == rep["targets"] and rep["none_ok"] == rep["none_cases"]


# ---------------------------------------------------------------------- never offered

@pytest.mark.parametrize("name", ["vscode_window_calc_clean", "vscode_window_calc_hover", "vscode_fullscreen_scrolled",
                                  "vscode_fullscreen_top", "vscode_terminal_flat", "vscode_lesson_calculator",
                                  "vscode_window_notes_inline_chat"])
def test_chrome_tooltip_and_side_panel_are_never_marks(name):
    _frame, obs = _load(name)
    cands = T.build_candidates(obs, "Code")
    for c in cands:
        if c.kind == "region":
            continue
        assert not M.is_breadcrumb(c.text), c
        assert not (c.kind == "text" and TAB.match(c.text.strip()) and c.region != "explorer"), c
    hover = [b.rect for b in obs.blocks if b.role in ("hover", "widget")]
    for h in hover:   # tooltip / inline-chat text never becomes a mark (the row under it may, flagged occluded)
        assert not any(c.kind == "text" and h.contains(c.rect) for c in cands)
    if name == "vscode_lesson_calculator":
        texts = " ".join(c.text for c in cands)
        assert "Chat" not in texts and "Sessions" not in texts and "Tip:" not in texts   # side panel
        assert "calculator.py X" not in texts                                            # tab
        assert not any(c.kind == "region" and c.text == "explorer" and c.rect.x2 > 550 for c in cands)
        assert sum(c.kind == "code" for c in cands) == 2                                  # lines 1 and 3


def test_hover_row_is_offered_but_flagged():
    _frame, obs = _load("vscode_window_calc_hover")
    l8 = [c for c in T.build_candidates(obs, "Code") if c.line == 8]
    assert l8 and l8[0].occluded
    assert "partly under a tooltip" in T.listing(l8)


def test_blank_rows_have_file_line_numbers():
    _frame, obs = _load("vscode_window_calc_clean")
    blanks = {c.line: c for c in T.build_candidates(obs, "Code") if c.kind == "blank"}
    assert {2, 3, 6, 7, 10, 11, 14, 15, 20, 21} <= set(blanks)
    assert abs(blanks[6].rect.cy - (215 + 9)) <= 4


# ---------------------------------------------------------------------- request, image, answer

def test_request_is_one_small_haiku_call_with_marked_image():
    frame, obs = _load("vscode_fullscreen_scrolled")
    stub = Stub(ans([1], 0.9))
    res = run(T.pick_target(frame, obs, "the VS Code integrated terminal panel", client=stub))
    assert res["kind"] == "region" and res["region"] == "terminal" and res["box_ids"] == [1]
    assert len(stub.calls) == 1
    kw = stub.calls[0]
    assert kw["model"] == "claude-haiku-5-5"
    assert kw["max_tokens"] <= 200
    assert kw["thinking"] == {"type": "disabled"} and kw["output_config"] == {"effort": "low"}
    assert not {"temperature", "top_p", "top_k"} & set(kw)            # Haiku 5.5 rejects them
    img_block, text_block = kw["messages"][0]["content"]
    img = Image.open(io.BytesIO(base64.b64decode(img_block["source"]["data"])))
    assert img.format == "JPEG" and max(img.size) <= 1280
    assert "Request: the VS Code integrated terminal panel" in text_block["text"]
    assert "1 [region] terminal" in text_block["text"]
    assert stub.options[0]["timeout"] == 2.5 and stub.options[0]["max_retries"] == 0
    assert res["input_tokens"] == 2000 and res["cost_usd"] == pytest.approx(2000 * 0.1e-6 + 25 * 0.5e-6, abs=1e-6)


def test_rect_is_in_screen_points_and_padded_rows():
    frame, obs = _load("vscode_window_calc_clean")
    cands = T.build_candidates(obs, "Code")
    l4 = next(c for c in cands if c.line == 4)
    res = run(T.pick_target(frame, obs, "def add", client=Stub(ans([l4.id]))))
    r = res["rect"]
    assert abs(r["y"] - (l4.rect.y - 2)) < 0.2 and abs(r["h"] - (l4.rect.h + 4)) < 0.2
    assert res["label"] == "code L4: def add(a, b):" and res["line"] == 4


def test_adjacent_ids_merge_far_ids_dont():
    frame, obs = _load("vscode_window_calc_clean")
    cands = T.build_candidates(obs, "Code")
    by_line = {c.line: c for c in cands if c.line}
    res = run(T.pick_target(frame, obs, "the add function", client=Stub(ans([by_line[4].id, by_line[5].id]))))
    assert res["box_ids"] == [by_line[4].id, by_line[5].id]
    assert res["rect"]["h"] > 2 * by_line[4].rect.h
    T.reset()
    res = run(T.pick_target(frame, obs, "add", client=Stub(ans([by_line[4].id, by_line[22].id, 3]))))
    assert res["box_ids"] == [by_line[4].id]                         # L22 far away, 3 = a region


def test_low_confidence_no_ids_unknown_ids_refusal_give_none():
    frame, obs = _load("vscode_window_calc_clean")
    l4 = next(c for c in T.build_candidates(obs, "Code") if c.line == 4)
    for answer in (ans([l4.id], 0.4), ans([], 0.9), ans([9999], 0.9), "I think it's line 4", "{bad json"):
        T.reset()
        assert run(T.pick_target(frame, obs, "def add", client=Stub(answer))) is None, answer
    T.reset()
    assert run(T.pick_target(frame, obs, "def add", client=Stub(ans([l4.id]), stop_reason="refusal"))) is None


def test_min_conf_from_env(monkeypatch):
    frame, obs = _load("vscode_window_calc_clean")
    l4 = next(c for c in T.build_candidates(obs, "Code") if c.line == 4)
    monkeypatch.setenv("MIYAGI_VISION_MIN_CONF", "0.3")
    assert run(T.pick_target(frame, obs, "def add", client=Stub(ans([l4.id], 0.4)))) is not None


def test_parse_answer_variants():
    assert T.parse_answer('```json\n{"ids": [12, "#13", 12], "confidence": 0.8, "why": "w"}\n```') == ([12, 13], 0.8, "w")
    assert T.parse_answer('{"id": 7, "confidence": 2}') == ([7], 1.0, "")
    assert T.parse_answer('{"ids": null, "confidence": "high"}') == ([], 0.0, "")
    assert T.parse_answer("none") is None


# ---------------------------------------------------------------------- cache, budget, timeout, key

def test_cache_by_frame_and_intent():
    frame, obs = _load("vscode_window_calc_clean")
    l4 = next(c for c in T.build_candidates(obs, "Code") if c.line == 4)
    stub = Stub(ans([l4.id]))
    a = run(T.pick_target(frame, obs, "def add", client=stub))
    b = run(T.pick_target(frame, obs, "def add", client=stub))
    assert len(stub.calls) == 1 and not a["cached"] and b["cached"] and a["rect"] == b["rect"]
    run(T.pick_target(frame, obs, "the add function", client=stub))   # another intent: a call
    assert len(stub.calls) == 2
    obs2 = ScreenObservation.from_dict(obs.to_dict())                    # the screen changed: a call
    obs2.blocks = [b for b in obs2.blocks if "subtract" not in b.text]
    run(T.pick_target(frame, obs2, "def add", client=stub))
    assert len(stub.calls) == 3
    none_stub = Stub(ans([], 0.9))                                       # "nothing" is cached too
    run(T.pick_target(frame, obs, "the Run button", client=none_stub))
    run(T.pick_target(frame, obs, "the Run button", client=none_stub))
    assert len(none_stub.calls) == 1
    assert T.stats()["cache_hits"] == 2


def test_budget_per_minute(monkeypatch):
    monkeypatch.setenv("MIYAGI_VISION_MAX_CALLS_PER_MIN", "2")
    frame, obs = _load("vscode_window_calc_clean")
    stub = Stub(ans([], 0.9))
    for i in range(4):
        run(T.pick_target(frame, obs, f"intent {i}", client=stub))
    assert len(stub.calls) == 2 and T.stats()["budget_skips"] == 2


def test_timeout_returns_none_fast():
    frame, obs = _load("vscode_window_calc_clean")
    stub = Stub(ans([2]), delay=5.0)
    import time
    t = time.perf_counter()
    assert run(T.pick_target(frame, obs, "editor", client=stub, timeout=0.2)) is None
    assert time.perf_counter() - t < 2.0
    assert T.stats()["timeouts"] == 1
    assert run(T.pick_target(frame, obs, "editor", client=Stub(ans([2], 0.9)))) is not None  # not cached


def test_api_error_returns_none_and_is_not_cached():
    frame, obs = _load("vscode_window_calc_clean")
    assert run(T.pick_target(frame, obs, "editor", client=Stub(exc=RuntimeError("529 overloaded")))) is None
    assert T.stats()["errors"] == 1
    assert run(T.pick_target(frame, obs, "editor", client=Stub(ans([2], 0.9)))) is not None


def test_no_key_no_call():
    frame, obs = _load("vscode_window_calc_clean")
    assert run(T.pick_target(frame, obs, "editor")) is None
    assert T.stats()["no_key"] == 1 and T.stats()["calls"] == 0


def test_concurrent_same_question_is_one_call():
    frame, obs = _load("vscode_window_calc_clean")
    stub = Stub(ans([2], 0.9), delay=0.1)

    async def both():
        return await asyncio.gather(T.pick_target(frame, obs, "editor", client=stub),
                                    T.pick_target(frame, obs, "editor", client=stub))
    a, b = run(both())
    assert len(stub.calls) == 1 and a["rect"] == b["rect"]


def test_overlay_is_masked_and_its_lines_dropped():
    frame, obs = _load("vscode_window_calc_clean")
    cands = T.build_candidates(obs, "Code")
    l4 = next(c for c in cands if c.line == 4)
    ov = [l4.rect.pad(4)]                     # e.g. our caption card sitting on line 4
    assert not any(c.line == 4 for c in T.build_candidates(obs, "Code", exclude=ov))
    _jpeg, size = T.render_marks(frame, cands, obs, exclude=ov)
    assert size[0] <= 1280 and size[1] <= 1280


def test_list_of_blocks_input():
    frame, obs = _load("vscode_window_calc_clean")
    res = run(T.pick_target(frame, obs.blocks, "editor", client=Stub(ans([], 0.9)), app=None, screen=obs.screen))
    assert res is None   # no windows known: still a valid request, the stub found nothing


def test_overlaps_helper():
    assert T.overlaps({"x": 0, "y": 0, "w": 100, "h": 20}, {"x": 10, "y": 2, "w": 50, "h": 16})
    assert not T.overlaps({"x": 0, "y": 0, "w": 100, "h": 20}, {"x": 0, "y": 40, "w": 100, "h": 20})


# ---------------------------------------------------------------------- verifier (E4's _confirm_spot)

def test_verdict_rules():
    row = {"x": 357, "y": 177, "w": 838, "h": 18}
    pick = {"rect": {"x": 355, "y": 175, "w": 842, "h": 22}, "kind": "code"}
    assert T.verdict(row, pick, "picked", 0.9) == (row, "agree")
    far = {"rect": {"x": 355, "y": 517, "w": 842, "h": 22}, "kind": "code"}
    assert T.verdict(row, far, "picked", 0.9) == (far["rect"], "moved")
    reg = {"rect": {"x": 300, "y": 800, "w": 1400, "h": 290}, "kind": "region"}
    assert T.verdict(row, reg, "picked", 0.9) == (row, "kept:region")
    assert T.verdict(row, None, "none", 0.9) == (None, "none")
    assert T.verdict(row, None, "none", 0.6) == (row, "kept:none")          # not sure enough to remove a box
    for outcome in ("timeout", "budget", "no_key", "error", "low_confidence"):
        assert T.verdict(row, None, outcome, 0.0) == (row, f"kept:{outcome}")


def test_confirm_spot_moves_a_wrong_box_and_keeps_it_when_haiku_is_unavailable():
    frame, obs = _load("vscode_fullscreen_scrolled")
    cands = T.build_candidates(obs, "Code")
    l48 = next(c for c in cands if c.line == 48)
    crumb = {"x": 312, "y": 40, "w": 260, "h": 14}                             # a box on the breadcrumb
    rect, why = run(T.confirm_spot(crumb, frame, obs, "where pde_residual is defined", client=Stub(ans([l48.id]))))
    assert why == "moved" and abs(rect["y"] - (l48.rect.y - 2)) < 0.2
    T.reset()
    rect, why = run(T.confirm_spot(crumb, frame, obs, "where pde_residual is defined"))        # no key
    assert (rect, why) == (crumb, "kept:no_key")
    rect, why = run(T.confirm_spot(crumb, frame, obs, "x", client=Stub(ans([2]), delay=1), timeout=0.05))
    assert (rect, why) == (crumb, "kept:timeout")


@pytest.mark.xfail(strict=False, reason="gap until E6's 11add98 (empty file: line 1 is a blank row) is merged; then "
                                        "this passes and the marker can go")
def test_known_gap_empty_file_line_one_under_inline_chat():
    _frame, obs = _load("vscode_window_notes_inline_chat")
    cands = T.build_candidates(obs, "Code")
    assert _truth_id(cands, row(134)) is not None
