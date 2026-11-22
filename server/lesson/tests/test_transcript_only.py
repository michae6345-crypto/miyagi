"""Build failed card's "Try transcript only" (learn_url {transcriptOnly: true}): offline, every model faked."""

import asyncio

import pytest

from server.lesson import builder, claude, gemini, transcript
from server.lesson.schema import schema_errors

from .test_builder import URL, WORKDIR, _claude_fakes, fake  # noqa: F401  (fake: the shared offline fixture)


def _gemini_must_not_run(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("transcript-only must never call the video model")

    for name in ("watch_video", "step_detail", "adapt_checks"):
        monkeypatch.setattr(gemini, name, boom)


def test_transcript_only_never_calls_gemini_and_skips_the_cache(fake, monkeypatch, tmp_path):
    monkeypatch.setenv("LESSON_ENGINE", "auto")  # the default: Gemini would normally race the transcript draft
    _gemini_must_not_run(monkeypatch)
    calls, stages = [], []
    _claude_fakes(monkeypatch, calls)
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True, detail=True, transcript_only=True,
                                         on_progress=lambda s, m="": stages.append(s)))
    assert calls == ["transcript", "claude-watch", "claude-adapt"]
    assert g["lesson"]["builtBy"] == "claude" and g["lesson"]["transcriptOnly"] is True
    assert g["build"]["model"]["video"].startswith("claude-opus-5-5 (transcript via")
    assert schema_errors(g) == []
    assert stages[0] == "transcript_only" and "watching" not in stages
    assert not list(tmp_path.glob("*.json")) and not (tmp_path / "raw").exists()  # nothing cached: its looser checks stay out


def test_transcript_only_ignores_a_cached_gemini_lesson_and_long_video_parts(fake, monkeypatch):
    asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR))  # a normal Gemini build fills the caches
    assert fake["watch"] == 1

    async def long_meta(vid):
        return {"video_id": vid, "title": "Long", "description": "", "length_s": 3 * 3600, "chapters": []}

    monkeypatch.setattr(transcript, "fetch_metadata", long_meta)  # > the long-video threshold: Gemini parts normally
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    _gemini_must_not_run(monkeypatch)
    calls = []
    _claude_fakes(monkeypatch, calls)
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, transcript_only=True))
    assert calls == ["transcript", "claude-watch", "claude-adapt"] and g["lesson"]["transcriptOnly"] is True


def test_transcript_only_without_a_transcript_fails_instead_of_watching(fake, monkeypatch):
    monkeypatch.setenv("LESSON_ENGINE", "auto")
    _gemini_must_not_run(monkeypatch)

    async def no_transcript(vid):
        raise RuntimeError("no transcript for AXXnSzmpyoI")

    monkeypatch.setattr(transcript, "fetch_video_info", no_transcript)
    with pytest.raises(RuntimeError, match="no transcript"):
        asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, refresh=True, transcript_only=True))


def test_normal_build_is_unchanged(fake, monkeypatch, tmp_path):
    stages = []
    g = asyncio.run(builder.build_lesson(URL, "train a PINN", WORKDIR, detail=True,
                                         on_progress=lambda s, m="": stages.append(s)))
    assert fake["watch"] == 1 and fake["detail"] == 3
    assert "transcriptOnly" not in g["lesson"] and "transcript_only" not in stages
    assert list(tmp_path.glob("*.json")) and (tmp_path / "raw").exists()  # normal builds still cache
    assert g["lesson"]["builtBy"] == "gemini"
