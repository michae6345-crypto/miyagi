#!/usr/bin/env python3
"""The recorded runs a Demo lesson shows (server/orchestrator/stage.py): demo/cache/stage/nn-runs.json.

Really runs the neural-net lesson's own code (scripts/make_nn_demo.py: STARTER + CODE) with NumPy, so every number a
Demo run prints is one the code prints:
  nn4 good   steps 1-3 as written (random start): the loss falls to 0.0009
  nn4 stuck  the same with W1 / W2 started at zeros: the loss sits at 0.2500
  nn6 good   steps 1-3 + 5: the loss lines, then [0 1 1 0] and the learned weights

    python3 scripts/make_stage_runs.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_nn_demo import ANCHOR, CODE, STARTER  # noqa: E402

OUT = ROOT / "demo" / "cache" / "stage" / "nn-runs.json"


def program(steps: list[str], zeros: bool = False) -> str:
    src = STARTER
    for sid in steps:
        code = CODE[sid]
        if zeros and sid == "nn1":
            code = code.replace("np.random.randn(2, 4) * 0.5", "np.zeros((2, 4))").replace(
                "np.random.randn(4, 1) * 0.5", "np.zeros((4, 1))")
        src = src.replace(ANCHOR[sid], f"{ANCHOR[sid]}\n{code}", 1)
    return src


def run(src: str) -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "nn.py"
        p.write_text(src, encoding="utf-8")
        out = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, check=True, cwd=d)
    return out.stdout.splitlines()


def main() -> None:
    runs = {
        "nn4": {"good": run(program(["nn1", "nn2", "nn3"])), "stuck": run(program(["nn1", "nn2", "nn3"], zeros=True))},
        "nn6": {"good": run(program(["nn1", "nn2", "nn3", "nn5"]))},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(runs, indent=1) + "\n", encoding="utf-8")
    for sid, v in runs.items():
        for k, lines in v.items():
            print(f"{sid} {k}: {lines[-1] if lines else '(nothing)'}")
    print(f"-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
