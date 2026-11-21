"""Two non-ML cases (GENERALITY RULE) plus a stand-in for the web layer.

The page text is a short excerpt of the real official pages, so the LLM responses
recorded against it (fixtures/) are realistic. `fake_fetch` replaces `web.fetch`.
"""

from __future__ import annotations

from urllib.parse import quote

# ---------- case 1: React hooks error (JS, eslint via `npm run lint`) --------------------

REACT_STEP = {
    "id": "r3",
    "index": 3,
    "title": "Fetch data with useEffect",
    "instructions": "Load the user list in an effect when the component mounts and store it in state.",
    "checks": [{"id": "r3a", "type": "command_exit_ok", "label": "lint passes", "command": "npm run lint"}],
    "targets": [{"file": "src/UserList.jsx", "match": "useEffect", "caption": "the effect"}],
}
REACT_FAILED = [{"checkId": "r3a", "label": "lint passes", "status": "fail", "detail": "exit code 1"}]
REACT_ERROR = """> eslint src

/app/src/UserList.jsx
  7:5  error  React Hook "useEffect" is called conditionally. React Hooks must be called in the exact same order in every component render  react-hooks/rules-of-hooks

✖ 1 problem (1 error, 0 warnings)"""
REACT_CODE = """import { useEffect, useState } from "react";

export default function UserList({ enabled }) {
  const [users, setUsers] = useState([]);

  if (enabled) {
    useEffect(() => {
      fetch("/api/users").then((r) => r.json()).then(setUsers);
    }, []);
  }

  return <ul>{users.map((u) => <li key={u.id}>{u.name}</li>)}</ul>;
}
"""
REACT_LESSON = {
    "lesson": {"id": "react-users", "title": "React data fetching basics", "goal": "Fetch and render a list", "libraries": {"react": "18.2"}},
    "sources": [{"id": "yt", "kind": "video", "title": "React useEffect tutorial", "url": "https://www.youtube.com/watch?v=REACTDEMO"}],
    "steps": [REACT_STEP],
}

# ---------- case 2: deprecated pandas API (Python) ---------------------------------------

PANDAS_ERROR = """Traceback (most recent call last):
  File "/work/clean.py", line 9, in <module>
    for name, value in counts.iteritems():
AttributeError: 'Series' object has no attribute 'iteritems'"""
PANDAS_CODE = """import pandas as pd

df = pd.read_csv("sales.csv")
counts = df["region"].value_counts()

for name, value in counts.iteritems():
    print(name, value)
"""
PANDAS_LIBS = {"pandas": "1.3"}

# ---------- fake web responses (DuckDuckGo-shaped results pages) -----------------------------------------------------

_SERP = {
    "react": {"organic": [
        {"link": "https://react.dev/reference/rules/rules-of-hooks", "title": "Rules of Hooks – React",
         "description": "Hooks are defined using JavaScript functions, but they represent a special type of reusable UI logic with restrictions on where they can be called."},
        {"link": "https://example-blog.com/react-hooks", "title": "Hooks explained", "description": "spam"},
    ]},
    "react-community": {"organic": [
        {"link": "https://stackoverflow.com/questions/1/placeholder-react-hook-called-conditionally", "title": "React Hook is called conditionally",
         "description": "Move the condition inside the effect: useEffect(() => { if (!enabled) return; ... }, [enabled])."},
    ]},
    "pandas": {"organic": [
        {"link": "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html", "title": "What's new in 2.0.0 (April 3, 2023) — pandas documentation",
         "description": "Removal of prior version deprecations/changes ..."},
    ]},
    "pandas-community": {"organic": [
        {"link": "https://stackoverflow.com/questions/2/placeholder-series-has-no-attribute-iteritems", "title": "AttributeError: 'DataFrame' object has no attribute 'iteritems'",
         "description": "iteritems was removed in pandas 2.0; use items() instead."},
    ]},
}
_PAGES = {
    "https://react.dev/reference/rules/rules-of-hooks": """<html><body><main><h1>Rules of Hooks</h1>
<p>Hooks are defined using JavaScript functions, but they represent a special type of reusable UI logic with restrictions on where they can be called.</p>
<h2>Only call Hooks at the top level</h2>
<p>Functions whose names start with use are called Hooks in React.</p>
<p>Don't call Hooks inside loops, conditions, nested functions, or try/catch/finally blocks. Instead, always use Hooks at the top level of your React function, before any early returns.</p>
<pre>function Bad({ cond }) { if (cond) { // 🔴 Bad: inside a condition (to fix, move it outside!)
    const theme = useContext(ThemeContext); } }</pre>
</main></body></html>""",
    "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html": """<html><body><h1>What's new in 2.0.0 (April 3, 2023)</h1>
<h2>Removal of prior version deprecations/changes</h2>
<ul><li>Removed deprecated Series.iteritems(), DataFrame.iteritems(), use obj.items instead (GH45321)</li>
<li>Removed deprecated DataFrame.append() and Series.append(), use concat() instead</li></ul></body></html>""",
}


def _ddg_html(serp: dict) -> str:
    """The shape of html.duckduckgo.com/html/: result links wrapped as //duckduckgo.com/l/?uddg=<url>."""
    rows = "".join(
        f'<div class="result results_links results_links_deep web-result">'
        f'<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg={quote(o["link"], safe="")}&amp;rut=x">{o["title"]}</a>'
        f'<a class="result__snippet" href="//duckduckgo.com/l/?uddg={quote(o["link"], safe="")}">{o["description"]}</a></div>'
        for o in serp["organic"]
    )
    return f"<html><body>{rows}</body></html>"


def fake_fetch_log() -> list[tuple[str, str]]:
    return _LOG


_LOG: list[tuple[str, str]] = []


async def fake_fetch(kind: str, url: str) -> str | None:
    _LOG.append((kind, url))
    if kind == "unlock":
        return _PAGES.get(url)
    community = "site%3Astackoverflow.com" in url
    if "react" in url.lower():
        return _ddg_html(_SERP["react-community" if community else "react"])
    if "pandas" in url.lower() or "iteritems" in url.lower():
        return _ddg_html(_SERP["pandas-community" if community else "pandas"])
    return _ddg_html({"organic": []})
