"""Live run of diagrams.build() on 4 contexts; writes examples/<name>.json (+ .svg) and examples/RESULTS.md.

    .venv/bin/python -m server.diagrams.live_examples            # needs ANTHROPIC_API_KEY (or ./.env)

The step/screen contexts below are test inputs (what the engine would pass at that moment); the
diagrams themselves come from Claude on every run.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from . import build, last_meta
from .render_svg import to_svg

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "examples"

REACT_CODE = """import { useEffect, useState } from "react";

export default function UserList() {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/users", { signal: controller.signal })
      .then((res) => res.json())
      .then((data) => setUsers(data))
      .catch((err) => {
        if (err.name !== "AbortError") setError(err);
      });
    return () => controller.abort();
  }, []);

  if (error) return <p>Could not load users</p>;
  return (
    <ul>
      {users.map((u) => <li key={u.id}>{u.name}</li>)}
    </ul>
  );
}
"""

PANDAS_CODE = """import pandas as pd

df = pd.read_csv("titanic.csv")
df.head()

summary = (
    df.groupby("pclass")
      .agg(mean_fare=("fare", "mean"), survival_rate=("survived", "mean"), passengers=("name", "count"))
      .reset_index()
)
summary
"""


def _hero():
    graph = json.loads((ROOT / "demo/cache/lessons/aebc6b8fba02dac5.json").read_text(encoding="utf-8"))
    step = next(s for s in graph["steps"] if s["id"] == "s6")
    code = (ROOT / "server/lesson/fixtures/diffusion_workdir/pinn_diffusion.py").read_text(encoding="utf-8")
    return step, {"lesson": graph["lesson"], "code": code, "file": "pinn_diffusion.py"}


def contexts():
    hero_step, hero_ctx = _hero()
    return [
        ("react-useeffect",
         {"id": "s4", "index": 4, "title": "Fetch users in useEffect",
          "instructions": "Add a useEffect that fetches /api/users once on mount, stores the result with setUsers, "
                          "and returns a cleanup that aborts the request.",
          "targets": [{"file": "src/UserList.jsx", "match": "useEffect", "caption": "The effect, its cleanup and the [] dependency array"}],
          "common_mistakes": ["Leaving out the dependency array, so the effect refetches after every render."]},
         {"lesson": {"title": "React hooks for beginners", "goal": "load data in a React component"},
          "code": REACT_CODE, "file": "src/UserList.jsx",
          "screen": {"Code": ["UserList.jsx", "useEffect(() => {", "const controller = new AbortController();",
                              "return () => controller.abort();", "}, []);"]}}),
        ("git-rebase",
         {"id": "s7", "index": 7, "title": "Rebase feature onto main",
          "instructions": "On feature/login run git rebase main so your two commits replay on top of the latest main, "
                          "then push with git push --force-with-lease.",
          "targets": [{"app": "Terminal", "match": "git rebase main", "caption": "Replays your commits onto main"}]},
         {"lesson": {"title": "Git branching and rebasing", "goal": "keep a feature branch up to date"},
          "screen": {"Terminal": [
              "$ git log --oneline --graph --all",
              "* 9f3c2d1 (main, origin/main) Fix footer links",
              "* 41aa7e0 Add pricing page",
              "| * c81b0f2 (HEAD -> feature/login) Add login form validation",
              "| * 2d9e4a7 Add login form",
              "|/",
              "* 7b1e9c3 Initial layout",
              "$ git rebase main",
              "Successfully rebased and updated refs/heads/feature/login.",
              "$ git log --oneline",
              "e04b6d9 (HEAD -> feature/login) Add login form validation",
              "5c7a1f8 Add login form",
              "9f3c2d1 (main, origin/main) Fix footer links"]},
          "question": "Why did my commit hashes change after the rebase?"}),
        ("pandas-groupby",
         {"id": "s5", "index": 5, "title": "Average fare by passenger class",
          "instructions": "Group the Titanic DataFrame by pclass and use .agg() to compute the mean fare, survival rate "
                          "and passenger count per class.",
          "targets": [{"file": "analysis.ipynb", "match": "groupby", "caption": "Split by pclass, aggregate, combine"}]},
         {"lesson": {"title": "Pandas for data analysis", "goal": "summarize a dataset with groupby"},
          "code": PANDAS_CODE, "file": "analysis.ipynb",
          "screen": {"Code": ["df.head()", "survived pclass name sex age fare embarked",
                              "0 3 Braund, Mr. Owen Harris male 22.0 7.2500 S"]}}),
        ("pinn-diffusion-hero", hero_step, hero_ctx),
    ]


async def main(names: list[str]) -> int:
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass
    OUT.mkdir(exist_ok=True)
    rows = []
    for name, step, ctx in contexts():
        if names and name not in names:
            continue
        t0 = time.monotonic()
        payload = await build(step, ctx)
        wall = time.monotonic() - t0
        (OUT / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (OUT / f"{name}.svg").write_text(to_svg(payload), encoding="utf-8")
        meta = dict(last_meta)
        kind = payload["kind"] + (f"/{payload['data']['layout']}" if payload["kind"] == "graph" else "")
        rows.append((name, kind, f"{wall:.2f}", meta.get("model", ""), meta.get("output_tokens", ""), payload["caption"]))
        print(f"{name:22s} {kind:20s} {wall:5.2f}s  {payload['caption']}")
    if not names:
        lines = ["# Live diagram examples", "",
                 "Generated by `python -m server.diagrams.live_examples` (one live Claude call each, no cache).",
                 "Each `<name>.json` is the exact `diagram` payload; `<name>.svg` is the reference render (render_svg.py).", "",
                 "| example | kind | latency (s) | model | output tokens | caption |", "|---|---|---|---|---|---|"]
        lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |" for r in rows]
        (OUT / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
