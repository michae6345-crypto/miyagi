"""`tut run` sends the engine's per-launch token (server/engine_token.py) on POST /ingest, only to an engine on this
Mac and only while that engine is alive (ROADMAP 5.3). Offline."""

from __future__ import annotations

import json
import os

from tut.sinks import engine_token


def _write(d, port: int, token: str, pid: int) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{port}.json").write_text(json.dumps({"token": token, "pid": pid, "port": port}))


def test_reads_the_live_engines_token_for_its_port(tmp_path, monkeypatch):
    d = tmp_path / "tokens"
    monkeypatch.setenv("MIYAGI_ENGINE_TOKEN_DIR", str(d))
    _write(d, 8787, "tok-8787", os.getpid())
    _write(d, 8791, "tok-8791", os.getpid())
    assert engine_token("http://localhost:8787/ingest") == "tok-8787"
    assert engine_token("http://127.0.0.1:8791/ingest") == "tok-8791"
    assert engine_token("http://[::1]:8787/ingest") == "tok-8787"
    assert engine_token("http://127.0.0.1:9999/ingest") is None  # no engine on that port


def test_never_sent_off_this_mac_or_for_a_dead_engine(tmp_path, monkeypatch):
    d = tmp_path / "tokens"
    monkeypatch.setenv("MIYAGI_ENGINE_TOKEN_DIR", str(d))
    _write(d, 8787, "tok", os.getpid())
    assert engine_token("http://my-mac.local:8787/ingest") is None
    assert engine_token("https://evil.example:8787/ingest") is None
    _write(d, 8787, "stale", 2 ** 22 + 999)  # the engine that wrote it crashed
    assert engine_token("http://localhost:8787/ingest") is None
    (d / "8787.json").write_text("{half")
    assert engine_token("http://localhost:8787/ingest") is None
