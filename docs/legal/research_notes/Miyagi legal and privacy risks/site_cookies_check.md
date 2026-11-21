# miyagi.study: what the site actually stores and loads

Checked 2026-11-21 from the site source (`miyagi-site` repo at `b3c867b`, "See it work: back to the animated story") and the live site in the built-in browser (desktop width 1440x900 and the pane's own width; motion allowed; WebGL on, so `html.gl gl-ready lenis`). The live page's HTML matches the repo (contains `SEALED`, `lenis@`, `youtube-nocookie`, `youtube.com/iframe_api`).

## First-party storage

| What | Key | When it is set | Evidence |
|---|---|---|---|
| Cookies | none | never; `document.cookie` was empty on load and after scrolling the whole "see it work" story | live check |
| localStorage | `miyagi-code` | only after a visitor types the right download code; it remembers the code so later clicks download straight away; removed if the code stops working | `index.html:510-518`, README "Download buttons" |
| sessionStorage, IndexedDB | none | | live check, source grep |
| localStorage (separate page) | `miyagi.prefs` | only on `miyagi.study/live/`, a built copy of the app's renderer; that path is public but not linked from the home page | `live/assets/index-_Vrjr0cb.js` |

No analytics, no tracking pixels, no ad tags, no `fetch`/beacon calls to any server.

## Third-party requests (each one sends the visitor's IP address, user agent and the page as referrer to that host)

| Host | What | When | Evidence |
|---|---|---|---|
| `cdn.jsdelivr.net` | three.js `three@0.160.0` (module + `SVGLoader`) for the 3D bonsai; `lenis@1.1.13` smooth scrolling | on every page load (modulepreload + import map; Lenis by dynamic import) | `index.html:41-47`, `index.html:1306-1307`, `index.html:1740`; live `performance` entries |
| `i.ytimg.com` (Google/YouTube) | thumbnails of the tutorial in the story (`w8yWXqWQYmU`) | on page load (images in the story desktop) | `index.html:661-665`; live `performance` entries |
| `www.youtube.com` (`/iframe_api`) and `www.youtube-nocookie.com` (player) | the story's muted embed of the real tutorial | only once the story reaches a playing part (`ytSync` → `ytLoad`); not triggered in this test, but the code path is live | `index.html:893-913` |
| `github.com` | download links resolve to GitHub Releases on the public repo after the code check | only on a download click | README "Download buttons"; sealed links in `SEALED` |

Fonts are self-hosted (`/fonts/GoogleSansFlex.woff2`, with `fonts/OFL.txt`), so there is no Google Fonts request. Hosting is GitHub Pages, which logs visitor IPs on its side (see the vendor notes).

## What this means

- No cookie banner is needed for first-party storage: the only key is `miyagi-code`, written after the visitor asks to unlock downloads. It is closest to a user-requested preference. It should still be listed in the cookie notice.
- The third-party loads (jsDelivr, i.ytimg.com, and YouTube once the embed starts) are the real disclosure item. Under EU/UK rules the YouTube player's own storage is the one that could need consent. Cheapest fix: self-host three.js and Lenis, and either self-host the story's thumbnails/stills or start the YouTube embed only after a click.
- The jsDelivr imports have no Subresource Integrity hashes. That is a security gap: a compromised CDN file would run on the page. Self-hosting fixes this too.
- `miyagi.study/live/` is public, unlinked, and writes `miyagi.prefs`. Either remove it or list it.
