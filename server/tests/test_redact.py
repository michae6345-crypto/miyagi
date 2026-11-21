"""ROADMAP 5.2, never send secrets (offline): server/redact.py and the boundaries that use it (screen OCR / AX text,
coach requests, screen describe, VS Code selections). Every key below is fake."""

from __future__ import annotations

import asyncio
import io
import time

import pytest

from server import config as cfg
from server.redact import (
    SECRET_MARK,
    is_secret_file,
    redact_file_text,
    redact_secrets,
    scrub_secrets,
)

ANT = "sk-ant-api03-" + "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv"
OPENAI = "sk-proj-" + "Zz9Yy8Xx7Ww6Vv5Uu4Tt3Ss2Rr1Qq0Pp"
GOOGLE = "AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
GITHUB = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
SLACK = "xoxb-" + "123456789012-abcdefghijKLMN"
JWT = "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
B64 = "c2VjcmV0LXZhbHVlLWZvci10ZXN0cw1234"
HF = "hf_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7"
NPM = "npm_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
GITLAB = "glpat-" + "x1Y2z3A4b5C6d7E8f9G0"
PYPI = "pypi-AgEIcHlwaS5vcmc" + "CJDAwMDAwMDAwLTAwMDAtMDAwMC0wMDAw"


@pytest.mark.parametrize("secret", [ANT, OPENAI, GOOGLE, GITHUB, SLACK, JWT, "AKIA" + "IOSFODNN7EXAMPLE",
                                    "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc", "github_pat_" + "11ABCDEFG0" * 4,
                                    HF, NPM, GITLAB, PYPI])
def test_known_token_formats_are_redacted_anywhere_in_a_line(secret):
    out = redact_secrets(f"client = make(key='{secret}')  # mine")
    assert secret not in out and SECRET_MARK in out and out.endswith("# mine")


@pytest.mark.parametrize("line", [
    f"API_KEY={B64}", f"export TOKEN={B64}", f'SECRET = "{B64}"', f"'auth_token': '{B64}'",
    f'"client_secret": "{B64}"', f"password: {B64}",
])
def test_long_values_after_key_token_secret_names(line):
    out = redact_secrets(line)
    assert B64 not in out and SECRET_MARK in out


V = "abcd1234efgh5678ijkl"


@pytest.mark.parametrize("line, want", [
    (f"API_KEY={V} python app.py", f"API_KEY={SECRET_MARK} python app.py"),
    (f"export API_KEY={V}  # mine", f"export API_KEY={SECRET_MARK}  # mine"),
    (f"HF_TOKEN={V}; python x.py", f"HF_TOKEN={SECRET_MARK}; python x.py"),
    ('curl "https://newsapi.org/v2/top?country=us&apiKey=0123456789abcdef0123456789abcdef"',
     f'curl "https://newsapi.org/v2/top?country=us&apiKey={SECRET_MARK}"'),
    (f'url = "https://api.x.com/v1?access_token={V}&x=1"', f'url = "https://api.x.com/v1?access_token={SECRET_MARK}&x=1"'),
    (f'curl -H "x-api-key: {V}"', f'curl -H "x-api-key: {SECRET_MARK}"'),
    ("Authorization: Basic dXNlcjpwYXNzd29yZDEyMzQ1Njc4", f"Authorization: Basic {SECRET_MARK}"),
    (f"tool --token={V} run", f"tool --token={SECRET_MARK} run"),
    (f"client = f(api_key={V}, x=1)", f"client = f(api_key={SECRET_MARK}, x=1)"),
])
def test_values_after_a_secret_name_mid_line(line, want):
    """Terminal output and the coach's code hold NAME=value mid-line: a command, a URL query, a header."""
    assert redact_secrets(line, known=()) == want


@pytest.mark.parametrize("line", [
    "a basic understanding of loops", "Basic usage: python app.py", "sort(key=lambda x: x)",
    "model.fit(x, epochs=10, batch_size=32)", "https://example.com/docs?tab=readme-ov-file&page=2",
])
def test_mid_line_matcher_leaves_ordinary_text(line):
    assert redact_secrets(line, known=()) == line


def test_urls_with_a_password_and_bearer_headers():
    assert redact_secrets("DATABASE_URL=postgres://me:hunter2pass@db.example.com/x") == \
        f"DATABASE_URL=postgres://me:{SECRET_MARK}@db.example.com/x"
    assert redact_secrets("Authorization: Bearer abcdefghijklmnop1234") == f"Authorization: Bearer {SECRET_MARK}"


def test_pem_private_keys_are_redacted_whole():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nAAAA\n-----END RSA PRIVATE KEY-----"
    assert redact_secrets(f"key:\n{pem}\ndone") == f"key:\n{SECRET_MARK}\ndone"


@pytest.mark.parametrize("line", [
    "max_tokens=8000", "tokenizer = AutoTokenizer.from_pretrained('bert-base-uncased')",
    'api_key = os.environ["ANTHROPIC_API_KEY"]', 'TOKEN_HEADER = "x-miyagi-token"', "loss = 0.0123 at step 1000",
    "def get_key(name):", "keyboard_layout = 'qwerty'", "https://github.com/pytorch/pytorch", "task: ask the desk",
    "API_KEY=your-api-key-here", "SECRET_KEY = '<your secret>'", "", "x",
])
def test_ordinary_code_and_placeholders_pass_untouched(line):
    assert redact_secrets(line) == line


def test_the_keys_this_engine_holds_are_redacted_whatever_their_shape(monkeypatch):
    monkeypatch.setattr(cfg, "_app_keys", {"miyagiToken": "plain-install-token-0000"})
    monkeypatch.setattr("server.redact._known_cache", (0.0, ()))
    assert redact_secrets("token plain-install-token-0000 here") == f"token {SECRET_MARK} here"


def test_secret_files():
    for name in (".env", ".env.local", ".env.production", ".envrc", "id_rsa", "id_ed25519", "server.pem", "tls.key",
                 ".netrc", ".npmrc", ".pypirc", "credentials.json", "service-account-prod.json", "/a/b/.ENV"):
        assert is_secret_file(name), name
    for name in (".env.example", ".env.sample", ".env.template", "main.py", "env.py", "keys.md", "", None):
        assert not is_secret_file(name), name


def test_env_file_text_keeps_names_and_hides_values():
    text = "# keys\nOPENAI_API_KEY=abc\nexport NAME=bob\nPORT=8080\nDEBUG=true\nEMPTY=\nURL=${BASE}/x\n"
    out = redact_file_text("/proj/.env", text)
    assert out.splitlines() == ["# keys", f"OPENAI_API_KEY={SECRET_MARK}", f"export NAME={SECRET_MARK}", "PORT=8080",
                                "DEBUG=true", "EMPTY=", f"URL={SECRET_MARK}"]
    assert redact_file_text("~/.ssh/id_rsa", "-----BEGIN OPENSSH PRIVATE KEY-----\nabc").startswith(SECRET_MARK)
    assert "abc" not in redact_file_text("~/.ssh/id_rsa", "-----BEGIN OPENSSH PRIVATE KEY-----\nabc")
    code = f"import os\nKEY = '{ANT}'\nprint(1)\n"
    assert redact_file_text("main.py", code) == f"import os\nKEY = '{SECRET_MARK}'\nprint(1)\n"


def test_npmrc_netrc_and_pgpass_never_leak_a_value():
    """Their secret lines have no NAME=value shape: .npmrc hides everything after `=`, .netrc and .pgpass go whole."""
    npmrc = f"//registry.npmjs.org/:_authToken={NPM}\n; scope\n@me:registry=https://npm.me.dev/\nemail=${{NPM_EMAIL}}\n"
    out = redact_file_text("/proj/.npmrc", npmrc)
    assert out.splitlines() == [f"//registry.npmjs.org/:_authToken={SECRET_MARK}", "; scope",
                                f"@me:registry={SECRET_MARK}", "email=${NPM_EMAIL}"]
    plain = "//registry.npmjs.org/:_authToken=plainOldTokenValue"  # no known format: hidden for being in .npmrc
    assert redact_file_text(".npmrc", plain) == f"//registry.npmjs.org/:_authToken={SECRET_MARK}"
    for name, text, secret in ((".netrc", "machine api.github.com login bob password s3cr3tPassw0rdValue",
                                "s3cr3tPassw0rdValue"),
                               ("/home/me/.pgpass", "db.example.com:5432:app:bob:Sup3rS3cretPass", "Sup3rS3cretPass")):
        out = redact_file_text(name, text)
        assert secret not in out and "bob" not in out and out.startswith(SECRET_MARK), name


def test_pypirc_hides_values_after_equals_or_colon():
    out = redact_file_text("~/.pypirc", f"[pypi]\nusername = __token__\npassword: {PYPI}\n# done\n")
    assert out.splitlines() == ["[pypi]", f"username = {SECRET_MARK}", f"password: {SECRET_MARK}", "# done"]


@pytest.mark.parametrize("text", [
    "key" + "a-" * 50_000, "token_" * 17_000, "a." * 50_000 + "key='x'", "a-" * 50_000 + "://", "k=\"" * 33_000,
    "x=a" + " " * 100_000 + "b", "api_key=" * 12_500, "token:" * 17_000, "&key=" * 20_000, "basic " * 17_000,
    "Basic " + "A" * 100_000, "?token=" + "a1" * 50_000 + "&", " key: " * 17_000,
])
def test_a_100kb_adversarial_line_redacts_quickly(text):
    """Coach requests redact the learner's whole file: a long run of `a-a-...` or `token_token_...` (minified code, a
    data line) must not backtrack for seconds. Every pattern is linear; this was 9.8 s / 23 s before."""
    assert len(text) >= 96_000
    for fn in (lambda: redact_secrets(text, known=()), lambda: redact_file_text(".env", text),
               lambda: redact_file_text(".npmrc", text)):
        t0 = time.perf_counter()
        fn()
        assert time.perf_counter() - t0 < 0.2


def test_scrub_walks_payloads():
    out = scrub_secrets({"code": f"k={GITHUB}", "lines": [GOOGLE, 3], "n": 1, "t": (SLACK,)})
    assert out == {"code": f"k={SECRET_MARK}", "lines": [SECRET_MARK, 3], "n": 1, "t": (SECRET_MARK,)}


# ------------------------------------------------------------------ boundaries

def test_screen_ocr_and_ax_text_is_redacted():
    from server.screen.privacy import holds_secret, redact

    out = redact(f"OPENAI_API_KEY={OPENAI}  mail jane@example.com")
    assert OPENAI not in out and "[email]" in out and holds_secret(out)
    assert not holds_secret("print('hello')")


def test_coach_requests_are_redacted_but_fixture_keys_are_not_changed():
    from server.coach import llm
    from server.coach.common import number_lines

    assert ANT not in number_lines(f"key = '{ANT}'\nprint(1)")
    blocks = [{"type": "image", "source": {"data": "xx"}}, {"type": "text", "text": f"code: {GITHUB}"}]
    out = llm.redact_user_content(blocks)
    assert out[0] is blocks[0] and out[1]["text"] == f"code: {SECRET_MARK}" and GITHUB in blocks[1]["text"]

    class Api:  # the shaped request, never sent
        messages = object()
        beta = type("B", (), {"messages": object()})()

    _, kwargs = llm._request(Api(), llm.SONNET, [], f"LEARNER CODE:\nKEY = '{ANT}'", {}, "low", 100)
    assert ANT not in json_dump(kwargs)


def json_dump(v) -> str:
    import json

    return json.dumps(v, default=str)


def test_screen_describe_masks_secret_rows_and_redacts_its_text():
    from PIL import Image

    from server.screen.describe import to_jpeg

    img = Image.new("RGB", (200, 100), (255, 255, 255))
    raw = to_jpeg(img, mask=[(10, 10, 50, 20)])
    back = Image.open(io.BytesIO(raw)).convert("RGB")
    assert back.getpixel((35, 20))[0] < 40  # blacked out
    assert back.getpixel((150, 80))[0] > 215  # the rest is untouched


def test_target_picker_masks_rows_that_held_a_secret():
    from server.screen.target import _secret_rects
    from server.screen.types import Block, Rect, ScreenObservation

    obs = ScreenObservation(t=0.0, app="Code", blocks=[Block(f"KEY={SECRET_MARK}", Rect(1, 2, 3, 4), 1.0, "Code"),
                                                       Block("print(1)", Rect(5, 6, 7, 8), 1.0, "Code")],
                            screen=Rect(0, 0, 100, 100), scale=1.0)
    assert _secret_rects(obs) == [Rect(1, 2, 3, 4)]


def test_vscode_selections_are_redacted_before_the_card_and_the_coach():
    from server.orchestrator.selection import from_drawer, from_vscode

    sel = from_vscode({"type": "explain_selection", "file": "/l/.env", "text": f"OPENAI_API_KEY={OPENAI}",
                       "around": {"startLine": 1, "text": f"OPENAI_API_KEY={OPENAI}\nPORT=8080"}})
    assert OPENAI not in sel["text"] and OPENAI not in sel["title"] and OPENAI not in sel["around"]["text"]
    assert sel["text"] == f"OPENAI_API_KEY={SECRET_MARK}"
    sel = from_vscode({"file": "/l/main.py", "text": f"client = Client('{ANT}')"})
    assert ANT not in sel["text"]
    assert GITHUB not in from_drawer(f"use {GITHUB}")["text"]


def test_a_secret_step_file_reaches_the_coach_as_names_only():
    """A step whose file is .env / .env.local: diagnose, explain, diagrams and "Explain this" get the names with every
    value hidden (a short password has no key shape); grading and patching still read the real text."""
    from types import SimpleNamespace

    from server.orchestrator.session import LessonSession, _for_coach

    env = "# db\nDB_PASSWORD=hunter2\nTOKEN=abc\nPORT=8080\n"
    for name in (".env", ".env.local", "sub/.env"):
        out = _for_coach(env, name)
        assert "hunter2" not in out and "=abc" not in out
        assert out.splitlines()[:2] == ["# db", f"DB_PASSWORD={SECRET_MARK}"]
    assert _for_coach("x = 'hunter2'\n", "main.py") == "x = 'hunter2'\n"  # not a secret file: llm.py redacts keys
    fake = SimpleNamespace(_code_excerpt=lambda step, limit=6000: (env, ".env"))
    code, file = LessonSession._coach_excerpt(fake, {"id": "s1"})
    assert file == ".env" and "hunter2" not in code and fake._code_excerpt({})[0] == env


def test_do_it_for_me_sends_a_secret_file_without_its_values(monkeypatch):
    from server.coach import actions, llm

    seen = []

    async def fake_call(**kw):
        seen.append(kw["user_text"])
        raise llm.CoachLLMError("offline test")

    monkeypatch.setattr(llm, "structured_call", fake_call)
    with pytest.raises(llm.CoachUnavailable):
        asyncio.run(actions.do_it_for_me({"id": "s", "title": "set the port"}, ".env",
                                          "DB_PASSWORD=hunter2\nPORT=80\n", {}, lesson={}, use_diagnosis=False))
    assert seen and "hunter2" not in seen[0] and f"DB_PASSWORD={SECRET_MARK}" in seen[0]


def test_a_patch_that_writes_the_secret_marker_is_refused():
    """The coach reads `api_key="[secret]"`; a patch echoing that line would write the placeholder into the learner's
    file. apply_fix returns no new_text, so Do it for me falls back to the fix-it-by-hand card."""
    from server.coach.hints import apply_fix

    yours = 'resp = client.chat.completions.create(model="gpt-4o-mini" messages=[])'
    text = f'from openai import OpenAI\nclient = OpenAI(api_key="{OPENAI}")\n{yours}\n'
    fixed = 'resp = client.chat.completions.create(model="gpt-4o-mini", messages=[])'
    p = apply_fix({"yours": yours, "expected": f'client = OpenAI(api_key="{SECRET_MARK}")\n{fixed}', "file": "main.py"},
                  text)
    assert p["new_text"] is None and SECRET_MARK in p["error"]
    ok = apply_fix({"yours": yours, "expected": fixed, "file": "main.py"}, text)
    assert ok["error"] is None and OPENAI in ok["new_text"]  # a patch that leaves the key line alone still applies


def _secret_obs():
    from server.screen.types import Block, Rect, ScreenObservation, Window

    return ScreenObservation(t=0.0, app="Code", windows=[Window("Code", "main.py", Rect(0, 0, 200, 100))],
                             blocks=[Block(f"OPENAI_API_KEY={SECRET_MARK}", Rect(10, 10, 80, 10), 1.0, "Code"),
                                     Block("print(1)", Rect(10, 60, 40, 10), 1.0, "Code")],
                             screen=Rect(0, 0, 200, 100), scale=1.0)


def test_scene_looks_black_out_rows_that_held_a_secret():
    from server.orchestrator.scene_watch import SceneWatch
    from server.screen.types import Rect

    assert SceneWatch._mask_args(_secret_obs())["mask"] == [Rect(10, 10, 80, 10)]


def test_diagnose_screenshots_black_out_rows_that_held_a_secret():
    from PIL import Image

    from server.coach.screen import ScreenContext

    ctx = ScreenContext.from_observation(_secret_obs(), Image.new("RGB", (200, 100), (255, 255, 255)), (150, 90))
    img = ctx.pil()
    assert img.getpixel((50, 15))[0] < 40  # the key's row
    assert img.getpixel((150, 50))[0] > 215  # the rest of the screen
    ov = ctx.overview()  # what claude_content encodes: the row stays black after the boxes are drawn
    f = ov.width / 200
    assert ov.getpixel((int(50 * f), int(15 * f)))[0] < 40
    assert len(ctx.claude_content()) == 3


def test_web_grounding_never_searches_with_a_secret(monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from server.coach import web

    urls = []

    async def fake_fetch(kind, url):
        urls.append(url)
        return None

    monkeypatch.setattr(web, "fetch", fake_fetch)
    monkeypatch.setattr(web, "configured", lambda: True)
    monkeypatch.setattr(web, "docs_for", web._docs_for)
    monkeypatch.setattr(web, "community_signals", web._community_signals)
    err = f"requests.exceptions.HTTPError: 403 for url: https://maps.example.com/api?key={GOOGLE}&q=x"
    asyncio.run(web.gather("requests", "", f"why 403 with token={B64} {GITHUB}", error=err, timeout=2.0))
    assert len(urls) == 2
    for u in urls:
        q = parse_qs(urlparse(u).query)["q"][0]
        assert GOOGLE not in q and B64 not in q and GITHUB not in q and SECRET_MARK not in q
    assert web.search_safe("TypeError: x is not a function") == "TypeError: x is not a function"
    assert GOOGLE not in web.serp_url(f"error {GOOGLE}")
