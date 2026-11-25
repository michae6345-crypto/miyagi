"""The link-lesson eval set (server/evals/links/cases) must not get worse: every metric stays at or above
baseline.json, and every case that passed there still passes. Offline and free: the fake model, no network.

    python -m pytest server/evals/links -q
    python -m server.evals.links -v                 # the metrics and the failing cases
    python -m server.evals.links --write-baseline   # after link lessons got better (or cases were added)
"""
from __future__ import annotations

import json
import socket

import pytest

from server.evals.links import fake_model, reader, runner

PAID_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY", "TIGER_DATABASE_URL")


def _offline(mp: pytest.MonkeyPatch, state_dir) -> None:
    mp.setenv("MIYAGI_STATE_DIR", str(state_dir))
    for k in PAID_KEYS:  # an accidental live call fails at once, for free
        mp.setenv(k, "")

    def no_network(*_a, **_k):
        raise AssertionError("the link eval must not touch the network")

    mp.setattr(socket.socket, "connect", no_network)

    def no_client(*_a, **_k):
        raise AssertionError("the link eval must not build a model client")

    from server.lesson import claude

    mp.setattr(claude, "client", no_client)


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> tuple[dict, list[runner.Result]]:
    with pytest.MonkeyPatch.context() as mp:
        _offline(mp, tmp_path_factory.mktemp("miyagi-state"))
        return runner.run_all()


def baseline() -> dict:
    return json.loads(runner.BASELINE.read_text(encoding="utf-8"))


def test_the_set_covers_docs_blogs_readmes_and_every_refusal():
    cases = runner.load_cases()
    assert len(cases) >= 15
    pages = {p.name for p in runner.PAGES_DIR.iterdir()}
    assert {c["page"] for c in cases} == pages, "every saved page has a case, and every case a page"
    assert sum(c["page"].endswith(".md") for c in cases) >= 3  # GitHub READMEs
    refusals = [(c.get("expect") or {}).get("refusal") for c in cases]
    assert set(runner.REFUSALS) <= set(refusals)
    assert refusals.count(None) >= 10  # teachable pages
    teach = [c for c in cases if (c.get("expect") or {}).get("refusal") is None]
    assert all("steps" in c["expect"] and "code" in c["expect"] for c in teach)
    text = " ".join(c["url"] for c in cases)
    for site in ("docs.python.org", "developer.mozilla.org", "git-scm.com", "docs.blender.org", "github.com"):
        assert site in text, site


def test_metrics_never_drop_below_the_baseline(run):
    summary, _ = run
    base = baseline()
    assert base["cases"] <= summary["cases"], "a case was removed: rewrite the baseline on purpose"
    worse = [r for r in runner.regressions(summary, base) if not r.startswith("case ")]
    assert not worse, worse


@pytest.mark.parametrize("case_id", baseline()["passed"])
def test_a_case_that_passed_in_the_baseline_still_passes(run, case_id):
    _, results = run
    r = next((x for x in results if x.id == case_id), None)
    assert r is not None, f"{case_id} is in the baseline but has no case file"
    assert r.passed, "\n".join(r.failures())


def test_the_baseline_matches_its_own_metrics():
    base = baseline()
    assert set(base["metrics"]) == set(runner.METRICS)
    assert all(v is None or 0.0 <= v <= 1.0 for v in base["metrics"].values())


def test_the_eval_is_deterministic(run, tmp_path):
    summary, results = run
    with pytest.MonkeyPatch.context() as mp:
        _offline(mp, tmp_path)
        again, results2 = runner.run_all()
    assert {k: summary[k] for k in runner.METRICS} == {k: again[k] for k in runner.METRICS}
    assert [r.failures() for r in results] == [r.failures() for r in results2]


def test_the_same_page_through_another_link_and_other_chrome_has_one_cache_key(run):
    _, results = run
    by_id = {r.id: r for r in results}
    a, b = by_id["python-venv"], by_id["python-venv-mirror"]
    assert a.cache_key == b.cache_key and a.cache_key.startswith("w_")
    gh = by_id["gh-flask-readme"]
    assert gh.cache_key.startswith("g_") and gh.site == "github.com/pallets/flask"


def test_reader_drops_chrome_and_keeps_code_verbatim():
    html = ("<html><head><title>T - Site</title></head><body><nav>Home Docs</nav><div class='cookie-banner'>Accept all"
            " cookies</div><main><h1 id='t'>Title here</h1><p>Some words to read in the body of this page.</p>"
            "<div class='highlight-python'><pre><span class='linenos'>1</span><span class='kn'>import</span> os\n"
            "<span class='nb'>print</span>(os.getcwd())</pre></div><footer>Last updated today</footer></main></body></html>")
    page = reader.read(html, "https://Example.com/a/?utm_source=x#t")
    assert page.title == "Title here" and page.site == "example.com"
    assert [c.text for c in page.code] == ["import os\nprint(os.getcwd())"] and page.code[0].lang == "python"
    assert "cookies" not in page.text and "Home Docs" not in page.text and "Last updated" not in page.text


def test_the_fake_verdict_needs_real_code_or_real_steps():
    md = "# Notes\n\nI like editors. " * 20 + "\n\n```\nvim\n```\n"
    v = fake_model.verdict(reader.read(md, "https://github.com/a/b", fmt="md"))
    assert v["teachable"] is False
    md2 = "# How to\n\n1. Open the app\n2. Click New\n3. Type a name\n4. Press Save\n" + "More words here. " * 10
    v2 = fake_model.verdict(reader.read(md2, "https://github.com/a/b", fmt="md"))
    assert v2["teachable"] is True and v2["teach"] == {"steps": True, "code": False}
