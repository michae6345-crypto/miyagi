# A. Security and money

Area A of Michael's launch-risk brief (v2, Nov 21, 2026). Owner of this file: Adrian's area-A session.
Status: **first full pass, Nov 21 afternoon.** Code read, history scanned, outside evidence verified. Nothing was patched.

Code read (read-only):
- App: `origin/michael/v2-integration` at `958f58af` (paths below start at `app/src/`).
- Engine and VS Code companion: `origin/integration/live` at `b0659978` (`server/`, `vscode-ext/`). The companion ships from this ref (`app/scripts/bundle-engine.mjs:58`); v2-integration itself has only `vscode-ext/README.md`.
- Cloud: `origin/claude/eng-proxy` at `787fc1df` (newest `cloud/`), `origin/integration/live` (likely the deployed one, inferred), `origin/claude/eng-proxy-cache` at `f5158250` (lesson cache, not merged).

Rules for this pass: offline only. The one request to the live cloud was a plain `GET /healthz` (12:26 PM: `{"ok":true,"version":"0.1.0","proxy_enabled":true}`). No minting, no load, no paid calls.

**Public-repo rule.** Rows marked *placeholder* are exploitable today. Their evidence, paths and fixes are in Michael's private notes (`michael-watch/private/security.md`, local only). They become full rows here once fixed.

## Bottom line

1. **No leaked keys.** All 1,907 public commits were scanned, every branch and every PR ref, plus the site repo, a fresh build and the Windows `app.asar`. Nothing live turned up, so nothing needs rotating today (A09).
2. **The biggest money risk is miyagi-cloud's cost controls (A01, A02).** It needs provider-side spend limits today and server-side limits before launch.
3. **The engine and the VS Code companion need tighter access control before launch (A03 to A06, details private).** The shipped app's per-launch engine token already stops web pages from driving the engine.
4. **The Electron shell is in good shape.** Sandbox, context isolation, a navigation lock, IPC sender checks, a CSP header and denied permissions mean the Cluely postMessage chain doesn't apply (see "Checked and fine"). The open items are update integrity (A13) and one third-party script in the app's origin (A14).
5. **Not ready yet:** no security.txt, no disclosure policy and no security contact (A17).

## Register

| id | area | risk | evidence (link) | applies to miyagi? (where) | severity | fix | owner | status |
|---|---|---|---|---|---|---|---|---|
| A01 | Cloud spend | *Placeholder:* miyagi-cloud cost controls. Details sent to Michael privately | Sysdig LLMjacking ([May 6, 2024](https://sysdig.com/blog/llmjacking-stolen-cloud-credentials-used-in-new-ai-attack/): over $46k/day; [Sep 18, 2024](https://sysdig.com/blog/growing-dangers-of-llmjacking/): over $100k/day) | **Applies** (`cloud/`) | P0 | In private notes. Today, without code: A10 | Michael | open |
| A02 | Cloud spend | *Placeholder:* proxy request validation. Details sent to Michael privately | Clicky [#34](https://github.com/farzaa/clicky/issues/34) (Apr 8, 2026) | **Applies** (`cloud/app.py`) | P0 | In private notes | Michael | open |
| A03 | Companion | *Placeholder:* VS Code companion configuration. Details sent to Michael privately | — | **Applies** (companion 0.0.6) | P0 | In private notes (small change plus a unit test) | Adrian (vscode-ext) | open |
| A04 | Engine | *Placeholder:* engine handling of learner-provided keys. Details sent to Michael privately | — | **Applies** (engine), BYOK users | P0 | In private notes | Michael | open |
| A05 | Engine, companion | *Placeholder:* engine and companion local access control. Details sent to Michael privately | Zoom localhost server, [CVE-2019-13450](https://nvd.nist.gov/vuln/detail/CVE-2019-13450) (Jul 8, 2019); MCP Inspector, [CVE-2025-49596](https://nvd.nist.gov/vuln/detail/CVE-2025-49596) (Jun 13, 2025; fixed with a session token plus Origin and Host checks); Ollama DNS rebinding, [CVE-2024-28224](https://www.nccgroup.com/research/technical-advisory-ollama-dns-rebinding-attack-cve-2024-28224/) (Apr 8, 2024) | **Applies** (engine, companion, app) | P0 | In private notes | Michael (engine), Adrian (app, companion) | open |
| A06 | Engine | *Placeholder:* engines started outside the app (dev and demo setups). Details sent to Michael privately | Same as A05 | **Applies** to dev and demo Macs | P0 when used | In private notes | Michael, Adrian (app) | open |
| A07 | Cloud | The install-token limit's client-IP handling has to be checked on Render. If it's wrong, new installs could be refused on launch day | Render doesn't document how it treats a client-sent `X-Forwarded-For` ([unofficial thread](https://feedback.render.com/features/p/send-the-correct-xforwardedfor)); details in private notes | **Unknown: verify on Render** | P0 until verified (blocks install) | Check on a throwaway staging service, or put our own Cloudflare in front and key on `CF-Connecting-IP` (needs A20) | Michael | open |
| A08 | Cloud | *Placeholder:* the shared lesson cache (`eng-proxy-cache`, not merged). Details sent to Michael privately | — | **Applies once the cache ships** (no engine client on any branch yet) | P0 before the cache ships | In private notes | Michael | open: gate the cache merge on it |
| A09 | Secrets | A key committed to the public repo, or built into the app, is harvested within minutes (Clicky #22: an Anthropic key in the first open-source commit; Rabbit R1: hardcoded ElevenLabs, Azure, Google Maps and SendGrid keys) | [Clicky #22](https://github.com/farzaa/clicky/issues/22) (Apr 8, 2026; removed Apr 10 in `d86c32f`); [Rabbit's own timeline](https://rabbit.tech/security-investigation-062524) (Jun 25 to Jul 5, 2024) | **Checked Nov 21: none found.** gitleaks 8.30.1 over a mirror with every branch and `refs/pull/*` (1,907 commits) found 3 hits: a test HS256 secret, the publishable Supabase key and an empty `ANTHROPIC_API_KEY=`. A second scan of every blob found only test fixtures. `adrian-erlikhman/miyagi` (site and releases) is clean. `npm run build` output holds only the publishable key and the cloud host. The local Windows `app.asar` is clean. The repo has no Actions secrets, and no workflow reads any. Not scanned: the published Mac zip and Windows installer | P0 class, clean today | Keep it clean: (1) confirm secret scanning and push protection are on (needs repo admin; Anthropic and Supabase secret keys are push-protected partners, a Google `AIza` key is alerted but not blocked, [GitHub docs](https://docs.github.com/en/code-security/secret-scanning/introduction/supported-secret-scanning-patterns)); (2) gitleaks in CI on every PR; (3) a build-time check that refuses `sb_secret_` and any JWT with `role: service_role` in `MAIN_VITE_*` (`main/publicConfig.ts`); (4) scan each release asset before it's published | Michael (repo admin), Adrian (CI, build check) | done (scan); open (guards) |
| A10 | Cloud spend | No provider-side backstop is known to be set. If anything gets past the proxy, the first stop is our Anthropic tier cap: $500 a month on Start, $1,000 on Build. After that **every** user gets 429 until the 1st of the month | [Claude API rate limits](https://platform.claude.com/docs/en/api/rate-limits) (tier caps, org and workspace spend limits; a self-set limit answers 400); [Gemini billing](https://ai.google.dev/gemini-api/docs/billing) (project spend cap, about 10 minutes of billing lag) | **Unknown: needs Michael's consoles** | P0 (today) | Give the proxy's Anthropic key its own workspace with a monthly spend limit and ITPM/OTPM limits, and set an org limit below the tier cap. Set a Gemini project spend cap and Cloud Billing budget alerts, and restrict the key to the Generative Language API. Make the app show "paused" for the 400 a self-set limit returns | Michael | open |
| A11 | Cloud ops | Nobody hears about abuse until the bill arrives, and stopping it is slow. `PROXY_ENABLED` is read at startup, so flipping it needs an env change plus a redeploy. Tokens can only be disabled one at a time. `cloud/app.py:296` says "the operators have been notified", but nothing notifies anyone | `cloud/app.py:60` (`PROXY_ENABLED`), `:539-553` (per-token disable), `:295-296`; [Render disks](https://render.com/docs/disks) (a service with a disk stops before it restarts) | **Applies** | P1 | A runtime kill flag in SQLite behind an admin POST. Automatic shutoff at the global cap. Disable tokens by creation-time range. Webhook alerts (Slack or Discord) at 50, 80 and 100% of the cap, for one token over $2/day, and for more than 500 mints an hour. A Render cron that polls `/admin/usage` in case the app itself is down. Show the deployed commit in `/healthz` (today every version reports `0.1.0`) | Michael | open |
| A12 | App | *Placeholder:* packaged-app configuration hardening. Details sent to Michael privately | — | **Applies** (app) | P1 | In private notes | Adrian (core) | open |
| A13 | Updates | Update integrity rests on two things: HTTPS, and whoever can publish to `adrian-erlikhman/miyagi` releases. There is no signature check. The installer URL may be any `github.com` path. The sha256 comes from the same response and is only displayed | `main/features/updates.ts:133-135`; `main/safeOpen.ts:26` (`'github.com'`); `renderer/src/features/updates/manifest.ts:87` (releases API for a personal account); update-chain bugs: [Doyensec electron-updater bypass](https://blog.doyensec.com/2020/02/24/electron-updater-update-signature-bypass.html) (Feb 24, 2020), [CVE-2024-39698](https://github.com/advisories/GHSA-9jxc-qjr9-vjxq) (Jul 9, 2024) | **Applies** (nothing installs by itself; the card opens the installer in the browser) | P1 | Pin the installer URL to `https://github.com/<release repo>/releases/download/`. Sign each release with an ed25519 or minisign key whose public half is built into the app, and verify before offering. Move releases to a shared org with 2FA required. Long term: Developer ID and notarization (area C, C01 to C03) | Adrian | open |
| A14 | App | A third-party script runs in the app's own origin with the full `window.tut` bridge. The YouTube IFrame API loader is injected into our document, not sandboxed in an iframe, so if it were ever compromised it could send engine commands and call every `feat:*` handler | `renderer/src/features/player/youtube.ts:80`; CSP `script-src … https://www.youtube.com https://s.ytimg.com` (`main/serve.ts:41`); `main/index.ts:84-90` trusts our origin; `preload/index.ts:23` | **Applies** (player window) | P1 (unlikely, high impact) | Host the player in its own page with no preload, talking to ours by postMessage with an origin check. Or give the player window a preload with only video channels and drop YouTube from the main CSP | Adrian | open |
| A15 | Engine | After a crash or force quit, the engine process keeps running with no UI. Per the code, **screen capture pauses 3 s after the app goes away**. The file watcher, the VS Code poll, any build in flight (model spend) and keys in memory stay alive until the next launch reclaims the pid. A clean quit sends SIGTERM with no escalation | `main/localEngine.ts:490, 497-502` (`detached: true`), `:719-729`; `main/index.ts:543-546`; `server/orchestrator/session.py:4375` (`SCREEN_NO_CLIENT_S = 3.0`), `:4541-4554`; #202 R04 | **Applies; capture pause needs a Mac check** (`kill -9` the app, watch the recording indicator and `pgrep -fl server.orchestrator.main`) | P1 (would be P0 if capture kept going) | Engine: exit when the parent dies (`getppid()==1`, or an inherited pipe closes) and after N minutes with no client. App: keep the pid file at quit, and SIGKILL the group after about 3 s | Michael (engine), Adrian (app) | open: Mac check |
| A16 | Data | "Delete my data" says "Delete everything on this Mac?" but removes only the API keys and prefs. The learner stays signed in, the install stays linked to their account on the cloud, and lessons, transcripts, run logs and file backups stay in `~/miyagi`. Nothing is deleted on the server. Sign-out also leaves the install linked, so on a shared Mac the next person's proxied usage is attributed to the last learner | `main/features/settings.ts:168-180`; `renderer/src/features/settings/sections/Privacy.tsx:39, 80`; `main/features/cloudLink.ts:24-25`; `main/features/auth.ts:547-554`; #202 R13 | **Applies** | P1 here; the legal side is area B and #199 | App: sign out, delete `cloud-link.json` and `reminders.json`, re-mint the install token, clear renderer storage and crash reports, and say plainly what stays until the engine and cloud can delete. Michael: an engine "delete my data" command, plus `DELETE /v1/me` (cloud) and Supabase account deletion | Adrian (app), Michael (engine, cloud) | open: fold into #199 |
| A17 | Incident response | There is nowhere to report a hole and no plan for the first hour. `miyagi.study/.well-known/security.txt` returns 404 (checked 12:26 PM), there's no SECURITY.md or disclosure policy, and private vulnerability reporting is unknown. Cluely had no disclosure program, filed a DMCA takedown against a researcher, and made bounty pay depend on taking disclosures down. Rabbit took about 40 days to rotate, and the rotation itself caused an outage | [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116) (Apr 2022); [CISA VDP template](https://www.cisa.gov/vulnerability-disclosure-policy-template); [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository); Cluely: [Critical Thinking ep. 136](https://criticalthinkingpodcast.io/episode-136-hacking-cluely-ai-prod-sec-and-how-to-not-get-sued-with-jack-cable/) (Aug 21, 2025), [Hacktron](https://hacktron.ai/blog/hacking-cluely) (Feb 14, 2026); Rabbit: [rabbit.tech](https://rabbit.tech/security-investigation-062524), [404 Media](https://www.404media.co/rabbit-says-breach-not-caused-by-a-breach-is-fault-of-malicious-employee-hacktivists-journalists/) (Aug 1, 2024) | **Applies** (site, repo); also noted in area D | P1 | Publish `/.well-known/security.txt` (Contact and Expires are required; GitHub Pages needs `.nojekyll` or `include: [".well-known"]` for dot-folders). Add SECURITY.md with a safe-harbor policy and turn on private vulnerability reporting. Pick one security contact address. Rehearse the runbook below once, including a rotation with no downtime | Adrian (site, SECURITY.md), Michael (repo settings, contact) | open: draft below |
| A18 | Supabase | Supabase is auth only (no branch calls `rest/v1`, `.from(`, `rpc` or storage), and the app holds only the publishable key, which is fine by design. What's left is console settings nobody has checked: RLS on any table in an exposed schema, email/password and anonymous sign-ins off, the redirect allowlist, and whether the legacy JWT secret is still active | `main/publicConfig.ts:19-20` (`sb_publishable_`); `cloud/render.yaml:27-28` (optional `SUPABASE_JWT_SECRET`); [Supabase API keys](https://supabase.com/docs/guides/api/api-keys) (legacy anon and service_role keys deprecated by end of 2026, must be turned off by hand); [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) | **Unknown: needs the Supabase console** | P1 | Michael confirms: no tables (or RLS on with no anon policies); only Google enabled; Redirect URLs exactly `http://127.0.0.1:47217/auth/callback**`; asymmetric signing keys on and legacy keys off; `SUPABASE_JWT_SECRET` unset on Render | Michael | open |
| A19 | Engine | "Run it for me" runs a model-written shell command (`/bin/sh -c`) with one click, and the lesson text comes from someone else's video. A tutorial built to steer the model could get a harmful command into a step. Install names allow third-party Homebrew taps | `server/orchestrator/session.py:2401-2412, 7748-7778`; `server/workspace/setup.py:40, 396-399`; prompt-injection-to-action is how the [Hacktron Cluely chain](https://hacktron.ai/blog/hacking-cluely) started | **Applies** | P1 | Show the exact command before running it. Refuse or warn on pipe-to-shell, `sudo` and `rm -rf`. Allow brew names only from the catalog, never with `/` | Michael | open |
| A20 | Cloud | The cloud host is hard-coded as `miyagi-cloud.onrender.com`. Putting Cloudflare (rate rules, a WAF) in front later, or moving hosts, would need every user to update first | `main/features/cloud.ts:46` (`DEFAULT_CLOUD_URL`) | **Applies** | P1 | Before launch, switch the default to a domain we own (for example `api.miyagi.study`, CNAMEd to Render today) | Adrian (app), Michael (DNS, Render) | open |
| A21 | Engine data | Local engine data is readable and never cleaned up. `~/miyagi/engine/logs/engine.log` keeps the first 60 characters of every question and query, card titles, OCR'd code rows and up to 300 characters of failed payloads. It's append-only, never rotated and mode 0644 by default. The run recorder is on by default. Keys and tokens are **not** logged | `server/orchestrator/hub.py:31-63`; `main.py:922-930, 950`; `server/screen/reader.py:986`; `server/orchestrator/recorder.py:31-36`; `main/localEngine.ts:286, 493`; Clicky [#44](https://github.com/farzaa/clicky/issues/44) (logs held transcripts) | **Applies; file modes need a Mac check** (`ls -ld ~/miyagi ~/miyagi/engine/logs`) | P1 | `~/miyagi` 0700 and files 0600. Rotate the log and cut it to metadata. `ORCH_RECORD=0` in the shipped engine. Delete my data wipes these (A16) | Michael | open |
| A22 | Cloud | *Placeholder:* cloud admin configuration. Details sent to Michael privately | — | **Applies** (cloud) | P1 | In private notes | Michael | open |
| A23 | Cloud | *Placeholder:* cloud capacity under load (one starter instance). Details sent to Michael privately | — | **Applies** (cloud) | P1 | In private notes | Michael | open |

### Recommended limits for miyagi-cloud (starting values; tune from `/admin/usage` after day 1)

| What | Anonymous install | Signed-in learner (all their installs) | Whole service |
|---|---|---|---|
| Install tokens | 3 per IP per hour, 10 per IP per day (persisted, IPv6 by /64) | — | Alert at 500 mints/hour, stop at 2,000/hour |
| Requests | 10/min (burst 20), 2 concurrent streams, 100/day | 300/day | Global semaphore of about 80 open upstream calls |
| Spend | $0.25/day | $1.50/day, $15/month | `GLOBAL_DAILY_USD`: $100 at 1k users, $500 at 10k (or 2× measured day-1 spend); hourly cap = daily ÷ 6; at 80% Haiku only and no new builds; at 100% a runtime kill, no redeploy |
| Lesson builds | 3/month, counted on the server | Per plan | — |

Counts and dollars are kept on the server, never read from a client header. The provider limits in A10 sit underneath as the last stop.

## Notes and sources

### Verified leads from the brief

- **Clicky** (farzaa/clicky, open-sourced Apr 8, 2026). Three issues opened on launch day are all still open and unanswered: [#22](https://github.com/farzaa/clicky/issues/22) (an Anthropic key in `project.pbxproj` in the first commit; removed Apr 10 in `d86c32f`, whose message says to rotate it, and a commenter found it already revoked), [#34](https://github.com/farzaa/clicky/issues/34) (an open proxy for paid APIs, transcripts to PostHog, a fallback key in the bundle) and [#44](https://github.com/farzaa/clicky/issues/44) (logs held transcripts and part of a token). Confirmed in public code: the key, a Worker with no auth or rate limit that forwards the client body unchanged, and a "hide the proxy URL" commit (`6b8257e`). The PostHog payloads and the logging claims are reported, not checked. Lesson: in a public repo a hidden URL protects nothing, and the proxy has to own the model, `max_tokens` and the quota.
- **Cluely.** *Confirmed by the researcher:* Jack Cable showed links in AI answers opening inside the app, with internal postMessage handlers (one of them takes screenshots) callable by any page opened that way, and the sandbox off. He says it was fixed ([Critical Thinking ep. 136](https://criticalthinkingpodcast.io/episode-136-hacking-cluely-ai-prod-sec-and-how-to-not-get-sued-with-jack-cable/), Aug 21, 2025). A DMCA takedown of his tweet followed; he filed a counter-notice on Jul 8, 2025. *Separate chain:* [Hacktron](https://hacktron.ai/blog/hacking-cluely) (found Jul 2025, published Feb 14, 2026) chained no `will-navigate` guard, generic `send`/`invoke` in the preload and the sandbox off. A prompt injection makes the model print a link, and one click gives screen, mic and system-audio capture. It was patched silently. *Not verified:* the "~83k users breached through admin credentials in a public repo" story traces to an anonymous Medium post and isn't in HIBP or the security press. Treat it as a rumor.
- **Rabbit R1.** Rabbitude says it had access from May 16, 2024 and published on Jun 25. Rabbit's own timeline: notified Jun 25, forced rotation, device downtime Jun 26, more secrets found outside AWS Secrets Manager Jun 27, and an employee blamed Jul 5 ([rabbit.tech](https://rabbit.tech/security-investigation-062524)). 404 Media sent email from internal Rabbit addresses with the leaked keys ([Aug 1, 2024](https://www.404media.co/rabbit-says-breach-not-caused-by-a-breach-is-fault-of-malicious-employee-hacktivists-journalists/)). How much the leaked keys exposed is disputed. Lesson: practise a rotation with no downtime for every key, including the boring ones.

### More precedents

- **LLMjacking** (Sysdig): stolen cloud LLM credentials resold through reverse proxies. Over $46k a day in the worst case ([May 2024](https://sysdig.com/blog/llmjacking-stolen-cloud-credentials-used-in-new-ai-attack/)), over $100k a day with Opus ([Sep 2024](https://sysdig.com/blog/growing-dangers-of-llmjacking/)), 30 days of access sold for $30 ([Feb 2025](https://sysdig.com/blog/llmjacking-targets-deepseek/)). Microsoft sued the Storm-2139 group in [Feb 2025](https://blogs.microsoft.com/on-the-issues/2025/02/27/disrupting-cybercrime-abusing-gen-ai/). An anonymous token that costs nothing to mint is resale stock unless it's capped.
- **Local servers driven from a browser:** Zoom's hidden web server ([CVE-2019-13450](https://nvd.nist.gov/vuln/detail/CVE-2019-13450); Apple removed it from every Mac), Ollama DNS rebinding ([CVE-2024-28224](https://www.nccgroup.com/research/technical-advisory-ollama-dns-rebinding-attack-cve-2024-28224/)), Oligo's ["0.0.0.0 Day"](https://www.oligo.security/blog/0-0-0-0-day-exploiting-localhost-apis-from-the-browser) (Aug 2024), MCP Inspector ([CVE-2025-49596](https://nvd.nist.gov/vuln/detail/CVE-2025-49596), CVSS 9.4) and the Claude Code IDE extension WebSocket ([CVE-2025-52882](https://nvd.nist.gov/vuln/detail/CVE-2025-52882)). The standard fix is a random per-launch token, Origin and Host checks, and a loopback-only bind. Our engine has all three when the app starts it.
- **Browsers today:** Chrome's Local Network Access prompt covers fetch from public pages (Chrome 142) and WebSockets since Chrome 147 (Apr 7, 2026) ([Chrome blog](https://developer.chrome.com/blog/local-network-access), [147 release notes](https://developer.chrome.com/release-notes/147)). It doesn't gate localhost-to-localhost, though, and the user can click Allow. Firefox is rolling it out from 151 (not confirmed from a primary release note). Safari has no equivalent. So the engine's own checks are the guard, not the browser.
- **Electron bugs that became code execution:** Discord (contextIsolation off plus [CVE-2020-15174](https://mksben.l0.cm/2020/10/discord-desktop-rce.html), Oct 2020), Electron protocol handlers on Windows (CVE-2018-1000006), Signal Desktop HTML injection (CVE-2018-10994), and 1Password 8 weak IPC validation (CVE-2024-42219, Aug 2024).

### Electron attack surface (mapped to the [official checklist](https://www.electronjs.org/docs/latest/tutorial/security))

| # | Item | miyagi |
|---|---|---|
| 2, 3, 4 | No Node in renderers, context isolation, sandbox | Done for every window: `main/index.ts:153-160` (`sandbox: true`, `contextIsolation: true`). P2: `...options.webPreferences` is spread last, so one feature could override `sandbox` (Later) |
| 5 | Permission requests | All denied (`main/index.ts:113-124`); the mic only if `VOICE_ENABLED`, which is false |
| 7 | CSP | Sent as a header in built apps (`main/serve.ts:39-52`). `style-src 'unsafe-inline'` (P2) |
| 13, 14 | Navigation, new windows | `hardenContents` blocks off-origin `will-navigate`, main-frame `will-redirect` and `will-attach-webview`, and routes `window.open` to the browser (https only) (`main/index.ts:126-142, 377`). One player-window handler skips the link check (Later) |
| 15 | `openExternal` with untrusted content | Through the `safeOpen.ts` allowlist everywhere except the player's own handler (Later) |
| 17 | IPC sender validation | Every `ipcMain` handler checks `trustedSender`: our window's main frame on our own origin (`main/index.ts:84-90`). Renderers can't send `config.keys` (`:410-416`) |
| 20 | Electron APIs to web content | The preload exposes generic `invoke`/`onFeature`, but only under the `feat:` prefix, and each handler checks the sender. Callbacks get payloads, never the event. See A14 for the one third-party script |
| — | Deep links | None: no `setAsDefaultProtocolClient`, `open-url` or `protocol.handle`. OAuth uses a loopback redirect on `127.0.0.1:47217` with PKCE (S256), a 24-byte state compared in constant time, one use, a 5-minute timeout and a CSP'd callback page (`main/features/auth.ts:96-101, 180-189, 429-505`) |
| 16 | Current Electron | 45.3.2 (`app/package.json`) |
| 19 | Fuses | Not set. Turn off `runAsNode`, `nodeCliInspect` and `nodeOptions`, and turn on `onlyLoadAppFromAsar` and ASAR integrity, at signing time (area C) |

### Checked and fine

- Tokens at rest: `auth.bin`, `install.bin` and `keys.bin` use safeStorage, written temp-then-rename with mode 0600. With no encryption available they stay in memory only, never in plaintext. Linux `basic_text` is refused.
- Renderers never see a token or key: auth sends only `{name, email, avatarInitial}`, and cloud status has no token.
- No token reaches a log. Crash reports stay on the Mac, are opt-in, and are scrubbed of emails, `mi_` tokens, Bearer values and home paths.
- The cloud forwards no client headers except a validated `anthropic-version`/`anthropic-beta`, allowlists response headers, redacts our keys from error bodies, uses fixed upstream URLs with `follow_redirects=False`, caps body size on both `Content-Length` and the streamed bytes, refuses any `Origin` on `/v1` (no browser use), and stores only token hashes. Admin uses `hmac.compare_digest`, never puts the token in a URL, and turns the access log off.
- The JWT check in `cloud/supabase_auth.py` pins the algorithm per path, requires aud, iss, exp and sub, caches JWKS with backoff, and has tests (`cloud/tests/test_link.py`).
- The engine as the app starts it: loopback bind, a fresh 32-byte token (passed in the env, popped from `os.environ`, compared in constant time), Host check (DNS rebinding), cross-origin POSTs refused, JSON bodies only, no CORS headers. The install token is never exported to the environment.
- `learn_url` accepts YouTube only (it rebuilds the watch URL), `open_in_browser` opens https only, pip and brew run as argv lists, and zip extraction skips symlinks and `..`. There are no telemetry SDKs, and OCR drops password managers and Messages and redacts emails, SSNs, phone and card numbers (`server/screen/privacy.py`).
- The companion binds 127.0.0.1, refuses any browser request (Origin, `Sec-Fetch-Site`, Host, JSON-only), and disposes its server and timers on deactivate.

## Incident response

### First hour after a leaked key or a reported hole (two people)

1. **T+0.** One person drives, the other keeps timestamped notes. Work in a private channel, never in a public issue.
2. **Stop the money.** Disable the leaked key in its console. If you're not sure which key it was, drop the Anthropic workspace limit and the Gemini project cap close to current spend.
3. **Rotate.** Create the new key, set it in Render ("Save, rebuild and deploy"), smoke-test through the proxy, then delete the old one. If it's being abused right now, delete first and accept the downtime.
4. **If the proxy is the hole rather than a key:** hit the kill switch or suspend the Render service. Invalidate the anonymous tokens, then check that the app re-mints cleanly.
5. **Supabase:** if a secret or service_role key leaked, rotate it and turn off the legacy keys. Read the Auth and API logs, and recheck RLS.
6. **Treat neighbours as burned.** Rotate whatever sat next to the leak: Render env values, deploy hooks, GitHub tokens.
7. **Measure the window.** It runs from the commit or release time to revocation. Pull usage per key from the Anthropic and Google consoles, and per token and IP from the proxy.
8. **Clean the source only after rotating.** Mark the secret-scanning alert revoked. Rewriting history is optional, and cached PR refs need GitHub Support.
9. **Shipped builds:** if the secret was in a release, ship a build without it, and make sure old builds fail politely.
10. **User data:** if screenshots, code or accounts could have been read, write down what, whose and when. Decide on notifying users (area B), and post a short, honest note.
11. **Billing:** open tickets with Anthropic and Google with request IDs and the timeline.
12. **Within 24 hours:** a blameless write-up, a new guardrail, and thanks to whoever reported it. No legal threats against good-faith researchers (the Cluely lesson).

Sources: [GitHub: removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository), [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [Anthropic: API key best practices](https://support.claude.com/en/articles/9767949). Anthropic is a GitHub secret-scanning partner, so a leaked Anthropic key in a public repo is usually deactivated automatically, with an email to the owner ([GitHub changelog, Aug 20, 2024](https://github.blog/changelog/2024-08-20-anthropic-is-now-a-github-secret-scanning-partner/)). Google `AIza` keys are alerted on but not blocked.

### security.txt draft (`miyagi.study/.well-known/security.txt`)

```
Contact: mailto:<security contact, to be decided>
Contact: https://github.com/michae6345-crypto/miyagi/security/advisories/new
Expires: 2027-11-01T00:00:00.000Z
Preferred-Languages: en
Policy: https://github.com/michae6345-crypto/miyagi/security/policy
```

The second Contact line and the Policy link work only once private vulnerability reporting and SECURITY.md exist. SECURITY.md should cover scope (the app, engine, companion, miyagi-cloud, miyagi.study), a promise of no legal action for good-faith research, what not to do (no DoS, no spending through the proxy, no other people's data), how to report, and that we answer within 3 business days ([CISA template](https://www.cisa.gov/vulnerability-disclosure-policy-template)).

## Needs Michael's consoles (today if possible)

1. **Anthropic:** which tier and monthly cap? Is an org spend limit set? Does the proxy key have its own workspace with limits? What has it spent since the proxy went live, and did anything spike? (A01, A10)
2. **Google:** which tier? Is a project spend cap set? Are budget alerts on? Is the key restricted to the Generative Language API? (A10)
3. **Render:** which commit is deployed (and is auto-deploy on)? The real values of the model allowlists and size caps, and the settings listed under A07 and A22 in the private notes. Is `SUPABASE_JWT_SECRET` set? Are PR previews off? Who can read env vars? (A07, A11, A18, A22)
4. **Supabase:** any tables in exposed schemas, and is RLS on? Which providers are enabled (email, anonymous)? Redirect URLs? Signing keys? (A18)
5. **GitHub (repo admin):** are secret scanning, push protection and private vulnerability reporting on? (A09, A17)

## Launch checklist (area A)

- [ ] Provider backstops set: Anthropic workspace and org spend limits, Gemini project cap, budget alerts (A10).
- [ ] miyagi-cloud enforces per-token, per-user and global limits, persisted, with a runtime kill switch and alerts (A01, A11, the limits table).
- [ ] Proxy request shapes are allowlisted (A02).
- [ ] Mint IP derivation verified on Render, or Cloudflare in front (A07), and the app's default cloud URL is on our own domain (A20).
- [ ] The lesson cache doesn't merge until A08 is fixed.
- [ ] A03 to A06 and A12 fixed and checked against the private notes (the companion fix ships as 0.0.7 through integration/live).
- [ ] Release assets are scanned with gitleaks before upload; secret scanning and push protection confirmed on; gitleaks runs in CI (A09).
- [ ] Update installer URL pinned to the release repo, with releases signed and verified (A13).
- [ ] security.txt, SECURITY.md, private vulnerability reporting and one security contact live; the runbook rehearsed once, including a rotation with no downtime (A17).
- [ ] Supabase console checked (A18).
- [ ] Mac checks done: capture stops when the app is killed (A15), `~/miyagi` file modes (A21), and the checks listed in Michael's private notes.

## Handed to other areas

- Delete my data: legal promises and wording go to area B and #199 (A16 keeps the security side).
- The Privacy page says screenshots go "to the AI provider". Every call actually goes through miyagi's own proxy first (`main/features/cloud.ts:2-3, 46`; `Privacy.tsx:65-66`). Wording goes to area B.
- Google OAuth Testing mode blocks sign-in for anyone not on the test list: area C.
- The renderer origin changes every launch, so localStorage resets: area E (E01).
- Lessons whose titles contain a path vanish from Library (`renderer/src/features/library/sanitize.ts:207-212`): area E.
- The install-token mint and `/v1/link` don't retry while offline until a relaunch (`main/features/cloud.ts:257-259`, `cloudLink.ts:138`): area C or E.

## Later (small, one line each)

- `main/index.ts:153-160`: put the security flags after `...options.webPreferences` so no feature can override `sandbox`.
- `main/features/player.ts:90-93`: its window-open handler calls `shell.openExternal` on any https URL, skipping `isBrowserLink`.
- `main/index.ts:74`: in the `file://` fallback, any `file:` URL counts as our own origin.
- `main/safeOpen.ts:25` still allows `elevenlabs.io` (no ElevenLabs option exists any more).
- `main/localEngine.ts:69`: the copied "install the engine" `curl | bash` points at a mutable branch where the script doesn't exist.
- Windows: no app menu, so Electron's default menu (and probably DevTools on Ctrl+Shift+I) is reachable in focusable windows (inferred).
- `main/features/auth.ts:56`: a fixed loopback port (47217); if something else holds it, sign-in fails with no fallback.
- `main/features/auth.ts:352-355`: any 400 or 401 on refresh signs the learner out, including one about a rotated API key.
- `main/features/auth.ts:479`: signing in as someone else doesn't revoke the old session.
- Sign-in window closed mid-wait doesn't cancel the loopback listener (5-minute timeout still applies).
- `cloud/app.py:161-162, 198`: every log line carries the Supabase user id, and the tokens, links and usage tables are never pruned (privacy page should say so; area B).
- Three more small cloud items are in the private notes.
- `server/workspace/resources.py:100-105`: downloads follow redirects with no host recheck (GET only, on a press).
- `vscode-ext`: the Output channel logs the full text of commands the engine runs and saved file paths.

### Small bugs from the earlier bug-hunt pass (not security; parked until miyagi is live)

- `main/prefs.ts:45`, `main/features/reminders.ts:72`: written in place, not temp-then-rename; a full disk or a crash mid-write resets prefs and turns launch at login off.
- The single-instance lock is taken inside features that load after auth, cloud and the windows (`main/features/launch.ts:76`, `windows.ts:78`); dev runs share userData with the installed app (`main/identity.ts:21`).
- Windows: Alt+F4 closes the launcher or player for good, and `display-metrics-changed` then throws on the destroyed window (`main/index.ts:491-496`).
- The ⌥Space launcher key often belongs to Alfred, Raycast or ChatGPT; registration fails with only a log line (`main/index.ts:481-482`), and `prefs.shortcuts` is never applied.
- Alt+Q quits instantly on Windows (`main/index.ts:488-489`).
- Lesson shortcut keys stay registered when the engine drops without `lesson.ended` (`main/index.ts:402-406`).
- The app stays on "external" once set, and there's no automatic restart after an engine crash (`main/localEngine.ts:651, 670, 685-688`).
- One listener or `onOpen` hook that throws stops the fan-out to the rest (`main/engine.ts:242, 298`); the `whenReady` chain has no catch (`main/index.ts:379`).
- `main/features/recover.ts:32-35` stops reloading a crashed renderer after 3 tries a minute and never tries again.
- Displays: `pillTop` is set once (`main/index.ts:393`); there are no `display-added`/`display-removed` handlers, and the player isn't re-docked.
- `main/features/overlay-raise.ts:132`: a 15 ms cursor poll runs for the app's whole life.
- The in-memory engine event log grows for the whole lesson and is replayed into every window on `ui:ready` (`main/engine.ts:297`, `main/index.ts:441`).
- Auth: a stale or late sign-in tab gets a blank 404 (`main/features/auth.ts:447-449`); `access_denied` always reads "account isn't allowed", including a plain Cancel (`:156`); token expiry uses the Mac's clock (`:124`, `cloudLink.ts:117`); reopening the login window clears "Waiting" mid-flow (`renderer/src/features/auth/AuthView.tsx:37`, `store.ts:63-64`).
- Settings: other windows keep showing old key state after Delete or Save (no broadcast, `main/features/settings.ts:168-187`); `tips` prefs are dropped by `sanitizePrefs` (`renderer/src/features/tips/store.ts:64`).
- Truncation can split an emoji in titles and names (`renderer/src/features/library/sanitize.ts:213`, `main/features/auth.ts:104`).
- Companion: notebook cells report the wrong active file, notebook saves send no events, Run it for me types into a busy terminal, "Do it for me" can overwrite keystrokes typed in between, and only Visual Studio Code.app is found (not Insiders, Cursor or VSCodium).
