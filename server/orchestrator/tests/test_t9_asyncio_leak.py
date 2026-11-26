"""V13 (t9 engine log, 06:16:00): "Task was destroyed but it is pending! ... coro=<Queue.get() ...>".

A learn cancelled mid-search ("learn cancelled: a newer request replaced it") left the streaming finder's pending
queue.get() task behind in Modules.search; only a reference cycle held it, so GC later destroyed it mid-flight.
No paid calls: the finder is a fake."""

from __future__ import annotations

import asyncio
import gc
import types

from server.orchestrator import bg
from server.orchestrator.modules import Modules


def _watch(loop: asyncio.AbstractEventLoop) -> list[str]:
    errors: list[str] = []
    loop.set_exception_handler(lambda _loop, ctx: errors.append(str(ctx.get("message"))))
    return errors


def _pending_queue_gets() -> list[asyncio.Task]:
    return [t for t in asyncio.all_tasks() if not t.done() and "Queue.get" in repr(t.get_coro())]


def test_cancelled_search_leaves_no_pending_queue_get():
    async def finder_search(query, on_result=None, api_keys=None):
        await on_result({"id": "a", "url": "https://www.youtube.com/watch?v=AXXnSzmpyoI"})
        await asyncio.Event().wait()  # the search hangs on (slow sources) until it is cancelled

    mods = Modules(demo=False, force_stubs="lesson,coach,diagrams")
    mods.real["finder"] = types.SimpleNamespace(search=finder_search)

    async def go():
        errors = _watch(asyncio.get_running_loop())
        rows: list[dict] = []
        first = asyncio.Event()

        async def consume():  # main.py's worker job: learn -> search, cancelled by a newer learn
            async for row in mods.search("mnist"):
                rows.append(row)
                first.set()

        job = asyncio.ensure_future(consume())
        await asyncio.wait_for(first.wait(), 2)
        await asyncio.sleep(0.01)  # the consumer is back in asyncio.wait({getter, finder}) for the next row
        assert _pending_queue_gets(), "repro precondition: a queue.get() task is pending"
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
        for _ in range(5):
            await asyncio.sleep(0)
        assert _pending_queue_gets() == []
        gc.collect()
        await asyncio.sleep(0)
        assert not [e for e in errors if "destroyed" in e], errors
        assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []  # the finder stopped too
        assert [r["id"] for r in rows] == ["a"]

    asyncio.run(go())


def test_spawned_task_survives_gc():
    """bg.spawn holds a fire-and-forget task whose only other reference is a cycle (its own future)."""

    async def go():
        errors = _watch(asyncio.get_running_loop())

        async def waits() -> None:
            await asyncio.get_running_loop().create_future()  # nothing outside the task holds this future

        t = bg.spawn(waits())
        await asyncio.sleep(0)
        gc.collect()
        await asyncio.sleep(0)
        assert not t.done() and t in bg._LIVE
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
        assert t not in bg._LIVE
        assert not [e for e in errors if "destroyed" in e], errors

    asyncio.run(go())
