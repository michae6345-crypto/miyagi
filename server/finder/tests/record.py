"""Re-record the real responses the tests replay: python -m server.finder.tests.record"""

import json
import re
from pathlib import Path

import httpx

from server.finder import youtube
from server.finder.sources import BROWSER_HEADERS

Q = "train a PINN on the convection equation"
OUT = Path(__file__).parent / "fixtures"
KEEP = {"videoId", "title", "lengthText", "viewCountText", "shortViewCountText", "publishedTimeText", "ownerText",
        "detailedMetadataSnippets", "thumbnail", "badges", "expandableMetadata"}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with httpx.Client(headers=BROWSER_HEADERS, follow_redirects=True, cookies={"CONSENT": "YES+1"}, timeout=15) as c:
        page = c.get("https://www.youtube.com/results", params={"search_query": Q, "hl": "en"}).text
        data = youtube.initial_data(page)
        vids = [{"videoRenderer": {k: v for k, v in r.items() if k in KEEP}} for r in youtube._walk(data, "videoRenderer")][:12]
        (OUT / "youtube_results.json").write_text(json.dumps({"contents": vids}, indent=1, ensure_ascii=False))
        oe = {}
        for v in vids[:12]:
            r = c.get("https://www.youtube.com/oembed", params={"url": youtube.watch_url(v["videoRenderer"]["videoId"]), "format": "json"})
            oe[v["videoRenderer"]["videoId"]] = json.loads(r.content) if r.status_code == 200 else None
        (OUT / "oembed.json").write_text(json.dumps(oe, indent=1, ensure_ascii=False))
        ddg = c.post("https://html.duckduckgo.com/html/", data={"q": "pinn convection equation tutorial code", "kl": "us-en"}).text
        body = ddg[ddg.find('<div class="serp__results">'):]
        body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        (OUT / "ddg.html").write_text(body[:60000])
        gh = c.get("https://api.github.com/search/repositories", params={"q": "pinn convection equation", "per_page": 6}).json()
        (OUT / "github.json").write_text(json.dumps(gh, indent=1))
        ax = c.get("https://export.arxiv.org/api/query", params={"search_query": "all:pinn AND all:convection", "max_results": 5, "sortBy": "relevance"}).text
        (OUT / "arxiv.xml").write_text(ax)
    print("recorded to", OUT)


if __name__ == "__main__":
    main()
