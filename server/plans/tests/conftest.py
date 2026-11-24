from __future__ import annotations

import httpx
import pytest

from server.plans import catalog, playlist


@pytest.fixture(autouse=True)
def plans_state(tmp_path, monkeypatch):
    """A private state folder; the shipped catalog; no network unless a test hands playlist.TRANSPORT a recording."""
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("MIYAGI_PLANS_CATALOG", raising=False)
    monkeypatch.delenv("MIYAGI_PLANS_PLAYLISTS", raising=False)
    catalog.reload()

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected fetch: {request.url}")

    monkeypatch.setattr(playlist, "TRANSPORT", httpx.MockTransport(no_network))
    playlist._inflight.clear()
    yield tmp_path / "state"
    catalog.reload()
