"""The miyagi cloud URL is pinned (claude/eng-keys-ssrf): whoever can send config.keys cannot point the install token,
the prompts and the learner's screen at a server of their own. Offline: no client makes a call here."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from server import config

PROD = "https://miyagi-cloud.onrender.com/v1"  # what app/src/main/features/cloud.ts sends (cloudApiRoot(DEFAULT_CLOUD_URL))
TOKEN = "mi_" + "b" * 43
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in (*config.KEY_ENV.values(), config.CLOUD_URL_ENV):
        monkeypatch.delenv(var, raising=False)
    config._warned_hosts.clear()
    config.set_app_keys({})
    yield
    config.set_app_keys({})


def test_the_production_cloud_is_accepted():
    config.set_app_keys({"miyagiCloud": PROD, "miyagiToken": TOKEN})
    assert config.cloud_url() == PROD and config.mode("anthropic") == "cloud"
    assert config.anthropic_kwargs("coach")["base_url"] == PROD + "/anthropic"


def test_an_attacker_host_is_ignored_and_the_url_is_unchanged(caplog):
    config.set_app_keys({"miyagiCloud": PROD, "miyagiToken": TOKEN})
    with caplog.at_level(logging.WARNING, logger="server.config"):
        config.set_app_keys({"miyagiCloud": "https://attacker.example/v1", "miyagiToken": TOKEN})
    assert config.cloud_url() == PROD
    assert config.anthropic_kwargs("coach")["base_url"] == PROD + "/anthropic"
    text = caplog.text
    assert "attacker.example" in text and "https://attacker.example/v1" not in text  # the host only, never the URL
    assert TOKEN not in text


def test_an_attacker_host_on_first_connect_leaves_the_cloud_off():
    config.set_app_keys({"miyagiCloud": "https://attacker.example/v1", "miyagiToken": TOKEN})
    assert config.cloud_url() is None and config.mode("anthropic") == "missing"
    assert config.anthropic_kwargs() == {}


@pytest.mark.parametrize("url", [
    "https://attacker.example/v1",
    "https://miyagi-cloud.onrender.com.attacker.example/v1",
    "https://attacker-miyagi-cloud.onrender.com/v1",
    "https://evil.onrender.com/v1",
    "http://miyagi-cloud.onrender.com/v1",            # plain http to the right host
    "https://miyagi-cloud.onrender.com@attacker.example/v1",
    "https://user:pw@miyagi-cloud.onrender.com/v1",
    "http://127.0.0.1:9000",                          # no MIYAGI_DEV_CLOUD in this process
    "http://localhost:9000/v1",
    "https://127.0.0.1:9000/v1",
    "http://[::1]:9000/v1",
    "https://10.0.0.5/v1",
    "https://attacker.test/v1",                       # no .test wildcard: a LAN resolver + a MITM CA could answer
    "https://miyagi-cloud.onrender.com.test/v1",
    "javascript:alert(1)",
    "file:///etc/passwd",
])
def test_refused_cloud_urls(url):
    assert config._clean_url(url) is None
    config.set_app_keys({"miyagiCloud": url, "miyagiToken": TOKEN})
    assert config.cloud_url() is None


def test_the_env_url_is_pinned_too(monkeypatch):
    monkeypatch.setenv(config.CLOUD_URL_ENV, "https://attacker.example/v1")
    assert config.cloud_url() is None
    monkeypatch.setenv(config.CLOUD_URL_ENV, PROD)
    assert config.cloud_url() == PROD


def test_turning_the_cloud_off_still_works():
    config.set_app_keys({"miyagiCloud": PROD, "miyagiToken": TOKEN})
    config.set_app_keys({"miyagiToken": TOKEN})  # the app sends no miyagiCloud: the cloud is off
    assert config.cloud_url() is None


def test_local_proxy_only_with_dev_cloud(monkeypatch):
    monkeypatch.setattr(config, "DEV_CLOUD", False)
    config.set_app_keys({"miyagiCloud": "http://127.0.0.1:9000", "miyagiToken": TOKEN})
    assert config.cloud_url() is None
    monkeypatch.setattr(config, "DEV_CLOUD", True)
    config.set_app_keys({"miyagiCloud": "http://127.0.0.1:9000", "miyagiToken": TOKEN})
    assert config.cloud_url() == "http://127.0.0.1:9000"
    config.set_app_keys({"miyagiCloud": "http://localhost:9000/v1", "miyagiToken": TOKEN})
    assert config.cloud_url() == "http://localhost:9000/v1"
    config.set_app_keys({"miyagiCloud": "https://attacker.example/v1", "miyagiToken": TOKEN})
    assert config.cloud_url() == "http://localhost:9000/v1"  # dev mode does not open the door to other hosts


def _engine_start(env_extra: dict, url: str | None) -> str:
    """A fresh interpreter = a fresh engine start: MIYAGI_DEV_CLOUD / MIYAGI_CLOUD_HOSTS / MIYAGI_CLOUD_URL are read at
    import. With `url`, the app then sends it as miyagiCloud; with None it sends no keys (the env URL alone)."""
    code = ("import sys; from server import config; "
            "url = sys.argv[1] if len(sys.argv) > 1 else None; "
            "config.set_app_keys({'miyagiCloud': url, 'miyagiToken': 'mi_x'}) if url else None; "
            "print(config.cloud_url())")
    env = config.safe_env({k: v for k, v in os.environ.items()
                           if k not in (config.DEV_CLOUD_ENV, config.CLOUD_HOSTS_ENV, config.CLOUD_URL_ENV)},
                          **env_extra)
    out = subprocess.run([sys.executable, "-c", code, *([url] if url else [])], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=60, check=True)
    return out.stdout.strip()


def test_dev_cloud_is_read_at_engine_start():
    assert _engine_start({}, "http://127.0.0.1:9000") == "None"
    assert _engine_start({"MIYAGI_DEV_CLOUD": "1"}, "http://127.0.0.1:9000") == "http://127.0.0.1:9000"
    assert _engine_start({"MIYAGI_DEV_CLOUD": "1"}, "https://attacker.example/v1") == "None"


def test_extra_hosts_come_from_miyagi_cloud_hosts_at_engine_start():
    staging = "https://miyagi-cloud-next.onrender.com/v1"
    assert _engine_start({}, staging) == "None"
    hosts = "miyagi-cloud-next.onrender.com, other.example.org"
    assert _engine_start({"MIYAGI_CLOUD_HOSTS": hosts}, staging) == staging
    assert _engine_start({"MIYAGI_CLOUD_HOSTS": hosts}, "https://attacker.example/v1") == "None"
    assert _engine_start({"MIYAGI_CLOUD_HOSTS": hosts}, "http://other.example.org/v1") == "None"  # https only


def test_the_start_time_cloud_url_is_trusted():
    """The app's engine spawn (localEngine.ts, {...process.env}) passes a staging or dev MIYAGI_CLOUD_URL to the
    engine at start, and features/cloud.ts sends the same host as miyagiCloud. Both must be accepted."""
    staging = "https://miyagi-cloud-next.onrender.com/v1"
    assert _engine_start({"MIYAGI_CLOUD_URL": staging}, None) == staging          # the env URL alone
    assert _engine_start({"MIYAGI_CLOUD_URL": staging}, staging) == staging       # the app sends the same host
    # the app may hold the bare host (it adds /v1 itself): the bare host at start trusts that host
    assert _engine_start({"MIYAGI_CLOUD_URL": "https://miyagi-cloud-next.onrender.com"}, staging) == staging
    assert _engine_start({"MIYAGI_CLOUD_URL": staging}, "https://attacker.example/v1") == staging  # refused: env URL
    assert _engine_start({"MIYAGI_CLOUD_URL": staging}, "http://miyagi-cloud-next.onrender.com/v1") == staging
    assert _engine_start({"MIYAGI_CLOUD_URL": "off"}, staging) == "None"
    assert _engine_start({"MIYAGI_CLOUD_URL": staging}, PROD) == PROD            # production stays allowed


def test_a_loopback_start_url_allows_the_local_proxy():
    dev = "http://127.0.0.1:8000/v1"
    assert _engine_start({}, dev) == "None"                                       # no dev flag, no start URL
    assert _engine_start({"MIYAGI_CLOUD_URL": dev}, None) == dev
    assert _engine_start({"MIYAGI_CLOUD_URL": dev}, dev) == dev
    assert _engine_start({"MIYAGI_CLOUD_URL": dev}, "https://attacker.example/v1") == dev  # refused: env URL


def test_a_runtime_env_url_widens_nothing(monkeypatch):
    """Only the MIYAGI_CLOUD_URL present at engine start is trusted; one set later (a lazily loaded .env) is not."""
    monkeypatch.setenv(config.CLOUD_URL_ENV, "https://miyagi-cloud-next.onrender.com/v1")
    assert config.cloud_url() is None
    config.set_app_keys({"miyagiCloud": "https://miyagi-cloud-next.onrender.com/v1", "miyagiToken": TOKEN})
    assert config.cloud_url() is None


def test_no_test_tld_wildcard_in_production(monkeypatch):
    monkeypatch.setattr(config, "CLOUD_HOSTS", frozenset({config.DEFAULT_CLOUD_HOST}))  # drop the conftest host
    assert not config.cloud_host_allowed("attacker.test")
    assert not config.cloud_host_allowed("cloud.example.test")
    config.set_app_keys({"miyagiCloud": "https://attacker.test/v1", "miyagiToken": TOKEN})
    assert config.cloud_url() is None


def test_the_app_sends_the_default_host():
    """app/src/main/features/cloud.ts DEFAULT_CLOUD_URL is the pinned default (read only, other branch)."""
    assert config.DEFAULT_CLOUD_HOST == "miyagi-cloud.onrender.com"
    assert config.cloud_host_allowed("MIYAGI-CLOUD.onrender.com.")  # case and a trailing dot do not matter
