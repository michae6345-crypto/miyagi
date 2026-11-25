"""server/linkread: any link -> teachable text, offline. Every fetch goes through an httpx.MockTransport serving saved
fixtures (server/linkread/tests/fixtures); nothing reaches the network or a model."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest

from server.linkread import fetch, github, preview
from server.linkread.markdown import parse_markdown, parse_rst
from server.linkread.model import Block, Extraction, LinkUnreadable, render
from shared.contracts.events import LINK_CACHE_KEY_RE, LinkPreview

FIX = Path(__file__).parent / "fixtures"
MDN = "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/map"
BLOG = "https://bytegarden.example/posts/first-flask-app/"
REPO = "https://github.com/acme-labs/tinyhttp"
API = "https://api.github.com/repos/acme-labs/tinyhttp"
RAW = "https://raw.githubusercontent.com/acme-labs/tinyhttp/main"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


HTML = {"content-type": "text/html; charset=utf-8"}


class Site:
    """A fake internet: {url: (status, body, headers)}; anything else is a 404. Records every URL asked for."""

    def __init__(self, pages: dict) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        assert "cookie" not in {k.lower() for k in request.headers}, "no cookies on a link read"
        hit = self.pages.get(url)
        if hit is None and url.startswith("https://api.github.com/"):  # GitHub's API ignores the case of owner / repo
            hit = next((v for k, v in self.pages.items() if k.lower() == url.lower()), None)
        if hit is None:
            return httpx.Response(404, text="not found")
        if isinstance(hit, Exception):
            raise hit
        status, body, headers = hit
        content = body.encode("utf-8") if isinstance(body, str) else body
        return httpx.Response(status, content=content, headers=headers)


@pytest.fixture
def site(monkeypatch):
    def make(pages: dict) -> Site:
        s = Site(pages)
        monkeypatch.setattr(fetch, "TRANSPORT", httpx.MockTransport(s))
        return s
    return make


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(request):
        raise AssertionError(f"unexpected fetch {request.url}")
    monkeypatch.setattr(fetch, "TRANSPORT", httpx.MockTransport(refuse))


def robots(origin: str, body: str | None = None, status: int = 200) -> dict:
    if body is None:
        return {}
    return {f"{origin}/robots.txt": (status, body, {"content-type": "text/plain"})}


ALLOW_ALL = "User-agent: *\nDisallow: /private/\n"


# ------------------------------------------------------------------------------------------------ MDN page


@pytest.mark.asyncio
async def test_mdn_page_main_content_and_code_kept_verbatim(site):
    s = site({MDN: (200, fx("mdn_array_map.html"), HTML), **robots("https://developer.mozilla.org", ALLOW_ALL)})
    ex = await fetch.read_link(MDN)
    assert ex.kind == "web" and ex.site == "developer.mozilla.org"
    assert ex.title == "Array.prototype.map()"
    text = ex.text()
    # navigation, sidebar, table of contents, feedback box, cookie banner, copy buttons: gone
    for junk in ("Skip to main content", "Array.prototype.concat", "In this article", "Help improve MDN",
                 "We use cookies", "Copy to Clipboard", "Your blueprint", "Search MDN", "References"):
        assert junk not in text, junk
    # images dropped (their alt text too)
    assert "Diagram of map" not in text and "map-diagram.png" not in text
    # code blocks: language from "brush: js", text verbatim (entities decoded, blank lines and indentation kept)
    codes = ex.code_blocks
    assert len(codes) == 4 and {c.lang for c in codes} == {"javascript"}
    assert codes[0].text.startswith("const numbers = [1, 4, 9, 16];\n\n// Pass a function to map\n")
    assert "numbers.map((x) => x * 2);" in codes[0].text
    assert 'if (reformatted.length < 3 && reformatted[0]) {\n    console.log(reformatted);' in codes[3].text
    assert "```javascript\nconst values = [1, 4, 9];" in text
    # headings as structure, with the page's anchors
    heads = [(h.level, h.text, h.anchor) for h in ex.headings]
    assert heads[:3] == [(1, "Array.prototype.map()", None), (2, "Try it", "try_it"), (2, "Syntax", "syntax")]
    ref = ex.page_ref(ex.headings[1])
    assert ref == {"url": f"{MDN}#try_it", "heading": "Try it"}
    # inline code survives as `code`; a table row as cells
    assert "The `map()` method of `Array` instances" in text
    assert "ECMAScript Language Specification, array.prototype.map" in text
    assert s.calls[0] == "https://developer.mozilla.org/robots.txt"


@pytest.mark.asyncio
async def test_mdn_preview_is_teachable_code(site):
    site({MDN: (200, fx("mdn_array_map.html"), HTML), **robots("https://developer.mozilla.org", ALLOW_ALL)})
    seen: list[str] = []
    p, ex = await preview.preview(MDN, "r1", is_cached=lambda key: seen.append(key) or True)
    assert isinstance(p, LinkPreview) and ex is not None
    assert p.kind == "web" and p.reqId == "r1" and p.pending is False and p.error is None
    assert p.teachable is True and p.teach.code is True
    assert p.tools == ["vscode"] and p.site == "developer.mozilla.org"
    assert p.cached is True and seen == [ex.cache_key] and LINK_CACHE_KEY_RE.match(ex.cache_key)
    assert 3 <= p.estMinutes <= 30
    assert p.finalUrl is None  # no redirect
    LinkPreview.model_validate(p.model_dump(exclude_none=True))  # the contract accepts it


# ------------------------------------------------------------------------------------------------ blog tutorial


@pytest.mark.asyncio
async def test_blog_tutorial_after_redirect(site):
    start = "http://www.bytegarden.example/?p=412&utm_source=newsletter"  # a WordPress short link
    s = site({
        start: (301, "", {"location": BLOG}),
        BLOG: (200, fx("blog_flask_tutorial.html"), HTML),
        **robots("http://www.bytegarden.example", ALLOW_ALL),
        **robots("https://bytegarden.example", ALLOW_ALL),
    })
    ex = await fetch.read_link(start)
    assert ex.final_url == BLOG and ex.site == "bytegarden.example"
    assert ex.title == "Build your first Flask app in 15 minutes"
    assert ex.author == "Dana Reyes"
    text = ex.text()
    for junk in ("cookies", "Subscribe to our newsletter", "Share this", "Great walkthrough", "You might also like",
                 "About Dana", "Popular", "All rights reserved", "Previous: Python lists", "March 3, 2026",
                 "Posted in", "A laptop with code"):
        assert junk not in text, junk
    assert [c.lang for c in ex.code_blocks] == ["bash", "bash", "python", "text"]
    py = ex.code_blocks[2].text
    assert py.startswith("from flask import Flask\n\napp = Flask(__name__)\n\n\n@app.route")
    assert '    return "<h1>Hello, Flask!</h1>"' in py
    items = [(b.number, b.text) for b in ex.blocks if b.kind == "item"]
    assert items == [(1, "Save `app.py`."), (2, "In the terminal, run `python app.py`."),
                     (3, "Open `http://127.0.0.1:5000` in your browser.")]
    # the code block inside list item 3 comes right after it
    i3 = next(i for i, b in enumerate(ex.blocks) if b.kind == "item" and b.number == 3)
    assert ex.blocks[i3 + 1].kind == "code" and "Running on" in ex.blocks[i3 + 1].text
    assert "1. Save `app.py`.\n2. In the terminal" in text  # items render as one list
    # robots.txt read for both hosts (the redirect changed host)
    assert "https://bytegarden.example/robots.txt" in s.calls

    p = preview.preview_from(ex, start, "r2")
    assert p.teachable and p.teach.steps and p.teach.code
    assert p.tools == ["vscode", "terminal"]
    assert p.finalUrl == "https://bytegarden.example/posts/first-flask-app"
    same = preview.preview_from(ex, "https://www.bytegarden.example/posts/first-flask-app/?utm_source=x")
    assert same.finalUrl is None  # only a spelling of the same link: no finalUrl
    assert p.why == "Walks through steps, with code you type and run."


# ------------------------------------------------------------------------------------------------ walls and nothing


@pytest.mark.asyncio
async def test_paywalled_page_is_blocked(site):
    url = "https://dataledger.example/2026/advanced-pandas"
    site({url: (200, fx("paywalled.html"), HTML)})  # no robots.txt (404): allowed
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "blocked" and "paywall" in e.value.reason and e.value.fail_code == "blocked"
    p, ex = await preview.preview(url, "r3")
    assert ex is None and p.kind == "web" and p.error == "blocked" and p.title == "Advanced pandas: ten tricks the pros use"
    LinkPreview.model_validate(p.model_dump(exclude_none=True))


@pytest.mark.asyncio
async def test_login_wall_is_blocked(site):
    url = "https://coursehub.example/lessons/42"
    site({url: (200, fx("login_wall.html"), HTML)})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "blocked" and "sign-in" in e.value.reason


@pytest.mark.asyncio
async def test_essay_is_not_teachable(site):
    url = "https://margin.example/why-i-switched-editors"
    site({url: (200, fx("essay_not_teachable.html"), HTML)})
    p, ex = await preview.preview(url)
    assert ex is not None and p.error is None and p.kind == "web"
    assert p.teachable is False and p.teach.steps is False and p.teach.code is False
    assert p.why == "It's mostly reading, with nothing to do or type."
    assert p.tools is None and p.estMinutes is None
    assert p.author == "Sam Okafor"
    assert "Share on Mastodon" not in ex.text() and "November 2, 2026" not in ex.text()


@pytest.mark.asyncio
async def test_script_only_page_has_no_content(site):
    url = "https://dashdocs.example/guide/install"
    site({url: (200, fx("spa_shell.html"), HTML)})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "no_content" and "JavaScript" in e.value.reason and e.value.fail_code == "no_content"
    p, _ = await preview.preview(url)
    assert p.error is None and p.teachable is False and "JavaScript" in p.why and p.title == "Dashboard Docs"


@pytest.mark.asyncio
async def test_sphinx_page_in_latin1(site):
    url = "https://docs.snake.example/3/tutorial/venv.html"
    body = fx("sphinx_venv.html").encode("iso-8859-1", errors="replace")
    site({url: (200, body, {"content-type": "text/html"})})
    ex = await fetch.read_link(url)
    assert "Café owners and résumé writers" in ex.text()
    assert ex.title == "12. Virtual Environments and Packages"
    assert [h.text for h in ex.headings][:2] == ["12. Virtual Environments and Packages", "12.1. Introduction"]
    assert ex.headings[1].anchor == "introduction"
    assert [(c.lang, c.text) for c in ex.code_blocks] == [
        ("bash", "python -m venv tutorial-env"), ("bash", "source tutorial-env/bin/activate"),
        ("bash", "(tutorial-env) $ python -m pip install novas"), ("python", "import novas\nprint(novas.__version__)")]
    assert "Navigation" not in ex.text() and "Table of Contents" not in ex.text() and "Copyright" not in ex.text()
    v = preview.verdict(ex)
    assert v.code and "terminal" in v.tools


@pytest.mark.parametrize("ctype, word", [("application/pdf", "PDF"), ("image/png", "image"),
                                          ("application/json", "isn't a web page")])
@pytest.mark.asyncio
async def test_not_text_is_no_content(site, ctype, word):
    url = "https://files.example/thing"
    site({url: (200, b"\x89PNG....", {"content-type": ctype})})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "no_content" and word in e.value.reason


@pytest.mark.asyncio
async def test_markdown_link_is_read_as_markdown(site):
    url = "https://notes.example/setup.md"
    md = "# Set up\n\nInstall the tools first, then check them.\n\n```sh\nbrew install git\ngit --version\n```\n" + \
         "\nThat is all there is to it, and it takes about five minutes on a fresh Mac with a decent connection.\n"
    site({url: (200, md, {"content-type": "text/plain; charset=utf-8"})})
    ex = await fetch.read_link(url)
    assert ex.title == "Set up" and ex.code_blocks[0].lang == "bash" and ex.code_blocks[0].text == "brew install git\ngit --version"


# ------------------------------------------------------------------------------------------------ status codes, robots


@pytest.mark.parametrize("status, code", [(401, "blocked"), (403, "blocked"), (451, "blocked"), (404, "not_found"),
                                          (410, "not_found"), (429, "busy"), (503, "unknown")])
@pytest.mark.asyncio
async def test_status_codes(site, status, code):
    url = "https://status.example/page"
    site({url: (status, "<html><body>nope</body></html>", HTML)})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == code


@pytest.mark.asyncio
async def test_unreachable_is_offline(site):
    url = "https://down.example/page"
    site({"https://down.example/robots.txt": httpx.ConnectError("refused"), url: httpx.ConnectError("refused")})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "offline" and e.value.fail_code == "network"


@pytest.mark.asyncio
async def test_robots_disallow_is_blocked(site):
    url = "https://strict.example/docs/guide"
    s = site({**robots("https://strict.example", "User-agent: *\nDisallow: /docs/\n"),
              url: (200, fx("blog_flask_tutorial.html"), HTML)})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "blocked" and "robots.txt" in e.value.reason
    assert url not in s.calls  # never fetched


@pytest.mark.asyncio
async def test_robots_names_us(site):
    url = "https://picky.example/a"
    site({**robots("https://picky.example", "User-agent: Miyagi\nDisallow: /\n\nUser-agent: *\nAllow: /\n"),
          url: (200, fx("blog_flask_tutorial.html"), HTML)})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "blocked"


@pytest.mark.parametrize("status", [404, 500])
@pytest.mark.asyncio
async def test_robots_missing_or_broken_allows(site, status):
    url = "https://lax.example/post"
    site({**robots("https://lax.example", "oops", status), url: (200, fx("blog_flask_tutorial.html"), HTML)})
    ex = await fetch.read_link(url)
    assert ex.title.startswith("Build your first Flask app")


@pytest.mark.asyncio
async def test_page_over_the_cap_is_read_up_to_it(site, monkeypatch):
    monkeypatch.setattr(fetch, "MAX_PAGE_BYTES", 40_000)
    url = "https://long.example/huge"
    para = "<p>" + "A sentence about lists, loops, and functions in Python. " * 20 + "</p>\n"
    body = "<html><head><title>Huge</title></head><body><article><h1>Huge</h1>" + para * 200 + "</article></body></html>"
    assert len(body) > 200_000
    site({url: (200, body, HTML)})
    ex = await fetch.read_link(url)
    assert ex.title == "Huge" and 10_000 < len(ex.text()) <= 40_000


# ------------------------------------------------------------------------------------------------ SSRF


@pytest.mark.parametrize("url", ["http://127.0.0.1:8787/health", "http://localhost/x", "http://[::1]/", "file:///etc/passwd",
                                 "ftp://files.example/a", "http://printer.local/", "http://10.0.0.8/admin",
                                 "http://169.254.169.254/latest/meta-data/", "http://2130706433/", "http://intranet/",
                                 "https://user:pw@example.com/", "javascript:alert(1)", "not a url"])
@pytest.mark.asyncio
async def test_private_and_odd_links_are_never_fetched(url):
    with pytest.raises(LinkUnreadable) as e:  # the autouse transport fails any fetch
        await fetch.read_link(url)
    assert e.value.code == "unsupported"
    p = preview.preview_error(url, e.value)
    assert p.kind == "unsupported" and p.error == "unsupported"


@pytest.mark.asyncio
async def test_redirect_to_a_private_address_is_refused(site):
    url = "https://evil.example/go"
    s = site({url: (302, "", {"location": "http://169.254.169.254/latest/meta-data/"})})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "unsupported"
    assert not any("169.254" in c for c in s.calls)


@pytest.mark.asyncio
async def test_too_many_redirects(site):
    pages = {f"https://loop.example/{i}": (302, "", {"location": f"https://loop.example/{i + 1}"}) for i in range(10)}
    site(pages)
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link("https://loop.example/0")
    assert "redirects" in e.value.reason


class _Resolving(httpx.AsyncBaseTransport):
    """Not a MockTransport, so netsafe resolves every host (through the patched getaddrinfo) before the request."""

    def __init__(self, inner: httpx.MockTransport) -> None:
        self.inner = inner

    async def handle_async_request(self, request):
        return await self.inner.handle_async_request(request)


@pytest.mark.asyncio
async def test_a_name_that_resolves_to_the_lan_is_refused(monkeypatch):
    seen: list[str] = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text="<html><body><p>router admin</p></body></html>", headers=HTML)

    def fake_dns(host, port, *a, **k):
        ip = "10.0.0.5" if host == "sneaky.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_dns)
    monkeypatch.setattr(fetch, "TRANSPORT", _Resolving(httpx.MockTransport(handler)))
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link("https://sneaky.example/page")
    assert e.value.code == "unsupported" and seen == []


@pytest.mark.asyncio
async def test_short_link_to_a_repo_reads_the_repo(site):
    short = "https://sho.rt/tiny"
    site({short: (301, "", {"location": REPO}), **_gh_pages()})
    ex = await fetch.read_link(short)
    assert ex.kind == "github" and ex.final_url == REPO and ex.title == "tinyhttp"
    direct = await fetch.read_link(REPO)
    assert ex.cache_key == direct.cache_key  # keyed on where the link ended


@pytest.mark.asyncio
async def test_short_link_to_a_video_is_left_to_the_video_path(site):
    short = "https://sho.rt/vid"
    site({short: (302, "", {"location": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(short)
    assert e.value.code == "unsupported" and e.value.final_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_youtube_links_are_left_to_the_video_path():
    assert fetch.link_kind("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
    assert fetch.link_kind("https://youtu.be/dQw4w9WgXcQ") == "youtube"
    assert fetch.link_kind("https://github.com/pallets/flask") == "github"
    assert fetch.link_kind("https://github.com/pallets/flask/issues/1") == "web"
    assert fetch.link_kind("https://docs.python.org/3/") == "web"
    assert fetch.link_kind("mailto:a@b.c") == "unsupported"


# ------------------------------------------------------------------------------------------------ GitHub


def _gh_pages(**over) -> dict:
    pages = {
        API: (200, fx("github/repo.json"), {"content-type": "application/json"}),
        f"{API}/git/trees/main?recursive=1": (200, fx("github/tree.json"), {"content-type": "application/json"}),
        f"{API}/languages": (200, json.dumps({"Python": 52000, "Shell": 800}), {"content-type": "application/json"}),
        f"{RAW}/README.md": (200, fx("github/README.md"), {"content-type": "text/plain; charset=utf-8"}),
        f"{RAW}/docs/quickstart.md": (200, fx("github/quickstart.md"), {"content-type": "text/plain"}),
        f"{RAW}/docs/advanced.md": (200, "## Retries\n\nPass `retries=3` to retry a failed request.\n", {"content-type": "text/plain"}),
    }
    pages.update(over)
    return pages


@pytest.mark.asyncio
async def test_github_repo_reads_the_readme(site):
    s = site(_gh_pages())
    ex = await fetch.read_link("https://github.com/Acme-Labs/TinyHTTP.git")
    assert ex.kind == "github" and ex.site == "github.com/acme-labs/tinyhttp" and ex.title == "tinyhttp"
    assert ex.author == "acme-labs" and ex.description == "A small, friendly HTTP client for Python"
    gh = ex.github
    assert gh["ref"] == "main" and gh["languages"] == ["Python", "Shell"] and gh["language"] == "Python"
    assert gh["docs"] == ["README.md"]  # the README alone: docs/ is its own link (/tree/main/docs)
    assert "src/tinyhttp/client.py" in gh["files"] and gh["fileCount"] == 10 and gh["filesTruncated"] is False
    text = ex.text()
    # badges, logo, screenshot, HTML comment and link reference definitions: gone
    for junk in ("badge.svg", "shields.io", "logo", "Screenshot", "<!--", "[qs]:", "<p align"):
        assert junk not in text, junk
    assert "See the docs folder and the quick start guide." in text
    heads = [(h.level, h.text, h.anchor) for h in ex.headings]
    assert heads[:3] == [(1, "tinyhttp", "tinyhttp"), (2, "Installation", "installation"), (2, "Quick start", "quick-start")]
    assert ex.page_ref(ex.headings[2]) == {"url": "https://github.com/acme-labs/tinyhttp#quick-start", "heading": "Quick start"}
    assert "Retries" not in text and "docs/advanced.md" not in text
    codes = [(c.lang, c.text) for c in ex.code_blocks]
    assert codes[0] == ("bash", "pip install tinyhttp")
    assert codes[1][0] == "python" and codes[1][1].startswith("import tinyhttp\n\nresp = tinyhttp.get(")
    assert codes[2] == (None, 'tinyhttp.post(url, json={"name": "lamp"})')  # an indented block
    assert "Method | What it does" in text and "`get` | Reads a resource" in text
    assert [b.number for b in ex.blocks if b.kind == "item"][:3] == [1, 2, 3]
    assert not any("robots.txt" in c for c in s.calls)  # the public API and raw files: no robots read
    assert sum(c.startswith("https://api.github.com") for c in s.calls) == 3

    p = preview.preview_from(ex)
    assert p.kind == "github" and p.teachable and p.teach.code and p.teach.steps
    assert p.tools == ["vscode", "terminal"] and p.site == "github.com/acme-labs/tinyhttp" and p.finalUrl is None
    assert LINK_CACHE_KEY_RE.match(ex.cache_key) and ex.cache_key.startswith("g_")


@pytest.mark.asyncio
async def test_github_rate_limited_reads_the_raw_readme(site):
    limited = (403, json.dumps({"message": "API rate limit exceeded"}), {"x-ratelimit-remaining": "0"})
    raw_head = "https://raw.githubusercontent.com/acme-labs/tinyhttp/HEAD/README.md"
    s = site({API: limited, raw_head: (200, fx("github/README.md"), {"content-type": "text/plain"})})
    ex = await fetch.read_link(REPO)
    assert ex.title == "tinyhttp" and ex.code_blocks[0].text == "pip install tinyhttp"
    assert ex.github["files"] == [] and ex.github["docs"] == ["README.md"]
    assert s.calls == [API, raw_head]


@pytest.mark.asyncio
async def test_github_missing_repo(site):
    site({})
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link("https://github.com/acme-labs/nope")
    assert e.value.code == "not_found" and "private" in e.value.reason


@pytest.mark.asyncio
async def test_github_blob_of_a_source_file(site):
    code = "def get(url):\n    return Response(url)\n"
    site(_gh_pages(**{f"{RAW}/src/tinyhttp/client.py": (200, code, {"content-type": "text/plain"})}))
    ex = await fetch.read_link(f"{REPO}/blob/main/src/tinyhttp/client.py")
    assert ex.title == "client.py in tinyhttp"
    assert ex.code_blocks[0].lang == "python" and ex.code_blocks[0].text == code.strip("\n")
    assert ex.final_url == f"{REPO}/blob/main/src/tinyhttp/client.py"


@pytest.mark.asyncio
async def test_github_docs_folder(site):
    site(_gh_pages())
    ex = await fetch.read_link(f"{REPO}/tree/main/docs")
    assert ex.github["docs"] == ["docs/advanced.md", "docs/quickstart.md"] and ex.title == "tinyhttp: docs"
    assert "pip install tinyhttp" not in ex.text() and "Retries" in ex.text()
    retries = next(h for h in ex.headings if h.text == "Retries")
    assert ex.page_ref(retries)["url"] == "https://github.com/acme-labs/tinyhttp/blob/main/docs/advanced.md#retries"


@pytest.mark.asyncio
async def test_github_cache_key_does_not_depend_on_the_rate_limit(site):
    """One repo, one lesson: the API read and the rate-limited raw read give the same text, so the same cache key."""
    site(_gh_pages())
    normal = await fetch.read_link(REPO)
    limited = (403, json.dumps({"message": "API rate limit exceeded"}), {"x-ratelimit-remaining": "0"})
    raw_head = "https://raw.githubusercontent.com/acme-labs/tinyhttp/HEAD/README.md"
    site({**_gh_pages(), API: limited, raw_head: (200, fx("github/README.md"), {"content-type": "text/plain"})})
    fallback = await fetch.read_link(REPO)
    assert normal.github["files"] and not fallback.github["files"]  # really two different reads
    assert normal.text() == fallback.text()
    assert normal.content_hash == fallback.content_hash and normal.cache_key == fallback.cache_key


@pytest.mark.asyncio
async def test_github_rate_limited_after_the_repo_call_keeps_the_key(site):
    """The tree call is the one rate limited (meta read): the README guesses at the default branch, same key."""
    site(_gh_pages())
    normal = await fetch.read_link(REPO)
    limited = (403, json.dumps({"message": "API rate limit exceeded"}), {"x-ratelimit-remaining": "0"})
    site(_gh_pages(**{f"{API}/git/trees/main?recursive=1": limited}))
    fallback = await fetch.read_link(REPO)
    assert fallback.github["files"] == [] and fallback.github["docs"] == ["README.md"]
    assert normal.cache_key == fallback.cache_key


# ------------------------------------------------------------------------------------------------ time cap and loop


class SlowSite(Site):
    """Every answer takes `delay` seconds (an async handler: the event loop stays free while it waits)."""

    def __init__(self, pages: dict, delay: float) -> None:
        super().__init__(pages)
        self.delay = delay

    async def handle(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(self.delay)
        return self(request)


@pytest.mark.asyncio
async def test_a_slow_github_repo_stops_at_the_read_deadline(monkeypatch):
    """Each fetch is under its own timeout, but a repo link makes several: the whole read is capped."""
    monkeypatch.setattr(fetch, "READ_DEADLINE_S", 0.3)
    slow = SlowSite(_gh_pages(), delay=0.12)  # 3 API calls + the README = 0.48 s without the cap
    monkeypatch.setattr(fetch, "TRANSPORT", httpx.MockTransport(slow.handle))
    t0 = time.monotonic()
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(REPO)
    took = time.monotonic() - t0
    assert e.value.code == "offline" and e.value.reason == "github.com/acme-labs/tinyhttp took too long to answer."
    assert e.value.site == "github.com/acme-labs/tinyhttp"
    assert took < 0.45, took
    assert len(slow.calls) < 4  # stopped before the README


@pytest.mark.asyncio
async def test_a_slow_web_page_stops_at_the_read_deadline(monkeypatch):
    monkeypatch.setattr(fetch, "READ_DEADLINE_S", 0.2)
    slow = SlowSite({BLOG: (200, fx("blog_flask_tutorial.html"), HTML)}, delay=0.15)  # robots.txt, then the page
    monkeypatch.setattr(fetch, "TRANSPORT", httpx.MockTransport(slow.handle))
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(BLOG)
    assert e.value.code == "offline" and e.value.reason == "bytegarden.example took too long to answer."


@pytest.mark.asyncio
async def test_html_extraction_runs_off_the_event_loop(site, monkeypatch):
    """A big page's extraction is CPU only: it runs in a worker thread, so the engine's loop keeps answering."""
    url = "https://big.example/guide"
    site({url: (200, "<html><body><main><h1>Guide</h1>" + "<p>Some words to read here.</p>" * 40
                + "</main></body></html>", HTML)})
    loop_thread = threading.get_ident()
    seen: list[int] = []
    real = fetch.extract_html

    def spy(text, *, site):
        seen.append(threading.get_ident())
        return real(text, site=site)

    monkeypatch.setattr(fetch, "extract_html", spy)
    ex = await fetch.read_link(url)
    assert ex.title == "Guide" and seen and seen[0] != loop_thread


@pytest.mark.asyncio
async def test_a_too_deep_page_in_the_worker_thread_is_no_content(site, monkeypatch):
    url = "https://deep.example/page"
    site({url: (200, "<html><body><p>hello</p></body></html>", HTML)})

    def boom(text, *, site):
        raise RecursionError

    monkeypatch.setattr(fetch, "extract_html", boom)
    with pytest.raises(LinkUnreadable) as e:
        await fetch.read_link(url)
    assert e.value.code == "no_content" and "tangled" in e.value.reason


@pytest.mark.parametrize("url, want", [
    ("https://github.com/pallets/flask", ("pallets", "flask", "repo", None, "")),
    ("https://www.github.com/pallets/flask.git", ("pallets", "flask", "repo", None, "")),
    ("https://github.com/pallets/flask/tree/main/docs", ("pallets", "flask", "tree", "main", "docs")),
    ("https://github.com/pallets/flask/blob/3.0.x/docs/quickstart.rst", ("pallets", "flask", "blob", "3.0.x", "docs/quickstart.rst")),
    ("https://github.com/pallets/flask/tree/main", ("pallets", "flask", "repo", "main", "")),
    ("https://github.com/pallets", None),
    ("https://github.com/features/actions", None),
    ("https://github.com/pallets/flask/issues/42", None),
    ("https://github.com/a/b/blob/main/../../etc/passwd", None),
    ("https://gist.github.com/someone/abc", None),
    ("https://github.com.evil.example/pallets/flask", None),
])
def test_parse_repo_url(url, want):
    r = github.parse_repo_url(url)
    assert (None if r is None else (r.owner, r.repo, r.mode, r.ref, r.path)) == want


# ------------------------------------------------------------------------------------------------ text, cache key, cut


def _ex(blocks, url="https://a.example/p") -> Extraction:
    return Extraction(kind="web", url=url, final_url=url, title="T", site="a.example", blocks=blocks)


def test_cache_key_ignores_link_spelling_and_follows_content():
    blocks = [Block("heading", "Intro", level=1), Block("text", "Some words here.")]
    a = _ex(blocks, "https://a.example/p")
    b = _ex(blocks, "http://www.a.example/p/?utm_source=x#top")
    assert a.cache_key == b.cache_key and a.cache_key.startswith("w_")
    c = _ex(blocks + [Block("text", "An edit.")])
    assert c.cache_key != a.cache_key


def test_cut_at_a_section_boundary():
    blocks = []
    for i in range(10):
        blocks += [Block("heading", f"Part {i}", level=2), Block("text", "word " * 200),
                   Block("code", "print(1)\n" * 5, lang="python")]
    ex = _ex(blocks)
    cut = ex.cut(4000)
    assert cut.truncated and not ex.truncated
    assert len(cut.text()) <= 4000 and cut.blocks[-1].kind == "code"  # ends at the end of a section
    assert cut.blocks[0].text == "Part 0"
    assert ex.cut(10**6) is ex


def test_render_fences_code_that_has_fences():
    out = render([Block("code", "```\ninner\n```", lang="markdown")])
    assert out.startswith("````markdown\n") and out.endswith("\n````")


def test_outline_for_the_model():
    ex = _ex([Block("heading", "Install", level=2), Block("code", "pip install x\nmore", lang="bash"),
              Block("heading", "Use", level=2), Block("text", "Call it.\nThen more.")])
    out = ex.outline()
    assert out.splitlines() == ["Title: T", "Site: a.example", "Code blocks: 1", "## Install", "    pip install x",
                                "## Use", "  Call it."]


def test_markdown_details():
    md = ("Title\n=====\n\nSub\n---\n\n- a\n  - b\n- c\n\n1. one\n2) two\n\n~~~js\nlet x = 1;\n~~~\n\n"
          "    1. Install it:\n\n       ```bash\n       pip install x\n       ```\n\n> quoted **text**\n")
    blocks = parse_markdown(md)
    kinds = [(b.kind, b.text, b.level, b.number) for b in blocks]
    assert kinds[0] == ("heading", "Title", 1, 0) and kinds[1] == ("heading", "Sub", 2, 0)
    assert ("item", "b", 1, 0) in kinds and ("item", "two", 0, 2) in kinds
    codes = [(b.lang, b.text) for b in blocks if b.kind == "code"]
    assert ("javascript", "let x = 1;") in codes and ("bash", "pip install x") in codes
    assert blocks[-1].text == "quoted **text**"


def test_rst_readme():
    rst = ("=======\nMyTool\n=======\n\n.. image:: https://img.example/badge.svg\n   :target: https://ci.example\n\n"
           "Install\n-------\n\nRun this::\n\n    pip install mytool\n\n.. code-block:: python\n\n    import mytool\n"
           "    mytool.run()\n\nSee :func:`mytool.run` and `the docs <https://docs.example>`_.\n")
    blocks = parse_rst(rst)
    assert [(b.kind, b.text) for b in blocks if b.kind == "heading"] == [("heading", "MyTool"), ("heading", "Install")]
    assert [(b.lang, b.text) for b in blocks if b.kind == "code"] == [(None, "pip install mytool"),
                                                                       ("python", "import mytool\nmytool.run()")]
    assert any(b.text == "See mytool.run and the docs." for b in blocks)
    assert not any("badge" in b.text for b in blocks)


def test_verdict_tools_and_minutes():
    nb = _ex([Block("code", "%pip install pandas\nimport pandas as pd", lang="python")])
    assert preview.verdict(nb).tools == ["vscode", "jupyter", "terminal"]
    xl = _ex([Block("heading", "Step 1: add a total", level=2), Block("code", "=SUM(A1:A10)"), Block("heading", "Step 2: average", level=2)])
    assert "excel" in preview.verdict(xl).tools
    steps_only = _ex([Block("item", f"Click thing {i}", ordered=True, number=i) for i in range(1, 5)])
    v = preview.verdict(steps_only)
    assert v.steps and not v.code and v.why == "Walks through steps you can follow." and v.tools == []
    long = _ex([Block("text", "word " * 4000)] + [Block("code", "x = 1\n" * 30, lang="python")] * 3)
    assert 20 <= preview.verdict(long).est_minutes <= 180
