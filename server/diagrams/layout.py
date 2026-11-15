"""Deterministic grid layout for `graph` diagrams, so the app only maps (col, row) to pixels.

Claude picks the nodes, edges and a layout family; this module assigns every node an integer
`col`/`row` and adds `grid: {cols, rows}` to the data. No randomness: the same graph always lays
out the same way.

  flow / data / architecture / tree : layered (rank = longest path from a source, cycles broken
                                      at back edges), order inside a rank by barycenter sweeps.
                                      LR -> col = rank, TB -> row = rank.
  git                               : col = commit order (as given, oldest first), row = branch lane
                                      (main/master first, then in order of first appearance).
  sequence                          : participants in one row (col = index); edges keep their order
                                      and get `order` = 1, 2, ...
"""

from __future__ import annotations

from collections import defaultdict

LAYERED = {"flow", "data", "architecture", "tree"}
TRUNK = ("main", "master", "trunk")


def _back_edges(ids: list[str], out: dict[str, list[str]]) -> set[tuple[str, str]]:
    """Edges that close a cycle in a DFS over `ids` (in their given order)."""
    state: dict[str, int] = {}  # 1 = on stack, 2 = done
    back: set[tuple[str, str]] = set()

    def visit(v: str) -> None:
        state[v] = 1
        for w in out[v]:
            if state.get(w) == 1:
                back.add((v, w))
            elif w not in state:
                visit(w)
        state[v] = 2

    for v in ids:
        if v not in state:
            visit(v)
    return back


def _layered(nodes: list[dict], edges: list[dict], direction: str) -> tuple[int, int]:
    ids = [n["id"] for n in nodes]
    out: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["from"] != e["to"]:
            out[e["from"]].append(e["to"])
    back = _back_edges(ids, out)
    dag = [(a, b) for a in ids for b in out[a] if (a, b) not in back]

    # longest-path ranks over the DAG (Kahn order)
    indeg = {v: 0 for v in ids}
    succ: dict[str, list[str]] = defaultdict(list)
    pred: dict[str, list[str]] = defaultdict(list)
    for a, b in dag:
        indeg[b] += 1
        succ[a].append(b)
        pred[b].append(a)
    rank = {v: 0 for v in ids}
    queue = [v for v in ids if indeg[v] == 0]
    while queue:
        v = queue.pop(0)
        for w in succ[v]:
            rank[w] = max(rank[w], rank[v] + 1)
            indeg[w] -= 1
            if indeg[w] == 0:
                queue.append(w)

    layers: dict[int, list[str]] = defaultdict(list)
    for v in ids:
        layers[rank[v]].append(v)
    pos = {v: i for r in layers for i, v in enumerate(layers[r])}

    def sweep(neigh: dict[str, list[str]], order: list[int]) -> None:
        for r in order:
            def bary(v: str) -> float:
                ns = [pos[u] for u in neigh[v]]
                return sum(ns) / len(ns) if ns else pos[v]
            layers[r].sort(key=lambda v: (bary(v), ids.index(v)))
            for i, v in enumerate(layers[r]):
                pos[v] = i

    ranks = sorted(layers)
    for _ in range(2):
        sweep(pred, ranks[1:])
        sweep(succ, list(reversed(ranks[:-1])))

    width = max(len(layers[r]) for r in ranks)
    for n in nodes:
        r, p = rank[n["id"]], pos[n["id"]]
        # center short layers across the widest one
        p2 = p + (width - len(layers[r])) / 2
        offset = int(p2 * 2) / 2  # half-steps are fine for the renderer
        if direction == "TB":
            n["row"], n["col"] = r, offset
        else:
            n["col"], n["row"] = r, offset
    depth = len(ranks)
    return (width, depth) if direction == "TB" else (depth, width)


def _git(nodes: list[dict]) -> tuple[int, int]:
    lanes: list[str] = []
    for n in nodes:
        g = n.get("group") or "main"
        if g not in lanes:
            lanes.append(g)
    first = list(lanes)
    lanes = sorted(first, key=lambda g: (g.lower() not in TRUNK, first.index(g)))
    for i, n in enumerate(nodes):
        n["col"], n["row"] = i, lanes.index(n.get("group") or "main")
    return len(nodes), len(lanes)


def _sequence(nodes: list[dict], edges: list[dict]) -> tuple[int, int]:
    for i, n in enumerate(nodes):
        n["col"], n["row"] = i, 0
    for i, e in enumerate(edges, 1):
        e["order"] = i
    return len(nodes), len(edges) + 1


def apply(data: dict) -> dict:
    """Add col/row to every node (and order to sequence edges) plus `grid`. Mutates and returns `data`."""
    nodes, edges = data["nodes"], data["edges"]
    layout = data.get("layout", "flow")
    if layout == "git":
        cols, rows = _git(nodes)
    elif layout == "sequence":
        cols, rows = _sequence(nodes, edges)
    else:
        cols, rows = _layered(nodes, edges, data.get("direction", "LR"))
    data["grid"] = {"cols": cols, "rows": rows}
    return data
