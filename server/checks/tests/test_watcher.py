import asyncio
import threading
import time

import pytest

from server.checks.watcher import watch_workdir


@pytest.mark.parametrize("force_polling", [False, True])
def test_watcher_reports_saves_and_ignores_noise(tmp_path, force_polling):
    (tmp_path / "__pycache__").mkdir()
    got: list[list[str]] = []
    done = threading.Event()

    def on_change(paths):
        got.append(paths)
        done.set()

    w = watch_workdir(str(tmp_path), on_change=on_change, force_polling=force_polling, poll_interval=0.1, debounce=0.1)
    try:
        time.sleep(0.3)
        (tmp_path / "__pycache__" / "x.pyc").write_text("noise")
        (tmp_path / "pinn.py").write_text("print('hi')\n")
        assert done.wait(5), "no change event"
        time.sleep(0.3)
    finally:
        w.stop()
    flat = {p for batch in got for p in batch}
    assert "pinn.py" in flat
    assert not any("__pycache__" in p for p in flat)


def test_watcher_async_iterator(tmp_path):
    async def main():
        w = watch_workdir(str(tmp_path), force_polling=True, poll_interval=0.1, debounce=0.1)
        it = w.changes().__aiter__()
        nxt = asyncio.ensure_future(it.__anext__())
        await asyncio.sleep(0.3)
        (tmp_path / "a.py").write_text("x = 1\n")
        paths = await asyncio.wait_for(nxt, 5)
        w.stop()
        return paths

    assert asyncio.run(main()) == ["a.py"]
