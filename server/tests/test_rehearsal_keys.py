"""The rehearsal / measurement engine never gets a paid key, also after the app's config.keys (blank keys) and the
lazy .env loaders that run later (coach/llm, finder/env, lesson/gemini). Runs in a subprocess: it patches dotenv."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROBE = r"""
import os, sys
sys.path.insert(0, ".")
from server.tests import rehearsal_engine
rehearsal_engine._no_dotenv()
from server.orchestrator import main  # imports config (its own load_dotenv) like the engine
main.apply_keys({"anthropic": "", "gemini": "", "brightdata": "", "elevenlabs": "", "tigerUrl": ""})
from server.coach import llm
from server.finder import env as fenv
from server.lesson import gemini
llm._load_env()
fenv._loaded = False
fenv.load_env()
gemini._load_env()
names = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY", "TIGER_DATABASE_URL")
print(",".join(n for n in names if os.environ.get(n)) or "none")
"""


def test_no_dotenv_keeps_paid_keys_out_after_config_keys(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ORCH_", "TUT_", "MIYAGI_", "LESSON_"))}
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "BRIGHTDATA_API_KEY", "ELEVENLABS_API_KEY",
              "TIGER_DATABASE_URL"):
        env[k] = ""
    env.update(HOME=str(tmp_path), TUT_ENV=str(tmp_path / "empty.env"), REHEARSAL_SIDE_EFFECTS="", ORCH_SCREEN="0",
               MIYAGI_LESSONS_DIR=str(tmp_path / "lessons"), MIYAGI_STATE_DIR=str(tmp_path / "state"))
    (tmp_path / "empty.env").write_text("")
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "none"
