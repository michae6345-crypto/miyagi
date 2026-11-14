# server/diagrams: Claude-built diagram for the current step

When the learner presses ⌥D, the engine asks Claude for **one small explanatory diagram** of the step they are on,
drawn from the step itself, the code / OCR text on screen and their question (if any). Works for any topic:
React data flow, a git commit graph, pandas groupby, a neural net...

## Interface

```python
from server.diagrams import build, DiagramError

payload = await build(step, context)        # -> `diagram` event payload (dict)
```

| arg | what |
|---|---|
| `step` | the current step-graph step (`id`, `title`, `instructions`, `targets[].caption`, `explanations[].topic`, `common_mistakes`) |
| `context["code"]` / `["file"]` | text of the step's file (the orchestrator's `_code_excerpt`, up to 6000 chars) and its name |
| `context["screen"]` | OCR text: `ScreenObservation.lines_by_app()` (`{app: [lines]}`), a list of lines, or a string |
| `context["question"]` | the learner's question, if the diagram answers one (the caption then answers it) |
| `context["lesson"]` | `{title, goal}` |
| `context["offtrack"]` | the last offtrack card `{title, body}`, if the learner is stuck |
| `context["kind"]` | optional preference, `"network"` or `"graph"` |

Every key is optional; extra keys (the orchestrator's `_explain_context()` has more) are ignored.

- **Errors:** raises `DiagramError`; `str(e)` is safe to show ("Claude took longer than 15s...", "Anthropic key was rejected...").
  There is **no canned fallback**: no key, API error, refusal, cut-off answer, bad JSON, > 12 nodes or no step all raise.
- **Cache:** in memory, by `(step id, sha256(code + screen text), normalized question, kind)`, 64 entries.
  Pressing ⌥D twice while the first call is still running shares that one call.
- **Model:** `claude-sonnet-5-5` with effort `low` and structured outputs (JSON schema), plus the server-side refusal
  fallback. Key: `server.config.get_key("anthropic")` (the app's key, then `ANTHROPIC_API_KEY`).
  Env overrides: `DIAGRAMS_MODEL` (e.g. `claude-haiku-5-5`), `DIAGRAMS_EFFORT`, `DIAGRAMS_TIMEOUT` (seconds, default 15).
- `server.diagrams.last_meta` holds `{model, latency_s, input_tokens, output_tokens, cached}` of the last call.

## What it returns

**`kind: "network"`** — the existing contract shape, chosen only when the code gives the real layer sizes
(`layers = np.array([2, 32, 32, 1])`). Renders in the app's `Network` view today. `data` also carries `inputs` and
`output`, which `Diagram.tsx` already reads.

```json
{"kind": "network", "stepId": "s6", "caption": "...",
 "data": {"layers": [2, 32, 32, 1], "activation": "Tanh", "inputs": ["x", "t"], "output": "y",
          "derivatives": ["f_t", "f_xx"], "residual": "f_t - f_xx + s"}}
```

**`kind: "graph"`** — everything else (PROPOSED, see below). Claude picks the nodes, edges and a layout family;
`layout.py` assigns grid positions deterministically, so the app only maps `(col, row)` to pixels.

```json
{"kind": "graph", "stepId": "s7", "caption": "A commit's hash includes its parent. ...",
 "data": {"title": "Rebase", "layout": "git", "direction": "LR", "grid": {"cols": 7, "rows": 3},
          "nodes": [{"id": "c1", "label": "7b1e9c3", "detail": "Initial layout", "group": "main",
                     "shape": "commit", "emphasis": false, "col": 0, "row": 0}, ...],
          "edges": [{"from": "c4", "to": "c6", "style": "dashed", "emphasis": false}, ...]}}
```

| layout | positions | render hint |
|---|---|---|
| `flow`, `data`, `architecture` | layered left to right (`col` = rank, `row` = slot, may be `.5` to center) | boxes + arrows |
| `tree` | layered top-down (`row` = depth) | boxes + arrows down |
| `git` | `col` = commit order, `row` = branch lane (main first); `node.group` = lane name | circles on lanes, lane names at left, curved parent→child edges, dashed = rewritten/copied |
| `sequence` | participants in row 0 (`col` = index); every edge has `order` 1..n | lifelines, one horizontal arrow per message top to bottom |

Node `shape` is `box | round | circle | data | commit`; `emphasis: true` marks the 1–2 nodes/edges carrying the
step's key idea (draw in the accent color). `detail` and edge `label` are optional.

`gradients` and `heatmap` are never produced here: they need real training numbers from the run (metrics),
not a language model.

## Proposed contract change (not made here; `shared/contracts/` is not mine to edit)

`events.ts`:
```ts
"diagram": {
  kind: "network" | "gradients" | "heatmap" | "graph";
  caption: string;
  stepId?: string;
  data:
    | { layers: number[]; activation: string; derivatives: string[]; residual: string; inputs?: string[]; output?: string } // network
    | { layers: string[]; epochs: number[]; norms: number[][] }                                                             // gradients
    | { x: number[]; t: number[]; predicted: number[][]; exact?: number[][] }                                               // heatmap
    | {                                                                                                                      // graph
        title: string;
        layout: "flow" | "sequence" | "tree" | "data" | "architecture" | "git";
        direction: "LR" | "TB";
        grid: { cols: number; rows: number };
        nodes: { id: string; label: string; detail?: string; group?: string;
                 shape: "box" | "round" | "circle" | "data" | "commit"; emphasis: boolean; col: number; row: number }[];
        edges: { from: string; to: string; label?: string; style: "solid" | "dashed"; emphasis: boolean; order?: number }[];
        groups?: { id: string; label: string }[];
      };
};
```
`events.py`: add `"graph"` to `Diagram.kind` and a `GraphDiagram` model to the `data` union
(`GraphEdge.from` needs `Field(alias="from")`). **Until this lands, the hub's `validate_engine_payload` rejects
`kind: "graph"`**, so only `network` diagrams reach the app. App side: a `Graph` view in
`features/diagrams/Diagram.tsx` for `kind === 'graph'` (title = `data.title`); `render_svg.py` is the reference.

## Examples (live, `examples/`)

`python -m server.diagrams.live_examples` runs the 4 contexts below with live Claude calls and writes each payload
to `examples/<name>.json` (exactly what the app receives), a reference render `examples/<name>.svg`, and
`examples/RESULTS.md` (captions, latency, tokens). The step/screen contexts are test inputs; the diagrams are Claude's.

| example | kind | latency |
|---|---|---|
| React `useEffect` fetch + cleanup | graph / flow | 3.9 s (first call, cold connection) |
| git rebase, with "why did my hashes change?" | graph / git | 4.4 s |
| pandas `groupby("pclass").agg(...)` | graph / data | 3.5 s |
| diffusion PINN hero step (s6, `FCN` + `lossPDE`) | network | 2.1 s |

## Files

- `build.py` — prompt, JSON schema, Claude call, validation, cache, `build()`
- `layout.py` — deterministic grid layout per layout family
- `render_svg.py` — reference SVG renderer (`python -m server.diagrams.render_svg examples/*.json`)
- `live_examples.py` — the 4 live runs
- `tests/test_build.py` — fake-client tests (`.venv/bin/python -m pytest server/diagrams -q`)
