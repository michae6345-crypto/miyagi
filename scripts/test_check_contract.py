"""Tests for scripts/check_contract.py (stdlib only): python3 scripts/test_check_contract.py"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_contract as cc  # noqa: E402

CONTRACT = '''
export interface EngineEvents {
  "a.one": { x: string };   // a "quoted" // comment
  "card": { kind: "explain" | "resume"; title: string; actions?: Array<"confirm" | "build">; url?: string /* ws://x */ };
  "offtrack": { actions: Array<"hint"> };
  "diagram": { kind: "network" | "graph"; data: {} };
  "lesson.ended": {};
}
export interface KeyStatusEvent { "config.status": { a: string } }
export interface AppCommands {
  "learn": { query: string };
  "action": { kind: "hint" | "confirm" | "build"; text?: string };
  "end_lesson": {};
}
'''

APP_FULL = {
    "wire.ts": "const KNOWN = new Set<string>(['a.one', 'card', 'offtrack', 'diagram', 'lesson.ended', 'config.status'] satisfies string[])",
    "cards/index.tsx": (
        "const KIND: Record<string, X> = { explain: {}, resume: {} }\n"
        "const ACTION: Partial<Record<string, X>> = { confirm: { label: 'Yes' } }\n"
        "o.actions.includes('hint')\n"
        "x = () => cardAct('build')\n"
    ),
    "core/handlers.ts": (
        "onMessage('a.one', f)\nonMessage('card', f)\nonMessage('config.status', f)\n"
        "for (const t of ['offtrack', 'diagram', 'lesson.ended'] as const) onMessage(t, g)\n"
    ),
    "launcher.tsx": "bridge.send(cmd('learn', { query: q }))\nbridge.send(cmd('action', { kind: 'hint' }))\nbridge.send(cmd('end_lesson', {}))\n",
    "diagrams/Diagram.tsx": "d.kind === 'network' && 1; d.kind === 'graph' && 2",
}


def app(files):
    return cc.App(dict(files), "test")


class ContractParsing(unittest.TestCase):
    def test_contract_members(self):
        c = cc.Contract(CONTRACT)
        self.assertEqual(c.events, ["a.one", "card", "offtrack", "diagram", "lesson.ended", "config.status"])
        self.assertEqual(c.card_kinds, ["explain", "resume"])
        self.assertEqual(c.card_actions, ["confirm", "build"])
        self.assertEqual(c.action_kinds, ["hint", "confirm", "build"])
        self.assertEqual(c.commands, ["learn", "action", "end_lesson"])
        self.assertEqual(c.diagram_kinds, ["network", "graph"])

    def test_strip_comments_keeps_strings(self):
        self.assertEqual(cc.strip_comments('a "ws://x" // gone\nb'), 'a "ws://x" \nb')

    def test_real_contract_parses(self):
        c = cc.load_contract(cc.DEFAULT_CONTRACT, None)
        for need in ("lesson.ended", "config.status", "card", "setup.progress"):
            self.assertIn(need, c.events)
        self.assertIn("preflight", c.card_kinds)
        self.assertIn("pick_another", c.card_actions)


class Conformance(unittest.TestCase):
    def missing(self, files, allow=None):
        f = cc.run_check(cc.Contract(CONTRACT), app(files), allow or {})
        return {"%s:%s" % (x["category"], x["name"]) for x in f if x["status"] == "missing"}

    def test_complete_app_passes(self):
        self.assertEqual(self.missing(APP_FULL), set())

    def test_each_gap_is_named(self):
        files = dict(APP_FULL)
        files["wire.ts"] = files["wire.ts"].replace("'lesson.ended', ", "")
        files["cards/index.tsx"] = files["cards/index.tsx"].replace("resume: {}", "").replace("cardAct('build')", "")
        files["diagrams/Diagram.tsx"] = "d.kind === 'network'"
        got = self.missing(files)
        self.assertEqual(got, {"event:lesson.ended", "card.kind:resume", "card.action:build", "action.kind:build", "diagram.kind:graph"})

    def test_allow_list_silences_a_gap(self):
        files = dict(APP_FULL)
        files["diagrams/Diagram.tsx"] = "d.kind === 'network'"
        self.assertEqual(self.missing(files, {"diagram.kind:graph": "later"}), set())

    def test_missing_map_is_a_structure_finding(self):
        files = dict(APP_FULL)
        files["cards/index.tsx"] = "o.actions.includes('hint')"
        got = self.missing(files)
        self.assertIn("structure:cards KIND map", got)
        self.assertIn("structure:cards ACTION map", got)
        self.assertIn("card.kind:explain", got)

    def test_top_level_end_lesson_counts_when_the_action_is_sent(self):
        files = dict(APP_FULL)
        files["x.tsx"] = "sendAction('end_lesson')"
        self.assertNotIn("command:end_lesson", self.missing(files))

    def test_commented_out_code_is_not_evidence(self):
        files = dict(APP_FULL)
        files["cards/index.tsx"] = files["cards/index.tsx"].replace("x = () => cardAct('build')", "// x = () => cardAct('build')")
        self.assertIn("card.action:build", self.missing(files))

    def test_dev_and_mock_files_are_ignored(self):
        files = dict(APP_FULL)
        files["dev/Stage.tsx"] = "cardAct('build'); onMessage('zzz', f)"
        files["cards/index.tsx"] = files["cards/index.tsx"].replace("x = () => cardAct('build')", "")
        self.assertIn("card.action:build", self.missing(files))


class Cli(unittest.TestCase):
    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "events.ts").write_text(CONTRACT)
            for rel, text in APP_FULL.items():
                p = root / "src" / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
            base = ["--contract", str(root / "events.ts"), "--app", str(root / "src"), "--allow", str(root / "none.txt")]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cc.main(base), 0)
                (root / "src" / "wire.ts").write_text("const KNOWN = new Set<string>(['card'])")
                self.assertEqual(cc.main(base), 1)
                self.assertEqual(cc.main(["--contract", str(root / "nope.ts"), "--app", str(root / "src")]), 2)


if __name__ == "__main__":
    unittest.main()
