"""A lesson build the miyagi cloud refuses (or that never connects) ends with ONE plain sentence, offline.

The refusals (claude/eng-proxy cloud/app.py): 429 miyagi_quota (today's limit), 401 unknown install token (miyagi_auth),
451 region_unavailable (miyagi_region), 503 paused. Each becomes claude.CloudRefusal whose line is config.CLOUD_ERRORS'
sentence; none is retried, escalated to another model or re-sent while the cloud's verdict holds. A network failure
("Claude unreachable") becomes claude.ClaudeOffline with the offline line. builder.human_error and the session's
human_build_error put that sentence first, with no Gemini or "both engines" wording (Gemini is off, D1).
"""

from __future__ import annotations

import asyncio

import anthropic
import httpx
import pytest

from server import config
from server.lesson import builder, claude

CLOUD = "https://cloud.example.test/v1"
TOKEN = "mi_" + "e" * 43


@pytest.fixture(autouse=True)
def _cloud_mode(monkeypatch):
    for var in (*config.KEY_ENV.values(), config.CLOUD_URL_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "CLOUD_HOSTS", config.CLOUD_HOSTS | {"cloud.example.test"})  # as server/tests/conftest
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": TOKEN})
    config._unknown.clear()
    monkeypatch.setattr(config, "_region_url", None)
    monkeypatch.setattr(config, "_verdict", None)
    monkeypatch.setattr(claude, "_override_key", None)
    monkeypatch.setattr(claude, "RATE_RETRIES", 2)
    yield
    config.set_app_keys({})
    config._unknown.clear()


def _resp(status: int, body: dict) -> httpx.Response:
    req = httpx.Request("POST", CLOUD + "/anthropic/v1/messages", headers={"x-api-key": TOKEN})
    return httpx.Response(status, json=body, request=req)


def _proxy(status: int, typ: str, message: str = "") -> dict:
    """The proxy's own error() shape."""
    return {"type": "error", "error": {"type": typ, "message": message, "status": typ.upper(), "code": status}}


def quota_429() -> anthropic.RateLimitError:
    body = _proxy(429, "miyagi_quota", "Daily limit reached for this install.")
    return anthropic.RateLimitError("Error code: 429 miyagi_quota", response=_resp(429, body), body=body)


def auth_401() -> anthropic.AuthenticationError:
    body = _proxy(401, "authentication_error", "unknown install token")
    return anthropic.AuthenticationError("Error code: 401", response=_resp(401, body), body=body)


def region_451() -> anthropic.APIStatusError:
    body = {"error": "region_unavailable", "message": "miyagi isn't available in your region yet."}
    return anthropic.APIStatusError("region_unavailable", response=_resp(451, body), body=body)


def paused_503() -> anthropic.APIStatusError:
    body = _proxy(503, "proxy_disabled", "miyagi_paused")
    return anthropic.APIStatusError("Error code: 503 proxy_disabled", response=_resp(503, body), body=body)


def unreachable() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=httpx.Request("POST", CLOUD + "/anthropic/v1/messages"))


class _Raising:
    """A client whose every stream raises `exc`; counts the requests."""

    def __init__(self, exc: BaseException):
        self.exc, self.calls = exc, 0
        self.messages = self
        self.beta = type("B", (), {"messages": self})()

    def stream(self, **kw):
        outer = self

        class _Ctx:
            async def __aenter__(self):
                outer.calls += 1
                raise outer.exc

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def _build_with(monkeypatch, exc: BaseException) -> tuple[BaseException, _Raising]:
    """One schema call through the full path (_generate_json: rate-limit retries, escalation), raising `exc`."""
    fake = _Raising(exc)
    monkeypatch.setattr(claude, "client", lambda: fake)

    async def no_sleep(*a, **k):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    with pytest.raises(RuntimeError) as e:
        asyncio.run(claude._generate_json("system", "prompt", {"type": "object"}, role="segment", escalate=True))
    return e.value, fake


@pytest.mark.parametrize("make,code", [(quota_429, "miyagi_quota"), (auth_401, "miyagi_auth"),
                                       (region_451, "miyagi_region"), (paused_503, "miyagi_paused")])
def test_a_cloud_refusal_is_typed_with_the_cloud_sentence_and_never_retried(monkeypatch, make, code):
    err, fake = _build_with(monkeypatch, make())
    assert isinstance(err, claude.CloudRefusal) and err.code == code
    assert err.line == config.CLOUD_ERRORS[code] and claude.user_line(err) == config.CLOUD_ERRORS[code]
    assert fake.calls == 1  # no rate-limit retry, no escalation to another model, no corrective retry


@pytest.mark.parametrize("make,code", [(quota_429, "miyagi_quota"), (auth_401, "miyagi_auth"),
                                       (region_451, "miyagi_region")])
def test_after_a_refusal_the_next_call_is_not_even_sent(monkeypatch, make, code):
    _build_with(monkeypatch, make())
    err, fake = _build_with(monkeypatch, AssertionError("no request after the cloud said no"))
    assert fake.calls == 0 and isinstance(err, claude.CloudRefusal) and err.code == code


def test_a_new_install_token_clears_the_quota_stop(monkeypatch):
    _build_with(monkeypatch, quota_429())
    config.set_app_keys({"miyagiCloud": CLOUD, "miyagiToken": "mi_" + "n" * 43})
    _, fake = _build_with(monkeypatch, quota_429())
    assert fake.calls == 1  # a new token is asked again (and refused again here)


def test_an_upstream_rate_limit_is_still_retried(monkeypatch):
    """Only the cloud's own quota is final: Anthropic's 429 (forwarded as is) is an ordinary rate limit."""
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "Number of concurrent requests"}}
    err, fake = _build_with(monkeypatch, anthropic.RateLimitError("429", response=_resp(429, body), body=body))
    assert not isinstance(err, claude.LessonCallError) and fake.calls == claude.RATE_RETRIES + 1


def test_claude_unreachable_is_the_offline_line_and_not_escalated(monkeypatch):
    err, fake = _build_with(monkeypatch, unreachable())
    assert isinstance(err, claude.ClaudeOffline) and "Claude unreachable" in str(err)
    assert claude.user_line(err) == claude.OFFLINE_LINE and fake.calls == 1
    assert claude.OFFLINE_LINE.startswith("miyagi ") and len(claude.OFFLINE_LINE.split()) <= 12
    assert "—" not in claude.OFFLINE_LINE


# ------------------------------------------------------------------ the sentence the learner sees


CLOUD_TEXTS = {
    "miyagi_quota": "no engine could build the lesson:\nclaude: Error code: 429 - {'type': 'error', 'error': "
                    "{'type': 'miyagi_quota', 'message': 'Daily limit reached'}}",
    "miyagi_auth": "no engine could build the lesson:\nclaude: miyagi_auth: " + config.CLOUD_ERRORS["miyagi_auth"],
    "miyagi_region": "lesson.build_lesson failed: RuntimeError: miyagi_region: " + config.CLOUD_ERRORS["miyagi_region"],
}


@pytest.mark.parametrize("code", sorted(CLOUD_TEXTS))
def test_build_errors_carry_the_cloud_sentence(code):
    from server.orchestrator.session import human_build_error

    text = CLOUD_TEXTS[code]
    first = builder.human_error(text, {"length_s": 1227}).splitlines()[0]
    assert first == config.CLOUD_ERRORS[code]
    assert human_build_error(RuntimeError(text)) == config.CLOUD_ERRORS[code]
    assert human_build_error(RuntimeError(builder.human_error(text))) == config.CLOUD_ERRORS[code]


def test_a_typed_refusal_wrapped_by_the_builder_keeps_its_sentence():
    from server.orchestrator.session import human_build_error

    try:
        try:
            raise claude.CloudRefusal("miyagi_quota")
        except RuntimeError as inner:
            raise RuntimeError("lesson.build_lesson failed: RuntimeError: something else") from inner
    except RuntimeError as e:
        assert human_build_error(e) == config.CLOUD_ERRORS["miyagi_quota"]


def test_claude_unreachable_text_is_the_offline_line():
    from server.orchestrator.session import human_build_error

    text = "no engine could build the lesson:\nclaude: Claude unreachable: APIConnectionError"
    assert builder.human_error(text).splitlines()[0] == claude.OFFLINE_LINE
    assert human_build_error(RuntimeError(text)) == claude.OFFLINE_LINE


def test_no_gemini_or_both_engines_wording_when_gemini_did_not_fail():
    from server.orchestrator.session import human_build_error

    for text in ("no engine could build the lesson:\nclaude: Claude rate-limited after 5 attempts: 429 quota",
                 "no engine could build the lesson:\nclaude: Claude reply did not match the schema",
                 "claude: no answer within 300s"):
        first = builder.human_error(text, {"length_s": 300}).splitlines()[0]
        assert "Gemini" not in first and "both engines" not in first, first
        assert "Gemini" not in human_build_error(RuntimeError(text))
    # a Gemini failure is still named as one (LESSON_ENGINE=auto with a Gemini key)
    assert "Gemini's quota" in builder.human_error("gemini: 429 RESOURCE_EXHAUSTED quota")


def test_the_last_resort_message_never_shows_the_exception():
    from server.orchestrator.session import BUILD_FAILED, human_build_error

    e = KeyError("steps at /Users/someone/.miyagi/lessons/x.json: Traceback (most recent call last)")
    assert human_build_error(e) == BUILD_FAILED
    assert "/Users" not in BUILD_FAILED and "KeyError" not in BUILD_FAILED
