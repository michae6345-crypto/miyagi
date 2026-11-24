#!/usr/bin/env python3
"""Contract parity: shared/contracts/events.ts and shared/contracts/events.py say the same thing.

Offline, no engine, no network. Run: python3 scripts/test_contract_parity.py (or python -m pytest scripts/test_contract_parity.py).

  - every Engine -> App event in events.ts (EngineEvents + KeyStatusEvent) is in events.py ENGINE_EVENTS and EngineEventType,
    and the other way round; the same for App -> Engine commands (AppCommands vs APP_COMMANDS / AppCommandType)
  - the shared constants (bon's levels, activity window, mastery rule, review schedule, proof caps) are equal
  - the ui-v4 mock scenario (app/mock/scenarios/ui-v4.json) only uses known events and commands, every payload in it
    validates against events.py, and it shows every ui-v4 event at least once
  - shared/contracts/UI-V4.md documents every ui-v4 event and command

The events.py checks need pydantic (the engine's venv has it); without it they are skipped, the text checks still run.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS = ROOT / "shared/contracts/events.ts"
PY = ROOT / "shared/contracts/events.py"
DOC = ROOT / "shared/contracts/UI-V4.md"
MOCK = ROOT / "app/mock/scenarios/ui-v4.json"

UI_V4_EVENTS = ("activity", "bon", "plans", "playlist", "plan.proposal", "link.preview", "proof", "data")
UI_V4_COMMANDS = ("activity.get", "bon.get", "bon.import", "plans.list", "plan.start", "plan.remove", "playlist.get", "plan.propose",
                  "link.get", "proof.get", "data.get", "data.delete", "review.start")

sys.path.insert(0, str(ROOT))
try:
    from shared.contracts import events as contract  # needs pydantic
except ImportError:  # pragma: no cover - a python without pydantic
    contract = None


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _block(src: str, header: str) -> str:
    """The body of `export interface <header> {` ... its matching `}`."""
    i = src.index(f"export interface {header} {{")
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[j + 1:k]
    raise AssertionError(f"unbalanced interface {header}")


def _top_keys(body: str) -> set[str]:
    """The quoted keys at depth 0 of an interface body ("search.result": ...)."""
    keys, depth, i = set(), 0, 0
    while i < len(body):
        c = body[i]
        if c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
        elif c == '"' and depth == 0:
            j = body.index('"', i + 1)
            rest = body[j + 1:].lstrip()
            if rest.startswith(":"):
                keys.add(body[i + 1:j])
            i = j
        i += 1
    return keys


def _ts_const(src: str, name: str) -> str:
    m = re.search(rf"export const {name}(?::[^=]+)? = (.+?)(?:\n(?=export|//|/\*)|\Z)", src, flags=re.S)
    assert m, f"events.ts has no export const {name}"
    return m.group(1).strip()


def _ts_number(src: str, name: str) -> int:
    return int(_ts_const(src, name))


def _ts_numbers(src: str, name: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", _ts_const(src, name).split("]")[0])]


def _ts_bon_levels(src: str) -> list[dict]:
    body = _ts_const(src, "BON_LEVELS")
    rows = re.findall(r'\{\s*level:\s*(\d+),\s*name:\s*"([^"]+)",\s*at:\s*(\d+),\s*has:\s*"([^"]+)"\s*\}', body)
    return [{"level": int(a), "name": b, "at": int(c), "has": d} for a, b, c, d in rows]


class TextParity(unittest.TestCase):
    """What can be checked without importing events.py."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ts = _strip_comments(TS.read_text(encoding="utf-8"))
        cls.py = PY.read_text(encoding="utf-8")
        cls.events = _top_keys(_block(cls.ts, "EngineEvents")) | _top_keys(_block(cls.ts, "KeyStatusEvent"))
        cls.commands = _top_keys(_block(cls.ts, "AppCommands"))

    def test_events_ts_parses(self) -> None:
        self.assertIn("step.passed", self.events)
        self.assertIn("config.status", self.events)
        self.assertIn("learn", self.commands)
        for e in UI_V4_EVENTS:
            self.assertIn(e, self.events)
        for c in UI_V4_COMMANDS:
            self.assertIn(c, self.commands)

    def test_every_type_is_named_in_events_py(self) -> None:
        for name in sorted(self.events | self.commands):
            self.assertIn(f'"{name}"', self.py, f"events.py never names {name!r}")

    def test_doc_covers_every_ui_v4_message(self) -> None:
        doc = DOC.read_text(encoding="utf-8")
        for name in UI_V4_EVENTS + UI_V4_COMMANDS:
            self.assertIn(f"`{name}`", doc, f"UI-V4.md does not document {name}")


@unittest.skipIf(contract is None, "pydantic is not installed: the events.py checks need it")
class ModelParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ts = _strip_comments(TS.read_text(encoding="utf-8"))
        cls.ts = ts
        cls.events = _top_keys(_block(ts, "EngineEvents")) | _top_keys(_block(ts, "KeyStatusEvent"))
        cls.commands = _top_keys(_block(ts, "AppCommands"))

    def test_engine_events_match(self) -> None:
        self.assertEqual(self.events, set(contract.ENGINE_EVENTS))
        self.assertEqual(set(contract.ENGINE_EVENTS), set(contract.EngineEventType.__args__))

    def test_app_commands_match(self) -> None:
        self.assertEqual(self.commands, set(contract.APP_COMMANDS))
        self.assertEqual(self.commands, set(contract.AppCommandType.__args__))

    def test_capability_lists_name_real_commands(self) -> None:
        for cap in contract.V2_CAPABILITIES + contract.UI_V4_CAPABILITIES:
            self.assertIn(cap, self.commands)
        self.assertEqual(set(contract.UI_V4_CAPABILITIES) | {"data.delete", "review.start"}, set(UI_V4_COMMANDS))

    def test_shared_constants_match(self) -> None:
        self.assertEqual(_ts_bon_levels(self.ts), list(contract.BON_LEVELS))
        self.assertEqual(len(contract.BON_LEVELS), 8)
        for name in ("ACTIVITY_DAYS", "RECENT_PASSED_MAX", "MASTERY_DAYS", "PROOF_TEXT_MAX", "PROOF_OUTPUT_MAX"):
            self.assertEqual(_ts_number(self.ts, name), getattr(contract, name), name)
        self.assertEqual(_ts_numbers(self.ts, "REVIEW_DAYS"), list(contract.REVIEW_DAYS))

    def test_bon_state_follows_the_levels(self) -> None:
        self.assertEqual(contract.bon_state(0)["level"], 1)
        self.assertEqual(contract.bon_state(2)["next"], {"level": 2, "name": "Sprout", "at": 3, "left": 1})
        self.assertEqual(contract.bon_state(25)["name"], "Budding")
        top = contract.bon_state(500)
        self.assertEqual((top["level"], top["fraction"]), (8, 1.0))
        self.assertNotIn("next", top)
        for n in (0, 7, 24, 25, 89, 90):
            contract.engine_message("bon", contract.bon_state(n, grew=n == 25, last_key="lesson-1:s3"))

    def test_mock_scenario_validates(self) -> None:
        s = json.loads(MOCK.read_text(encoding="utf-8"))
        seen = set()
        for seg, items in s["segments"].items():
            for it in items:
                if "goto" in it:
                    self.assertIn(it["goto"], s["segments"], f"{seg}: goto {it['goto']!r}")
                if "type" not in it:
                    continue
                seen.add(it["type"])
                try:
                    contract.engine_message(it["type"], it.get("payload"))
                except Exception as e:  # noqa: BLE001 - name the item that failed
                    self.fail(f"{seg} {it['type']}: {e}")
        for e in UI_V4_EVENTS:
            self.assertIn(e, seen, f"the mock never sends {e}")
        for trigger, seg in s["on"].items():
            self.assertIn(seg, s["segments"], trigger)
            cmd = trigger.split("@")[0]
            if cmd == "connect":
                continue
            if cmd.startswith("action:"):
                self.assertIn(cmd.split(":", 1)[1], contract.ActionKind.__args__)
            else:
                self.assertIn(cmd.split(":")[0], contract.APP_COMMANDS, trigger)
        a = next(it["payload"] for it in s["segments"]["uiv4_activity"] if it.get("type") == "activity")
        self.assertEqual(len(a["days"]), contract.ACTIVITY_DAYS)
        self.assertLessEqual(len(a["recent"]), contract.RECENT_PASSED_MAX)

    def test_ui_v4_commands_parse(self) -> None:
        samples = {
            "activity.get": {}, "bon.get": {}, "bon.import": {"steps": 12, "seen": ["lesson-1:s1"]}, "plans.list": {},
            "plan.start": {"catalogId": "intro-blender"}, "plan.remove": {"id": "intro-blender"},
            "playlist.get": {"url": "https://www.youtube.com/playlist?list=PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv"},
            "plan.propose": {"goal": "I want to 3D print a stand for my phone", "tool": "freecad"},
            "link.get": {"url": "https://www.youtube.com/watch?v=YYXdXT2l-Gg"}, "proof.get": {"skillId": "np.indexing"}, "data.get": {},
            "data.delete": {"what": ["notes"]}, "review.start": {"skillId": "bl.transform"},
        }
        for t, p in samples.items():
            self.assertEqual(contract.parse_app_message({"type": t, "payload": p}).type, t)
        lp = contract.parse_app_message({"type": "learn", "payload": {"query": "Teach x", "mode": "lesson", "plan": {"id": "intro-python", "index": 0}}})
        self.assertEqual(lp.payload.plan.index, 0)
        # review.start keeps the engine's old leniency: a wrong type reads as absent
        self.assertEqual(contract.parse_app_message({"type": "review.start", "payload": {"skillId": 5}}).payload.skillId, "")

    def test_old_payloads_still_validate(self) -> None:
        """Additive only: the shapes both branches sent before the Nov 24 sync still pass."""
        contract.engine_message("answer.delta", {"askId": "a1", "text": "Each pass", "done": True})  # app reading
        contract.engine_message("answer.delta", {"askId": "a1", "seq": 0, "text": "Each pass"})  # engine reading
        contract.engine_message("answer.done", {"askId": "a1", "text": "Each pass runs the model."})
        contract.engine_message("status", {"state": "busy", "retryInS": 5, "epoch": 2, "gen": 7})
        contract.engine_message("step.passed", {"stepId": "s1", "nextStepId": "s2", "summary": "Loaded the data"})
        contract.engine_message("lesson.ready", {"lesson": {"id": "l", "title": "t", "sources": []}, "steps": [], "buildS": 41.5})


if __name__ == "__main__":
    unittest.main(verbosity=1)
