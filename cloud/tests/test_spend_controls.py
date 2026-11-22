"""Spend controls (R01, R03, D1, D13), offline: caps that no client header can move, the daily new-install cap, the
runtime pause, alert dedupe, the 32000-token cap, Gemini off by default, and /healthz.

Upstreams are a closed local port or an httpx.MockTransport (test_security.Upstream). The alert webhook is never
called: tests replace app._dispatch with a recorder.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from test_caps import ADMIN, ADMIN_TOKEN, CLOUD, install, make_cloud  # noqa: F401  (make_cloud is a fixture)
from test_security import HAIKU, SONNET, Upstream, msg, post_anthropic, post_gemini

DEFAULT_CAPS = ("FREE_DAILY_USD", "FREE_DAILY_REQUESTS", "LINKED_DAILY_USD", "LINKED_DAILY_REQUESTS",
                "ANON_DAILY_USD_PER_NETWORK", "DAILY_USD_CAP", "RATE_LIMIT_PER_TOKEN_PER_HOUR", "MAX_TOKENS_CAP")
HOOK = "https://hooks.slack.example/services/T000/B000/not-a-real-hook"


def th_of(app_mod, h: dict) -> str:
    return app_mod.hash_token(h["Authorization"][7:])


def haiku(client, h, role: str | None = None, max_tokens: int = 300):
    body = {"model": HAIKU, "max_tokens": max_tokens, "messages": msg()}
    return post_anthropic(client, h, body, **({"x-miyagi-role": role} if role is not None else {}))


# --------------------------------------------------------------------------- 1. role spoofing cannot lift a cap

SPOOFED_ROLES = [None, "coach", "scene", "lesson", "screen", "finder", "pro", "admin", "free", "", "COACH",
                 "x" * 40, "coach; drop"]


def test_role_header_cannot_lift_the_install_cap(make_cloud):
    """Every cap keys on the install token: an install at its dollar cap is refused whatever role it claims."""
    client, app_mod = make_cloud(unset=("FREE_DAILY_USD",))
    up = Upstream(app_mod)
    h, _ = install(client)
    app_mod.store.add_tokens(th_of(app_mod, h), "anthropic", HAIKU, 10, 10, app_mod.FREE_DAILY_USD)
    for role in SPOOFED_ROLES:
        r = haiku(client, h, role=role)
        assert r.status_code == 429, (role, r.text)
        err = r.json()["error"]
        assert err["limit"] == "daily_spend" and err["scope"] == "install" and err["cap"] == app_mod.FREE_DAILY_USD
    assert up.requests == []
    other, _ = install(client)  # the cap is per install, not per role
    assert haiku(client, other, role="coach").status_code == 200


def test_role_header_cannot_lift_the_user_or_network_caps(make_cloud):
    client, app_mod = make_cloud(LINKED_DAILY_USD="0.50", ANON_DAILY_USD_PER_NETWORK="0.50", FREE_DAILY_USD="5")
    Upstream(app_mod)
    linked, _ = install(client)
    app_mod.store.link_user(th_of(app_mod, linked), "user-1")
    app_mod.store.add_tokens(th_of(app_mod, linked), "anthropic", HAIKU, 10, 10, 0.50)
    anon, _ = install(client)
    spent, _ = install(client)  # same mint network as `anon`
    app_mod.store.add_tokens(th_of(app_mod, spent), "anthropic", HAIKU, 10, 10, 0.50)
    for role in SPOOFED_ROLES:
        r = haiku(client, linked, role=role)
        assert r.status_code == 429 and r.json()["error"]["scope"] == "account", role
        r = haiku(client, anon, role=role)
        assert r.status_code == 429 and r.json()["error"]["scope"] == "network", role


def test_role_is_only_a_label(make_cloud, caplog):
    client, app_mod = make_cloud()
    Upstream(app_mod)
    h, _ = install(client)
    with caplog.at_level("INFO", logger="miyagi.cloud"):
        assert haiku(client, h, role="scene").status_code == 200
    assert "role=scene" in caplog.text  # in the log line
    assert app_mod.store.role_requests_today(th_of(app_mod, h), "scene") == 1  # and the usage view
    assert not hasattr(app_mod, "FREE_COACH_CALLS_PER_DAY")
    src = (CLOUD / "store.py").read_text()
    admit = src[src.index("    def admit_call("):src.index("    def usd_today(")]
    assert "FROM role_usage" not in admit  # no cap reads the role table


def test_a_lessons_busiest_hour_passes_every_default(make_cloud):
    """720 scene looks an hour, plus the judge and screen picks, on one install: no role cap, no request count and
    the per-token rate limit (2400 an hour by default) leave it alone; the dollar cap is far away."""
    client, app_mod = make_cloud(unset=DEFAULT_CAPS)
    assert app_mod.RATE_LIMIT_PER_TOKEN_PER_HOUR == 2400 and app_mod.FREE_DAILY_REQUESTS == 0
    up = Upstream(app_mod)
    h, _ = install(client)
    hour = ["scene"] * 720 + ["coach"] * 180 + ["screen"] * 360
    codes = [haiku(client, h, role=role, max_tokens=200).status_code for role in hour]
    assert codes == [200] * len(hour)
    assert len(up.requests) == len(hour)
    assert app_mod.store.usd_today_for(th_of(app_mod, h)) < app_mod.FREE_DAILY_USD / 5


# --------------------------------------------------------------------------- 2. daily new-install cap (D13)

def _assert_full(r) -> dict:
    assert r.status_code == 429, r.text
    err = r.json()["error"]
    assert err["type"] == "miyagi_full" and err["status"] == "MIYAGI_FULL" and err["code"] == 429
    assert err["limit"] == "new_installs" and err["message"] == "miyagi is full today, try tomorrow."
    assert "used" not in err and "cap" not in err  # the route is public: no counts
    assert r.headers["x-should-retry"] == "false" and int(r.headers["retry-after"]) >= 60
    resets = datetime.strptime(err["resets_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert timedelta(0) < resets - datetime.now(UTC) <= timedelta(days=1) and resets.hour == 0 and resets.minute == 0
    return err


def test_new_install_cap_refuses_new_installs_and_keeps_old_ones(make_cloud):
    client, app_mod = make_cloud(NEW_INSTALLS_PER_DAY="3")
    up = Upstream(app_mod)
    minted = [install(client)[0] for _ in range(3)]
    _assert_full(client.post("/v1/install", json={"app": "test"}))
    _assert_full(client.post("/v1/register", json={"install_id": "x", "app_version": "1", "platform": "darwin"}))
    for h in minted:  # installs already minted keep working
        assert haiku(client, h).status_code == 200
    assert len(up.requests) == 3
    assert app_mod.store.new_installs_on() == 3 and app_mod.store.usage_report(1)["new_installs_today"] == 3


def test_new_install_cap_survives_a_restart_and_resets_at_midnight(make_cloud):
    client, app_mod = make_cloud(NEW_INSTALLS_PER_DAY="2")
    install(client)
    install(client)
    client2, app2 = make_cloud(NEW_INSTALLS_PER_DAY="2")  # a new process on the same database
    _assert_full(client2.post("/v1/install", json={}))
    s, t = app2.store, time.time()
    assert s.mint_check("203.0.113.9", 0, 0, 0, now=t, new_per_day=2)["hit"] == "new_installs"
    tomorrow = (t // 86400 + 1) * 86400 + 5
    assert s.mint_check("203.0.113.9", 0, 0, 0, now=tomorrow, new_per_day=2)["hit"] is None
    r = s.mint_check("203.0.113.9", 0, 0, 0, now=t, new_per_day=2)
    assert r["hit"] == "new_installs" and 0 < r["retry_s"] <= 86400


def test_new_install_cap_default_and_off(make_cloud):
    _, app_mod = make_cloud(unset=("NEW_INSTALLS_PER_DAY",))
    assert app_mod.NEW_INSTALLS_PER_DAY == 500
    client, app_mod = make_cloud(NEW_INSTALLS_PER_DAY="0", REGISTER_LIMIT_PER_HOUR="0", REGISTER_LIMIT_PER_DAY="0")
    assert all(client.post("/v1/install", json={}).status_code == 200 for _ in range(30))


def test_refused_mints_do_not_use_the_days_installs(make_cloud):
    """A mint the per-network limit refuses is not counted against the day."""
    client, app_mod = make_cloud(NEW_INSTALLS_PER_DAY="5", REGISTER_LIMIT_PER_HOUR="2")
    assert [client.post("/v1/install", json={}).status_code for _ in range(4)] == [200, 200, 429, 429]
    assert app_mod.store.new_installs_on() == 2


# --------------------------------------------------------------------------- 3. runtime kill switch

def test_pause_needs_the_admin_token(make_cloud):
    client, app_mod = make_cloud()
    wrong = {"X-Admin-Token": "wrong-" + ADMIN_TOKEN}
    for r in (client.post("/admin/proxy/pause"), client.post("/admin/proxy/pause", headers=wrong),
              client.post("/admin/proxy/resume", headers=wrong), client.get("/admin/proxy", headers=wrong)):
        assert r.status_code == 401, r.text  # four misses: under the lockout's five
    assert app_mod.store.paused() is False
    assert client.post("/admin/proxy/pause", headers=wrong).status_code == 401
    assert client.post("/admin/proxy/pause", headers=ADMIN).status_code == 429  # locked out, the right token included
    assert app_mod.store.paused() is False
    weak, weak_mod = make_cloud(ADMIN_TOKEN="admin")  # a weak token still turns admin off: nobody can pause
    assert weak.post("/admin/proxy/pause", headers={"X-Admin-Token": "admin"}).status_code == 503
    assert weak_mod.store.paused() is False


def test_pause_stops_every_v1_route_at_once_and_resume_restores_it(make_cloud):
    client, app_mod = make_cloud()
    up = Upstream(app_mod)
    h, _ = install(client)
    assert haiku(client, h).status_code == 200
    r = client.post("/admin/proxy/pause", headers=ADMIN)
    assert r.status_code == 200 and r.json()["paused"] is True
    for r in (haiku(client, h), post_gemini(client, h, {"contents": []}), client.post("/v1/install", json={}),
              client.post("/v1/events", headers=h, json={"events": []})):
        assert r.status_code == 503 and r.json()["error"]["type"] == "proxy_disabled"
    assert len(up.requests) == 1
    health = client.get("/healthz").json()
    assert health["paused"] is True and health["proxy_enabled"] is False
    assert client.get("/admin/usage", headers=ADMIN).json()["paused"] is True  # admin keeps working
    assert client.post("/admin", data={"admin_token": ADMIN_TOKEN}).status_code == 200
    r = client.post("/admin/proxy/resume", headers=ADMIN)
    assert r.status_code == 200 and r.json()["paused"] is False
    assert haiku(client, h).status_code == 200


def test_pause_is_read_on_every_call_and_survives_a_restart(make_cloud):
    client, app_mod = make_cloud()
    Upstream(app_mod)
    h, _ = install(client)
    app_mod.store.set_paused(True)  # as another process (or a direct database write) would
    assert haiku(client, h).status_code == 503
    client2, app2 = make_cloud()  # a restart or a deploy on the same disk
    assert client2.post("/v1/install", json={}).status_code == 503
    assert client2.get("/admin/proxy", headers=ADMIN).json()["paused"] is True
    client2.post("/admin/proxy/resume", headers=ADMIN)
    assert app_mod.store.paused() is False
    assert haiku(client, h).status_code == 200


def test_env_switch_still_wins_over_resume(make_cloud):
    client, _ = make_cloud(PROXY_ENABLED="false")
    assert client.post("/admin/proxy/resume", headers=ADMIN).status_code == 200
    assert client.post("/v1/install", json={}).status_code == 503


# --------------------------------------------------------------------------- 4. alerts

@pytest.fixture
def alerts(make_cloud):
    """make_cloud with a (fake) webhook set and the sender replaced by a recorder: nothing leaves the machine."""
    sent: list[dict] = []

    def make(**env):
        client, app_mod = make_cloud(ALERT_WEBHOOK_URL=HOOK, **env)
        app_mod._dispatch = sent.append
        app_mod.ALERT_SPEND_CHECK_S = 0
        return client, app_mod

    return make, sent


def test_spend_alerts_fire_at_50_80_100_once_a_day(alerts):
    make, sent = alerts
    client, app_mod = make(ALERT_DAILY_USD="1")
    Upstream(app_mod)
    h, _ = install(client)
    other = "a" * 64
    for usd, want in ((0.10, []), (0.40, ["50%"]), (0.10, ["50%"]), (0.25, ["50%", "80%"]), (0.30, ["50%", "80%", "100%"]),
                      (5.00, ["50%", "80%", "100%"])):
        app_mod.store.add_tokens(other, "anthropic", HAIKU, 1, 1, usd)
        assert haiku(client, h).status_code == 200
        assert haiku(client, h).status_code == 200  # a second call never repeats an alert
        assert [p["text"].split(", ")[1].split(" ")[0] for p in sent] == want
    assert all(set(p) == {"text"} and "$1.00 daily alert line" in p["text"] for p in sent)
    assert app_mod.store.alerts_on() == ["spend_50", "spend_80", "spend_100"]
    client2, app2 = make(ALERT_DAILY_USD="1")  # a restart does not fire them again
    Upstream(app2)
    assert haiku(client2, h).status_code == 200
    assert len(sent) == 3


def test_token_alert_fires_once_per_token_per_day(alerts):
    make, sent = alerts
    client, app_mod = make(ALERT_TOKEN_DAILY_USD="0.30", ALERT_DAILY_USD="0")
    Upstream(app_mod)
    h, token_id = install(client)
    quiet, _ = install(client)
    app_mod.store.add_tokens(th_of(app_mod, h), "anthropic", HAIKU, 1, 1, 0.31)
    for _ in range(3):
        assert haiku(client, h).status_code == 200
        assert haiku(client, quiet).status_code == 200
    assert len(sent) == 1
    text = sent[0]["text"]
    assert token_id in text and "over the $0.30 alert line for one install" in text
    assert h["Authorization"][7:] not in text and HOOK not in text  # never the token or the webhook
    assert app_mod.store.alerts_on() == [f"token:{token_id}"]


def test_token_alert_defaults_to_three_times_the_install_cap(make_cloud):
    _, app_mod = make_cloud(unset=("FREE_DAILY_USD", "ALERT_TOKEN_DAILY_USD", "ALERT_DAILY_USD"))
    assert app_mod.ALERT_TOKEN_DAILY_USD == 3 * app_mod.FREE_DAILY_USD == 6.0
    assert app_mod.ALERT_DAILY_USD == 25.0


def test_install_cap_and_brake_alerts_fire_once(alerts):
    make, sent = alerts
    client, app_mod = make(NEW_INSTALLS_PER_DAY="1", DAILY_USD_CAP="1", ALERT_DAILY_USD="0")
    Upstream(app_mod)
    h, _ = install(client)
    for _ in range(3):
        _assert_full(client.post("/v1/install", json={}))
    app_mod.store.add_tokens("b" * 64, "anthropic", HAIKU, 1, 1, 1.0)
    for _ in range(3):
        assert haiku(client, h).json()["error"]["limit"] == "daily_usd"
    assert app_mod.store.alerts_on() == ["installs_full", "brake"]
    assert len(sent) == 2 and "new-install cap (1)" in sent[0]["text"] and "global spend brake" in sent[1]["text"]


def test_admin_test_alert_is_admin_only_and_once_a_day(alerts):
    make, sent = alerts
    client, _ = make()
    assert client.post("/admin/alerts/test").status_code == 401
    assert client.post("/admin/alerts/test", headers=ADMIN).json() == {"alerts": True, "sent": True}
    assert client.post("/admin/alerts/test", headers=ADMIN).json() == {"alerts": True, "sent": False}
    assert [p["text"] for p in sent] == ["miyagi-cloud: test alert. Alerts reach this channel."]


def test_discord_webhooks_get_content(make_cloud):
    _, app_mod = make_cloud(ALERT_WEBHOOK_URL="https://discord.com/api/webhooks/1/not-real")
    assert app_mod._alert_payload("hi") == {"content": "hi"}
    _, app_mod = make_cloud(ALERT_WEBHOOK_URL=HOOK)
    assert app_mod._alert_payload("hi") == {"text": "hi"}


@pytest.mark.parametrize("url", [None, "", "http://hooks.example/plain-http"])
def test_no_webhook_is_a_no_op(make_cloud, url, caplog):
    sent: list[dict] = []
    with caplog.at_level("ERROR", logger="miyagi.cloud"):
        client, app_mod = make_cloud(unset=("ALERT_WEBHOOK_URL",)) if url is None else make_cloud(ALERT_WEBHOOK_URL=url)
    if url:
        assert "ALERT_WEBHOOK_URL is not an https URL" in caplog.text and url not in caplog.text
    app_mod._dispatch = sent.append
    app_mod.ALERT_SPEND_CHECK_S = 0
    assert app_mod.ALERT_WEBHOOK_URL == ""
    Upstream(app_mod)
    h, _ = install(client)
    app_mod.store.add_tokens(th_of(app_mod, h), "anthropic", HAIKU, 1, 1, 100.0)
    assert haiku(client, h).status_code == 200
    assert app_mod.alert("spend_100", "x") is False
    assert sent == [] and app_mod.store.alerts_on() == []


def test_webhook_failures_never_break_a_call(alerts, caplog):
    make, _ = alerts
    client, app_mod = make(ALERT_DAILY_USD="0.000001")

    def boom(_payload):
        raise RuntimeError("webhook down")

    app_mod._dispatch = boom
    Upstream(app_mod)
    h, _ = install(client)
    assert haiku(client, h).status_code == 200


# --------------------------------------------------------------------------- 5. the 32000-token cap (R03)

BUILDER = {"model": SONNET, "max_tokens": 32000, "thinking": {"type": "adaptive"},
           "output_config": {"effort": "high"}, "system": "You write lessons.", "messages": msg("t" * 40_000)}


def test_token_cap_defaults_to_32000_and_the_builder_is_not_clamped(make_cloud):
    client, app_mod = make_cloud(unset=("MAX_TOKENS_CAP",))
    assert app_mod.MAX_TOKENS_CAP == 32000
    up = Upstream(app_mod)
    h, _ = install(client)
    assert post_anthropic(client, h, BUILDER, **{"x-miyagi-role": "lesson"}).status_code == 200
    assert up.last["max_tokens"] == 32000 and up.last["thinking"] == {"type": "adaptive"}
    assert post_anthropic(client, h, {**BUILDER, "max_tokens": 64000}).status_code == 200
    assert up.last["max_tokens"] == 32000  # still clamped above the cap
    render = (CLOUD / "render.yaml").read_text()
    block = render.split("key: MAX_TOKENS_CAP", 1)[1].split("- key:", 1)[0]
    assert 'value: "32000"' in block


def test_a_builds_parallel_calls_fit_the_default_install_cap(make_cloud):
    """The builder runs up to 4 Claude calls at once (LESSON_CLAUDE_CONCURRENCY). Each reserves max_tokens at the
    output price while in flight: 4 Sonnet calls at 32000 hold about $1.40, over the old $1.00 cap. The default
    FREE_DAILY_USD leaves room for them on a fresh install."""
    _, app_mod = make_cloud(unset=DEFAULT_CAPS)
    clean, uses, tokens = app_mod.sanitize_anthropic(json.loads(json.dumps(BUILDER)))
    reserve = app_mod.anthropic_reserve(clean, len(json.dumps(clean).encode()), uses, tokens)
    assert 0.33 < reserve < 0.36
    s = app_mod.store
    fresh, old = "c" * 64, "d" * 64
    assert [s.admit_call(fresh, "anthropic", SONNET, "lesson", usd_cap=app_mod.FREE_DAILY_USD, reserve_usd=reserve)[0]
            for _ in range(4)] == [None] * 4
    assert [s.admit_call(old, "anthropic", SONNET, "lesson", usd_cap=1.00, reserve_usd=reserve)[0]
            for _ in range(4)] == [None, None, "usd", "usd"]


# --------------------------------------------------------------------------- 6. Gemini off by default (D1)

@pytest.mark.parametrize("value", [None, "", "none", "None"])
def test_gemini_route_refuses_by_default(make_cloud, value):
    client, app_mod = (make_cloud(unset=("ALLOWED_GEMINI_MODELS",)) if value is None
                       else make_cloud(ALLOWED_GEMINI_MODELS=value))
    assert app_mod.ALLOWED_GEMINI == []
    up = Upstream(app_mod)
    h, _ = install(client)
    th = th_of(app_mod, h)
    for path in ("/v1/gemini/gemini-3.8-flash:generateContent", "/v1/gemini/v1beta/models/gemini-4-hydrogen:streamGenerateContent"):
        r = client.post(path, headers=h, json={"contents": [{"parts": [{"text": "hi"}]}]})
        assert r.status_code == 403, r.text
        err = r.json()["error"]
        assert err["type"] == "gemini_disabled" and err["type"] != "permission_error" and "Claude" in err["message"]
    assert up.requests == [] and app_mod.store.requests_today(th) == 0
    assert haiku(client, h).status_code == 200  # the install itself is fine
    assert client.get("/healthz").json()["gemini_enabled"] is False


def test_gemini_can_come_back_by_env(make_cloud):
    client, app_mod = make_cloud(ALLOWED_GEMINI_MODELS="gemini-3.8-flash")
    up = Upstream(app_mod)
    h, _ = install(client)
    assert post_gemini(client, h, {"contents": [{"parts": [{"text": "hi"}]}]}).status_code == 200
    assert len(up.requests) == 1 and client.get("/healthz").json()["gemini_enabled"] is True
    render = (CLOUD / "render.yaml").read_text()
    assert "value: none" in render.split("key: ALLOWED_GEMINI_MODELS", 1)[1].split("- key:", 1)[0]


# --------------------------------------------------------------------------- 7. /healthz

def test_healthz_reports_the_commit_and_booleans_only(make_cloud):
    sha = "0123456789abcdef0123456789abcdef01234567"
    client, app_mod = make_cloud(RENDER_GIT_COMMIT=sha, GEMINI_API_KEY="")
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["commit"] == sha and body["db_ok"] is True and body["paused"] is False and body["proxy_enabled"] is True
    assert body["keys_configured"] == {"anthropic": True, "gemini": False}
    assert "fake-upstream-key" not in r.text and ADMIN_TOKEN not in r.text and app_mod.store.path not in r.text
    assert all(isinstance(v, bool) for v in [body["db_ok"], *body["keys_configured"].values()])


@pytest.mark.parametrize("value", [None, "", "not a sha; <b>", "main"])
def test_healthz_commit_is_null_unless_a_sha(make_cloud, value):
    client, _ = make_cloud(unset=("RENDER_GIT_COMMIT",)) if value is None else make_cloud(RENDER_GIT_COMMIT=value)
    assert client.get("/healthz").json()["commit"] is None


def test_healthz_db_ok_false_still_answers(make_cloud, monkeypatch):
    client, app_mod = make_cloud()

    def broken():
        raise RuntimeError("disk gone")

    monkeypatch.setattr(app_mod.store, "ping", broken)
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["db_ok"] is False and "disk gone" not in r.text
