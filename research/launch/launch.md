# D. Landing page and launch

Area D of Michael's launch-risk brief (Nov 21, 2026). Adrian's side. Not legal advice.

Checked 2026-11-21:
- Site source `miyagi-site` (public repo adrian-erlikhman/miyagi) at `b3c867b` (Nov 21, 10:49 AM PT).
- The live site in a browser at 1440x900 and at phone size (375x812).
- Michael's draft download page, #188 (`web/download/index.html` on `michael/web-download-page`).
- The app at `origin/michael/v2-integration`, the engine and cloud at `origin/integration/live`, and the newest cloud
  branch `origin/claude/eng-proxy` (Nov 21, 12:04 PM), where a site or launch claim depends on them.
- Research: seven parallel researchers (launch postmortems, launch playbook, site rules, crash reporting, usage and
  spend and uptime, support, a map of the code), then two fact-checkers on the P0 and P1 claims. HN's Show HN page,
  `/showlim` and guidelines were re-read directly. Only `GET /healthz` on miyagi-cloud was called; no paid API calls.
- Fact-check: of 90 P0/P1 claims, 46 were confirmed outright and 43 were partly right (a date, a number or an
  attribution off); those are corrected below. One could not be checked (a Render staff forum quote). Claims still
  unverified say so where they appear.

Other areas own: cookies and the banner (B, `cookies.md`), legal text and minors (B), signing, updates and Render (C),
key and proxy security (A), grading and first run (E). Rows here point to their row ids (A01, B04, ...) instead of
repeating them.

Security details that could be exploited are not in this public file. They went to the shared notes folder for the
coordinating session to send Michael privately. The register says "see A (held privately)".

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
- **Nowhere on the page** does it say that miyagi is an AI app, that it looks at your screen, that screenshots and code
  go to Anthropic (and video links to Google), that it needs VS Code, that it teaches coding, that it is free, or that
  it is a beta. One story callout says the opposite: "miyagi runs on your computer." (`index.html:605`).

### Claims against what ships

| Claim on the site | Where | What ships (Nov 21) | Verdict |
|---|---|---|---|
| "miyagi runs on your computer." | story note, `index.html:605` | During a lesson the engine looks at the screen about every 5 s (`server/orchestrator/scene_watch.py:2,77-78`) and sends screenshots and code to Anthropic through miyagi-cloud | **Misleading by omission.** Reword and add the data line. |
| "ask for anything." / pitch "learning anything by doing" | step card 1, `index.html:604` | VS Code is the only editor; lessons are coding tutorials; the story is the curated neural-net lesson | **Over-promise.** Say what works today. |
| "download for windows (windows 10 and 11)" as an equal button | `index.html:437-441` | The engine is macOS only: `app/src/main/localEngine.ts:206` and `:829` return "not macOS" / `unavailable`. A Windows install can't build or check a lesson. | **Can't keep.** |
| "it sets up what you need, right on your computer" | story note, `index.html:607` | Engine installs packages; real-machine failure rates are area E's | Keep only if E's clean-Mac first run passes |
| "it checks your work as you type" / "only when it works does the video move on" | `index.html:611` | Grading has had false passes and fails (ROADMAP 1.8, area E) | Soften to "checks each step" and add "can be wrong" |
| "click the pill and say what you want to learn" | `index.html:604` | Voice is off (`app/src/common/flags.ts:6`); you type | Change "say" to "type" |
| "apple silicon · macos 13 or later" | `index.html:434` | Matches `electron-builder.yml` and #188 | OK |
| The two downloads | `SEALED` links → releases `mac`, `windows` | Both are the pre-v2 app (`1b6ddcb`, assets updated Nov 20 01:19Z and 01:30Z). `windows-sync/state.json` has `macVerified: false`: nobody has opened the public Mac zip on a real Mac. 7 Mac and 11 Windows downloads so far. | **Swap before launch** |

### AI disclosure

None on the site. In the app, Settings > Privacy says screenshots and code are "Sent to the AI provider"
(`Privacy.tsx:65-66`) without naming Anthropic or Google, and nothing says lessons are AI-generated or can be wrong
(code map, Nov 21). #188's FAQ does name the models and says what it reads on screen, so merging #188 fixes most of the
site side once its claims are checked (D14).

What the code actually sends (corrects the brief): screen and code go to Claude only (`server/screen/describe.py`); through
the cloud, Gemini gets YouTube links only (`server/config.py:243-245`). The cloud doesn't enforce that split. Some
redaction exists: regex scrubbing of emails, SSNs, phone and card numbers in OCR text, and blacking out
password-manager and Messages windows (`server/screen/privacy.py`), but not browsers, mail or Slack.

### Footer and contact

- Only "contact": Adrian's and Michael's personal Gmail addresses and GitHub profiles (`index.html:476-489`).
- No privacy policy, terms, cookie notice, security contact, or support address.
- `/privacy`, `/terms`, `/download`, `/.well-known/security.txt`, `/robots.txt` and a custom 404 all return 404. The
  app links to `miyagi.study/terms`, `/privacy`, `/pricing`, `/teams` and `/account` (`app/src/main/features/account.ts:22-27`)
  and its sign-in copy says you accept the Terms and Privacy Policy (`auth/Login.tsx:260`). All five 404.
- `miyagi.study` has **no MX record**, so there is no support@ or hello@ address on the domain yet.
- Both public repos (michae6345-crypto/miyagi and adrian-erlikhman/miyagi) have private vulnerability reporting
  **off** and no `SECURITY.md`.

### The download flow

1. Two equal buttons, no OS detection (Adrian's Nov 14 call, README "Download buttons").
2. The first click swaps the buttons for a code field: "enter the code to download · back" (`index.html:536-541`).
   Nothing says what the code is for or how to get one.
3. The right code unseals the GitHub release link (PBKDF2 then AES-GCM, `index.html:520-527`), stores the code in
   localStorage `miyagi-code`, and starts the download. The note under the button then shows the first-open tip.
4. Limits: the code is easy to guess from the page, and the releases are public on GitHub anyway (the app's update
   check reads them from the GitHub API). It keeps casual visitors out, nothing more. The README says so.
5. **Windows visitors** get a 127 MB unsigned installer (Chrome may hold it; the tip says ctrl+j › keep) for an app
   that can't run a lesson on Windows.
6. **Phone visitors** get the same two desktop buttons and the code field. Nothing says "this is a desktop app". With
   the code they would download a 133 MB zip or a 127 MB exe to a phone.

**#188 compared** (Michael's draft `web/download/`, 136 KB, one file):

| | Site today | #188 |
|---|---|---|
| OS detection | none (Adrian chose equal buttons on Nov 14) | Mac / Windows / phone, Intel-Mac warning |
| Phones | desktop buttons + code field | "miyagi runs on your Mac", copy link, share, optional "email me the link" |
| Install help | one-line tip after the click | three illustrated steps per OS, Open Privacy & Security link |
| Code gate | yes | no |
| Release file | `Miyagi-Mac.zip` | defaults to `Miyagi-Mac.dmg`, falls back to the zip via the GitHub API |
| AI and data story | none | FAQ: models, what it reads on screen, cost, uninstall, SHA-256, privacy line |
| Accessibility | focus rings, no skip link | landmarks, skip link, native `<details>`, live regions, reduced motion |
| Claims to check | above | "Turn any tutorial into an auto-graded lab"; "Install in 30 seconds"; "Our server passes them along and doesn't keep them"; "used only to guide your lesson"; "It never uses your camera or microphone" (true only while voice is off); the Windows steps, which promise an app that then can't run a lesson |

The cloud half of "our server doesn't keep them" checks out in code: one log line per request with method, path,
status, latency, model, token counts and a hash prefix; no bodies, screenshots, tokens or IPs (`cloud/app.py:161-162`).
"Used only to guide your lesson" also depends on Anthropic's and Google's retention and on the Gemini key being on
Google's paid tier (D20).

### Load weight

Measured from the live site (compressed bytes over the wire):

| File | Bytes | Note |
|---|---|---|
| `index.html` | 51.5 KB (168 KB raw) | GitHub Pages, `Cache-Control: max-age=600` |
| three.js 0.160.0 from jsDelivr | 200.9 KB (1.24 MB raw to parse) | every visit with WebGL, phones too |
| SVGLoader + Lenis (jsDelivr) | 16.5 KB | |
| Google Sans Flex woff2 | 36.1 KB | self-hosted |
| YouTube stills (`i.ytimg.com`) | ~200 KB | preloaded on every desktop visit, even before the story |
| YouTube IFrame API + nocookie player | YouTube's player JS | only once the story reaches a video part |

About 300 KB before the page can show its words with 3D on. On a slow 3G link (~50 KB/s) that is 6 to 10 seconds of
a blank paper page, and the fallback only kicks in after a 6 s timeout (`index.html:35`). No `integrity` hashes on
the CDN imports (B noted this too). Traffic itself is not a risk: at under 1 MB a visit, GitHub Pages' 100 GB soft
limit is over 100k visits, and GitHub Releases has no bandwidth cap (D37).

### Accessibility (quick pass, not a full audit)

- The two lines that say what miyagi does ("watching isn't learning.", "miyagi waits until you've done it.") are
  `aria-hidden` (`index.html:420`). A screen reader hears "miyagi bonsai, miyagi, wax on, wax off."
- The faint notes (system requirements, first-open tips, the "scroll" hint, step numbers) are `#8f8f88` on `#f6f6f3`:
  3.0:1, below the 4.5:1 WCAG AA asks for at 13 px. `--m-ink-muted` (`#66665f`, 5.3:1) passes.
- No skip link; on desktop a keyboard user tabs from the downloads straight to "sound off" and the footer, past a
  1500vh story.
- Good: `lang="en"`, focus-visible rings on buttons and links, reduced motion honored, the story has a text label.
- Lawsuit risk is low for a free, online-only, no-revenue project (ADA Title III suits target e-commerce; the
  European Accessibility Act doesn't cover a free educational app or a microenterprise). Fix the basics anyway.

### What the site loads or sets (for area B, no verdict here)

- No cookies (`document.cookie` empty before and after the whole story).
- localStorage `miyagi-code`, only after a right code.
- Third parties: `cdn.jsdelivr.net` (three.js, SVGLoader, Lenis) on every visit; `i.ytimg.com` stills on every desktop
  visit; `www.youtube.com/iframe_api` + `www.youtube-nocookie.com/embed/w8yWXqWQYmU`, autoplayed muted once the
  story reaches a video part. GitHub Pages logs visitor IPs.
- The story draws a cursor and callouts over the scaled desktop that holds the YouTube player; YouTube's API rules
  ban overlays on the player (https://developers.google.com/youtube/terms/required-minimum-functionality). B's
  click-to-load fix (or stills only) solves both.
- `/live/` is still public: an old web build of the app (Nov 14, 676 KB) with settings fields for Anthropic, Gemini,
  Bright Data, ElevenLabs and Tiger Data keys, and code that reaches for the engine on the visitor's own machine
  (localhost). See A.

## 2. What happened to others

Each line: what happened, the source, and what it means for miyagi. Fact-checker notes are folded in.

| Case | What happened | Source (date) | For miyagi |
|---|---|---|---|
| Clicky (AI teacher next to your cursor, closest to us) | Launch tweet Apr 7, 2026 (3.0M views); open-sourced Apr 8. Within 48 h outsiders filed: a committed Anthropic key (#22, removed ~39 h later, still in history), an open public proxy for paid APIs (#34), transcripts in PostHog (#34), logs with transcripts and token pieces (#44). The three security issues have no maintainer reply seven months on. First-48-hour user bugs were all first-run friction: hotkey not discoverable, mic not starting, blank settings, no second-monitor support, couldn't stop it talking, slow (#1, #2, #12, #24, #35, #36). Day-1 Chrome flagged the unsigned download (#4). It went closed-source and freemium within three weeks. The "fixing a lot of tiny bugs" quote could not be found (X isn't searchable). | https://github.com/farzaa/clicky/issues/34 (2026-04-08), /issues/22, /issues/44, /issues/4 | Same architecture (key proxy, screen-seeing). The open-proxy lesson is A's. The launch lesson is D's: the first 48 hours are first-run friction plus security reports in public, and silence reads as abandonment. |
| Cluely (screen-seeing Electron overlay) | "Cheat on everything" launch video and $5.3M seed drew ethics backlash (Apr 2025); tagline softened by July. A researcher published its system prompts from the desktop bundle (Jun 2025) and said Cluely filed a DMCA against him (Jul 2025; his X post, not independently verified). Hacktron showed a prompt-injected link could open an attacker page inside the app that silently screenshotted the screen (found Jul 2025, published Feb 14, 2026); patched silently, no credit. The CEO retracted a $7M ARR claim made in a July 2025 interview (Mar 5, 2026). The "83k-user breach" traces only to an anonymous Medium post and competitor blogs: **unverified, likely false**. | https://techcrunch.com/2026/03/05/cluely-ceo-roy-lee-admits-to-publicly-lying-about-revenue-numbers-last-year/ (2026-03-05); https://www.hacktron.ai/blog/hacking-cluely (2026-02-14) | Positioning: a screen-seeing tutor can be read as a cheating tool. Say it teaches and checks your work, never does it. Post only numbers you can show. Never answer a researcher with legal threats. |
| Rabbit R1 | "Large Action Model" pitch at CES (Jan 2024); reviewers found an Android app (Apr 30) and called it "barely reviewable". Rabbitude published hardcoded provider keys (Jun 25, 2024). Rabbit's own page confirms ElevenLabs and SendGrid keys, rotation a day later with "brief downtime", and on Jul 5 blamed a since-fired employee for leaking code. | https://rabbit.tech/security-investigation-062524 (2024-06-25); https://www.androidauthority.com/rabbit-r1-is-an-android-app-3438805/ (2024-04-30) | Reviewers test the claim, not the roadmap. "Learn anything" will be tested on someone's own tutorial on day one. |
| Humane AI Pin | Launch video widely reported to contain wrong answers (Nov 2023); harsh reviews (Apr 2024); returns exceeded sales May-Aug 2024 (~$9M lifetime sales against a 100k-unit goal); HP bought the assets and every pin stopped working Feb 28, 2025. | https://www.macrumors.com/2024/08/07/humane-ai-pin-returns (2024-08-07); https://techcrunch.com/2025/02/18/humanes-ai-pin-is-dead-as-hp-buys-startups-assets-for-116m/ (2025-02-18) | A visible wrong answer in the demo becomes the story. Every install depends on miyagi-cloud: if the kill switch trips, the app must say so plainly. |
| Devin | "First AI software engineer" demo (Mar 2024) didn't survive outside testing; Answer.AI's month of use: 3 successes, 14 failures, 3 inconclusive out of 20 tasks (Jan 2025). | https://www.answer.ai/posts/2025-01-08-devin (2025-01-08) | Use a one-take, unedited demo on a tutorial you didn't pick for it, including a failed check. |
| Microsoft Recall | Screenshot timeline announced May 2024; HN "privacy nightmare"; researchers read the database; made opt-in Jun 7, pulled from launch Jun 13; relaunched in preview only in 2025 after several delays; press tests reported the sensitive-data filter still missed card numbers (Tom's Hardware, Dec 2024, date not re-verified). | https://blogs.windows.com/windowsexperience/2024/06/07/update-on-the-recall-preview-feature-for-copilot-pcs/ (2024-06-07) | The top HN comment on a screen-seeing tool will be about what's captured and where it goes. Answer it in the first comment, with facts. |
| Screenpipe (Show HN) | Thread dominated by "how is the data stored and protected" and other people's data on calls; separately, starring the repo added people to a marketing list. | https://news.ycombinator.com/item?id=41695840 (2024-09-30) | Same questions will come. Outreach only to people with a reason to hear from us. |
| Surprise bills | A 3-person startup billed $82,314 over Feb 11-12, 2026 after its Gemini key was abused (usual spend ~$180/month; the developer says Google told them to pay, Google declined to comment). Sysdig "LLMjacking": stolen LLM access resold, worst case $46,080/day (2024-05-06). Cara's $98,280 Vercel bill after 56M function calls in a day of going viral (InfoQ, 2024-06-14). Midjourney ended free trials over throwaway-account abuse (Mar 2023). | https://www.theregister.com/2026/03/03/gemini_api_key_82314_dollar_charge/ (2026-03-03); https://www.infoq.com/news/2024/06/vercel-serverless-scale-expenses (2024-06-14) | A good launch day is miyagi's most expensive day, and free anonymous access gets farmed. See D18-D19. |

## 3. Monitoring we need before launch

What exists today (code map, Nov 21): no crash upload, no analytics, no alerting. The app records crashes and child
process deaths into a local `errors.json` (`app/src/main/features/errors.ts`), has no `unhandledRejection` handler,
and drops renderer errors in packaged builds. The engine log (`~/miyagi/engine/logs/engine.log`) grows without limit
and holds learner goals, questions and full folder paths. The cloud keeps per-day counts per token and model and a
read-only admin page (`/admin`), and `/healthz` returns `{"ok":true,"version":"0.1.0","proxy_enabled":true}`
(200 in 0.25 s on Nov 21). `render.yaml` says plan `starter` with a 1 GB disk; the live plan is unconfirmed.

### Crash reporting (privacy-safe)

**The trap:** the default setup of today's Sentry SDKs would leak exactly what miyagi promises not to send.
- `@sentry/electron` 8.x (on JS SDK 11) deprecates `sendDefaultPii`; from v8 the `dataCollection` defaults apply, and
  any key you don't set defaults to collect: IP, headers, query strings, HTTP bodies, gen-AI inputs and outputs, console breadcrumbs, stack variables
  (https://docs.sentry.io/platforms/javascript/guides/electron/configuration/options/, read 2026-11-21; the
  researcher checked the 11.10 source). Native minidumps (raw process memory) are on by default
  (https://docs.sentry.io/platforms/native/guides/minidumps/). The quick-start snippet turns on Session Replay and
  the feedback widget (https://docs.sentry.io/platforms/javascript/guides/electron/). `attachScreenshot` captures
  every window on any error event, and server-side scrubbing can't be relied on for image attachments (the advanced
  scrubbing docs only have a `$minidump` selector).
- Python `sentry-sdk` 2.x sends stack-frame local variables with no length cap (a base64 screenshot or a prompt in a
  local goes out whole), attaches FastAPI request bodies up to 10 KB, turns every `log.error`/`log.exception` (~150
  in `server/`) into an event, and sends the hostname. A partial `data_collection` dict, or the 3.0 upgrade (rc1 out
  2026-11-19), switches the auto-enabled Anthropic and Gemini integrations to record prompts and responses
  (https://docs.sentry.io/platforms/python/integrations/anthropic/).
- Sentry's server-side scrubbing runs only after the data has left the Mac.

**Recommendation:** Sentry Developer plan ($0; 5k errors a month, 1 user, overage dropped, not billed;
https://sentry.io/pricing/), **opt-in**, with an allowlist config. Fallback with no third party: a fixed-schema
`POST /v1/crash` on miyagi-cloud (version, os, process, reason, exit code, error type, a 200-character scrubbed
message, stack as `basename:line:function`), authenticated by the install token. Bugsink or GlitchTip accept the same
SDK config with a different DSN.

Config rules (the full snippets are in the crash-reporting research notes; hand them to whoever adds it):
- **Electron main:** pin `@sentry/electron` 8.4.x; a complete `dataCollection` object with every key off;
  `attachScreenshot: false`; `includeLocalVariables: false`; filter out the `SentryMinidump`, `ElectronMinidump`,
  `Screenshots`, `Console`, `ElectronNet`, `NodeFetch`, `Http`, `ContextLines`, `LocalVariables` and `Modules`
  integrations; `beforeBreadcrumb` keeps only `electron` lifecycle crumbs with no data; `beforeSend` returns null
  without consent, sets `hint.attachments = []`, and rebuilds the event from allowed fields with paths, JWTs,
  `sk-ant-`, `AIza…`, Bearer values and URL queries scrubbed; no tracing.
- **Electron renderer:** no `replayIntegration`, `feedbackIntegration` or `browserTracingIntegration` (a CI grep
  fails the build if they appear); drop `Breadcrumbs` and `HttpContext`.
- **Python engine:** pin `sentry-sdk>=2.75,<3`; init only when the app passes `MIYAGI_CRASH_REPORTS=1`;
  `send_default_pii=False`, `include_local_variables=False`, `include_source_context=False`,
  `max_request_body_size='never'`, `max_value_length=1024`, `server_name='engine'`, `default_integrations=False`,
  `auto_enabling_integrations=False` with a short explicit list; `before_send` rebuilds from allowed keys and keeps
  only the log message template, not its arguments. Never pass a partial `data_collection`.
- **VS Code extension:** no Sentry SDK (Sentry says not to `init` in extension hosts; VS Code requires honoring
  `isTelemetryEnabled`). Forward caught errors to the app over the existing channel.
- **Sentry org, once:** pick US or EU region at creation (permanent); Prevent Storing of IP Addresses on; minidumps
  as attachments off; advanced scrubbing rules removing `$frame.vars`, `$http` and `$breadcrumb.data`; spike
  protection on; Legal & Compliance › Service Data Usage all off.
- **DSN:** hand it out in the `/v1/install` response so it can be rotated without an app update.
- **Consent:** an unchecked first-run toggle "Send crash reports (never your screen, code or words)"; after a crash,
  a one-time "send a report?" prompt; a Settings toggle with "Show last report". EU ePrivacy Art. 5(3) as the EDPB
  reads it covers SDK reporting (https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf,
  2024-10-07). VS Code and Zed are opt-out, but they don't see the screen.
- **Before launch:** a canary test. Put a unique string into a fake screenshot, OCR text, code buffer, prompt and
  install token, force errors in the engine and app against a local fake DSN, and assert the string never appears.

**Never in a crash report or event:** screenshots or image bytes; OCR or accessibility text; code, diffs or file
contents; prompts and model replies; the install token; Supabase tokens or OAuth codes; file paths with usernames,
workspace or project names; window titles and app names; clipboard; YouTube links or titles; keystrokes; IP,
hostname, OS username, email, user ID; env vars, argv, console logs; native minidumps.

Smaller fixes from the code map, worth doing even without an SDK:
- Add `process.on('unhandledRejection')` into `errors.json`; send renderer Boundary errors to main over IPC.
- A "Report a problem" button that copies the scrubbed report and opens `mailto:support@miyagi.study?subject=...`
  (`safeOpen` already allows mailto with a subject).
- Rotate `engine.log` at 5 MB and run the engine "Copy details" text through `scrub()`, not only `redact()`, which
  keeps the macOS username in the log path and can leave a Bearer token visible (`localEngine.ts:215,305`).

### Usage counts without content ($0)

Count on the server what miyagi-cloud already sees, as daily totals: no third-party SDK, nothing on the user's Mac,
no consent prompt. Keep counters somewhere that survives a Render restart (Supabase Postgres, or the attached disk
once confirmed).

- Events (enums only): `install_created`, `app_open` (once a day), `signin_choice {google|anonymous}`,
  `lesson_build_result {ok|error_code}`, `lesson_started`, `step_checked {pass|fail|error}`, `lesson_finished`,
  `limit_hit {install|ip|global|provider}`, `error {app|engine|ext|cloud, code}`. Context: os, app/engine version,
  model family, cost bucket.
- **Never** an event property: screenshots or anything derived from them (OCR text, hashes, thumbnails); code, file
  names or paths; window titles; YouTube links or lesson titles; prompts or model output; raw error messages or stack
  traces; email or user IDs; IP or hardware IDs; the install token in any third-party tool.
- Downloads: each GitHub release asset's `download_count` (free, REST API) once a day into the admin page.
- Website: none for now. B's cookie decision says keep the site tracker-free; if counts are wanted later, Cloudflare
  Web Analytics is free and cookieless, but re-check with B first.
- Not at launch: PostHog (autocapture and session replay would record lesson panels: Clicky's #34 mistake), and
  client SDKs like Aptabase or TelemetryDeck (fine later, opt-in, same event list).

### Spend alerts and hard stops

Provider caps fire after the money is spent and lag; miyagi-cloud's own automatic breaker is A's (held privately).
D's part is that someone is told, fast.

| Where | Setting (suggested) | Why |
|---|---|---|
| Anthropic Console | Move the miyagi-cloud key to its own workspace (not Default, which can't have limits); workspace limit ~$50-100/month for launch; email alerts at $10/$25/$40 to both founders; auto-reload **off** so the credit balance is a hard stop | Self-set limit returns 400; tier cap returns 429 `enforced_spend_limit_reached` with no retry-after (https://platform.claude.com/docs/en/api/rate-limits) |
| Google (Gemini) | Billing linked (paid tier) and prepaid $10-20 with auto-reload off; AI Studio project spend cap ~$20-50/month; Cloud budget alerts at 50/80/100%; key restricted to the Gemini API | Budgets only alert; prepay stops at $0 (402); project caps lag ~10 min (https://aistudio.google.com/docs/billing, 2026-03-23) |
| miyagi-cloud | A daily GitHub Actions cron reads `/admin/usage` (admin token as a repo secret) and fails, which emails both founders, when today's estimated USD passes the alert line; it pings a Healthchecks.io check so a silent cron is noticed | The admin page exists but nobody is paged (`cloud/app.py:494-561`) |
| Render | Starter instance confirmed, card on file (bandwidth overage bills at $0.15/GB instead of suspending), pipeline spend limit ~$5 | Hobby includes 5 GB outbound; forwarding screenshots is outbound (https://render.com/docs/outbound-bandwidth) |
| Written down | The dollar line where the kill switch trips, who flips `PROXY_ENABLED`, and the status text users see | Decide before, not during, the spike |

Rough size: a Sonnet step check with one downscaled image is about a cent; a 20-step lesson about $0.30 (assumption
from list prices; area C/E have the real per-lesson numbers). Screenshots at full Retina size cost up to ~3x the
tokens of a 1,456 px JPEG (https://platform.claude.com/docs/en/build-with-claude/vision); downscaling also cuts Render
bandwidth.

### Uptime and status

- UptimeRobot free (50 monitors, 5-minute checks, email and Discord alerts, one status page, commercial use allowed
  per its help center, 2026-09-28): a keyword monitor on `https://miyagi-cloud.onrender.com/healthz` for
  `"ok":true` and a second for `"proxy_enabled":true` (so a tripped kill switch alerts too); a keyword check on
  miyagi.study; a HEAD check on the current release asset. Better Stack free is the alternative if Slack matters.
- Ask Michael to add `keys_configured` and `db_ok` booleans (no values) to `/healthz`.
- Subscribe both founders to status.claude.com (Claude API component) and Google AI Studio status: most launch-day
  "it's broken" moments will be upstream or our own limits.
- Never use a pinger to keep a free Render service awake: it burns the 750 free hours, and a Render staff forum post
  reportedly calls it abuse (the fact-checker couldn't open it). Starter is $7/month and never sleeps.
- Status page: not needed at launch. A pinned "Known issues and status (updated <date>)" GitHub issue plus the X
  account is enough; link it from `/help`, the in-app error cards and the first HN comment. Add the free UptimeRobot
  status page later.

## 4. Support

Recommended setup, all $0:

| Piece | Setup |
|---|---|
| Email | support@, security@, hello@miyagi.study on Porkbun's free forwarding (no nameserver change) to a **new shared team Gmail** with 2-step verification and a parent as recovery contact. Never to a personal inbox. Don't build on Gmail "Send mail as" for outside addresses: Google is removing it in January 2027 (https://support.google.com/mail/answer/17101213). To reply as support@, use Zoho Mail Forever Free instead (moves MX to Zoho). |
| Bug reports | GitHub issue form `.github/ISSUE_TEMPLATE/bug.yml` on adrian-erlikhman/miyagi (where the downloads live, and quieter than the agent-heavy team repo). No upload field. First block: "This is public. Don't attach screenshots of your screen, code, API keys or passwords. Security problem? Use Report a vulnerability." Fields: OS, version, area (install / sign-in / building / checking / speed / other), what you did, what happened, optional "Copy details" (render: text), required "I removed anything private". `config.yml`: blank issues off, contact links to /help, email, advisories. |
| In-app | "Report a bug" opens the issue form with `?template=bug.yml&os=<os>&version=<v>&area=<area>` and nothing else in the URL; "Email us" opens `mailto:support@...` with a subject. |
| Help page | `miyagi.study/help`: five canned answers (Mac won't open, Windows warning, sign-in, wrong grading, slow) and one GIF of Privacy & Security › Open Anyway, linked from the app's Help and error cards above the report buttons. One indie app that shows its FAQ before the email button got 259 support emails in the 6 days after a big launch, most of them unique questions (https://www.david-smith.org/blog/2023/03/06/design-notes-30/, 2023-03-06). |
| Security | Turn on private vulnerability reporting on **both** public repos (both are public; it's off on both today). `SECURITY.md`: scope, the Advisories link, security@, "we acknowledge within 72 hours", "don't run up usage or touch other people's data", "no bounty, we'll credit you". `/.well-known/security.txt` plus `/security.txt` with Contact and an Expires before the domain's renewal; add `.nojekyll` so GitHub Pages serves the dot folder. Both founders Watch › Security alerts. |
| Response time | Public: "We're two high-school students. We read everything and reply within 2 days, slower during exams." Launch week: same-day acknowledgement, triage morning, lunch and evening. |
| Not at launch | Discord (moderation load, and stranger DMs to minor founders), Canny or Featurebase, a hosted status page. GitHub Discussions is fine for questions. A free Tally form is an optional channel for learners without GitHub accounts. |
| Minors | Personal Gmails off the site; both founders switch git commit email to the GitHub noreply address; never share phone numbers, school or city in replies; if a message shows the sender is under 13, answer once and delete the thread (16 CFR 312.5(c)). |

Canned replies (short versions; the full text is in the support research notes):
- **Mac won't open:** not signed by Apple yet; System Settings › Privacy & Security › Open Anyway (within about an hour
  of the first try) and your login password; Control-click no longer works since Sequoia (Apple, 2024-08-06). If it says "damaged" with no Open Anyway button, that's download quarantine; only for a
  copy from miyagi.study, `xattr -dr com.apple.quarantine /Applications/miyagi.app`.
- **Windows warning:** More info › Run anyway; Smart App Control has no per-app bypass and we don't suggest turning it
  off; and step checking needs the engine, which is Mac only for now.
- **Sign-in:** "Continue without an account" works for everything; finish the browser tab; for "timeout" or "port",
  quit every copy of miyagi and retry; send the exact words, no screenshot.
- **Grading is wrong:** send the YouTube link, the step number and one sentence; don't post code publicly. Label
  `grading` for Michael.
- **Slow:** long videos take longer; first lesson after a quiet spell can be slow; status link.

## 5. Register

Severity: P0 = could leak data, run up an unbounded bill, get us sued or block launch. P1 = hurts trust or
conversion at launch. P2 = later.

| id | area | risk | evidence (link) | applies to miyagi? (where) | severity | fix | owner | status |
|---|---|---|---|---|---|---|---|---|
| D01 | Site | The Windows download is offered as an equal button, but the app can't run a lesson on Windows | `app/src/main/localEngine.ts:206,829` at `origin/michael/v2-integration`; Microsoft SmartScreen docs https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation (2026-05-04) | applies: `index.html:437-441`; #188's Windows steps | P0 | Until a Windows engine ships: drop the button, or label it "windows preview: lessons need a mac for now" and leave Windows out of launch posts | Adrian (site), Michael (engine) | open |
| D02 | Site | The public downloads are the pre-v2 app, and the Mac zip has never been opened on a real Mac | `windows-sync/state.json` (`publishedSha 1b6ddcb`, `macVerified false`); release assets updated 2026-11-20 | applies: releases `mac`, `windows` on adrian-erlikhman/miyagi | P0 | Post the v2 launch build under a versioned tag (C03), list SHA-256s, scan both files on VirusTotal (a bundled Python engine can trip antivirus), open it on a clean Mac (E's first-run test) before any post | Adrian, Michael | open |
| D03 | Launch | The download code gate stops everyone without the code; Show HN asks for no barriers, and Product Hunt doesn't feature closed betas | https://news.ycombinator.com/showhn.html (read 2026-11-21: "ideally without barriers such as signups or emails"); https://help.producthunt.com/en/articles/9883485-product-hunt-featuring-guidelines (2026-03-10) | applies: `index.html:536-541` | P0 on launch day | Remove the gate on launch morning and link the releases directly (or at least print the code in every post) | Adrian | decision needed |
| D04 | Site | No AI disclosure and no data story; the page implies it runs locally ("miyagi runs on your computer.") | FTC: privacy and data commitments bind wherever made, omissions count https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/01/ai-companies-uphold-your-privacy-confidentiality-commitments (2024-01-09); Anthropic Usage Policy in-product AI disclosure https://www.anthropic.com/legal/aup (2026-11-12); EU AI Act Art. 50 applies since 2026-08-02; B11 | applies: `index.html:605`, whole page; app Settings > Privacy doesn't name providers | P1 | Two plain lines by the downloads (draft below) plus a privacy link; reword `:605`; in the app, an "AI tutor · can be wrong" label (wording with B) | Adrian | open |
| D05 | Site | No privacy policy or terms pages, yet the app's sign-in says users accept them and links to them; Google OAuth production and brand verification need a homepage privacy link on a verified domain | `/privacy`, `/terms` 404; `app/src/main/features/account.ts:22-27`, `auth/Login.tsx:260`; https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification; B04, B10 | applies: footer, app sign-in | P0 | Publish B's drafts at `/privacy` and `/terms`; footer links "privacy", "terms", "support", "security"; point or remove the app's `/pricing`, `/teams`, `/account` links; verify miyagi.study in Search Console (DNS TXT at Porkbun) | Adrian (site, app links), B (text) | open |
| D06 | Site | The only contacts are two minors' personal Gmail addresses; the domain has no email | `index.html:476-489`; no MX on miyagi.study | applies | P1 | support@ / security@ / hello@ forwarding to a shared team inbox; take the personal addresses off; noreply git commit email | Adrian | open |
| D07 | Site | Over-promising: "ask for anything", "any tutorial", "learn anything" while lessons are coding in VS Code on Apple-silicon Macs | FTC Operation AI Comply (2024-09-25) and Workado (FR notice 2025-05-02: a "98%" accuracy claim alleged to be 53% on general content), "Keep your AI claims in check" (2023-02-27); Rabbit and Devin above; B14 | applies: `index.html:604`, #188 tagline, launch copy | P1 | Scope it: "pick a coding tutorial on YouTube; miyagi turns it into steps with checks, inside VS Code"; a "beta" label; one line on limits; keep a dated evidence note (tutorials tried, how many worked) | Adrian | open |
| D08 | Site | The first screen doesn't say what miyagi is; on phones it's a tree and "scroll"; the describing lines are `aria-hidden` (also hurts Google's "homepage describes the app" check) | section 1 | applies | P1 | One plain sentence under the wordmark, visible without scrolling and readable by screen readers | Adrian | open |
| D09 | Site | Phones get desktop buttons and a code field, and could download a 130 MB desktop file | section 1 | applies | P1 | Phone view: "miyagi is a desktop app (mac)" + copy link, as #188 does | Adrian | open |
| D10 | Site | `/live/` is an old public build with API-key fields (incl. ElevenLabs) that reaches for the local engine | `miyagi-site/live/`; B's `cookies.md`; A05 | applies | P1 | Delete `live/`; engine exposure is A's (held privately) | Adrian | open |
| D11 | Site | Heavy first load: ~300 KB and 1.2 MB of JS to parse before the words show; 6 s fallback; CDN imports without SRI | load table | applies: phones and slow links | P2 | Show the words first, load 3D after; self-host three.js with SRI; skip 3D on small screens or low memory | Adrian | open |
| D12 | Site | Accessibility gaps: core lines `aria-hidden`, 3:1 notes, no skip link | https://www.w3.org/TR/WCAG22/ (2023-10-05) | applies | P2 | Darken `--m-ink-faint` or use `--m-ink-muted` under 18 px; expose the hero sentence; "skip to downloads" link; run axe/Lighthouse; no overlay widgets | Adrian | open |
| D13 | Site | No download button after the 15-screen story | section 1 | applies | P2 | Repeat the download block at the end of the story | Adrian | open |
| D14 | Site | #188's FAQ makes claims nobody has verified ("install in 30 seconds", "any tutorial", "used only to guide your lesson", Windows steps) and conflicts with the code gate and the equal-buttons decision | #188 body "Check before going live" | applies once merged | P1 | Check each claim (cloud logging checks out; retention and Gemini tier don't yet); time a real install; Adrian decides OS detection vs equal buttons and gate vs none | Michael (cloud facts), Adrian (copy, decision) | open |
| D15 | Launch | HN is temporarily restricting Show HNs because of an influx "mostly by users who aren't yet familiar with the site"; no threshold is published, so a Show HN from a little-used account may be blocked | https://news.ycombinator.com/showlim (read 2026-11-21: "temporarily restricting Show HNs") | unknown: depends on Adrian's and Michael's HN account history | P0 for the HN channel | Each founder opens `/showlim` logged in, now. Post from the account with real history (not a "miyagi" username). If neither qualifies, lead with X and Product Hunt, and participate on HN for real before trying | both | open |
| D16 | Launch | HN asks people not to post generated text; an AI-written post or replies get flagged | https://news.ycombinator.com/newsguidelines.html (read 2026-11-21: "Please don't put generated text in HN posts.") | applies: the team drafts most copy with Claude | P1 | Founders write the title, post, first comment and every reply themselves; AI only for internal prep (facts, FAQ) | both | open |
| D17 | Launch | Asking for upvotes, voting rings, mass DMs or undisclosed friend reviews get launches penalized; fake or insider reviews are an FTC issue | Show HN rules ("Please don't ask friends to upvote or comment"); https://help.producthunt.com/en/articles/17734384-5-how-to-promote-your-launch-and-what-to-avoid; FTC Consumer Review Rule 16 CFR 465 (in force 2024-10-21) | applies: the outreach plan (hundreds of emails) | P1 | Outreach asks people to try it and give feedback, never to vote, never with the HN link; friends say how they know us; no testimonials except real users with permission; CAN-SPAM postal address and opt-out on outreach | Adrian | open |
| D18 | Money | Launch day is the most expensive day, and spend can't be capped automatically yet | Register, $82k in ~48 h (2026-03-03); Sysdig LLMjacking (2024-05); Cara (2024-06); code: see A (held privately); A01, A10, A11 | applies: miyagi-cloud | P0 | A's automatic breaker and per-install caps before launch; provider hard stops (section 3 table); a written dollar line for the kill switch | Michael (cloud), A | open |
| D19 | Money | Nobody is alerted when spend climbs: the admin page is pull-only and no provider alerts are known to be set | `cloud/app.py:494-561`; https://aistudio.google.com/docs/billing (2026-03-23); https://platform.claude.com/docs/en/api/rate-limits; A10, A11 | applies | P0 | Anthropic workspace alerts, Google budget alerts, daily `/admin/usage` cron that emails, Healthchecks.io on the cron; both founders get the alerts on their phones | Michael | open |
| D20 | Legal/money | Gemini terms: unpaid-tier content can be used for training and read by reviewers, unpaid can't serve EEA/UK users, and API users must be 18+ and not build apps likely used by under-18s | https://aistudio.google.com/docs/terms (2026-03-23); B02, B07 | unknown: billing tier of the Gemini project; founders' ages; whether teens are an audience. Through the cloud, Gemini gets YouTube links only (`server/config.py:243-245`), which narrows the data part | P0 | Michael confirms paid tier; B decides the age rule and who holds vendor accounts (likely a parent); the site and launch copy follow B's answer (don't market to teens while Gemini stays, if that's the call) | Michael, B | open |
| D21 | Monitoring | No crash reporting: crashes only reach us if users email | `app/src/main/features/errors.ts`; no SDK anywhere (code map) | applies | P1 | Section 3: unhandledRejection, renderer errors to main, Report-a-problem flow; opt-in Sentry with the allowlist config, or `/v1/crash` | Adrian (app), Michael (engine) | open |
| D22 | Monitoring | No usage counts: on launch day we won't know installs, activation or failures | code map: only cloud tokens table and per-day usage | applies | P1 | Server-side enum counters (section 3); release `download_count` daily | Michael (cloud), Adrian (app events) | open |
| D23 | Monitoring | No uptime check on miyagi-cloud, the site or the download | `/healthz` exists (200, 0.25 s, 2026-11-21) | applies | P1 | UptimeRobot free monitors (section 3), alerts to both founders; subscribe to status.claude.com | Michael | open |
| D24 | Ops | If miyagi-cloud is ever on Render Free: sleeps after 15 min, ~1 min wake, the app's 10 s install-token timeout fails first run, local disk is lost | https://render.com/docs/free; `app/src/main/features/cloud.ts:38-39`; `render.yaml` says `starter` | unknown: live plan (C05) | P1 | Confirm Starter in the dashboard; raise the mint timeout or show "waking up"; no keep-alive pingers on Free | Michael, C | open |
| D25 | Ops | When limits or providers fail, users see raw provider text ("Couldn't build this lesson: <raw error>"), and one shared Anthropic rate limit hits everyone at once | `server/orchestrator/session.py:210`; `server/lesson/claude.py:146-156` | applies | P1 | Map spend-limit, allowlist and 5xx errors to one calm line ("miyagi is at capacity today, try again after <time>"), no retries on those; check the Anthropic org tier (new orgs start in a lower Evaluation tier, and a sharp jump in usage returns 429 "ramp limits" even under the limit: https://platform.claude.com/docs/en/api/rate-limits, read 2026-11-21) and ask for a raise before launch | Michael (engine), Adrian (app text) | open |
| D26 | Support | No support path: no in-app report, no support address, no issue form, no help page | code map: no Report a problem anywhere; `index.html:476-489` | applies | P1 | Section 4 | Adrian | open |
| D27 | Security | No private security channel: no SECURITY.md, private vulnerability reporting off on both public repos, no security.txt; a public report of a cloud hole means an unbounded bill until someone notices | `gh api .../private-vulnerability-reporting` → false (2026-11-21); Clicky's unanswered #34; Cluely's DMCA; A17 | applies | P0 | Section 4 "Security"; A owns the incident runbook | both | open |
| D28 | Support | Public bug reports leak users' secrets and names (pasted logs, screenshots of VS Code with `.env`); edits don't erase history | https://arxiv.org/html/2410.23657v3 (v3 2025-11-06; 5,881 verified secrets in issue reports); Truffle Security, 721 live keys in comments, ~10% only in edit history (2023-09-27); engine "Copy details" uses `redact()` (`localEngine.ts:215,305`) | applies | P1 | Issue form with no uploads and a warning; run engine details through `scrub()`; delete whole issues that leak, revoke the install token | Adrian | open |
| D29 | Launch | Over-polished demo: the site story is scripted and the demo lesson runs in DEMO mode; first users will try their own tutorials | Devin, Humane above; memory `miyagi-offline-demo` | applies: site story, launch video | P1 | One-take unedited video on a real tutorial, including a failed check; label the site story "illustration of a real run"; never show DEMO-mode output as live | both | open |
| D30 | Launch | Positioning backlash: a screen-seeing tutor read as a cheating or surveillance tool | Cluely (2025), Recall (2024), Friend (2025-10), Screenpipe HN (2024-09-30); B15 | applies | P1 | First comment and site say exactly what is captured, how often (every few seconds during a lesson), where it goes, what isn't (no audio, no camera), how to pause; "it checks your work, it never does it for you" | both | open |
| D31 | Ops | The Windows sync agent or a CI run replaces a public file mid-launch: SHA-256s in posts stop matching and SmartScreen reputation resets | memory `sandhacks-windows-sync` (`publishNext`); Microsoft SmartScreen docs | applies | P1 | Freeze uploads from 24 h before to 72 h after each launch; one versioned hotfix a day at most | Adrian | open |
| D32 | Launch | HN and Product Hunt on the same day: two founders can't staff both, and both spikes hit the caps at once | https://danfking.github.io/blog/2026/04/23/show-hn-by-the-numbers/ (2026-04-23: best slot Monday 00:00 UTC, which is Sunday 4 PM PST in winter, 10.8% reach 50+ points); PH launch guide | applies | P2 | Soft launch week -1; Show HN Sunday ~4-5 PM PT; Product Hunt a week later on a weekend at 12:01 AM PT | both | open |
| D33 | Launch | X link posts from small accounts get almost no reach | https://buffer.com/resources/links-on-x/ (2025-10-14; X staff later said there's no link penalty, unverified) | applies | P2 | Native 30-60 s screen recording, link in the first reply | Adrian | open |
| D34 | Launch | Saying "free" without conditions while the cloud has caps and a kill switch | 16 CFR 251.1 | applies to launch copy | P2 | "Free while in beta. Usage limits apply." Never "free forever" | Adrian | open |
| D35 | Site | Google's homepage rules for OAuth brand verification (verified domain, plain description, privacy link on the same domain, matching name) | https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification; B10 | applies: miyagi.study | P1 | Covered by D05 + D08; C06 owns publishing the OAuth app (basic scopes may not need verification: https://support.google.com/cloud/answer/15549945) | Adrian, C | open |
| D36 | Support | Launch-day spam or brigading on the public repo | https://docs.github.com/en/communities/moderating-comments-and-conversations/limiting-interactions-in-your-repository | applies if it happens | P2 | Interaction limits "existing users" for 24 h | Adrian | open |
| D37 | Ops | Traffic spike takes the site or downloads down | GitHub Pages limits https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits; an HN #1 post: peak ~1.75k pageviews/hour, ~15k+ uniques and 18k pageviews over 20 h (https://harrisonbroadbent.com/blog/hacker-news-traffic-spike-anatomy/, 2024-05-27); most Show HNs get almost nothing (median 2 points, ~6% reach 50: https://danfking.github.io/blog/2026/04/23/show-hn-by-the-numbers/); PH #1 ~2k visitors (https://dub.co/blog/product-hunt, 2024-03-25) | doesn't apply: under 1 MB a visit fits 100 GB/month many times over; Releases has no bandwidth cap. Pages' "not for commercial SaaS" clause matters once miyagi charges | P2 | Keep the page under 1 MB, video off Pages; move to Cloudflare Pages if GitHub emails or paid plans start | Adrian | checked |
| D38 | Monitoring | Adding a crash or analytics SDK with its default settings would upload screenshots, code, prompts, paths and IPs: Clicky's PostHog mistake | Sentry docs in section 3; https://github.com/farzaa/clicky/issues/34 (2026-04-08); A21 (engine.log) | applies the moment anyone adds Sentry or PostHog "for debugging" | P0 if done carelessly | Only the allowlist config (section 3, appendix A); minidumps, screenshots, replay and breadcrumbs off; canary test before shipping; nothing in `vscode-ext` | Adrian, Michael | open |
| D39 | Install | The Mac install path on the newest macOS is unverified. In an Aug 2026 test on a fresh macOS Tahoe 26.6.1, an ad-hoc-signed app launched from quarantine was offered only "Move to Trash"; a broken or missing signature never ran in any setting. Whether the System Settings › Open Anyway route still works there wasn't tested. Our site, #188 and the canned reply all assume it does | https://eclecticlight.co/2026/08/11/how-can-you-run-code-that-hasnt-been-notarised/ (2026-08-11); Apple https://developer.apple.com/news/?id=saqachfa (2024-08-06) | unknown: needs a fresh Mac or VM on the newest macOS; `windows-sync/state.json` says the public zip was never opened on a Mac | P0 until tested | Download the public zip on a fresh, current macOS; check `codesign --verify --deep` passes (valid ad-hoc signature, nothing broken by zipping); walk the exact Open Anyway steps; fix the site, #188 and the canned reply to match what really happens. Lasting fix is C01 (Developer ID + notarization) | Adrian, C | open |
| D40 | Ops | A launch-day bug or security fix can't reach people who already installed: Electron's auto-updater needs a signed app on macOS, there is no forced-update path, and the update card needs a parseable version on the release | https://www.electronjs.org/docs/latest/api/auto-updater ("must be signed for automatic updates on macOS", read 2026-11-21); C03, C04; #189 | applies | P0 | Before launch: versioned releases (C03) and the update card (#189) working, and a minimum-version check in miyagi-cloud (on `/v1/install` and proxied calls) that answers old builds with "please update" and a download link | Michael (cloud), Adrian (app) | open |
| D41 | Product | The engine's fixed port 8787 is also the default port of Cloudflare's `wrangler dev`, which many HN readers run; the engine may fail to start, or the app may talk to someone's local Worker | https://developers.cloudflare.com/workers/wrangler/commands/workers/ ("send HTTP requests to localhost:8787", read 2026-11-21); engine port defaults to 8787 (`localEngine.ts:406-411`); `app/src/main/localEngine.ts` | applies: Macs running `wrangler dev` | P1 | A port fallback or random port with a handshake, a clear "port in use" message, and a canned reply; E or A may already cover the handshake | Michael (engine), E | open |

## 6. Draft copy (Adrian rewrites it before use)

Hero line under the wordmark:
> miyagi turns a coding tutorial on YouTube into steps you do yourself in VS Code, and checks each one before the video moves on.

Data line by the downloads (facts to confirm with Michael and B before shipping):
> miyagi is an AI tutor (Claude, by Anthropic). During a lesson it looks at your screen every few seconds and reads
> your code, and sends what it needs to Anthropic through our server to build and check steps. We don't keep your
> screenshots. Lessons are AI-generated and can be wrong. [privacy]

Requirements line:
> Mac with Apple silicon, macOS 13 or later, and VS Code. Free while in beta; usage limits apply.

## 7. Launch-day runbook (draft)

Roles: **Thread** (answers HN or PH and X, by hand) and **Ops** (spend, monitors, issues and inbox). Swap every 4
hours. Both founders block the first 8-12 hours and plan sleep around school.

**Week -2 to -1**
1. Each founder checks `news.ycombinator.com/showlim` logged in (D15). Decide the posting account.
2. Michael: provider hard stops and alerts set (section 3), Render plan confirmed, A's breaker and caps merged, the
   kill-switch dollar line written down with the status text.
3. Monitors live (UptimeRobot on `/healthz`, site, release asset); status.claude.com subscriptions; the daily spend
   cron and its Healthchecks.io check.
4. Support live: support@/security@/hello@ forwarding with auto-reply; issue form; SECURITY.md and private reporting
   on both repos; security.txt; `/help` with canned replies; pinned "Known issues and status".
5. Site changes shipped (section 9); `/privacy` and `/terms` live; app links resolve.
6. Soft launch to hackathon contacts and the outreach list with a feedback ask (no votes). Fix the top issues.
7. Write by hand: Show HN title (e.g. "Show HN: miyagi – turns a YouTube coding tutorial into checked steps in VS
   Code"), post text, first comment. Record the one-take 30-60 s video. Prepare PH assets (tagline, gallery, maker
   comment) for a week later. Have a plain answer ready for "how is this different from Miyagi Labs?" (B08: a YC
   company with a similar name and pitch).

**Day -1**
8. Freeze builds (sync agent `publishNext` false; no CI uploads to the release tags) until day +3.
9. From a clean Mac: download from the live site, check SHA-256, Open Anyway, sign in and skip sign-in, run one real
   lesson end to end through production miyagi-cloud (E's Test 1).
10. Baseline: note the spend page total, token count and download counts. Check the Supabase project isn't paused
    (free projects pause after a week idle: https://supabase.com/pricing) and Google sign-in works from a new account.

**Launch (Show HN, Sunday ~4-5 PM PT)**
11. T-30 min: all monitors green, `/healthz` shows `proxy_enabled: true`, download links work without a code, inbox
    auto-reply on.
12. Post. Within minutes, the first comment (by hand): who we are and why we built it, how it works, exactly what
    leaves the computer and how often, what's not built yet (redaction is partial, Windows can't run lessons),
    unsigned-app steps, where to report bugs and security issues.
13. Thread: answer every comment; facts and what we'll change, never arguments. Unsigned builds and screen capture
    will be the top comments: link `/help` and the privacy page.
14. Ops, every 30 minutes: spend vs the alert line, Render logs (status codes only), new issues and emails
    (acknowledge same day), monitors.
15. If spend passes the alert line: tighten per-install caps (A's knobs) and post a note in the pinned issue. If it
    passes the kill line: the breaker trips (or flip `PROXY_ENABLED`), post the capacity note in the thread, the
    pinned issue and X, and say when it comes back.
16. If someone posts a security hole publicly: thank them, ask to move to the private channel, delete content with
    secrets, follow A's first-hour runbook (rotate keys, disable tokens).
17. If miyagi-cloud or a provider is down: pinned issue and a reply in the thread within 15 minutes; the app should
    already show a calm message (D25).
18. Don't: ask for votes, post AI-written text, ship an unreviewed hotfix during the peak, republish installers.

**Days +1 to +7**
19. Triage morning, lunch and evening; same-day acknowledgement; 48-hour public promise.
20. Daily numbers into a note: downloads, new install tokens, lessons started and finished, step pass/fail/error,
    spend, top three issues. Update "Known issues".
21. Hotfixes: at most one a day, versioned tag, changelog line, new SHA-256, after the freeze ends. They only reach
    installed users through the update card (D40).
22. Day +7: Product Hunt on a weekend at 12:01 AM PT, same roles; repeat steps 11-18.
23. Day +10: a short postmortem (what broke, numbers, what changes), shared with Michael.

## 8. Launch checklist (area D: must be true before we post publicly)

- [ ] Anyone can download without a code, or the code is in every post (D03).
- [ ] The public files are the launch build, under versioned tags, with SHA-256s listed, scanned on VirusTotal, and one
      was downloaded from the live site and opened on a fresh Mac on the newest macOS, following our own steps (D02, D39).
- [ ] A broken build can be fixed for people who already installed it: update card working, or a minimum-version
      message from the cloud (D40).
- [ ] Windows is removed from the page or clearly labeled as a preview that can't run lessons yet (D01).
- [ ] The first screen says what miyagi is in one plain, screen-reader-visible sentence (D08).
- [ ] The site says it's AI, what it captures and how often, and where it goes; no "anything" or "any tutorial";
      "miyagi runs on your computer" reworded (D04, D07).
- [ ] `/privacy` and `/terms` are live and linked from the footer; every miyagi.study link the app opens resolves (D05).
- [ ] support@, security@ and hello@ reach a shared team inbox with an auto-reply; no personal emails on the site (D06).
- [ ] SECURITY.md, private vulnerability reporting on both public repos, and security.txt are live (D27).
- [ ] Bug form without uploads, `/help` with canned answers, pinned "Known issues and status" (D26, D28).
- [ ] Provider hard stops and alerts are set and reach both founders' phones; the kill-switch dollar line and status
      text are written down; A's automatic breaker is deployed (D18, D19).
- [ ] Uptime monitors on `/healthz`, the site and the download; status.claude.com subscribed (D23).
- [ ] Some crash or error signal exists beyond users' emails (D21), and server-side usage counts with no content (D22).
- [ ] No crash or analytics SDK ships without the allowlist config, opt-in consent and a passing canary test (D38).
- [ ] The app shows calm messages for capacity, provider down and cloud unreachable (D25).
- [ ] The Gemini tier and the age rule are settled (D20, with B).
- [ ] The posting HN account passes `/showlim`; the post, first comment and replies are written by hand (D15, D16).
- [ ] The demo video is one honest take on a real tutorial; no DEMO-mode output shown as live (D29).
- [ ] Outreach asks for feedback, not votes (D17).
- [ ] Builds are frozen from day -1 to day +3 (D31).
- [ ] `/live/` is gone (D10).
- [ ] Both founders have the first 8-12 hours blocked, with roles (runbook).

## 9. Site changes recommended for Adrian (in order)

1. Launch day: remove the download code (or print it in the posts).
2. Windows: remove the button or label it "preview: lessons need a mac for now".
3. Add `/privacy`, `/terms` (B's drafts), `/help`, `/.well-known/security.txt` + `/security.txt` and `.nojekyll`;
   footer: privacy · terms · help · support@ · security@; take off the personal Gmails.
4. A plain hero sentence and the AI/data line by the downloads; reword "miyagi runs on your computer", "ask for
   anything" and "say what you want to learn".
5. Delete `live/`.
6. YouTube embed: click-to-load or stills only (B's fix; also YouTube's no-overlay rule).
7. Phones: "miyagi is a desktop app" with copy link instead of the buttons (or merge #188's phone view).
8. A download block after the story; darker small text; a skip link; unhide the hero sentence for screen readers.
9. Self-host three.js with SRI, show text before 3D, and skip 3D on small or low-memory devices.
10. Swap the releases to the v2 build under versioned tags, and freeze uploads around launch.

## 10. Open questions (need a console, a Mac or a person)

| Question | Who can answer | Row |
|---|---|---|
| Do Adrian's and Michael's HN accounts pass `news.ycombinator.com/showlim`? | each founder, logged in | D15 |
| Live Render plan, disk attached, and live env values (`PROXY_ENABLED`, model allowlists, token caps) | Michael (Render dashboard) | D24 |
| Anthropic org tier, whether the cloud key is in its own workspace, which limits and alerts are set | Michael (Console) | D18, D19, D25 |
| Gemini project billing tier, key restriction, project cap, budget alerts | Michael (AI Studio, Cloud Billing) | D19, D20 |
| Who legally holds the Anthropic, Google, Render and Apple accounts, given the founders' ages | B, parents | D20 |
| Which scopes the Supabase Google provider requests (basic scopes may not need verification) | Michael, C | D35 |
| Do Product Hunt's and X's terms let under-18 founders run maker accounts? Not checked | Adrian | D32, D33 |
| Will the launch be offered in the EU/UK? (Gemini paid-tier rule, GDPR, AI Act) | B | D20 |
| Does Open Anyway still work for our zip on the newest macOS? | Adrian or Michael, fresh Mac or VM | D39 |
| Is Porkbun email forwarding available on this domain (it was registered through an MLH offer)? | Adrian (Porkbun) | D06 |

## 11. Later

- `<title>` is just "miyagi"; add a few words for search and tabs.
- No `robots.txt`, sitemap or custom 404.
- The "scroll" hint overlaps the "see it work" button on phones mid-fade.
- The app's open-link allowlist still includes elevenlabs.io (`safeOpen.ts:17-28`); no ElevenLabs option is shown.
- The update check calls the unauthenticated GitHub API (60 requests/hour per IP); school NAT can make it fail
  silently. Serve a small manifest from miyagi.study later.
- "Delete my data" removes keys and settings only (B and #199 own the scope).
- `engine.log` rotation at 5 MB (in section 3, but not launch-blocking).
- Gemini Flash list prices double on 2027-01-01 (https://aistudio.google.com/docs/pricing); update the cloud's price
  table and caps before then.
- Cloudflare Web Analytics on the site, only after B re-checks the cookie page.
- A Tally form for learners without GitHub accounts.
- A real status page once traffic justifies it.

## Appendix A. Crash-reporting config (draft, untested)

From the crash-reporting research (Sentry docs and SDK source read 2026-11-21). Test it with the canary before
shipping; check the integration names against the installed SDK version.

Electron main (`@sentry/electron` 8.4.x):

```ts
Sentry.init({
  dsn: dsnFromInstallResponse,            // served by /v1/install so it can be rotated
  release: `miyagi@${app.getVersion()}`,
  environment: app.isPackaged ? 'prod' : 'dev',
  enabled: app.isPackaged,
  attachScreenshot: false,
  includeLocalVariables: false,
  maxBreadcrumbs: 30,
  dataCollection: {
    userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false,
    graphQL: { document: false, variables: false }, genAI: { inputs: false, outputs: false },
    mcp: { inputs: false, outputs: false }, databaseQueryData: false, queues: false,
    stackFrameVariables: false, frameContextLines: 0,
  },
  integrations: d => d.filter(i => ![
    'SentryMinidump', 'ElectronMinidump', 'Screenshots', 'Console', 'ElectronNet', 'NodeFetch', 'Http',
    'ContextLines', 'LocalVariables', 'LocalVariablesAsync', 'AdditionalContext', 'GpuContext', 'Modules',
    'RendererProfiling',
  ].includes(i.name)),
  beforeBreadcrumb: b => b.category === 'electron'
    ? { category: b.category, message: b.message, level: b.level, timestamp: b.timestamp } : null,
  beforeSend: (e, hint) => { if (!crashConsent()) return null; hint.attachments = []; return scrubEvent(e) },
  transportOptions: { shouldStore: () => crashConsent(), maxQueueSize: 10, maxAgeDays: 7 },
})
```

Renderer (`@sentry/electron/renderer`): drop `Breadcrumbs`, `BrowserSession`, `HttpContext`; same `beforeSend`; never
`replayIntegration`, `feedbackIntegration` or `browserTracingIntegration`.

`scrubEvent`: delete `user`, `request`, `extra`, `server_name`, `modules`; in exception values replace
`/(Users|home)/<name>` with `~`, JWTs, `sk-ant-…`, `AIza…` and `Bearer x` with `[secret]`, strip URL queries and
fragments, cap at 300 characters; delete frame vars and context lines; keep contexts `os`, `runtime`, `electron` and
tags `process`, `environment`; drop breadcrumb data.

Python engine (`sentry-sdk>=2.75,<3`, only when `MIYAGI_CRASH_REPORTS == '1'`):

```python
sentry_sdk.init(
    dsn=os.environ["MIYAGI_SENTRY_DSN"], release=f"miyagi-engine@{VERSION}", environment="prod",
    send_default_pii=False, include_local_variables=False, include_source_context=False,
    max_request_body_size="never", max_value_length=1024, server_name="engine",
    max_breadcrumbs=0, before_breadcrumb=lambda c, h: None,
    default_integrations=False, auto_enabling_integrations=False,
    integrations=[ExcepthookIntegration(), ThreadingIntegration(), AsyncioIntegration(), AtexitIntegration(),
                  DedupeIntegration(), LoggingIntegration(level=None, sentry_logs_level=None, event_level=logging.ERROR)],
    traces_sample_rate=None, profiles_sample_rate=None, before_send=_before_send,
)
```

`_before_send` builds a new dict from `event_id`, `timestamp`, `platform`, `level`, `logger`, `release`,
`environment`, `exception`, `threads`, `sdk`, `fingerprint` only; cleans exception values with the same patterns;
removes frame vars and context lines; sets `logentry` to the message template only (never its arguments).

## Sources

Primary unless marked. Dates are publication or event dates; "read" means the page is undated and was read on
2026-11-21.

- Site source: github.com/adrian-erlikhman/miyagi at `b3c867b` (2026-11-21). Live site https://miyagi.study/ (2026-11-21).
- #188: https://github.com/michae6345-crypto/miyagi/pull/188 (updated 2026-11-21).
- App `origin/michael/v2-integration`; engine and cloud `origin/integration/live` and `origin/claude/eng-proxy`.
- HN: https://news.ycombinator.com/showhn.html, https://news.ycombinator.com/showlim,
  https://news.ycombinator.com/newsguidelines.html (all read 2026-11-21).
- Product Hunt: https://help.producthunt.com/en/articles/9883485-product-hunt-featuring-guidelines (2026-03-10),
  https://help.producthunt.com/en/articles/17734384-5-how-to-promote-your-launch-and-what-to-avoid (read),
  https://www.producthunt.com/launch/preparing-for-launch (read).
- Clicky: https://github.com/farzaa/clicky/issues/22, /34, /44, /4, /24, /132, /138 (2026-04-07 to 2026-09-28).
- Cluely: https://www.hacktron.ai/blog/hacking-cluely (2026-02-14); TechCrunch (2025-04-21, 2025-07-09, 2026-03-05);
  https://x.com/jackhcable/status/1942636823525679182 (2025-07-08).
- Rabbit: https://rabbit.tech/security-investigation-062524 (2024-06-25); Android Authority (2024-04-30).
- Humane: MacRumors (2024-08-07); TechCrunch (2025-02-18). Devin: Answer.AI (2025-01-08).
- Recall: https://blogs.windows.com/windowsexperience/2024/06/07/update-on-the-recall-preview-feature-for-copilot-pcs/ (2024-06-07).
- Bills: The Register (2026-03-03, press); InfoQ on Cara (2024-06, press); Sysdig LLMjacking (2024-05).
- FTC: Tech@FTC (2024-01-09); Operation AI Comply (2024-09-25); Workado order (2025-08-28); Consumer Review Rule
  (2024-08-14); 16 CFR 251.1 "Free"; CAN-SPAM guide.
- AI disclosure: Anthropic Usage Policy https://www.anthropic.com/legal/aup (2026-11-12); EU AI Act Art. 50
  https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-50; Gemini API terms https://aistudio.google.com/docs/terms (2026-03-23).
- Spend: https://platform.claude.com/docs/en/api/rate-limits (read); https://aistudio.google.com/docs/billing
  (2026-03-23); https://render.com/docs/free (read); https://render.com/docs/outbound-bandwidth (read).
- Uptime: https://help.uptimerobot.com/en/articles/11604710-who-should-use-uptimerobot-s-free-plan (2026-09-28);
  https://betterstack.com/docs/uptime/check-frequency/ (read); https://status.claude.com/.
- Support: https://kb.porkbun.com/article/10-how-to-set-up-email-forwarding-service (2026-07-09);
  https://support.google.com/mail/answer/17101213 (2026-09); https://www.rfc-editor.org/rfc/rfc9116.html (2022-04);
  https://github.blog/changelog/2026-10-01-structured-forms-for-private-vulnerability-reports (2026-10-01);
  https://arxiv.org/html/2410.23657v3 (2024-10); https://www.david-smith.org/blog/2023/03/06/design-notes-30/ (2023-03-06, blog);
  https://discord.com/press-releases/discord-launches-teen-by-default-settings-globally (2026-02-09).
- Traffic: https://harrisonbroadbent.com/blog/hacker-news-traffic-spike-anatomy/ (2024-05-27, blog);
  https://dub.co/blog/product-hunt (2024-03-25, blog); https://danfking.github.io/blog/2026/04/23/show-hn-by-the-numbers/
  (2026-04-23, blog); https://buffer.com/resources/links-on-x/ (2025-10-14, blog).
- Crash reporting: https://docs.sentry.io/platforms/javascript/guides/electron/configuration/options/,
  https://docs.sentry.io/platforms/javascript/guides/electron/, https://docs.sentry.io/platforms/native/guides/minidumps/,
  https://docs.sentry.io/platforms/python/integrations/anthropic/ (2026-11-19),
  https://docs.sentry.io/security-legal-pii/scrubbing/advanced-datascrubbing/, https://sentry.io/pricing/ (all read);
  https://github.com/getsentry/sentry-python/blob/2.75.0/sentry_sdk/integrations/_wsgi_common.py;
  https://www.electronjs.org/docs/latest/api/crash-reporter; https://code.visualstudio.com/api/extension-guides/telemetry
  (2026-11-18); https://glitchtip.com/pricing (read).
- Accessibility: https://www.w3.org/TR/WCAG22/ (2023-10-05); https://eur-lex.europa.eu/eli/dir/2019/882/oj (2019-06-07);
  https://www.adatitleiii.com/2026/03/federal-court-website-accessibility-lawsuit-filings-bounce-back-in-2025/ (2026-03-25, blog).
