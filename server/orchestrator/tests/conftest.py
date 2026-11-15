import pytest

PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY",
             "TIGER_DATABASE_URL")


@pytest.fixture(autouse=True)
def _isolated_and_free(tmp_path_factory, monkeypatch):
    """S7's Resumer saves lesson progress: tests must never touch ~/miyagi/state. COST FREEZE: tests never call a
    paid API (Gemini, Claude, Bright Data, ElevenLabs); with the keys blanked an accidental live call fails at once
    and for free (modules fall back / report an error), so fakes and fixtures are the only way to get data."""
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path_factory.mktemp("miyagi-state")))
    for k in PAID_KEYS:
        monkeypatch.setenv(k, "")
    from server.orchestrator import workspace as wsmod

    monkeypatch.setattr(wsmod, "find_resources", lambda graph: [])  # no watch-page fetches in tests
    try:
        from server.config import set_app_keys

        set_app_keys({})
    except Exception:  # noqa: BLE001
        pass
