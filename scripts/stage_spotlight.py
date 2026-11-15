"""Offline (0 API calls) spotlight check on the REAL screen: autostart a cached lesson whose step-1 target is
text that is on screen right now, then `show_me` must send a spotlight with a real, on-screen rect within ~1 s,
and no "can't see your screen" notice may appear.

  .venv/bin/python scripts/stage_spotlight.py <lesson.json>   (DEMO=1 + stubs; the real screen; keys blanked)
"""
import asyncio
import sys
import time

sys.path.insert(0, "scripts")
import stage  # noqa: E402
from stage_actions import rect_ok  # noqa: E402
from stage_lifecycle import Client  # noqa: E402

OFFLINE = ["DEMO=1", "ORCH_STUBS=coach,diagrams,finder,lesson", "ORCH_AUTOSTART=1", "TUT_SCREEN_FIXTURE=",
           "ANTHROPIC_API_KEY=", "GEMINI_API_KEY=", "BRIGHTDATA_API_KEY=", "ELEVENLABS_API_KEY=",
           "HTTPS_PROXY=http://127.0.0.1:9", "HTTP_PROXY=http://127.0.0.1:9", "ALL_PROXY=http://127.0.0.1:9"]


async def main(lesson: str) -> None:
    e = stage.Engine(8790)
    e.ensure(screen=True, open_ws=False, workdir=None, fresh=True, extra_env=OFFLINE + [f"ORCH_LESSON={lesson}"])
    async with Client(e, "app") as c:
        await asyncio.sleep(12)
        st = e.state()
        print("state: screen", st.get("screen"), "step", st.get("stepId"), "targets", (st.get("step") or {}).get("targets"))
        for n in range(3):
            i = c.mark()
            t0 = time.monotonic() - c.t0
            await c.send("action", {"kind": "show_me"})
            await asyncio.sleep(4)
            evs = [(round(t - t0, 2), ty, p) for t, ty, p in c.since(i)]
            spots = [(t, p) for t, ty, p in evs if ty == "spotlight" and p.get("rect")]
            print(f"show_me #{n + 1}:", [(t, ty) for t, ty, _ in evs])
            for t, p in spots:
                print(f"   spotlight @{t}s rect {p['rect']} ok={rect_ok(p['rect'])} app={p.get('app')} matched={p.get('matched')!r}")
        notices = [p.get("message") for _, ty, p in c.events if ty == "error"]
        print("error events:", notices)
        await c.send("end_lesson", {})
        await asyncio.sleep(1)
    e.stop()


asyncio.run(main(sys.argv[1]))
