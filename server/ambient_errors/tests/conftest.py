import pytest

PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY")


@pytest.fixture(autouse=True)
def _offline(tmp_path_factory, monkeypatch):
    """COST FREEZE: never a model call (keys blanked, the coach client offline unless a test fakes it), and the hourly
    cap's file in a temp state dir."""
    monkeypatch.setenv("MIYAGI_STATE_DIR", str(tmp_path_factory.mktemp("miyagi-state")))
    for k in PAID_KEYS:
        monkeypatch.setenv(k, "")
    from server import ambient_cap
    from server.coach import llm

    async def offline(**_k):
        raise llm.CoachLLMError("offline test", "offline")

    monkeypatch.setattr(llm, "structured_call", offline)
    ambient_cap.reset_shared(None)
    yield
    ambient_cap.reset_shared(None)
