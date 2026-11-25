#!/usr/bin/env python3
"""Contract parity: shared/contracts/events.ts and shared/contracts/events.py say the same thing.

Offline, no engine, no network. Run: python3 scripts/test_contract_parity.py (or python -m pytest scripts/test_contract_parity.py).

  - every Engine -> App event in events.ts (EngineEvents + KeyStatusEvent) is in events.py ENGINE_EVENTS and EngineEventType,
    and the other way round; the same for App -> Engine commands (AppCommands vs APP_COMMANDS / AppCommandType)
  - the shared constants (bon's levels, activity window, mastery rule, review schedule, proof caps) are equal
  - the ui-v4 mock scenario (app/mock/scenarios/ui-v4.json) only uses known events and commands, every payload in it
    validates against events.py, and it shows every ui-v4 event at least once
  - shared/contracts/UI-V4.md documents every ui-v4 event and command
  - any link (Nov 24): the "link.any" flag and the new kinds are the same on both sides, ANY-LINK.md documents them, the
    any-link mock scenario validates, and the link cache key helpers in events.py normalize the way ANY-LINK.md says

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
ANY_LINK_DOC = ROOT / "shared/contracts/ANY-LINK.md"
ANY_LINK_MOCK = ROOT / "app/mock/scenarios/any-link.json"
ANY_LINK_FIELDS = ("site", "author", "estMinutes", "teachable", "teach", "why", "tools", "cached", "finalUrl", "pageRef", "origin")

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


def _ts_union(src: str, name: str) -> set[str]:
    m = re.search(rf"export type {name} = ([^\n;]+)", src)
    assert m, f"events.ts has no export type {name}"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


class AnyLinkText(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ts = _strip_comments(TS.read_text(encoding="utf-8"))
        cls.doc = ANY_LINK_DOC.read_text(encoding="utf-8")

    def test_ts_has_the_new_kinds(self) -> None:
        self.assertEqual(_ts_union(self.ts, "LinkKind"), {"video", "playlist", "unsupported", "web", "github"})
        self.assertEqual(_ts_union(self.ts, "BuildSourceKind"), {"youtube", "goal", "library", "web", "github"})
        self.assertIn("blocked", _ts_union(self.ts, "LookupError"))
        self.assertTrue({"no_content", "blocked"} <= _ts_union(self.ts, "BuildFailCode"))
        self.assertEqual(_ts_const(self.ts, "LINK_ANY_CAPABILITY"), '"link.any"')

    def test_doc_covers_the_fields(self) -> None:
        for name in ("link.any", "link.get", "link.preview", "learn_url", "lesson.building", "lesson.ready", "web", "github",
                     "blocked", "no_content", "normalize_link_url", "link_cache_key", "link_content_hash") + ANY_LINK_FIELDS:
            self.assertTrue(f"`{name}`" in self.doc or f'"{name}"' in self.doc, f"ANY-LINK.md does not document {name}")
        for name in ANY_LINK_FIELDS:
            self.assertIn(f"{name}?", self.ts, f"events.ts has no optional {name}")


@unittest.skipIf(contract is None, "pydantic is not installed: the events.py checks need it")
class AnyLinkModels(unittest.TestCase):
    def test_python_matches_ts(self) -> None:
        ts = _strip_comments(TS.read_text(encoding="utf-8"))
        self.assertEqual(f'"{contract.LINK_ANY_CAPABILITY}"', _ts_const(ts, "LINK_ANY_CAPABILITY"))
        self.assertEqual(set(contract.LinkKind.__args__), _ts_union(ts, "LinkKind"))
        self.assertEqual(set(contract.BuildSourceKind.__args__), _ts_union(ts, "BuildSourceKind"))
        self.assertEqual(set(contract.LookupError_.__args__), _ts_union(ts, "LookupError"))
        self.assertEqual(set(contract.BuildFailCode.__args__), _ts_union(ts, "BuildFailCode"))
        for model, fields in ((contract.LinkPreview, ("site", "author", "estMinutes", "teachable", "teach", "why", "tools", "cached", "finalUrl")),
                              (contract.BuildSource, ("site", "author")), (contract.StepSummary, ("pageRef",)), (contract.LessonInfo, ("origin",))):
            for f in fields:
                self.assertIn(f, model.model_fields, f"{model.__name__}.{f}")

    def test_mock_scenario_validates(self) -> None:
        s = json.loads(ANY_LINK_MOCK.read_text(encoding="utf-8"))
        kinds, sources, errors = set(), set(), set()
        for seg, items in s["segments"].items():
            for it in items:
                if "goto" in it:
                    self.assertIn(it["goto"], s["segments"], f"{seg}: goto {it['goto']!r}")
                if "type" not in it:
                    continue
                try:
                    msg = contract.engine_message(it["type"], it.get("payload"))
                except Exception as e:  # noqa: BLE001 - name the item that failed
                    self.fail(f"{seg} {it['type']}: {e}")
                p = msg["payload"]
                if it["type"] == "link.preview":
                    kinds.add(p["kind"])
                    if "error" in p:
                        errors.add(p["error"])
                    if p.get("teachable") is False:
                        errors.add("not_teachable")
                if it["type"] == "lesson.ready":
                    sources.add(p["lesson"]["origin"]["kind"])
                    self.assertEqual(p["lesson"]["mode"], "lesson")
                    self.assertTrue(all("pageRef" in st and "video" not in st for st in p["steps"]))
                if it["type"] == "engine.hello":
                    self.assertIn(contract.LINK_ANY_CAPABILITY, p["capabilities"])
        self.assertEqual(kinds, {"web", "github"})
        self.assertEqual(sources, {"web", "github"})
        self.assertEqual(errors, {"blocked", "not_teachable"})
        for trigger, seg in s["on"].items():
            self.assertIn(seg, s["segments"], trigger)
            cmd = trigger.split("@")[0]
            if cmd != "connect":
                self.assertIn(cmd, contract.APP_COMMANDS, trigger)

    def test_normalize_link_url(self) -> None:
        n = contract.normalize_link_url
        same = ["https://docs.python.org/3/tutorial/venv.html", "http://docs.python.org/3/tutorial/venv.html",
                "https://www.docs.python.org/3/tutorial/venv.html#creating", "https://DOCS.python.org:443/3/tutorial/venv.html/",
                "https://docs.python.org/3//tutorial/venv.html?utm_source=x&fbclid=y", " https://user:pw@docs.python.org./3/tutorial/venv.html "]
        self.assertEqual({n(u) for u in same}, {"https://docs.python.org/3/tutorial/venv.html"})
        self.assertEqual(n("https://example.com"), "https://example.com/")
        self.assertEqual(n("https://example.com:8443/a?b=2&a=1&ref=hn"), "https://example.com:8443/a?a=1&b=2")
        self.assertEqual(n("https://github.com/Pallets/Flask.git"), "https://github.com/pallets/flask")
        self.assertEqual(n("https://github.com/Pallets/Flask/tree/main/docs/Tutorial"), "https://github.com/pallets/flask/tree/main/docs/Tutorial")
        self.assertNotEqual(n("https://example.com/a?page=1"), n("https://example.com/a?page=2"))
        for bad in ("ftp://example.com/x", "file:///etc/hosts", "javascript:alert(1)", "https://", "not a url"):
            with self.assertRaises(ValueError, msg=bad):
                n(bad)

    def test_link_cache_key(self) -> None:
        h = contract.link_content_hash("Make a  venv\n\nthen pip install")
        self.assertEqual(h, contract.link_content_hash("Make a venv then pip install"))
        k = contract.link_cache_key("web", "http://www.example.com/a/#x", h)
        self.assertRegex(k, contract.LINK_CACHE_KEY_RE)
        self.assertTrue(k.startswith("w_"))
        self.assertEqual(k, contract.link_cache_key("web", "https://example.com/a", h))
        self.assertNotEqual(k, contract.link_cache_key("web", "https://example.com/a", contract.link_content_hash("edited")))
        self.assertTrue(contract.link_cache_key("github", "https://github.com/a/b", h).startswith("g_"))
        with self.assertRaises(ValueError):
            contract.link_cache_key("youtube", "https://example.com/a", h)  # type: ignore[arg-type]

    def test_old_link_preview_still_validates(self) -> None:
        contract.engine_message("link.preview", {"url": "https://www.youtube.com/watch?v=YYXdXT2l-Gg", "kind": "video", "title": "x"})
        contract.engine_message("lesson.building", {"message": "m", "progress": 0.1, "source": {"kind": "youtube", "title": "t"}})


if __name__ == "__main__":
    unittest.main(verbosity=1)
