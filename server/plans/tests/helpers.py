from __future__ import annotations

from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def youtube_transport(pages: dict[str, tuple[int, str]], calls: list[str]) -> httpx.MockTransport:
    """Recorded answers by path ("/playlist", "/feeds/videos.xml"): (status, body). Anything else: 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.url.host == "www.youtube.com"
        status, body = pages.get(request.url.path, (404, "not found"))
        if isinstance(body, Exception):
            raise body
        return httpx.Response(status, text=body, request=request)

    return httpx.MockTransport(handler)
