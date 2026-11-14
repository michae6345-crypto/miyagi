"""diagrams.build() against a fake Anthropic client (no network)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from server import diagrams
from server.diagrams import DiagramError, build
from server.diagrams.render_svg import to_svg
from shared.contracts.events import validate_engine_payload


class FakeClient:
    def __init__(self, raw=None, *, stop="end_turn", text=None, delay=0.0):
        self.raw, self.stop, self.text, self.delay = raw, stop, text, delay
        self.calls: list[dict] = []
        self.messages = self
        self.beta = self  # client.beta.messages.create (refusal fallback path) lands here too

    async def create(self, **kw):
        self.calls.append(kw)
        if self.delay:
            await asyncio.sleep(self.delay)
        text = self.text if self.text is not None else json.dumps(self.raw)
        return SimpleNamespace(stop_reason=self.stop, model="fake-model",
                               content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=20))


def node(i, label=None, **kw):
    return {"id": i, "label": label or i, "detail": kw.get("detail", ""), "group": kw.get("group", ""),
            "shape": kw.get("shape", "box"), "emphasis": kw.get("emphasis", False)}


def edge(a, b, label="", **kw):
    return {"from": a, "to": b, "label": label, "style": kw.get("style", "solid"), "emphasis": kw.get("emphasis", False)}


def graph(layout, nodes, edges, direction="LR", title="T"):
    return {"kind": "graph", "caption": "What to notice.", "network": None,
            "graph": {"title": title, "layout": layout, "direction": direction, "nodes": nodes, "edges": edges, "groups": []}}


FLOW = graph("flow", [node("render"), node("effect", "useEffect", emphasis=True), node("fetch"), node("set", "setUsers"),
                      node("cleanup")],
             [edge("render", "effect", "after paint"), edge("effect", "fetch"), edge("fetch", "set"),
              edge("set", "render", "re-render"), edge("effect", "cleanup", "on unmount", style="dashed")])
STEP = {"id": "s4", "title": "Fetch users in useEffect", "instructions": "Add a useEffect that fetches users."}
CTX = {"code": "useEffect(() => { fetch('/api/users') }, [])", "file": "UserList.jsx"}


@pytest.fixture(autouse=True)
def _fresh_cache():
    diagrams.clear_cache()
    yield
    diagrams.clear_cache()


def run(coro):
    return asyncio.run(coro)


def test_graph_payload_has_layout_and_step_id():
    fake = FakeClient(FLOW)
    d = run(build(STEP, CTX, client=fake))
    assert d["kind"] == "graph" and d["stepId"] == "s4" and d["caption"] == "What to notice."
    data = d["data"]
    assert data["layout"] == "flow" and data["grid"]["cols"] >= 3
    pos = {n["id"]: (n["col"], n["row"]) for n in data["nodes"]}
    assert pos["render"][0] == 0 and pos["effect"][0] == 1 and pos["fetch"][0] == 2  # cycle set->render ignored for ranks
    assert all("detail" not in n for n in data["nodes"])  # empty strings dropped
    assert to_svg(d).startswith("<svg")
    kw = fake.calls[0]
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert "UserList.jsx" in kw["messages"][0]["content"] and "useEffect" in kw["messages"][0]["content"]


def test_cache_by_step_and_code_hash():
    fake = FakeClient(FLOW)
    run(build(STEP, CTX, client=fake))
    run(build(STEP, dict(CTX), client=fake))
    assert len(fake.calls) == 1 and diagrams.last_meta.get("cached")
    run(build(STEP, {**CTX, "code": CTX["code"] + "\n// edited"}, client=fake))
    run(build(STEP, {**CTX, "question": "why the empty array?"}, client=fake))
    assert len(fake.calls) == 3


def test_concurrent_presses_share_one_call():
    fake = FakeClient(FLOW, delay=0.05)

    async def two():
        return await asyncio.gather(build(STEP, CTX, client=fake), build(STEP, CTX, client=fake))
    a, b = run(two())
    assert a == b and len(fake.calls) == 1


def test_network_payload_matches_existing_contract():
    raw = {"kind": "network", "caption": "x,t in, u out; autograd gives u_t and u_xx.", "graph": None,
           "network": {"layers": [2, 32, 32, 1], "activation": "tanh", "inputs": ["x", "t"], "output": "u",
                       "derivatives": ["u_t", "u_xx"], "residual": "u_t - u_xx - f"}}
    d = run(build(STEP, CTX, client=FakeClient(raw)))
    assert d["data"]["layers"] == [2, 32, 32, 1] and d["data"]["inputs"] == ["x", "t"]
    validate_engine_payload("diagram", d)  # what the hub does before sending
    assert to_svg(d).startswith("<svg")


@pytest.mark.parametrize("raw,stop,text,msg", [
    (FLOW, "refusal", None, "declined"),
    (FLOW, "max_tokens", None, "cut off"),
    (None, "end_turn", "not json", "unreadable"),
    (graph("flow", [node(f"n{i}") for i in range(13)], []), "end_turn", None, "13 nodes"),
    (graph("flow", [node("a"), node("a")], []), "end_turn", None, "duplicate"),
    ({"kind": "network", "caption": "c", "graph": None, "network": {"layers": [], "activation": "", "inputs": [],
                                                                      "output": "", "derivatives": [], "residual": ""}},
     "end_turn", None, "layer sizes"),
    ({**FLOW, "caption": ""}, "end_turn", None, "caption"),
])
def test_errors_raise_no_canned_fallback(raw, stop, text, msg):
    with pytest.raises(DiagramError, match=msg):
        run(build(STEP, CTX, client=FakeClient(raw, stop=stop, text=text)))
    # nothing cached after a failure
    with pytest.raises(DiagramError):
        run(build(STEP, CTX, client=FakeClient(raw, stop=stop, text=text)))


def test_no_step_raises():
    with pytest.raises(DiagramError, match="No current step"):
        run(build({}, CTX, client=FakeClient(FLOW)))


def test_api_errors_become_diagram_errors():
    import anthropic
    import httpx

    class Boom(FakeClient):
        async def create(self, **kw):
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    with pytest.raises(DiagramError, match="reach Claude"):
        run(build(STEP, CTX, client=Boom()))


def test_dangling_edges_dropped():
    raw = graph("flow", [node("a"), node("b")], [edge("a", "b"), edge("a", "ghost")])
    d = run(build(STEP, CTX, client=FakeClient(raw)))
    assert [(e["from"], e["to"]) for e in d["data"]["edges"]] == [("a", "b")]


def test_git_layout_lanes_and_order():
    raw = graph("git", [node("c1", "C1", group="main"), node("c2", "C2", group="feature"), node("c3", "C3", group="main"),
                        node("c2b", "C2'", group="feature")],
                [edge("c1", "c2"), edge("c1", "c3"), edge("c3", "c2b"), edge("c2", "c2b", style="dashed")])
    d = run(build(STEP, CTX, client=FakeClient(raw)))
    pos = {n["id"]: (n["col"], n["row"]) for n in d["data"]["nodes"]}
    assert pos == {"c1": (0, 0), "c2": (1, 1), "c3": (2, 0), "c2b": (3, 1)}
    assert d["data"]["grid"] == {"cols": 4, "rows": 2}
    assert to_svg(d).startswith("<svg")


def test_sequence_edges_ordered():
    raw = graph("sequence", [node("comp", "UserList"), node("hook", "useEffect"), node("api", "/api/users")],
                [edge("comp", "hook", "mount"), edge("hook", "api", "fetch"), edge("api", "hook", "json")])
    d = run(build(STEP, CTX, client=FakeClient(raw)))
    assert [e["order"] for e in d["data"]["edges"]] == [1, 2, 3]
    assert [n["col"] for n in d["data"]["nodes"]] == [0, 1, 2]
    assert to_svg(d).startswith("<svg")


def test_tree_top_down():
    raw = graph("tree", [node("app", "App"), node("h", "Header"), node("f", "Footer"), node("n", "Nav")],
                [edge("app", "h"), edge("app", "f"), edge("h", "n")], direction="TB")
    d = run(build(STEP, CTX, client=FakeClient(raw)))
    rows = {n["id"]: n["row"] for n in d["data"]["nodes"]}
    assert rows == {"app": 0, "h": 1, "f": 1, "n": 2}


def test_prompt_carries_screen_question_and_offtrack():
    fake = FakeClient(FLOW)
    ctx = {"screen": {"Terminal": ["$ git log --oneline", "a1b2c3 add login"]}, "question": "why new hashes?",
           "offtrack": {"title": "Force push rejected", "body": "use --force-with-lease"},
           "lesson": {"title": "Git basics", "goal": "use branches"}}
    run(build(STEP, ctx, client=fake))
    p = fake.calls[0]["messages"][0]["content"]
    for s in ("[Terminal]", "a1b2c3 add login", "why new hashes?", "Force push rejected", "Git basics"):
        assert s in p


def test_long_caption_cut_at_sentence():
    long = "First sentence is short. " + "Second sentence goes on and on " * 10 + "."
    d = run(build(STEP, CTX, client=FakeClient({**FLOW, "caption": long})))
    assert d["caption"] == "First sentence is short."
