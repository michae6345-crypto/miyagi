import pytest


@pytest.fixture(autouse=True)
def _isolated_saved_sessions(tmp_path_factory, monkeypatch):
    """S7's Resumer saves lesson progress; tests must never touch ~/miyagi/state."""
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path_factory.mktemp("miyagi-state")))
