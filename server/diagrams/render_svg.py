"""Reference renderer: a `diagram` payload -> standalone SVG (dark, like the island).

Not used on the live path. It exists so the app's Graph renderer has a spec to match, and so the
examples in examples/ can be eyeballed:   python -m server.diagrams.render_svg examples/*.json
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

ACCENT = "#5b8cff"
FG = "#ffffff"
DIM = "rgba(255,255,255,.45)"
LINE = "rgba(255,255,255,.35)"
W = 600


def _fit(s: str, width: float, size: float, mono=False) -> str:
    """Truncate to roughly `width` px (average glyph ~0.6em mono, ~0.56em sans)."""
    n = max(3, int(width / (size * (0.62 if mono else 0.56))))
    return s if len(s) <= n else s[: n - 1] + "…"


def _t(x, y, s, size=12, fill=FG, anchor="middle", weight="400", mono=False, width=None):
    if width:
        s = _fit(s, width, size, mono)
    fam = ' font-family="ui-monospace, monospace"' if mono else ' font-family="-apple-system, system-ui, sans-serif"'
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" fill="{fill}" font-size="{size}" font-weight="{weight}"{fam}>{escape(s)}</text>'


def _arrow_defs():
    return ('<defs>'
            f'<marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker>'
            f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{ACCENT}"/></marker>'
            '</defs>')


def _node(n, cx, cy, bw, bh):
    stroke = ACCENT if n.get("emphasis") else "rgba(255,255,255,.7)"
    shape = n.get("shape", "box")
    out = []
    if shape in ("circle", "commit"):
        r = 9 if shape == "commit" else bh / 2
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#000" stroke="{stroke}" stroke-width="1.5"/>')
        ly = cy + r + 14 if shape == "commit" else cy + 4
        out.append(_t(cx, ly, n["label"], 11.5, mono=shape == "commit", width=bw))
        if n.get("detail") and shape == "commit":
            out.append(_t(cx, ly + 13, n["detail"], 10, DIM, width=bw))
        return "".join(out)
    rx = bh / 2 if shape == "round" else 8
    out.append(f'<rect x="{cx - bw / 2}" y="{cy - bh / 2}" width="{bw}" height="{bh}" rx="{rx}" fill="#000" stroke="{stroke}" stroke-width="1.3"/>')
    if shape == "data":
        out.append(f'<line x1="{cx - bw / 2}" x2="{cx + bw / 2}" y1="{cy - bh / 2 + 7}" y2="{cy - bh / 2 + 7}" stroke="{stroke}" stroke-width=".8"/>')
    if n.get("detail"):
        out.append(_t(cx, cy - 2, n["label"], 12, weight="600", width=bw - 10))
        out.append(_t(cx, cy + 12, n["detail"], 9.5, DIM, mono=True, width=bw - 10))
    else:
        out.append(_t(cx, cy + 4, n["label"], 12, weight="600", width=bw - 10))
    return "".join(out)


def _edge(e, p, q, bw, bh, curve=False):
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    # leave the box edges
    def clip(dx, dy):
        if dx == 0 and dy == 0:
            return 0, 0
        sx = (bw / 2) / abs(dx) if dx else 1e9
        sy = (bh / 2) / abs(dy) if dy else 1e9
        s = min(sx, sy)
        return dx * s, dy * s
    ox, oy = clip(dx, dy)
    a, b = (x1 + ox, y1 + oy), (x2 - ox, y2 - oy)
    color = ACCENT if e.get("emphasis") else LINE
    dash = ' stroke-dasharray="4 3"' if e.get("style") == "dashed" else ""
    marker = "ah" if e.get("emphasis") else "a"
    if curve:
        mx = (a[0] + b[0]) / 2
        d = f"M{a[0]:.1f},{a[1]:.1f} C{mx:.1f},{a[1]:.1f} {mx:.1f},{b[1]:.1f} {b[0]:.1f},{b[1]:.1f}"
    else:
        d = f"M{a[0]:.1f},{a[1]:.1f} L{b[0]:.1f},{b[1]:.1f}"
    out = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.4"{dash} marker-end="url(#{marker})"/>'
    if e.get("label"):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        room = max(abs(b[0] - a[0]) - 4, 90.0 if abs(b[1] - a[1]) > abs(b[0] - a[0]) else 0)
        if room < 40:  # no space between the boxes: the app can show it on hover instead
            return out
        label = _fit(e["label"], room, 10)
        lw = len(label) * 5.6 + 8
        out += f'<rect x="{mx - lw / 2:.1f}" y="{my - 8:.1f}" width="{lw:.1f}" height="14" rx="4" fill="#0b0b0d"/>'
        out += _t(mx, my + 3, label, 10, DIM)
    return out


def graph_svg(d: dict) -> tuple[str, int]:
    data = d["data"]
    nodes, edges, lay = data["nodes"], data["edges"], data["layout"]
    cols, rows = max(1, data["grid"]["cols"]), max(1, data["grid"]["rows"])
    parts = [_arrow_defs()]
    if lay == "sequence":
        cw = W / cols
        top, step = 30, 34
        h = top + 20 + step * len(edges) + 10
        xs = {n["id"]: cw * (n["col"] + 0.5) for n in nodes}
        for n in nodes:
            x = xs[n["id"]]
            parts.append(f'<line x1="{x}" x2="{x}" y1="{top + 16}" y2="{h - 6}" stroke="rgba(255,255,255,.18)" stroke-dasharray="3 4"/>')
            parts.append(_node(n, x, top, min(cw - 16, 130), 30))
        for e in edges:
            y = top + 20 + step * e["order"]
            parts.append(_edge(e, (xs[e["from"]], y), (xs[e["to"]], y), 2, 2))
        return "".join(parts), h
    if lay == "git":
        cw, rh, left = (W - 130) / cols, 62, 130
        h = rows * rh + 26
        pos = {n["id"]: (left + cw * (n["col"] + 0.5), 22 + rh * n["row"]) for n in nodes}
        lanes = {}
        for n in nodes:
            lanes.setdefault(n["row"], n.get("group", "main"))
        for r, name in lanes.items():
            parts.append(_t(0, 26 + rh * r, name, 10.5, DIM, anchor="start", mono=True, width=left - 6))
        for e in edges:  # no edge labels here: dashed already reads as "copied", and lanes are tight
            parts.append(_edge({**e, "label": ""}, pos[e["from"]], pos[e["to"]], 20, 20, curve=True))
        for n in nodes:
            parts.append(_node({**n, "shape": "commit"}, *pos[n["id"]], cw - 4, 18))
        return "".join(parts), h
    tb = data.get("direction") == "TB"
    cw = W / cols
    rh = 74 if tb else 66
    bw, bh = max(96, min(cw - 24, 150)), 40
    h = rows * rh + 8
    pos = {n["id"]: (cw * (n["col"] + 0.5), 4 + rh * (n["row"] + 0.5)) for n in nodes}
    for e in edges:
        parts.append(_edge(e, pos[e["from"]], pos[e["to"]], bw, bh))
    for n in nodes:
        parts.append(_node(n, *pos[n["id"]], bw, bh))
    return "".join(parts), h


def network_svg(d: dict) -> tuple[str, int]:
    data = d["data"]
    layers = data["layers"]
    n = len(layers)
    xs = [40 + i * (380 / max(1, n - 1)) for i in range(n)]
    parts = [_arrow_defs()]

    def ys(k):
        k = min(k, 5)
        return [80 - (k - 1) * 14 + i * 28 for i in range(k)]
    for i in range(n - 1):
        for y1 in ys(layers[i]):
            for y2 in ys(layers[i + 1]):
                parts.append(f'<line x1="{xs[i]}" y1="{y1}" x2="{xs[i + 1]}" y2="{y2}" stroke="rgba(255,255,255,.12)"/>')
    for i, k in enumerate(layers):
        for y in ys(k):
            parts.append(f'<circle cx="{xs[i]}" cy="{y}" r="{11 if i in (0, n - 1) else 7}" fill="#000" stroke="{ACCENT if i == n - 1 else "rgba(255,255,255,.75)"}"/>')
        parts.append(_t(xs[i], 168, str(k), 12, weight="600"))
        parts.append(_t(xs[i], 183, "inputs" if i == 0 else "output" if i == n - 1 else data["activation"], 10.5, DIM))
    for j, name in enumerate(data.get("inputs", [])[:5]):
        parts.append(_t(xs[0], ys(layers[0])[j] + 4, name, 11))
    if data.get("output"):
        parts.append(_t(xs[-1], ys(layers[-1])[0] + 4, data["output"], 11))
    for j, name in enumerate(data.get("derivatives", [])[:2]):
        y = 38 if j == 0 else 122
        parts.append(f'<path d="M{xs[-1] + 12},80 L494,{y}" stroke="{ACCENT}" stroke-dasharray="4 3" fill="none"/>')
        parts.append(f'<rect x="494" y="{y - 13}" width="64" height="26" rx="8" fill="#000" stroke="{LINE}"/>')
        parts.append(_t(526, y + 4, name, 12, mono=True))
    parts.append(f'<rect x="478" y="66" width="104" height="28" rx="14" fill="{ACCENT}"/>')
    res = data.get("residual") or "residual"
    parts.append(_t(530, 84, res if len(res) <= 13 else "residual", 11, mono=True))  # same rule as the app
    return "".join(parts), 196


def to_svg(d: dict) -> str:
    body, h = network_svg(d) if d["kind"] == "network" else graph_svg(d)
    title = "Architecture" if d["kind"] == "network" else d["data"].get("title", "")
    cap_lines = _wrap(d["caption"], 86)
    total = 30 + h + 14 + 18 * len(cap_lines) + 10
    head = _t(16, 22, "Intuition", 14, weight="600", anchor="start") + _t(90, 22, "· " + title, 13, DIM, anchor="start")
    caps = "".join(_t(W / 2, 30 + h + 22 + 18 * i, line, 13.5, "rgba(255,255,255,.8)") for i, line in enumerate(cap_lines))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 40}" height="{total}" viewBox="-20 0 {W + 40} {total}">'
            f'<rect x="-20" y="0" width="{W + 40}" height="{total}" rx="22" fill="#0b0b0d"/>{head}'
            f'<g transform="translate(0,30)">{body}</g>{caps}</svg>')


def _wrap(s: str, n: int) -> list[str]:
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        p = Path(arg)
        rec = json.loads(p.read_text(encoding="utf-8"))
        p.with_suffix(".svg").write_text(to_svg(rec.get("payload", rec)), encoding="utf-8")
        print(p.with_suffix(".svg"))
