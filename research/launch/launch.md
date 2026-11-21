# D. Landing page and launch

Area D of Michael's launch-risk brief (Nov 21, 2026). Adrian's side. Not legal advice.

Status: **early**. The site audit below is done. The research on launches, monitoring and support is still running
and lands in the register as D20 and up.

Checked 2026-11-21:
- Site source `miyagi-site` (public repo adrian-erlikhman/miyagi) at `b3c867b` (Nov 21, 10:49 AM PT).
- The live site in a browser at 1440x900 and at phone size (375x812).
- Michael's draft download page, #188 (`web/download/index.html` on `michael/web-download-page`).
- The app at `origin/michael/v2-integration` and the engine and cloud at `origin/integration/live` where a site claim depends on them.

Cookies and the banner are area B's call (`cookies.md`). What the site loads is listed below for B.

## 1. miyagi.study today

### What a visitor sees

All the words on the page:

> miyagi · watching isn't learning. · miyagi waits until you've done it. · wax on, wax off. · download for mac
> (apple silicon · macos 13 or later) · download for windows (windows 10 and 11) · see it work · see it work. ·
> five step cards ("ask for anything." … "watch it learn.") · contact: two names, two Gmail addresses, two GitHub links.

`<title>` is "miyagi". The meta description is "miyagi pauses the video at every step and waits until you've done it."

- **Desktop:** the 3D bonsai grows in, then scrolling reveals the captions, the wordmark, the two download buttons and
  "see it work". "See it work" is a 1500vh pinned story (13,749 px of scroll at 1440x900) that plays a scripted
  neural-net lesson on a drawn Mac desktop, with a muted YouTube embed of the real tutorial. Then the contact footer.
  There is no download button after the story.
- **Phone (375 px):** the first screen is the 3D bonsai and the word "scroll", nothing else. The hero (wordmark,
  buttons) starts at opacity 0 and fades in on scroll. Phones still run the WebGL tree; only "no WebGL" or reduced
  motion gets the flat page. The story becomes five cards with real frames.
- **Nowhere on the page** does it say that miyagi is an AI app, that it sees your screen, that screenshots and code
  go to Anthropic and Google, that it needs VS Code, that it teaches coding, that it is free, or that it is a beta.

### Claims against what ships

| Claim on the site | Where | What ships (Nov 21) | Verdict |
|---|---|---|---|
| "ask for anything." / pitch "learning anything by doing" | step card 1, `index.html:604` | VS Code is the only editor; lessons are coding tutorials; the story is the curated neural-net lesson (engine DEMO mode, see memory `miyagi-offline-demo`) | **Over-promise.** Say what works today. |
| "download for windows (windows 10 and 11)" as an equal button | `index.html:437-441` | The app's engine is macOS only: `app/src/main/localEngine.ts:206` and `:829` return "not macOS" / `unavailable`. A Windows install can't build or check a lesson. | **Can't keep.** |
| "it sets up what you need, right on your computer" | story note, `index.html:607` | Engine installs packages (`install_all` in the contract); real-machine failure rates are area E's | Keep only if E's first-run test passes on a clean Mac |
| "it checks your work as you type" / "only when it works does the video move on" | `index.html:611` | Grading has had false passes and fails (ROADMAP 1.8, area E) | Soften to "checks each step" until E01/E02 are closed |
| "click the pill and say what you want to learn" | `index.html:604` | Voice is off (`app/src/common/flags.ts:6`); you type | Change "say" to "type" |
| "apple silicon · macos 13 or later" | `index.html:434` | Matches `electron-builder.yml` and #188 | OK |
| The two downloads | `SEALED` links → releases `mac` and `windows` | Both are the pre-v2 app (`1b6ddcb`, posted Nov 20 01:19Z and 01:30Z UTC). The Mac zip is marked `macVerified: false` in `windows-sync/state.json`: nobody has opened it on a real Mac. 7 Mac and 11 Windows downloads so far. | **Swap before launch** |

### AI disclosure

None on the site. The download code, the story and the cards never say "AI", "Claude", "Gemini" or "screen". #188's
FAQ does ("Which AI models does it use?", "What does it read on my screen?"), so merging #188 fixes most of this, once
its claims are checked (D14).

### Footer and contact

- Only "contact": Adrian's and Michael's personal Gmail addresses and GitHub profiles (`index.html:476-489`).
- No privacy policy, terms, cookie notice, security contact, or support address.
- `/privacy`, `/terms`, `/download`, `/.well-known/security.txt`, `/robots.txt` and a custom 404 all return 404.
- `miyagi.study` has **no MX record**, so there is no support@ or hello@ address on the domain yet.

### The download flow

1. Two equal buttons, no OS detection (Adrian's Nov 14 call, README "Download buttons").
2. The first click swaps the buttons for a code field: "enter the code to download · back" (`index.html:536-541`).
   Nothing says what the code is for or how to get one.
3. The right code unseals the GitHub release link (PBKDF2 then AES-GCM, `index.html:520-527`), stores the code in
   localStorage `miyagi-code`, and starts the download. The note under the button then shows the first-open tip.
4. Limits: the code is the headline with the spaces taken out, and the releases are public on GitHub anyway. It keeps
   casual visitors out, nothing more (README says so).
5. **Windows visitors** get a 127 MB unsigned installer (Chrome may hold it; the tip says ctrl+j › keep) for an app
   that can't run a lesson on Windows (above).
6. **Phone visitors** get the same two desktop buttons and the code field. Nothing says "this is a desktop app". With
   the code they would download a 133 MB zip or a 127 MB exe to a phone.

**#188 compared** (Michael's draft `web/download/`, 136 KB, one file):

| | Site today | #188 |
|---|---|---|
| OS detection | none (Adrian chose equal buttons) | Mac / Windows / phone, Intel-Mac warning |
| Phones | desktop buttons + code field | "miyagi runs on your Mac", copy link, share, optional "email me the link" |
| Install help | one-line tip after the click | three illustrated steps per OS, Open Privacy & Security link |
| Code gate | yes | no |
| Release file | `Miyagi-Mac.zip` | defaults to `Miyagi-Mac.dmg`, falls back to the zip via the GitHub API |
| AI and data story | none | FAQ: models, what it reads on screen, cost, uninstall, SHA-256, privacy line |
| Accessibility | focus rings, no skip link | landmarks, skip link, native `<details>`, live regions, reduced motion |
| Claims to check | above | "Turn any tutorial into an auto-graded lab"; "Install in 30 seconds"; "Our server passes them along and doesn't keep them"; "used only to guide your lesson"; "It never uses your camera or microphone" (true only while voice is off) |

### Load weight

Measured from the live site (compressed bytes over the wire):

| File | Bytes | Note |
|---|---|---|
| `index.html` | 51.5 KB (168 KB raw) | GitHub Pages, `Cache-Control: max-age=600` |
| three.js 0.160.0 from jsDelivr | 200.9 KB (1.24 MB raw to parse) | every visit with WebGL, phones too |
| SVGLoader + Lenis (jsDelivr) | 16.5 KB | |
| Google Sans Flex woff2 | 36.1 KB | self-hosted |
| YouTube stills (`i.ytimg.com`) | ~200 KB | preloaded on every desktop visit, even before the story |
| YouTube IFrame API + nocookie player | ~1 MB+ of YouTube's JS | only once the story reaches a video part |

About 300 KB before the page can show its words with 3D on. On a slow 3G link (~50 KB/s) that is 6 to 10 seconds of
a blank paper page, and the fallback only kicks in after a 6 s timeout (`index.html:34-35`). No `integrity` hashes on
the CDN imports (B noted this too).

### Accessibility (quick pass, not a full audit)

- The two lines that say what miyagi does ("watching isn't learning.", "miyagi waits until you've done it.") are
  `aria-hidden` (`index.html:420`). A screen reader hears "miyagi bonsai, miyagi, wax on, wax off."
- The faint notes (system requirements, first-open tips) are `#8f8f88` on `#f6f6f3`: 3.0:1, below the 4.5:1 that
  WCAG AA asks for 13 px text.
- No skip link; on desktop a keyboard user tabs from the downloads straight to "sound off" and the footer, past a
  1500vh story.
- Good: `lang="en"`, focus-visible rings on buttons and links, reduced motion honored, the story has a text label.

### What the site loads or sets (for area B, no verdict here)

- No cookies (`document.cookie` empty before and after the whole story).
- localStorage `miyagi-code`, only after a right code.
- Third parties: `cdn.jsdelivr.net` (three.js, SVGLoader, Lenis) on every visit; `i.ytimg.com` stills on every desktop
  visit; `www.youtube.com/iframe_api` + `www.youtube-nocookie.com/embed/w8yWXqWQYmU`, autoplayed muted once the
  story reaches a video part.
- `/live/` is still public: an old web build of the app (Nov 14, 676 KB) with settings fields for Anthropic, Gemini,
  Bright Data, ElevenLabs and Tiger Data keys, and code that tries to reach the engine on the visitor's own machine
  (localhost). Area A owns the question of what a web page can do to the local engine.

## 2. Register

Severity: P0 = could leak data, run up an unbounded bill, get us sued or block launch. P1 = hurts trust or
conversion at launch. P2 = later.

| id | area | risk | evidence (link) | applies to miyagi? (where) | severity | fix | owner | status |
|---|---|---|---|---|---|---|---|---|
| D01 | Site | The Windows download is offered as an equal button, but the app can't run a lesson on Windows | `app/src/main/localEngine.ts:206,829` at `origin/michael/v2-integration`; memory `miyagi-store` | applies: `index.html:437-441` | P0 | Until a Windows engine ships: drop the button, or label it "windows preview: lessons need a mac for now" and keep it out of launch posts | Adrian (site), Michael (engine) | open |
| D02 | Site | The public downloads are the pre-v2 app, and the Mac zip has never been opened on a real Mac | `windows-sync/state.json` (`publishedSha 1b6ddcb`, `macVerified false`); release assets updated 2026-11-20 | applies: releases `mac`, `windows` on adrian-erlikhman/miyagi | P0 | Post the v2 launch build; open it on a clean Mac (area E Test 1) before the post; versioned tags (C03) | Adrian, Michael | open |
| D03 | Site | The download code gate stops everyone without the code; at launch that is a dead end | `index.html:536-541`; HN/PH rules: see D2x when research lands | applies: both buttons | P0 on launch day | Decide: remove the gate on launch morning, or replace it with a waitlist that says how to get in | Adrian | decision needed |
| D04 | Site | No AI disclosure and no data story: the site never says it's AI, that it sees the screen, or where screenshots go | section 1 above | applies: whole page | P1 | One plain line in the hero plus a "how it works / privacy" block, or merge #188's FAQ | Adrian | open |
| D05 | Site | No privacy policy, terms or support links; Google OAuth verification needs a homepage that links the privacy policy | `/privacy`, `/terms` 404; brief section 3 (Google OAuth) | applies: footer | P0 (blocks Google publishing) | Footer: privacy, terms, support, security; publish B's drafts at `/privacy` and `/terms` | Adrian (site), B (text) | open |
| D06 | Site | The only contacts are two minors' personal Gmail addresses; the domain has no email | `index.html:476-489`; no MX on miyagi.study | applies | P1 | Free forwarding at Porkbun: hello@, support@, security@ → both founders; take the personal addresses off | Adrian | open |
| D07 | Site | Over-promising: "ask for anything", "learn anything", "any tutorial" while lessons are coding in VS Code on Apple-silicon Macs | `index.html:604`; #188 tagline; brief section 2 | applies | P1 | Say exactly what works today; a "beta" label; one honest line on limits | Adrian | open |
| D08 | Site | The first screen doesn't say what miyagi is; on phones it's a tree and "scroll" | section 1 above | applies | P1 | One plain sentence under the wordmark, visible without scrolling | Adrian | open |
| D09 | Site | Phones get desktop buttons and a code field, and could download a 130 MB desktop file | section 1 above | applies | P1 | Phone view: "miyagi is a desktop app" + copy link / email me (as #188 does) | Adrian | open |
| D10 | Site | `/live/` is an old public build with API-key fields (incl. ElevenLabs) that reaches for the local engine | `miyagi-site/live/`; B's `cookies.md` item 4 | applies | P1 | Delete `live/` from the site repo; A checks the engine port | Adrian | open |
| D11 | Site | Heavy first load: ~300 KB and 1.2 MB of JS to parse before the words show; 6 s fallback | load table above | applies: phones and slow links | P2 | Show the words first and load 3D after; self-host three.js with SRI; skip 3D on small screens or low memory | Adrian | open |
| D12 | Site | Accessibility gaps: core lines `aria-hidden`, 3:1 notes, no skip link | accessibility above | applies | P2 | Unhide the captions for readers, darken notes to `#6f6f69` or darker, add a skip link | Adrian | open |
| D13 | Site | No download button after the 15-screen story | section 1 above | applies | P2 | Repeat the download block at the end of the story | Adrian | open |
| D14 | Site | #188's FAQ makes claims nobody has verified (server "doesn't keep" screenshots, "used only to guide your lesson", "install in 30 seconds", "any tutorial") | #188 body "Check before going live" | applies once merged | P1 | Check each against `cloud/app.py` logging, Anthropic and Gemini retention and tier, and a timed install; cut what fails | Michael (cloud facts), Adrian (copy) | open |

## 3. Launch-day runbook (draft)

Pending the research on HN, Product Hunt and X.

## 4. Launch checklist (area D items)

Pending.

## 5. Later

- Change "say what you want to learn" to "type" while voice is off.
- The "scroll" hint overlaps the "see it work" button on phones mid-fade.
- `<title>` is just "miyagi"; add a few words for search and tabs.
- No `robots.txt`, sitemap or custom 404.

## Sources

- Site source: github.com/adrian-erlikhman/miyagi at `b3c867b` (2026-11-21).
- Live site: https://miyagi.study/ (checked 2026-11-21).
- #188: https://github.com/michae6345-crypto/miyagi/pull/188 (updated 2026-11-21).
- App: `origin/michael/v2-integration`; engine and cloud: `origin/integration/live` (michae6345-crypto/miyagi).
