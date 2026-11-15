"""Offline (0 API calls) check that the app is told when the screen reader is down, and that show_me says so.
  .venv/bin/python scripts/stage_screen_down.py   (DEMO=1 + stubs + cached React lesson + the real screen)"""
import asyncio, json, sys, time
sys.path.insert(0, "scripts")
import stage
from stage_lifecycle import Client

OFFLINE = ["DEMO=1", "ORCH_STUBS=coach,diagrams,finder,lesson", "ORCH_AUTOSTART=1",
           "ORCH_LESSON=demo/cache/lessons/8741b6aef237862a.json", "TUT_SCREEN_FIXTURE=",
           "ANTHROPIC_API_KEY=", "GEMINI_API_KEY=", "BRIGHTDATA_API_KEY=", "ELEVENLABS_API_KEY=",
           "HTTPS_PROXY=http://127.0.0.1:9", "HTTP_PROXY=http://127.0.0.1:9", "ALL_PROXY=http://127.0.0.1:9"]

async def main():
    e = stage.Engine(8790)
    e.ensure(screen=True, open_ws=False, workdir=None, fresh=True, extra_env=OFFLINE)
    async with Client(e, "app") as c:
        await asyncio.sleep(25)
        st = e.state()
        print("state: screen", st.get("screen"), "phase", st.get("phase"), "step", st.get("stepId"), "modules", st.get("modules"))
        down = [(round(t, 1), p.get("message")) for t, ty, p in c.events if ty == "error"]
        print("errors in first 25 s:", down)
        i = c.mark(); t0 = time.monotonic() - c.t0
        await c.send("action", {"kind": "show_me"})
        await asyncio.sleep(6)
        print("show_me ->", [(round(t - t0, 2), ty, (p.get("title") or p.get("message") or p.get("t") or "")) for t, ty, p in c.since(i)])
        await asyncio.sleep(20)
        print("screen-down errors total after ~50 s:", sum(1 for _, ty, p in c.events if ty == "error" and "screen" in (p.get("message") or "")))
        await c.send("end_lesson", {})
        await asyncio.sleep(2)
    e.stop()

asyncio.run(main())
