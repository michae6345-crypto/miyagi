"""Account-level bans and cap carry-over across account deletion, offline.

Deleting an account must not lift a ban or reset the day's spend and the month's builds: both hang on a salted hash of
the provider email (id_hash), not on the install token or the Supabase user id.

    cd cloud && python -m pytest tests -q
"""

from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip("jwt")

from test_account_delete import ADMIN, OTHER, SERVICE_KEY, delete, make_cloud, new_install  # noqa: E402,F401
from test_link import USER, make_token  # noqa: E402

EMAIL = "Learner@Example.com"
VIDEOS = ["dQw4w9WgXcQ", "oHg5SJYRHA0", "aaaaaaaaaaa", "bbbbbbbbbbb"]


def tok(email: str = EMAIL, sub: str = USER) -> str:
    return make_token(sub=sub, email=email)


def link(client, headers, **kw):
    return client.post("/v1/link", headers=headers, json={"access_token": tok(**kw)})


def test_delete_keeps_a_disabled_token_disabled(make_cloud):
    client, app_mod, _ = make_cloud()
    headers, t = new_install(client)
    h = app_mod.hash_token(t)
    assert link(client, headers).status_code == 200
    assert client.post(f"/admin/tokens/{h[:12]}/disable", headers=ADMIN).status_code == 200
    # a disabled install token cannot call delete itself, but the signed-in account delete still runs
    r = delete(client, headers, {"access_token": tok()})
    assert r.status_code == 200 and r.json()["install"] is False
    row = app_mod.store.get_token(h)
    assert row is not None and row["disabled"] == 1
    assert app_mod.store.get_link(h) is None
    assert client.get("/v1/lessons/dQw4w9WgXcQ?schema=1", headers=headers).status_code == 403


def test_resign_after_delete_gets_the_carried_over_caps(make_cloud):
    client, app_mod, _ = make_cloud()
    s = app_mod.store
    headers, t = new_install(client)
    h = app_mod.hash_token(t)
    assert link(client, headers).status_code == 200
    s.add_tokens(h, "anthropic", "claude-haiku-5-5", 1000, 200, 1.25)
    for v in VIDEOS[:2]:
        assert s.claim_build(h, v, 3, user_id=USER)[0]
    assert delete(client, headers, {"access_token": tok()}).status_code == 200
    assert s.user_usage_today(USER)[1] == 0  # the old account's rows are gone

    # same Google account, new Supabase id (case and gmail-style variants of the email count as the same person)
    headers2, t2 = new_install(client)
    h2 = app_mod.hash_token(t2)
    assert link(client, headers2, email="learner@example.com", sub=OTHER).status_code == 200
    assert s.user_usage_today(OTHER)[1] == pytest.approx(1.25)
    # builds: 2 of 3 are already used, so one more fits and the next is capped
    assert s.claim_build(h2, VIDEOS[2], 3, user_id=OTHER) == (True, 3)
    assert s.claim_build(h2, VIDEOS[3], 3, user_id=OTHER) == (False, 3)
    assert s.builds_in_month(h2, user_id=OTHER) == 3

    # a different person does not inherit it
    headers3, t3 = new_install(client)
    assert link(client, headers3, email="someone@else.org", sub="11111111-2222-4333-8444-555555555555").status_code == 200
    assert s.user_usage_today("11111111-2222-4333-8444-555555555555")[1] == 0

    # a second delete the same day adds, it does not replace
    s.add_tokens(h2, "anthropic", "claude-haiku-5-5", 10, 10, 0.5)
    assert delete(client, headers2, {"access_token": tok(email=EMAIL, sub=OTHER)}).status_code == 200
    headers4, _ = new_install(client)
    assert link(client, headers4, sub="22222222-2222-4333-8444-555555555555").status_code == 200
    assert s.user_usage_today("22222222-2222-4333-8444-555555555555")[1] == pytest.approx(1.75)


def test_gmail_dots_and_plus_tags_are_one_identity(make_cloud):
    _, app_mod, _ = make_cloud()
    s = app_mod.store
    assert s.identity_hash("A.B+x@gmail.com") == s.identity_hash("ab@googlemail.com")
    assert s.identity_hash("a.b@example.com") != s.identity_hash("ab@example.com")
    assert s.identity_hash("ab+spam@example.com") == s.identity_hash("AB@example.com")
    assert s.identity_hash("not-an-email") is None


def test_no_raw_email_is_stored(make_cloud):
    client, app_mod, _ = make_cloud()
    headers, t = new_install(client)
    link(client, headers)
    app_mod.store.ban_identity(app_mod.store.identity_hash(EMAIL), "test")
    con = sqlite3.connect(app_mod.store.path)
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        for row in con.execute(f"SELECT * FROM {table}"):
            assert not any(isinstance(v, str) and "example.com" in v.lower() for v in row), table
    con.close()


def test_banned_identity_is_refused_on_link_session_and_model_call(make_cloud):
    client, app_mod, _ = make_cloud()
    headers, t = new_install(client)
    assert link(client, headers).status_code == 200
    r = client.post("/admin/identities/ban", headers=ADMIN, json={"email": EMAIL.upper(), "reason": "abuse"})
    assert r.status_code == 200 and r.json()["banned"] is True and r.json()["tokens_disabled"] == 1

    # the install token was disabled with it, and deleting the account does not lift anything
    assert client.get("/v1/lessons/dQw4w9WgXcQ?schema=1", headers=headers).status_code == 403
    assert delete(client, headers, {"access_token": tok()}).status_code == 200
    assert app_mod.store.get_token(app_mod.hash_token(t))["disabled"] == 1

    # a fresh install and a fresh Supabase id with the same email: refused at link and session
    headers2, t2 = new_install(client)
    new_tok = tok(sub=OTHER)
    r = client.post("/v1/link", headers=headers2, json={"access_token": new_tok})
    assert r.status_code == 403 and r.json() == {"error": "account_banned"}
    r = client.post("/v1/session", headers=headers2, json={"access_token": new_tok})
    assert r.status_code == 403 and r.json() == {"error": "account_banned"}
    assert app_mod.store.get_link(app_mod.hash_token(t2)) is None


def test_ban_by_user_id_refuses_model_calls_of_a_live_account(make_cloud):
    client, app_mod, _ = make_cloud()
    headers, t = new_install(client)
    headers_b, _t = new_install(client)
    assert link(client, headers).status_code == 200
    # a second install of the same account that stays enabled until the ban
    assert link(client, headers_b).status_code == 200
    app_mod.store.ban_identity(app_mod.store.identity_of(USER))  # no token disabling needed for the refusal below
    app_mod.store._q("UPDATE tokens SET disabled = 0")  # prove the identity check alone refuses
    for h in (headers, headers_b):
        r = client.post("/v1/anthropic/messages", headers=h,
                        json={"model": "claude-haiku-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 403
        assert r.json()["error"]["type"] == "permission_error"
        assert r.json()["error"]["message"] == app_mod.ACCOUNT_BANNED_MESSAGE

    # the admin route by user id
    r = client.post("/admin/identities/ban", headers=ADMIN, json={"user_id": USER})
    assert r.status_code == 200 and r.json()["tokens_disabled"] == 2
    assert client.post("/admin/identities/ban", headers=ADMIN, json={}).status_code == 400
    assert client.post("/admin/identities/ban", json={"user_id": USER}).status_code == 401
    listed = client.get("/admin/identities", headers=ADMIN).json()["banned"]
    assert len(listed) == 1 and listed[0]["id"] == app_mod.store.identity_of(USER)[:12]


def test_unban_lets_the_identity_link_again(make_cloud):
    client, app_mod, _ = make_cloud()
    headers, _t = new_install(client)
    assert client.post("/admin/identities/ban", headers=ADMIN, json={"email": EMAIL}).status_code == 200
    assert link(client, headers).status_code == 403
    r = client.post("/admin/identities/unban", headers=ADMIN, json={"email": EMAIL})
    assert r.status_code == 200 and r.json() == {"id": r.json()["id"], "banned": False, "was_banned": True}
    assert link(client, headers).status_code == 200
    assert client.get("/admin/identities", headers=ADMIN).json()["banned"] == []
    assert client.post("/admin/identities/unban", headers=ADMIN, json={"email": EMAIL}).json()["was_banned"] is False


def test_banned_user_who_changes_email_stays_banned(make_cloud):
    client, app_mod, _ = make_cloud()
    headers, _t = new_install(client)
    assert link(client, headers).status_code == 200
    assert client.post("/admin/identities/ban", headers=ADMIN, json={"email": EMAIL}).status_code == 200
    headers2, _t2 = new_install(client)
    for path in ("/v1/link", "/v1/session"):  # same Supabase user id, another email
        r = client.post(path, headers=headers2, json={"access_token": tok(email="new.address@other.org")})
        assert r.status_code == 403 and r.json() == {"error": "account_banned"}
    assert app_mod.store.identity_of(USER) == app_mod.store.identity_hash(EMAIL)  # never moved to a fresh hash
    # unban lifts both
    assert client.post("/admin/identities/unban", headers=ADMIN, json={"email": EMAIL}).status_code == 200
    assert link(client, headers2, email="new.address@other.org").status_code == 200


def test_ban_by_user_id_works_for_a_legacy_link(make_cloud):
    client, app_mod, _ = make_cloud()
    s = app_mod.store
    headers, t = new_install(client)
    h = app_mod.hash_token(t)
    s.link_user(h, USER)  # linked before identities were recorded: no user_identity row
    assert s.identity_of(USER) is None
    r = client.post("/admin/identities/ban", headers=ADMIN, json={"user_id": USER})
    assert r.status_code == 200 and r.json()["tokens_disabled"] == 1
    assert s.get_token(h)["disabled"] == 1
    # the legacy user deletes the account (the delete request's claims carry the email) and signs in again
    assert delete(client, headers, {"access_token": tok()}).status_code == 200
    headers2, _t2 = new_install(client)
    r = client.post("/v1/link", headers=headers2, json={"access_token": tok(sub=OTHER)})
    assert r.status_code == 403 and r.json() == {"error": "account_banned"}
    # and the user id alone stays refused, whatever the email
    r = client.post("/v1/link", headers=headers2, json={"access_token": tok(email="x@y.org")})
    assert r.status_code == 403
    assert client.post("/admin/identities/unban", headers=ADMIN, json={"user_id": USER}).json()["was_banned"] is True


def test_ban_by_email_of_an_unmapped_user_refuses_the_next_link(make_cloud):
    client, _app, _ = make_cloud()
    headers, _t = new_install(client)
    r = client.post("/admin/identities/ban", headers=ADMIN, json={"email": "never.seen@example.org"})
    assert r.json()["tokens_disabled"] == 0
    assert link(client, headers, email="never.seen@example.org").status_code == 403


def test_unverified_email_is_no_identity_but_still_links(make_cloud):
    client, app_mod, _ = make_cloud()
    headers, _t = new_install(client)
    assert client.post("/admin/identities/ban", headers=ADMIN, json={"email": EMAIL}).status_code == 200
    r = client.post("/v1/link", headers=headers, json={"access_token": make_token(email=EMAIL, email_verified=False)})
    assert r.status_code == 200
    assert app_mod.store.identity_of(USER) is None


def test_identity_key_is_random_persisted_and_not_derived(make_cloud):
    _, app_mod, _ = make_cloud()
    s = app_mod.store
    assert len(s._identity_key) == 32
    again = type(s)(s.path)
    assert again._identity_key == s._identity_key and again.identity_hash(EMAIL) == s.identity_hash(EMAIL)
