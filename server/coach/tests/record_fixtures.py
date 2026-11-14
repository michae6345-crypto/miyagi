"""Re-record every LLM fixture the tests replay (live Opus/Haiku calls; costs a few cents).

    rm server/coach/fixtures/*.json && .venv/bin/python -m server.coach.tests.record_fixtures

The web layer is replaced by `generic_cases.fake_fetch` (excerpts of the real pages) for the
React/pandas cases, and switched off for the PINN cases, exactly as in the tests.
"""

from __future__ import annotations

import asyncio
import os

os.environ["COACH_RECORD_DIR"] = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "fixtures")

from server import coach
from server.coach import case_convection as cv
from server.coach import case_diffusion as d
from server.coach import common, web
from server.coach.diagnose import LAST
from server.coach.tests import generic_cases as g
from server.coach.tests.screen_case import make_screen


def show(name: str, card: dict | None) -> None:
    if card is None:
        print(f"{name}: None")
        return
    m = card.get("_meta", {})
    print(f"{name}: [{card.get('severity', card.get('kind'))}] {card['title']} — {card['body']}"
          f"\n    cite={card.get('citation', {}).get('url')} route={m.get('route')} triage={m.get('triage', {}).get('by')}")


async def main() -> None:
    real_fetch, real_configured = web.fetch, web.configured
    web.configured = lambda: False  # PINN cases: no web, same as the tests

    common.set_lesson(d.LESSON)
    show("diffusion/missing-bc", await coach.diagnose(d.STEP, d.MISSING_BC_FAILED, d.MISSING_BC_METRICS, d.MISSING_BC_CODE))
    show("diffusion/explain", await coach.explain(d.STEP, None, {"metrics_summary": d.MISSING_BC_METRICS}))
    LAST.clear()
    show("diffusion/high-lr", await coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE))
    show("diffusion/no-grad", await coach.diagnose(d.STEP, d.NO_GRAD_FAILED, None, d.NO_GRAD_CODE, error_text=d.NO_GRAD_ERROR))

    LAST.clear()
    screen = make_screen()
    show("diffusion/high-lr+screen", card := await coach.diagnose(d.STEP, d.HIGH_LR_FAILED, d.HIGH_LR_METRICS, d.HIGH_LR_CODE, screen=screen))
    print("    targets:", [(t["boxId"], t["label"], t["text"][:40]) for t in card["targets"]])
    for q in ("the learning rate", "where the total loss is computed"):
        print(f"locate {q!r}:", [(t["boxId"], t["text"][:40]) for t in await coach.locate(q, screen)])

    LAST.clear()
    common.set_lesson(cv.LESSON)
    show("convection", await coach.diagnose(cv.STEP, cv.FAILED_CHECKS, cv.METRICS, cv.CODE))
    show("convection/explain", await coach.explain(cv.STEP, None, {"metrics_summary": cv.METRICS}))

    # MPS error no regex rule matches → Haiku triage
    step = {"id": "s3", "title": "Run training", "instructions": "Run the training script once.",
            "checks": [{"id": "c3", "type": "command_exit_ok", "label": "script runs", "command": "python pinn.py"}]}
    err = ("Traceback (most recent call last):\n  File \"pinn.py\", line 41, in <module>\n    loss = residual(model, x, t)\n"
           "RuntimeError: Placeholder storage has not been allocated on MPS device!")
    code = 'device = "mps"\nmodel = PINN().to(device)\nx = torch.rand(1000, 1)\nt = torch.rand(1000, 1)'
    print("triage/mps:", await coach.triage(step, [{"checkId": "c3", "label": "script runs", "status": "fail"}], set(), code, err))

    web.fetch, web.configured = g.fake_fetch, (lambda: True)
    common.set_lesson(g.REACT_LESSON)
    show("react", await coach.diagnose(g.REACT_STEP, g.REACT_FAILED, None, g.REACT_CODE, error_text=g.REACT_ERROR))
    show("pandas", await coach.fix_outdated(g.PANDAS_ERROR, g.PANDAS_LIBS, code=g.PANDAS_CODE))
    web.fetch, web.configured = real_fetch, real_configured


if __name__ == "__main__":
    asyncio.run(main())
