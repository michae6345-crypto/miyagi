# miyagi launch risks: the solutions plan

The fix for every risk in [`RISKS.md`](RISKS.md), grouped into work streams and put in order. Each fix has concrete
steps, an owner, an effort, what it depends on, and how we check it's done. Where the founders have to choose, the
options and a recommendation come first.

- Effort: **S** under an hour, **M** under a day, **L** several days.
- Owners: Adrian (app, companion, site), Michael (engine, cloud, consoles). Engine and cloud steps are plans for
  Michael, not patches. "Parent" means the adult who holds the accounts (R11).
- ★ marks the **critical path**: everything that has to be true before we post publicly.
- *Placeholder* rows point to Michael's private notes for the parts that would show how to exploit them.
- Not legal advice.

## The plan on one page

### Critical path to posting publicly

Three chains set the launch date. Every ★ item below sits on one of them.

1. **Michael's engine and cloud queue (the long pole).** R02 today → R01 (L) and R07 (M) → R05 (L) → the launch
   build → R06 Test 1 on clean Macs (M). That's two L items in a row. Adrian can shorten it by taking the app-side
   pieces: R08's companion fix, R25's app copy, R10's release script and update-card wiring.
2. **Decisions → legal pages.** D1 (Gemini) and D2 (who runs miyagi) today → R04's policy and terms, with R23's
   deletion wording and R19's age text → R03's consent screen links to them → a lawyer reads them → live.
3. **Accounts.** R11's parent conversation today. It's on the path for R04 (who the operator is) and R02 (whose
   card). It's also on the path for signing (R15) only if the founders pick a signed launch (D7).

On launch morning: R33 (the code gate comes off), R13 (no Windows button), R38 (posting account checked, post written
by hand) and R22 (the name decision is made).

### Lanes

| Lane | Owner | Risks | P0s |
|---|---|---|---|
| 1. Money and cloud | Michael | R01, R02, R07, R12, R16, R20, R25 (engine), R30 (cloud) | 4 |
| 2. Consent, policy and legal | Adrian, Michael, parents, lawyer | R03, R04, R09, R11, R17, R19, R21, R22, R23, R35, R36, R43 | 4 |
| 3. Release and install | Adrian, Michael's Mac, a parent | R06, R10, R13, R15, R32, R34 | 2 |
| 4. Grading and lessons | Michael | R05, R14 (engine), R24 (engine), R26 (engine), R27 | 1 |
| 5. App shell | Adrian | R14 (app), R18 (app), R24 (app), R25 (app), R26 (app), R42 | 0 |
| 6. Local security | Michael, Adrian (mostly private) | R08, R28, R39, R40, R41 | 1 |
| 7. Site, support and launch | Adrian, both founders | R29, R30 (app), R31, R33, R37, R38, R44 | 0 |

### Today (console steps, no code)

| ★ | What | R | Owner | Effort |
|---|---|---|---|---|
| ★ | Anthropic: the proxy key in its own workspace with a monthly spend limit, an org limit below the tier cap, alerts to both founders, auto-reload off. Gemini: paid tier confirmed, project spend cap, budget alerts, key restricted | R02 | Michael | S |
| ★ | Read the live `MAX_TOKENS_CAP` and `ALLOWED_GEMINI_MODELS` on Render; grep an engine log that built through the cloud for `hit max_tokens` | R07 | Michael | S |
| ★ | Talk to parents: who enrolls with Apple and holds billing for Anthropic, Google Cloud, Render, Supabase and Porkbun | R11 | Founders | S |
| ★ | Make D1 (Gemini) and D2 (who signs) at least; the other decisions this week | Decisions | Founders | S |
| | If D1 is "Claude only": remove Gemini from the proxy on Render | R09 | Michael | S |
| | Release immutability on, a passkey for 2FA, a single-repo publishing token, windows-sync `publishNext` false | R10 | Adrian | S |
| | `windows` release body says lessons need a Mac | R13 | Adrian | S |
| | Render: Starter or larger with the disk attached, auto-deploy off for launch week, a second person with access. Anthropic: read the tier and ask for Build or Scale | R16, R34 | Michael | S |
| | Google Auth Platform: scopes, a sign-in test with an unlisted account, Branding, Publish. Supabase: plan, providers, redirect URLs, RLS, signing keys | R18 | Michael | S |
| | Email forwarding (support@, security@, privacy@, copyright@), SPF and DMARC; private vulnerability reporting on both repos | R29 | Adrian, Michael | S |
| | UptimeRobot on `/healthz`, the site and the release asset; status subscriptions | R30 | Michael | S |
| | Verify miyagi.study on GitHub Pages; Porkbun 2FA, auto-renew, a parent's card | R34 | Adrian | S |
| | Both founders open `news.ycombinator.com/showlim` logged in | R38 | Founders | S |
| | Confirm secret scanning and push protection on the team repo | R41 | Michael | S |

### Before private beta (the outreach list installs)

| ★ | What | R | Owner | Effort |
|---|---|---|---|---|
| ★ | Server-side caps, runtime kill switch, alerts | R01 | Michael | L |
| ★ | Consent screen before the Screen Recording prompt, "AI, can be wrong", providers named | R03 | Adrian, Michael | M |
| ★ | `/privacy` and `/terms` live, app links fixed, "I agree" step | R04 | Adrian, Michael | M |
| ★ | Grading: E15 (newest output only) and E17 (coach can say "your code works"), and the beta's curated lessons pass the repros | R05 | Michael | L |
| ★ | Test 1 R0 on clean macOS 15 and 26 VMs with the beta build; public releases swapped to a versioned v2 build | R06 | Michael, Adrian | M |
| ★ | Token cap per route; allowlist matches D1 | R07 | Michael | M |
| ★ | Companion 0.0.7 and the engine key fix (or own-key fields hidden) | R08 | Adrian, Michael | M |
| ★ | D1 implemented in engine, cloud and Settings | R09 | Michael, Adrian | S |
| ★ | Install-limit IP check on staging, limit raised, plain copy | R12 | Michael, Adrian | M |
| ★ | Versioned releases, one publisher, update card with a pinned installer URL | R10 | Adrian, Michael | M |
| | Windows button off the site | R13 | Adrian | S |
| | "Start again" label on recent rows; hero lesson folder out of the engine tree | R14 | Adrian | S |
| | Karate Kid cues gone (code "waxon", "wax on, wax off") | R22 | Adrian | S |
| | Delete my data says what it really deletes | R23 | Adrian | S |
| | `MIYAGI_NET_PROBE` set to the cloud host | R26 | Adrian | S |
| | Delete `/live/` from the site | R37 | Adrian | S |
| | `ORCH_RECORD=0` in the shipped engine | R40 | Adrian, Michael | S |
| | A06's fix before any demo on venue Wi-Fi | R28 | Michael | S |

### Before public launch

| ★ | What | R | Owner | Effort |
|---|---|---|---|---|
| ★ | The rest of the grading false fails (E14, E16, E20, E24, E25) | R05 | Michael | L |
| ★ | Signed update manifest on miyagi.study, minimum-version answer from the cloud, upload freeze | R10 | Adrian, Michael | M |
| ★ | Full Test 1 (all variants) on macOS 15, 26 and 27 with the launch build | R06 | Michael | M |
| ★ | Accounts held by an adult; lawyer consult held; lawyer read of the policy and terms | R11, R04 | Founders, parents | M |
| ★ | Name decision made | R22 | Founders | S |
| ★ | Code gate off on launch morning; Windows off; posting account checked, post written by hand | R33, R13, R38 | Adrian, founders | S |
| | Signed and notarized build (D7), or the first-launch capture check if unsigned | R15 | Parent, Michael, Adrian | L |
| | Capacity: tier raised, pool limits, load test, lighter scene looks | R16 | Michael | M |
| | Capture: private apps excluded on every path, secret scrubbing | R17 | Michael | L |
| | Sign-in: copy, button, branding, school-account hint | R18 | Michael, Adrian | M |
| | Age gate and minors safeguards | R19 | Michael, Adrian | M |
| | Cache not merged; "Run it for me" shows and screens the command | R20 | Michael | M |
| | D4 (transcripts) implemented | R21 | Michael | S |
| | Server delete, full app erase, unlink on sign-out | R23 | Michael, Adrian | M |
| | Watchdogs and build deadline | R24 | Adrian, Michael | M |
| | Plain errors and mint retry | R25 | Adrian, Michael | M |
| | First-run fixes | R26 | Adrian, Michael | L |
| | Judge can't overrule a failing check (E18) | R27 | Michael | S |
| | Hardening (private), player isolation, Electron bump | R28 | Michael, Adrian | M |
| | security.txt, SECURITY.md, issue form, `/help`, runbook | R29 | Adrian, both | M |
| | Counters, crash path, funnel counts | R30 | Michael, Adrian | M |
| | Copy rewrite, one-take video | R31 | Adrian, both | M |
| | Permission re-ask card, 27.3 copy | R32 | Adrian, Michael | M |
| | Region decision implemented | R35 | Michael | M |
| | Creator content out of the repo, DMCA agent | R36 | Michael, Adrian | M |
| | Site first screen, phone view, click-to-load embed, SRI | R37 | Adrian | M |
| | Engine exits with the app; Mac check of B09 | R39 | Michael, Adrian | M |
| | Log rotation, file modes, scrubbed Copy details | R40 | Michael, Adrian | S |
| | gitleaks in CI, build-time key check, release scans | R41 | Adrian | S |
| | Port 8787 message and Retry | R42 | Adrian | M |

### After launch

Entity formed and accounts moved to it (R11). Auto-update once signed (R15). Capture only the editor and tutorial
windows (R17). The remaining false passes (R27). Creator-authorized captions as the long-term lesson source (R21).
EU and UK, if chosen (R35). Licenses and notices (R43). Site polish (R44). The Windows lane (R13). Everything in
[`later.md`](later.md).

## Solutions by risk

### R01
**Anyone can use miyagi-cloud as free AI.** ★ · Michael · L · Before private beta
1. A persisted limiter in SQLite (survives restarts and redeploys), IPv6 bucketed by /64.
2. `check_quota` enforces per-install, per-user (all installs of a linked account) and global caps, counted on the
   server from the usage table, never from a client header. Starting values from `security.md`:

   | What | Anonymous install | Signed-in learner | Whole service |
   |---|---|---|---|
   | Install tokens | 3 per IP per hour, 10 per day | — | alert at 500 mints an hour, stop at 2,000 |
   | Requests | 10 a minute (burst 20), 2 concurrent streams, 100 a day | 300 a day | about 80 open upstream calls |
   | Spend | $0.25 a day | $1.50 a day, $15 a month | `GLOBAL_DAILY_USD` $100 at launch (or 2× measured day-1); hourly cap = daily ÷ 6; at 80% Haiku only and no new builds; at 100% the kill switch |
   | Lesson builds | 3 a month | per plan | — |

   R12 asks for a higher per-IP install limit for classrooms; with per-token spend caps in place that's safe.
3. Apply the A02 and A22 fixes from the private notes.
4. A runtime kill flag in SQLite behind an admin POST, so stopping traffic needs no redeploy. Disable tokens by
   creation-time range.
5. Alerts: a Discord or Slack webhook at 50, 80 and 100% of the cap, for one token over $2 a day and for more than
   500 mints an hour. A daily cron outside the service (Render cron or a GitHub Actions schedule with the admin token
   as a secret) reads `/admin/usage`, fails loudly when spend passes the alert line, and pings Healthchecks.io so a
   silent cron is noticed.
6. `/healthz` reports the deployed commit, plus `keys_configured` and `db_ok` booleans (no values).
7. App (Adrian): show "miyagi is paused" for the 400 a self-set provider limit returns (part of R25).
8. Trim `cloud/README.md`'s SDK how-to once step 3 lands.
- **Depends on:** nothing. R02 goes first as the backstop.
- **Verify:** on a staging service, a script past each cap gets a 429 with the right reason; the kill flag stops
  proxied calls within a minute without a redeploy; each alert reaches both founders' phones; a unit test per cap.
- **Decision:** the dollar line where the kill switch trips and the status text users see (D13).

### R02
**No provider-side spend caps or alerts.** ★ · Michael · S · Today
1. Anthropic Console: move the proxy's key to its own workspace (Default can't have limits); a workspace monthly
   spend limit (about $100 for the private beta, raised on purpose for launch) and ITPM and OTPM limits; an org
   limit below the tier cap; email alerts at about $10, $25 and $40 to both founders; auto-reload off, so the credit
   balance is a hard stop.
2. Google, only if D1 keeps Gemini: confirm the project behind `GEMINI_API_KEY` is on a paid tier; prepay $10-20 with
   auto-reload off; AI Studio project spend cap about $20-50 a month; a billing account that holds only miyagi; Cloud
   budget alerts at 50, 90 and 100%; restrict the key to the Generative Language API; AI Studio logging off or 7 days.
   If D1 is "Claude only", unset the key on Render instead.
3. Set `PRICES_JSON` on Render with the real Gemini prices now and again on Jan 1, 2027, price Haiku 5.5 in two
   tiers (prompts over 100k cost 5×), and count web-search fees (C27).
4. Subscribe both founders to status.claude.com and Google AI Studio status.
- **Depends on:** whose card pays (R11), but don't wait for it.
- **Verify:** a screenshot of each limit page goes in the private notes folder; with a deliberately tiny test
  workspace limit, a call returns 400 and the app says "paused".

### R03
**No consent before capture, no AI disclosure.** ★ · Adrian, Michael · M · Before private beta
1. App onboarding: one screen before the macOS Screen Recording prompt (`app/src/renderer/src/features/onboarding/steps.ts`,
   copy at `:23-24`, and the guided flow). Draft, facts to confirm with Michael: "During a lesson, miyagi looks at
   your screen every few seconds and reads your code. It sends what it needs to Anthropic (Claude) through miyagi's
   server to build and check your steps. We don't keep your screenshots." A link to `/privacy`, and a button whose
   text matches the sentence.
2. One persistent line in onboarding and the lesson panel: "miyagi's coach is AI. It can be wrong."
3. Settings > Privacy (`settings/sections/Privacy.tsx:65-66`): name Anthropic (and Google if D1 keeps Gemini), and say
   every call goes through miyagi's server. Land #199's `facts.ts` rows as listed in `privacy-review.md` (editor "To
   Anthropic", code and files you ask about, a YouTube row, an account-link row, questions you type), with the panel,
   policy and `facts.test.ts` moving together.
4. A pause control on the overlay that stops capture (engine: Michael).
5. Site: replace "miyagi runs on your computer." (`index.html:605`) and add the data line by the downloads from
   `launch.md` section 6, with a privacy link.
- **Depends on:** R04 (the link target), D1 (which providers to name).
- **Verify:** on a clean install the consent screen appears before the system prompt (Test 1 screenshots);
  `facts.test.ts` passes; the site no longer says "runs on your computer".

### R04
**No live privacy policy or terms.** ★ · Adrian, Michael · M · Before private beta (lawyer read before public launch)
1. Finish the policy from #199 with #201's edits, fixing the five points in `privacy-review.md`: the account link,
   the full scope of what goes to Anthropic, the YouTube player (name "YouTube API Services" and link Google's Privacy
   Policy), honest retention (say what is kept and that server deletion is coming, R23), and age text that matches
   R19.
2. Publish `/privacy` (it includes the site section from `cookies.md`) and `/terms` (`web/terms.md`). Footer: privacy ·
   terms · help · support · security.
3. App: point or remove the `/pricing`, `/teams` and `/account` links (`app/src/main/features/account.ts:22-27`).
4. A first-run "I agree" step, also on "Continue without an account", with the button text matching the sentence
   above it; store the policy version and time (locally now, on the cloud once R23 lands). The terms ask a parent or
   guardian to accept for under-18s.
5. Name who runs miyagi and a contact (R11, privacy@ from R29).
6. Add a release step: re-check the policy against the release commit (`facts.ts`, engine, cloud) before every release.
7. A lawyer reads the final text before public launch.
- **Depends on:** D1, D2, R23's wording, R19's age text, D9 (regions).
- **Verify:** `/privacy` and `/terms` return 200; a script that greps `app/src` for `miyagi.study/` links finds none
  that 404; the "I agree" record exists after a fresh install.

### R05
**Correct work marked wrong.** ★ · Michael · L · E15 and E17 before private beta, the rest before public launch
1. E15: grade "No errors" on the terminal rows after the last run of the step's command (`terminal_runs` already finds
   that row), never on editor text, and skip patterns the step's expected output contains (`server/checks/evaluator.py:534-549`).
2. E17: add a "looks correct" outcome to the coach (`server/coach/diagnose.py:48-102`, `server/coach/triage.py:43-119`).
   When it, or a run of the code, says the learner's version works, pass the row ("matches the tutorial's result")
   and log the check for repair.
3. E14: build run checks from the output's shape (`You rolled: \d+`), never from values that depend on input,
   randomness or time; or run the reference code twice at build time and drop exact-line checks when the runs differ
   (`server/lesson/textlesson.py:703-721, 782-791`).
4. E16: check names and shape, not literals; skip string literals in the code gate; accept positional arguments for
   keyword ones; decide a function body by running it on a sample input or by AST equivalence
   (`server/lesson/coverage.py`, `server/orchestrator/code_gate.py`).
5. E20: accept a run seen in any terminal app's OCR, and `./x.py`, `-m` and `uv run`; otherwise say "VS Code's
   terminal" in the row (`server/orchestrator/session.py:6892-6915`, `terminal_run.py:86-116`).
6. E24: cut the source text before escaping it, then re-lint (`server/lesson/builder.py:1249-1264`, as
   `textlesson.py:513-519` already does).
7. E25: when the judge times out, say "Couldn't double-check this one. Check again?" instead of "Not yet"
   (`server/coach/judge.py:142-149`, `session.py:6540-6551`).
8. Tests for each case in `server/checks/tests/`: stale scrollback, intended "Error:" output, random and `input()`
   output, own names, call versus def, a Terminal.app run.
- **Depends on:** nothing.
- **Verify:** Mac repros R-E14, R-E15a, R-E15b, R-E16 and R-E20 go green on a curated lesson; a deliberate real
  mistake is still caught (the control); the new tests pass.

### R06
**Launch build never installed on a clean Mac.** ★ · Michael, Adrian · M · Before private beta (full run before public launch)
1. Build the candidate from pinned SHAs (R10) and publish it as a draft `vX.Y.Z` with a `.dmg` and SHA-256s.
2. Scan both files with gitleaks and on VirusTotal (a bundled Python engine can trip antivirus) (R41).
3. Run Test 1 from `product.md` on clean macOS 15, 26 and 27 VMs (UTM or Tart), as admin and as a Standard user, in
   Safari and Chrome. Record every Gatekeeper dialog, any second dialog naming `python3` or a `.so` (E38), and
   `codesign --verify --deep` on the downloaded app.
4. Rewrite SHIP.md's first-open and test steps for the cloud path, and template the release body: version, what's
   new, the four Open Anyway steps, no right-click > Open, ⌃⌥Q (C39).
5. Make the site's tip, #188 and the canned "Mac won't open" reply match what Test 1 showed.
6. Only then point the site at the new release and set `macVerified: true`.
- **Depends on:** R10 (versioned releases); R05, R07 and R08 in the build.
- **Verify:** Test 1's pass line: a passed calculator step with no Terminal, no key and no developer-tools dialog, at
  most two password prompts, under 5 minutes from first launch to all-green setup.

### R07
**Cloud lesson builds may fail.** ★ · Michael · S to check, M to fix · Today, then before private beta
1. Today: on any Mac that has built through the cloud, `grep -n "hit max_tokens\|claude call: model" ~/miyagi/engine/logs/engine.log`,
   and note the largest `out=`. Read the live `MAX_TOKENS_CAP` and `ALLOWED_GEMINI_MODELS` on Render (they may differ
   from `render.yaml`) and the out-token column on `/admin`.
2. Build one video and one text lesson through a local proxy at 4096, then at 32000 (area C repro 4).
3. Fix: a per-route cap in the proxy (the lesson-build role gets what the builder needs; coach roles stay small),
   which is safe once R01 caps spend per token. Or lower the builder's asks with thinking budgets that fit, and split
   long transcripts.
4. Allowlist to match D1. If Gemini stays: add `gemini-4-hydrogen` and set the fallbacks to 3.8-flash and 3.6-flash
   (3.5 and 3.7 flash are retired). If D1 is "Claude only": make cloud mode skip Gemini cleanly, with no 404 round trips.
5. Add a cloud build to `evals/lesson/report.md`.
- **Depends on:** D1 (step 4), R01 (safe higher caps).
- **Verify:** a 20-minute tutorial builds through production miyagi-cloud with no key in Settings, and the log has no
  `hit max_tokens`.

### R08
***Placeholder:* companion configuration and engine key handling.** ★ · Adrian, Michael · S + M · Before private beta
1. A03: the fix in the private notes, with its unit test, shipped as companion 0.0.7 through `integration/live`
   (`bundle-engine.mjs` packs `vscode-ext` from there). Adrian.
2. A04: the engine change in the private notes. Michael.
3. Until A04 ships, hide every own-key field in the launch build, ElevenLabs included (Settings UI;
   `app/src/renderer/src/features/settings/keys.ts`). Adrian.
- **Depends on:** nothing.
- **Verify:** the checks in the private notes; the launch build reports companion 0.0.7.

### R09
**Gemini terms vs teens and teen account holders.** ★ · Founders decide, Michael · S · Before private beta

| Option | For | Against |
|---|---|---|
| **(a) Claude only for everyone at launch; keep 13+** (recommended) | Removes the breach; the engine already falls back to Claude; simplest | Video lessons are built from transcripts (R21), and R07's cap fix becomes essential |
| (b) 13+, with Gemini only for verified 18+ users | Keeps video watching for adults | The terms bar an app "likely to be accessed by" under-18s, so per-user routing may not cure it; needs a working gate and age on the token |
| (c) 18+ only, Gemini on | Clean under Gemini's terms | Drops the student audience and the founders' peers; the account holder must still be an adult (R11) |
| (d) Vertex AI under Google Cloud terms held by an adult or entity | May allow teens | Minors clause unconfirmed; needs a lawyer read, a new account and engine work |

Steps for (a): remove Gemini from the proxy on Render (Michael, console); make cloud mode skip Gemini (Michael, part of
R07); hide the Gemini own-key field (Adrian, part of R08); the policy says lessons are built with Claude (R04).
Revisit (d) once R11's entity exists.
- **Verify:** Render's env has no Gemini model; `/admin/usage` shows no Gemini calls; a video lesson builds from
  its transcript.

### R10
**No fix path to installs; one account controls releases.** ★ · Adrian, Michael · M · Before public launch (versioned releases before private beta)
1. Today (console): release immutability on `adrian-erlikhman/miyagi`; a passkey for the account's 2FA; publish
   with a fine-grained single-repo token and revoke broader tokens on the laptop; windows-sync `publishNext` false
   until the launch build.
2. Versions: bump `app/package.json` on every build; pin the engine to a SHA (`MIYAGI_ENGINE_REF`), lock Python
   packages with hashes, and write both into the release body and About (C18).
3. One publisher: `ship-mac.sh` creates a draft `vX.Y.Z`, uploads every asset (`.dmg` and `.zip`), then publishes.
   Never delete a published asset; keep stable asset names; the site links to `releases/latest/download/<name>`;
   CI stops uploading its zip to the same release (`.github/workflows/ci.yml:39-40`) (C16).
4. Ship #189's update card in the launch build. The parser keeps only `state === 'uploaded'` assets, and the
   installer URL is pinned to `https://github.com/adrian-erlikhman/miyagi/releases/download/` (`app/src/main/features/updates.ts:133-135`,
   `app/src/main/safeOpen.ts:26`) (A13).
5. Before public launch: a signed `https://miyagi.study/update/latest.json` (Ed25519 key kept off GitHub, public key
   built into the app) with version, URL, sha256 and `minimumVersion`. The app checks the signature before offering;
   the GitHub API is only a fallback (C01, C17).
6. A floor in the cloud: the app sends its version on `/v1/install` and every proxied call, the cloud answers 426
   below a floor, and the app shows "Update miyagi" with the download link (C19, D40).
7. Freeze uploads from day -1 to day +3; after that, at most one versioned hotfix a day (D31). Never rename or move
   the release repo, or change the GitHub username, after the launch build ships, unless step 5 is live.
- **Depends on:** R34 (domain verified before the manifest lives on miyagi.study).
- **Verify:** install vN, publish vN+1: the card offers it on relaunch; a manifest with a bad signature is refused;
  a build below the floor shows "Update miyagi"; vN is still in the release history.

### R11
**Founders are minors; accounts need an adult.** ★ · Founders, parents, lawyer · M (accounts), L (entity) · Before public launch

| Option | For | Against |
|---|---|---|
| **A parent holds and pays for the accounts now; an LLC later** (recommended) | Fast; fixes the age clauses and the Apple block; no lawyer needed to start | The parent carries the accounts until the entity exists |
| Form an LLC now | Clean ownership and liability from day one | Lawyer, about $890 in year one in California, D-U-N-S for Apple org enrollment takes 1-2 weeks |
| Keep the accounts personal | Nothing to do | Breaches Gemini's and probably Render's terms; minors and maybe parents personally liable; no Developer ID |

1. Today: pick one parent to enroll in the Apple Developer Program as an individual ($99 a year) and share it, and to
   take over or co-own billing for Anthropic, Google Cloud, Render, Supabase and Porkbun with a card that won't lapse.
2. Before public launch: move the accounts (or add the parent as owner and billing contact) and keep a private list
   of who holds what.
3. Before public launch: a lawyer consult on the entity (a California LLC with a parent as manager or officer), the
   founders' equity held by a parent as custodian (CUTMA), a founders' IP assignment, who signs vendor terms, and who
   the privacy policy names as the operator.
4. After launch, before taking money: form the entity and move the accounts to it.
- **Verify:** every vendor console shows an adult as owner and on billing; the Apple account is active.

### R12
**New installs may be refused.** ★ · Michael, Adrian · M · Before private beta
1. A throwaway staging service on Render that logs the raw `X-Forwarded-For`; two installs from different networks
   with `REGISTER_LIMIT_PER_HOUR=1` (area C's staging check). Michael.
2. If the IP is wrong: the fix in the private notes, or our own Cloudflare in front, keyed on `CF-Connecting-IP`,
   with a secret header from a Transform Rule so the onrender.com host can't be used to go around it. Michael.
3. Raise the per-IP install limit for classrooms and hackathons (for example 50 an hour), relying on R01's per-token
   spend caps; when it trips, say "Too many new installs on this network right now. Try again in a few minutes."
   (`cloud/app.py:68, 222-239`; onboarding copy). Michael, Adrian.
4. `api.miyagi.study` as a Render custom domain (a CNAME), and `DEFAULT_CLOUD_URL` switched to it
   (`app/src/main/features/cloud.ts:46`) before launch, so Cloudflare or a host move later needs no app update.
   Adrian, Michael.
5. Electron `net.fetch` in the main process for mint, auth and updates (system proxy and Keychain roots); the engine
   uses the system trust store (`truststore`). Adrian, Michael.
- **Depends on:** R34 (DNS) for step 4.
- **Verify:** staging logs show each client's own IP; 15 installs from one network in an hour all succeed; the app
  talks to `api.miyagi.study`.

### R13
**Windows download can't run a lesson.** Adrian · S · Before private beta

| Option | For | Against |
|---|---|---|
| **Remove the button for launch: "mac only for now. windows is next."** (recommended) | Honest; no SmartScreen or Smart App Control dead end | Windows visitors leave |
| Label it "windows preview: lessons need a mac for now" | Keeps a foothold | Still sends people through warnings to an app that can't do a lesson |
| Keep it | — | A claim we can't keep |

1. Remove the Windows button and tip from `miyagi-site/index.html:437-441` and #188's Windows steps.
2. Edit the `windows` release body (or turn it back into a draft) to say lessons need a Mac.
3. Keep the windows-sync agent from bringing the button back (`publishNext` false, or pause it for launch).
4. Never tell users to turn off Smart App Control.
5. After launch, the Windows lane: a screen-less engine first, then the Microsoft Store (MSIX), then a signed direct
   download (needs R11).
- **Verify:** no Windows download on the site; the release says Mac only.

### R14
**Progress and settings get lost.** Adrian, Michael · M · Before public launch (label before private beta)
1. E01 (Adrian): serve the renderer from a fixed origin, either a privileged custom scheme
   (`protocol.registerSchemesAsPrivileged` with `standard: true, secure: true`, then `protocol.handle`) or a fixed
   loopback port saved in userData (`app/src/main/serve.ts:81`, `main/index.ts:181`). Check YouTube embeds still play
   from the new origin. Move durable choices (tips, sounds, dashboard goals) into main prefs (`common/prefs.ts:30`).
2. E03 now (Adrian): label recent rows "Start again", not "Continue" (`renderer/src/features/library/homeModel.ts:35`).
   Then (Michael): `library.start` of any saved or recent lesson restores its step (keep a graph per recent entry, or
   restore `stepIndex`, `passedSteps` and the files) and never sets files aside on a Continue
   (`server/orchestrator/main.py:743-786`, `session.py:2108-2123`, `server/sessions/progress.py:13`).
3. E29: the app passes `ORCH_HERO_WORKDIR=~/miyagi/lessons/pinn-lab`, or the engine puts the hero folder under
   `lessons_root()` (`server/workspace/paths.py:13, 71-92`). Adrian or Michael.
4. E13 (Michael): temp-file-and-replace for every lesson-cache write, using the helper in `server/sessions/store.py:55-69`,
   and treat an unreadable cache file as a miss (`server/lesson/builder.py:258`).
- **Verify:** R-E01 and R-E03 repros; a dismissed tip stays dismissed after ⌘Q; Continue opens at the saved step
  with the files in place; the hero folder survives an update.

### R15
**Unsigned Mac app.** Parent, Michael, Adrian · L · Before public launch

| Option | For | Against |
|---|---|---|
| **Signed and notarized public launch** (recommended, if a parent enrolls this week) | One normal open; permissions survive updates; auto-update becomes possible; school IT can allow it | About a week: enrollment, then C11's config and Michael's test matrix |
| Unsigned public launch | No wait | Open Anyway for everyone; every update re-asks permissions. Only acceptable if Test 1 passes on macOS 26 and 27 and step 3 ships |

1. A parent enrolls (R11). Today, Michael can already run area C's entitlement test matrix on a copy of the bundled
   Python (no Apple account needed): site `.so` imports, ctypes and cffi callbacks, a PyObjC handler, numpy in a lesson
   venv, plus the Mach-O inventory and the `otool` dangling-path check.
2. Signing config (drafted in area C's Apple notes): explicit entitlement plists (`disable-library-validation` on the
   interpreter, `allow-jit` and maybe unsigned memory, per the matrix), a `signIgnore` regex for non-Mach-O files, no
   `--deep`, hardened runtime, notarize and staple both the app and the DMG; Electron fuses (`runAsNode`,
   `nodeCliInspect`, `nodeOptions` off; `onlyLoadAppFromAsar` and ASAR integrity on). Adrian (config), Michael (Mac).
3. Until signed (Adrian): on the first launch of a new version, run a test capture; if it comes back black, open a
   recovery step ("Remove miyagi from Screen Recording and add it again"); copy for the Keychain prompt; the same
   steps in SHIP.md and the release body.
4. Site: say school-managed Macs may not install it; after signing, publish an IT note with the PPPC payload (C09).
5. After signing: electron-updater from the versioned releases (R10).
- **Depends on:** R11, R06.
- **Verify:** `spctl -a -vv` accepts the app and `stapler validate` passes; numpy imports in a lesson venv; an update
  from vN to vN+1 keeps Screen Recording.

### R16
**miyagi-cloud capacity and plan.** Michael · M · Before public launch (checks today)
1. Today: Starter (`0.5c-512mb`) or larger with the `miyagi-data` disk attached; auto-deploy off for launch week;
   card on file; Anthropic tier read and a raise to Build or Scale requested; Gemini payments started for the Tier 2
   and 3 clocks only if D1 keeps Gemini.
2. Code: raise the httpx pool limits, move SQLite calls off the event loop, lower `MAX_GEMINI_BODY_MB` to the real
   need, apply A23's fix from the private notes, and load-test with a mock upstream.
3. Lighter scene looks: skip identical frames and downscale to about 1,500 px (also cuts Render bandwidth); honor
   `retry-after` with jitter; Sonnet and Haiku fall back to each other on 529 and 5xx.
4. Consider `1c-2g` ($25 a month) for launch week. Later: Postgres through `store.py`, no disk, more instances.
- **Verify:** a mock-upstream load test at about 200 learners gives no 502s; the Console shows the new tier.

### R17
**Capture takes more than the lesson needs.** Michael · L · Before public launch (window-only capture after) · lawyer before scaling
1. On the fallback capture path, black out (or don't capture) the private apps that the ScreenCaptureKit path
   excludes, and add Slack, WhatsApp, Signal, Mail and banking apps to the list (`server/screen/sck.py:31-34`,
   `reader.py:784-793, 921-947`).
2. Scrub secrets from code and files before upload: skip `.env*` and key files; replace `sk-ant-`, `AIza`,
   `sb_secret_`, JWTs, Bearer values and private keys in buffers, selections and the project scan; strip the home
   path (`server/lesson/workdir.py:39-93`, `server/coach/judge.py:100-111`).
3. A visible capture indicator and the pause control (R03).
4. The policy says exactly what is excluded and when, and claims no blackout the fallback doesn't do.
5. **Decision (D8):** capture only the editor and tutorial windows (a ScreenCaptureKit window filter) instead of the
   whole display. Recommended as the target, after launch.
- **Verify:** with a canary `.env` value and a password-manager window open, a local proxy log of a lesson shows
  neither.

### R18
**Google sign-in and Supabase not launch-ready.** Michael, Adrian · M · Before public launch (consoles today)
1. Today (Michael): scopes are only `openid`, `email` and `profile`; sign in with a Google account not on the test
   list; fill Branding (no logo yet); Publish app. Supabase: plan and Active; only Google enabled; Redirect URLs exactly
   `http://127.0.0.1:47217/auth/callback**`; no tables in exposed schemas, or RLS on with no anon policies; asymmetric
   signing keys on and legacy keys off; `SUPABASE_JWT_SECRET` unset on Render.
2. App copy (Adrian): fix the `access_denied` text that says "ask to be added as a tester" (`app/src/main/features/auth.ts:147`)
   and the "account isn't allowed" shown on a plain Cancel; while waiting, "Using a school account? It may be blocked.
   Use a personal one, or continue without an account."
3. The standard-color Google button (`features/account/ui.tsx`, `GoogleGlyph`). Adrian.
4. Branded consent screen, two ways: Supabase Pro plus the custom-domain add-on for `auth.miyagi.study` (about $35 a
   month, an adult pays, also ends pausing), or a Google Desktop client with PKCE that hands the ID token to Supabase
   (free, about a day). Don't change `SUPABASE_URL` itself; it would sign everyone out. Then Search Console for
   miyagi.study and Verify Branding (needs R04 live). Michael, Adrian. Decision D15.
5. Until Supabase Pro: a daily heartbeat so the project doesn't pause.
- **Depends on:** R04, R11 (who pays).
- **Verify:** an unlisted Google account signs in; after branding the consent screen says "miyagi"; Supabase shows
  Active.

### R19
**No age gate or minors safeguards.** Michael, Adrian · M · Before public launch
1. The gate, per the checklist in `privacy-review.md`: neutral month and year pickers before Google sign-in or
   anything stored; no hint of the cutoff; generic failure copy; store only an age band (13-15, 16-17, 18+) and the
   month given. Under 13: a flag that survives restarts (app data and Keychain), the same message on every retry,
   sign out, and delete any session, install token and server rows (needs R23). 13-17: Claude only, no own key,
   high-privacy defaults, a parent or guardian accepts the terms.
2. Anthropic's safeguards: the AI disclosure (R03), Anthropic's child-safety system prompt in the coach and build
   prompts, a "report this answer" link, monitoring through R30's counts, and a short public COPPA and teen-safety
   statement on the site.
3. Market to "13 and up"; no middle-school outreach.
4. A lawyer reads Anthropic's Commercial Terms ("not for consumer use") against a consumer app.
- **Depends on:** D1, R23.
- **Verify:** an under-13 month and year is refused on every retry and after a relaunch; no birth date is stored.

### R20
**One-click model-written commands; shared cache.** Michael · M · Before public launch
1. Gate: don't merge `claude/eng-proxy-cache` for launch. If it merges later, fix A08 first (private notes), and cache
   only content built from the public video, never a learner's goal, screen or code. **Decision D11.**
2. "Run it for me": show the exact command before it runs; refuse or warn on pipe-to-shell, `sudo` and `rm -rf`; allow
   brew names only from the catalog, never with `/` (`server/orchestrator/session.py:2401-2412, 7748-7778`;
   `server/workspace/setup.py:40, 396-399`).
- **Verify:** a step whose command is `curl ... | sh` is refused; the launch engine SHA doesn't contain the cache.

### R21
**YouTube scraping.** Founders decide, Michael · S (limits) to L (other sources) · Before public launch · lawyer if kept past beta

| Option | For | Against |
|---|---|---|
| **(a) Keep the on-device transcript fetch, with limits** (recommended for launch) | Works today; runs on the learner's Mac for a video they chose | Still against YouTube's Terms; YouTube can block it; a lawyer should read it before the public post |
| (b) No transcripts: Data API metadata (title, description, chapters) plus the learner watching the embedded video | No scraping | Much weaker lessons |
| (c) Gemini's YouTube-URL input | Google's own path | Only with an 18+ or Vertex choice in D1 |
| (d) Captions from creators who connect their channel (`captions.download`) | Fully licensed; a creator story | Needs creator partnerships; slow |

Limits for (a): nothing scraped through our servers; no Bright Data in shipped builds; no spoofed browser user agent;
transcripts never stored on the cloud, shared or committed; every lesson credits and links the creator. Build toward
(d) after launch.
- **Verify:** the shipped engine has no Bright Data path and no spoofed user agent; no transcripts in the repo or on
  the cloud.

### R22
**Name collision with Miyagi Labs.** Founders, lawyer · S (cues) to M (decision) · Before public launch

| Option | For | Against |
|---|---|---|
| **Keep "miyagi" for now, drop every Karate Kid cue today, get a clearance opinion before the public post** (recommended) | Keeps the brand and the domain; cheap | About $1-2k for clearance (or a law-school clinic); a rebrand may still follow |
| A composite name (for example "miyagi.study") | Some distance | Same core word, same space |
| Rebrand before launch | No conflict | Loses the brand work and the domain |

1. Now (Adrian): change the "waxon" code; no "wax on, wax off", no "Mr. Miyagi" or sensei styling, no film stills or
   voice imitation.
2. Before the public post: the clearance opinion; a plain answer ready for "how is this different from Miyagi Labs?";
   no trademark filing until cleared. If the opinion says high risk, rebrand before the post, not after.
- **Verify:** no "wax" in the site or app.

### R23
**Delete my data is misleading.** Adrian, Michael · M · Before public launch (copy before private beta)
1. Now (Adrian, S): the button says what it really does: "Removes your keys and settings on this Mac. Your lessons in
   ~/miyagi stay; delete that folder to remove them." (`settings/sections/Privacy.tsx:39, 80`, `main/features/settings.ts:168-180`).
2. App erase (Adrian), per the #199 checklist: sign out; delete `install.bin`, `cloud-link.json`, `reminders.json`,
   `onboarding.json`, the error log and crash reports, and the app's browser storage (YouTube cookies); re-mint the
   install token; revoke the Supabase session (`scope=global`); "Also delete my lesson folders" as a second choice.
3. Cloud (Michael): `DELETE /v1/me` by install and by user (tokens, links, usage, builds, uploader fields) plus
   Supabase `deleteUser`; retention limits (usage 12 months, logs as short as Render allows); drop `user=` from log
   lines (`EP:cloud/app.py:161-162, 198`).
4. Engine (Michael): a "delete my data" command for local engine data.
5. **Decision D10:** unlink on sign-out (recommended), or keep linking and say so (`app/src/main/features/cloudLink.ts:23-25`).
- **Verify:** after Delete, `~/Library/Application Support/miyagi` holds no tokens and the cloud has no rows for that
  install; the Supabase user is gone.

### R24
**Spinners and builds with no way out.** Adrian, Michael · M · Before public launch
1. App (Adrian): a renderer watchdog (45-60 s after Check with no answer: clear the press, "No answer yet. Try again.",
   Check back on); a websocket ping every 15 s that drops a dead socket; reconnect on `powerMonitor` `resume`
   (`app/src/main/engine.ts:219-275`, `renderer/src/core/ui/atoms.tsx:125-128`, `core/lesson.ts:385-388`).
2. Engine (Michael): a hard timeout on every model call and a `finally` that always sends a non-thinking status; one
   deadline (about 180 s) for the whole build after the placeholder, `wait_for` on every model call, the normal
   build-failed card on failure; never save a placeholder as the resumable lesson (`server/lesson/builder.py:78, 123-204`,
   `server/orchestrator/modules.py:284-301`, `server/lesson/claude.py:75-85`, `server/sessions/resume.py:164-166`).
3. Progress by stage (video read, steps drafted, checks written, folder ready) with elapsed time and "Stop building"
   always visible (`server/orchestrator/session.py:1998-2009`; `renderer/src/features/building/Card.tsx`). Michael, Adrian.
4. Let `check_step` jump the queue, or cancel the running coach call when Check is pressed (`main.py:110, 1031-1048`).
   Michael.
- **Verify:** R-E02 (`kill -STOP` the engine during Check) ends in a message within 60 s; R-E09 shows the
  build-failed card within 3 minutes.

### R25
**Raw or wrong errors when the cloud fails.** Adrian, Michael · M · Before public launch
1. Engine (Michael): map paused, quota, spend-limit, allowlist and 5xx answers to one plain card ("miyagi's AI is
   paused for a bit. Your lessons are saved. Try again later."), with no retries on those; `human_build_error` returns
   the plain text from `CLOUD_ERRORS` plus a `failCode` (`server/lesson/builder.py:619-629`, `server/config.py:248-252`);
   raw exceptions become "Something went wrong on our side. Try again." and go to the log (`session.py:5570-5579`).
2. Cloud (Michael): keep `/v1/install` minting while paused, or return a body the app reads as paused; keep the paused
   state while `/healthz` says `proxy_enabled: false`.
3. App (Adrian): map the new failCodes in `features/errors/cards.tsx`; first-mint timeout 30-45 s with "waking up"
   copy; retry with backoff (30 s, 2 min, 5 min) and on `online` and wake; own-key users skip the cloud
   (`app/src/main/features/cloud.ts:38-46, 198-235, 256-259`).
- **Verify:** area C repros 1 and 3 (cloud down then up; paused mid-build) show the plain card and recover with no
  relaunch.

### R26
**First run on a real student's Mac.** Adrian, Michael · L in total (each S-M) · Before public launch
1. E28 (before private beta): the app sets `MIYAGI_NET_PROBE` to the cloud host in cloud mode (`localEngine.ts` env).
   Adrian, S. The engine never gates local checks on the network. Michael.
2. E30: flag one stdlib-only lesson ("Build a Python calculator") as `suggested` for a new Mac. Michael, Adrian.
3. E31: Accessibility is "recommended", not a gate ("Continue without it: miyagi can't arrange windows")
   (`onboarding/steps.ts:73-75`, `rows.ts:143-156`, `library/Home.tsx:111-148`). Adrian.
4. E32: find VS Code anywhere; if it's in Downloads, offer "Move Visual Studio Code to Applications" (`localEngine.ts:795-805`,
   `features/onboarding.ts:68-72`, `server/orchestrator/health.py:217-226`). Adrian, Michael.
5. E33: the companion reports `isTrusted`, and a card says "Click Trust". Michael.
6. E34: always make the `.venv` on open for Python lessons; the fallback is `.venv/bin/python -m pip install x`. Michael.
7. E35: apply the developer-tools stub check to every `/usr/bin` shim, and a nonzero `--version` means not installed
   (`server/workspace/setup.py:368-377`). Michael.
8. E36: keep `_tkinter` with Tcl/Tk and the headers in the bundle (about 12 MB), or steer lesson search away from
   turtle and tkinter (`app/scripts/bundle-engine.mjs:104-105`). Adrian.
9. E37: `net.fetch` (R12) and the system proxy passed to pip. Adrian, Michael.
10. E39: if Test 1 step 12 fails, set `SSL_CERT_FILE` to certifi's bundle in lesson terminals. Adrian.
- **Verify:** Test 1 variants V1 to V9 pass.

### R27
**Wrong work marked right.** Michael · S (E18) to M · E18 before public launch, the rest after
1. E18: on Check, a machine fail can only become a "Looks done?" question, never a pass; evidence limited to the
   step's file and the lesson's terminal; file and screen text quoted as data in the prompt (`server/coach/judge.py:249-262`,
   `session.py:6530-6538`).
2. E19: grade output on the rows after the last run of the step's command (same fix as E15).
3. E21: run checks on the file with comments and strings masked (`code_gate._mask` exists); `def name(` isn't a call.
4. E22: when the companion has the step's file open, its exact text decides both ways; ignore screen text outside the
   editor; match app names exactly.
5. E23: Confirm goes through the same evaluation as Check.
- **Verify:** repros R-E18, R-E19, R-E21 and R-E23 now fail as they should.

### R28
**Local access hardening.** Michael, Adrian · M · Before public launch (A06 before any venue demo)
1. A05, A06, A12 and area C's app-to-engine item: the fixes in the private notes. Michael (engine), Adrian (app,
   companion).
2. A14 (Adrian): host the YouTube player in its own page with no preload, talking to ours by postMessage with an
   origin check; or give the player window a preload with only video channels and drop YouTube from the main CSP
   (`renderer/src/features/player/youtube.ts:80`, `main/serve.ts:41`, `preload/index.ts:23`). While moving it, follow
   YouTube's player rules: nothing of miyagi's drawn over the player, at least 200×200, and consider the
   `youtube-nocookie.com` host (today it's `www.youtube.com`, `renderer/src/features/player/store.ts:461-490`).
3. C40 (Adrian): Electron to the latest 45.x for the launch build; plan 46 or 47 before Apr 27, 2027.
4. The small Electron items in `later.md` (security flags after `...options.webPreferences`, the player's window-open
   handler, `elevenlabs.io` in `safeOpen.ts`).
- **Verify:** the checks in the private notes; `npm ls electron` shows 45.4 or later.

### R29
**No support, security or privacy contact.** Adrian, Michael · M · Before public launch (email and reporting today)
1. Today (Adrian): Porkbun forwarding for support@, security@, privacy@ and copyright@ to a new shared team Gmail with
   2-step verification and a parent as recovery contact; SPF `include:_spf.porkbun.com` and DMARC `p=none`; an
   auto-reply.
2. Today: private vulnerability reporting on both repos; both founders watch security alerts. Michael (team repo),
   Adrian (site repo).
3. Site (Adrian): personal Gmails off; `/.well-known/security.txt` and `/security.txt` (draft in `security.md`) plus
   `.nojekyll`; footer links; `/help` with the five canned answers and an Open Anyway GIF.
4. SECURITY.md on both repos: scope, a no-legal-action promise for good-faith research, no spending through the proxy,
   no other people's data, a reply within 3 business days, credit, no bounty.
5. An issue form (`.github/ISSUE_TEMPLATE/bug.yml` on `adrian-erlikhman/miyagi`) with no upload field and a "this is
   public" warning; in-app "Report a bug" opens it with only os, version and area in the URL; "Copy details" goes
   through `scrub()` (R40).
6. A one-page incident runbook (who decides, notice templates, the 30-day California and 72-hour GDPR clocks), using
   the first-hour steps in `security.md`, rehearsed once with a no-downtime key rotation.
7. Both founders' git commit email set to the GitHub noreply address; no phone, school or city in replies; if a sender
   is under 13, answer once and delete the thread.
- **Verify:** a test email to each address arrives; `security.txt` returns 200; private reporting shows on both repos.

### R30
**Launch-day blindness.** Michael, Adrian · M · Before public launch (monitors today)
1. Today: UptimeRobot (free) keyword monitors on `/healthz` for `"ok":true` and for `"proxy_enabled":true`, one on the
   site, a HEAD on the current release asset; alerts to both founders; status subscriptions for Anthropic, Google AI
   Studio, Render and Supabase.
2. Cloud (Michael): daily counters with enum values only (install created, app open, sign-in choice, build result,
   lesson started, step checked, lesson finished, limit hit, error), kept where a restart doesn't lose them; each
   release asset's `download_count` daily on `/admin`.
3. App (Adrian): `process.on('unhandledRejection')` into `errors.json`; renderer Boundary errors to main over IPC;
   setup-funnel counts with no content (setup shown, Screen Recording on, relaunch, Accessibility on, first check
   passed), sent with the counters.
4. Crash reports (D14): a fixed-schema `POST /v1/crash` on miyagi-cloud (version, os, process, reason, exit code,
   error type, a 200-character scrubbed message, the stack as `basename:line:function`), opt-in and authenticated by
   the install token. Or opt-in Sentry, only with `launch.md` appendix A's config and a passing canary test.
5. Rule: no crash or analytics SDK ships without the allowlist config, opt-in consent and the canary test; nothing in
   `vscode-ext`; CI fails on `replayIntegration`, `feedbackIntegration` or `browserTracingIntegration`.
- **Verify:** a forced error shows on `/admin` within a minute; the canary string never appears in anything sent.

### R31
**Copy over-promises; cheating read.** Adrian, both founders · M · Before public launch
1. The hero and requirements lines from `launch.md` section 6: "miyagi turns a coding tutorial on YouTube into steps
   you do yourself in VS Code, and checks each one before the video moves on." and "Mac with Apple silicon, macOS 13 or
   later, and VS Code. Free while in beta; usage limits apply."
2. Reword `index.html:604-611`: what works today instead of "ask for anything"; "type" instead of "say"; "checks each
   step" plus "can be wrong" instead of "as you type"; a "beta" label.
3. #188: check or drop "install in 30 seconds", "any tutorial", "auto-graded", "used only to guide your lesson" and
   the Windows steps.
4. No accuracy or outcome claim without a dated evidence note on file (tutorials tried, how many worked).
5. Label the site story "illustration of a real run"; record a one-take, unedited 30-60 s video on a tutorial we
   didn't pick, including a failed check; never show DEMO-mode output as live.
6. Positioning: "it checks your work, it never does it for you"; the terms forbid use on graded work where AI isn't
   allowed (already in `web/terms.md`); never market for exams or interviews; the first HN comment says exactly what's
   captured, how often, where it goes and how to pause.
7. Later (engine): a question or pointer first, "Do it for me" only after a real attempt (E26).
- **Verify:** the site no longer says "anything", "any tutorial" or "say what you want".

### R32
**macOS permission prompts.** Adrian, Michael · M · Before public launch
1. Mac tests: set the clock a month ahead (or wait) with a lesson running; run guided setup on the macOS 27.3 beta.
2. When capture is refused while the grant looks on, pause the lesson with a plain card ("macOS asks again about once
   a month. Click Allow, then come back.") instead of a black frame or a false "Not yet"; poll permissions during
   lessons (`app/src/main/permissions.ts:36-41`, `server/orchestrator/session.py:7038-7074`). Michael, Adrian.
3. Onboarding names the monthly alert before it appears; the Accessibility step is rewritten for 27.3, with a "+"
   fallback in System Settings; later, evaluate `SCContentSharingPicker`. Adrian.
- **Verify:** repro R-E05 shows the card.

### R33
**Download code gate.** Adrian · S · Before public launch

| Option | For | Against |
|---|---|---|
| **Keep it for the private beta, remove it on public launch morning** (recommended) | Marks "not yet" while R01 and R02 land | None, as long as it isn't treated as security |
| Remove it now | One less step for testers | Signals open launch before the spend controls are in |
| Keep it through launch and print the code in every post | — | A barrier HN and Product Hunt penalize |

Until then, one line saying what the code is ("miyagi is in private beta. Ask us for a code."). On launch morning,
link `releases/latest/download/<name>` directly (`miyagi-site/index.html:520-541`).
- **Verify:** a fresh browser downloads with no code on launch day.

### R34
**Personal accounts are single points of failure.** Adrian, Michael · S · Today
1. github.com/settings/pages: add miyagi.study, add the `_github-pages-challenge` TXT at Porkbun, verify; verify again
   under the org before any repo transfer. Adrian.
2. Porkbun: 2FA, auto-renew, a parent's card, more years; after launch, push the domain to a shared Porkbun account.
   Adrian, parent.
3. Render: a second person with access (a Pro workspace, or shared credentials in a password manager) and a written
   kill-switch runbook. Michael.
- **Verify:** Pages shows the domain verified; Porkbun shows auto-renew; Adrian can open the Render service.

### R35
**Where miyagi is offered.** Founders, Michael · M · Before public launch

| Option | For | Against |
|---|---|---|
| **US first: block the EEA, UK, Switzerland and Anthropic's unsupported regions at the proxy, with a plain message; say so in the terms** (recommended) | Avoids GDPR representatives, a DPIA and the UK Children's Code until there's an entity | Turns away EU and UK visitors from the HN thread |
| Serve the EU and UK and comply | Bigger launch | Representatives, a DPIA, a full Art. 13 notice, the Children's Code for under-18s, Gemini paid-only |
| Serve everyone and do nothing | — | Exposure under GDPR, and a breach of Anthropic's regions policy |

Anthropic's unsupported and sanctioned regions are blocked in every option. Render passes no country header, so use
Cloudflare's `CF-IPCountry` once R12 puts Cloudflare in front, or a GeoIP lookup. Revisit with a lawyer after R11.
- **Verify:** a request from a blocked region gets the message.

### R36
**Creators' content in the public repo, no DMCA agent.** Michael, Adrian · M · Before public launch
1. Take third-party lesson content out of the public repo (`demo/cache/lessons/`, `evals/lesson/` fixtures that
   transcribe creators' code), or keep only our own examples; add `demo/cache/transcripts/` to `.gitignore`; scrub the
   team member's macOS username from fixture paths. History keeps old copies, so note that in the takedown policy.
   Michael.
2. Register a DMCA agent ($6 for 3 years at copyright.gov; it needs a name and address, so a parent's or the entity's,
   R11) and publish a takedown policy using copyright@ (R29). Adrian.
3. Every lesson shows the creator, channel, title and link; steps in our own words; no full transcripts or instructor
   code on screen; a creator opt-out and a per-video kill switch. Michael.
4. A fair-use review before charging (lawyer).
- **Verify:** a search of the repo for a known creator's code finds nothing; the DMCA directory lists miyagi.

### R37
**Site first screen, phones, `/live/`, embed.** Adrian · M · Before public launch (`/live/` before private beta)
1. One plain sentence under the wordmark, visible without scrolling and not `aria-hidden` (R31's hero line;
   `index.html:420`).
2. Phones: "miyagi is a desktop app (mac)" with a copy-link button instead of the downloads (or #188's phone view).
3. Delete `miyagi-site/live/`.
4. The YouTube embed loads only on a click (or stills only), with nothing drawn over the player (`index.html:893-913`).
   This also settles the cookie-banner question (`cookies.md`).
5. Self-host three.js and Lenis, or add `integrity` hashes to the CDN imports.
- **Verify:** `miyagi.study/live/` returns 404; a phone screenshot shows the desktop-app note; no YouTube request
  before a click.

### R38
**Launch channel rules.** Founders · S · Before public launch (`/showlim` today)
1. Each founder opens `news.ycombinator.com/showlim` logged in; post from the account with real history. If neither
   qualifies, lead with X and Product Hunt, and take part in HN for real before trying.
2. The founders write the title, post, first comment and every reply themselves; AI only for internal prep.
3. Outreach asks people to try it and give feedback, never to vote, never with the HN link; friends say how they know
   us; CAN-SPAM needs a postal address and an opt-out, so use a PO box or the entity's address, not a home address.
4. Timing: soft launch the week before; Show HN on a Sunday around 4-5 PM PT; Product Hunt a week later on a weekend
   at 12:01 AM PT; on X, a native 30-60 s video with the link in the first reply. Turn on the repo's interaction limit
   ("existing users", 24 h) if spam starts. **Decision D16.**
- **Verify:** `/showlim` screenshots from both accounts.

### R39
**Engine keeps running with no UI.** Michael, Adrian · S-M · Before public launch
1. Mac check (Michael): `kill -9` the app mid-lesson and watch the recording indicator and
   `pgrep -fl server.orchestrator.main`; on the launch build, quit mid-lesson, relaunch, and confirm no capture or
   Claude calls before a lesson starts (B09).
2. Engine (Michael): exit when the parent dies (`getppid()==1`, or an inherited pipe closes) and after N minutes with
   no client. App (Adrian): keep the pid file at quit and SIGKILL the group after about 3 s
   (`app/src/main/localEngine.ts:490-502, 719-729`, `main/index.ts:543-546`).
- **Verify:** after `kill -9` of the app, the engine is gone within a minute.

### R40
**Local logs keep questions, code and paths.** Michael, Adrian · S · Before public launch (`ORCH_RECORD=0` before private beta)
1. Mac check, then `~/miyagi` at 0700 and its files at 0600. Michael.
2. Rotate `engine.log` at 5 MB and cut it to metadata (no question text, OCR or payloads) (`server/orchestrator/hub.py:31-63`).
   Michael.
3. `ORCH_RECORD=0` in the shipped engine (`server/orchestrator/recorder.py:31-36`, the app's engine env). Adrian or
   Michael.
4. "Copy details" goes through `scrub()`, not only `redact()` (`app/src/main/localEngine.ts:215, 305`). Adrian.
5. Delete my data wipes these (R23).
- **Verify:** a 6 MB log rotates; Copy details shows `~` instead of the username.

### R41
**Keep secrets out of the repo and builds.** Michael, Adrian · S · Before public launch (settings today)
1. Today (Michael, repo admin): confirm secret scanning and push protection are on.
2. gitleaks in CI on every PR; a build-time check that refuses `sb_secret_` and any JWT with `role: service_role` in
   `MAIN_VITE_*` (`app/src/main/publicConfig.ts`); scan every release asset before upload. Adrian.
3. Scan the currently published Mac zip and Windows installer once.
- **Verify:** a test PR with a fake key fails CI.

### R42
**Fixed ports.** Adrian, Michael · M · Before public launch
1. Detect a foreign listener on 8787 and say so: "Another app is using miyagi's port (8787), often `wrangler dev`.
   Quit it and press Retry." Retry works without a relaunch (`app/src/main/localEngine.ts:683-688`,
   `features/errors/cards.tsx:112`). Adrian.
2. Later: a port chosen at launch with a handshake (Michael, engine; Adrian, app); fallback ports for the 47217
   sign-in loopback. The security side is R28.
- **Verify:** area C repros 6 and 7 (8787 and 47217 busy).

### R43
**Licenses and third-party notices.** Adrian, Michael · M · After launch
1. Choose a license for miyagi on purpose (or an explicit "all rights reserved"), after R11's IP assignment.
2. Generate THIRD_PARTY_NOTICES at build time (Vite 8 `build.license`, or `license-checker-rseidelsohn` or
   `cyclonedx-npm`, plus `pip-licenses`) for Mac and Windows, linked from Settings; ship `OFL.txt` with the font.
3. Mac check for Pillow's libimagequant (GPL-3.0) and GNU readline or gdbm in the bundled CPython; if found, this
   becomes P1.
- **Verify:** the notices file lists every shipped package.

### R44
**Site polish.** Adrian · S-M · After launch
1. Words first and 3D after; skip 3D on small or low-memory devices (D11).
2. Darker small text (`--m-ink-muted`), a skip link, an axe or Lighthouse pass (D12).
3. A download block after the story (D13).
- **Verify:** Lighthouse accessibility 90+; words visible before the 3D loads.

## Decisions only Adrian and Michael can make

The six the brief asked for come first. Each has its options and trade-offs in the row named.

| # | Decision | Recommendation | Risk |
|---|---|---|---|
| D1 | **Gemini's 18+ terms vs our 13+ gate** | Claude only for everyone at launch; keep 13+; Gemini off in the cloud and in Settings. Revisit Vertex AI once an entity holds the account | R09 |
| D2 | **The entity and who signs** | A parent holds and pays for every vendor account now (Apple individual enrollment by a parent); a lawyer consult before public launch; form an LLC with a parent as manager before taking money | R11 |
| D3 | **The Miyagi Labs name collision** | Drop every Karate Kid cue now; a clearance opinion before the public post; if it comes back high-risk, rebrand before posting, not after | R22 |
| D4 | **How lessons get transcripts (YouTube scraping)** | Keep the on-device fetch with the four limits for launch, after a short lawyer read; work toward creator-connected captions | R21 |
| D5 | **The Windows download** | Off the site for launch: "mac only for now. windows is next." | R13 |
| D6 | **The download code gate** | Keep it for the private beta; remove it on public launch morning, once R01 and R02 are live | R33 |
| D7 | Signed or unsigned public launch | Signed, if a parent enrolls this week; unsigned only if Test 1 passes on macOS 26 and 27 and the first-launch capture check ships | R15 |
| D8 | Capture scope | Editor and tutorial windows only, as the post-launch target; before launch, exclude private apps on every path and scrub secrets | R17 |
| D9 | Where miyagi is offered | US first; block the EEA, UK, Switzerland and Anthropic's unsupported regions at the proxy; revisit with an entity | R35 |
| D10 | Account link on sign-out | Unlink on sign-out | R23 |
| D11 | The shared lesson cache at launch | Not at launch | R20 |
| D12 | Own API keys (BYOK) | Hidden in the launch build; Anthropic only, adults only, once A04's fix ships | R08, R09 |
| D13 | The kill-switch dollar line | About $100 a month on the Anthropic workspace for the beta; at launch a $100 daily breaker (or 2× measured day-1 spend), alerts at 50, 80 and 100% | R01, R02 |
| D14 | Crash reporting | `/v1/crash` on miyagi-cloud, opt-in, fixed schema; no third-party SDK at launch | R30 |
| D15 | Paying for sign-in branding | Supabase Pro plus the custom domain (about $35 a month) if a parent will pay, since it also ends pausing; otherwise the free Desktop-client route | R18 |
| D16 | Posting account and dates | The founder account that passes `/showlim`; Show HN on a Sunday around 4-5 PM PT; Product Hunt a week later | R38 |
| D17 | Where disputes go | California courts with small claims for now; arbitration later with counsel | R04 |

## Needs a lawyer

| Item | Why | When | Risk |
|---|---|---|---|
| Entity, custodial equity, founders' IP assignment, who signs vendor terms, who the policy names as operator | Minors' capacity and personal liability decide everything else | Before public launch (a consult); entity before taking money | R11 |
| Trademark clearance | Miyagi Labs likely has an earlier claim to the same name in the same space | Before the public post | R22 |
| One read of the final privacy policy and terms | Liability cap and warranty wording, minors' acceptance, the disputes clause, EU and UK rights | Before public launch | R04 |
| The YouTube transcript approach | Terms of Service and the 2026 anti-circumvention rulings | Before the public post, if D4 keeps on-device fetching | R21 |
| Anthropic's Commercial Terms ("not for consumer use") against a consumer app for teens | It's in the vendor contract we rely on most | Before public launch | R19 |
| The screen-capture consent flow | California's all-party consent law and Washington's health-data law are fact-specific, with private plaintiffs | Before scaling | R17, R03 |
| Fair use of the lesson format and any shared cache | Abridgement cases trend against substitutes | Before charging, or before the cache ships | R20, R36 |
| Gemini for under-18s | Only if D1 stays on Google for teens | If needed | R09 |
| An EU or UK launch, school deals, paid plans | Representatives and a DPIA; school data agreements; auto-renewal law | Later | R35 |

## Needs Michael's Mac or consoles

**Consoles**
- Anthropic: tier and real RPM, ITPM and OTPM for Sonnet 5.5 and Haiku 5.5; org spend limit; the proxy key in its own
  workspace with a limit and alerts; spend since the proxy went live (R02, R16).
- Google AI Studio and Cloud Billing: the tier behind `GEMINI_API_KEY`, a project spend cap, budget alerts, key
  restriction, logging (R02, R09).
- Render: instance type and disk; live `MAX_TOKENS_CAP`, `ALLOWED_*`, `PROXY_ENABLED` and whether
  `SUPABASE_JWT_SECRET` is set; the deployed commit; auto-deploy; members and 2FA; billing, card and bandwidth; the
  private-notes items (R02, R07, R12, R16, R18, R34).
- Supabase: plan and Active; providers; redirect URLs; tables and RLS; signing keys; rate limits; team and MFA (R18).
- Google Auth Platform: publishing status, scopes, Branding, Verification Center, a sign-in with an unlisted account
  (R18).
- GitHub (repo admin): secret scanning, push protection, private vulnerability reporting (R29, R41).

**Michael's Mac**
- Test 1 (R0 and V1 to V10) on clean macOS 15, 26 and 27 VMs, as admin and Standard users (R06, R26, R32).
- The engine-log grep and one cloud build at 4096 vs 32000 (R07).
- Grading repros R-E14 to R-E23 (R05, R27); R-E01, R-E02, R-E03, R-E09 (R14, R24); R-E05, R-E06 (R32, R15).
- Area C's entitlement test matrix, Mach-O inventory and `otool` check; an update test between two builds
  (permissions, Keychain, session) (R15).
- `kill -9` the app mid-lesson and watch capture (R39); `~/miyagi` file modes (R40); the private-notes checks (R08,
  R28).
- A staging Render service for the install-limit IP (R12); mitmproxy as the system proxy (R12, R26); ports 8787 and
  47217 busy (R42); cloud down, paused mid-build and Supabase unreachable (R25, R18).
