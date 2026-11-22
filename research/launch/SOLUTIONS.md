# miyagi launch risks: the solutions plan

The fix for every risk in [`RISKS.md`](RISKS.md), grouped into work streams and put in order. Each fix has concrete
steps, an owner, an effort, what it depends on, and how we check it's done. Where the founders have to choose, the
options and a recommendation come first.

- Effort: **S** under an hour, **M** under a day, **L** several days.
- Owners: Adrian (app, companion, site), Michael (engine, cloud, consoles). Engine and cloud steps are plans for
  Michael, not patches. "Parent" means the parent who will manage the LLC (R09).
- ★ marks the **critical path**: everything that has to be true before we post publicly.
- *Placeholder* rows point to Michael's private notes for the parts that would show how to exploit them.
- Not legal advice.

## The plan on one page

### Critical path to posting publicly

Four chains set the launch date. Every ★ item below sits on one of them.

1. **Michael's engine and cloud queue (the long pole).** R02 today → R03 (raise the token cap, M) → measure one
   real lesson → R01's caps (L) → the grading gate R10 (L), measured on the beta's curated lessons. Almost every ★
   engine, cloud and console item, and the only real Mac, sit with Michael, so Adrian should take every app-side
   piece: R07's companion fix, R08's update card and release script, R04's CI, R05's consent screen, R30's copy.
2. **The first build outsiders install.** It must already carry the update path (R08: versions, the update card, the
   cloud's minimum-version answer) and the cloud on our own domain (R12 step 4), or those installs can never be reached
   or moved. Freeze its SHA, run CI, then Test 1 on clean Macs (R04) before the private beta.
3. **Decisions → legal pages.** D1 (Gemini) today → R06's policy and terms, with the honest delete wording and R21's
   age text → R05's consent screen links to them → a lawyer reads them → live.
4. **The company.** R09's freeze-and-list today → the LLC formed (a lawyer or a free clinic) → every account moved
   into it, a parent signing for it → the policy names it (R06). Insurance (R24) follows. Signing (R15) joins this
   chain only if Test 1 shows Open Anyway is gone on macOS 26 or 27.

On launch morning: R38 (the code gate comes off), R23 (the name decision is made) and R43 (posting account checked,
post written by hand).

### Lanes

| Lane | Owner | Risks | P0s |
|---|---|---|---|
| 1. Money and cloud | Michael | R01, R02, R03, R12, R16, R27, R30 (engine), R35 (cloud) | 3 |
| 2. Consent, policy and legal | Adrian, Michael, parents, lawyer | R05, R06, R09, R13, R18, R21, R22, R23, R24, R25, R28, R40, R41, R48 | 3 |
| 3. Release and install | Adrian, Michael's Mac | R04, R08, R15, R19, R26, R37, R39 | 2 |
| 4. Grading, lessons and the coach | Michael | R10, R11, R14 (engine), R17, R29 (engine), R31 (engine), R32 | 0 |
| 5. App shell | Adrian | R14 (app), R20 (app), R29 (app), R30 (app), R31 (app), R47 | 0 |
| 6. Local security | Michael, Adrian (mostly private) | R07, R33, R44, R45, R46 | 1 |
| 7. Site, support and launch | Adrian, both founders | R34, R35 (app), R36, R38, R42, R43, R49 | 0 |

### Today

Console steps and two site edits that take minutes. No app, engine or cloud code.

| ★ | What | R | Owner | Effort |
|---|---|---|---|---|
| ★ | Prepaid credit with auto-reload off (the hard stop); the proxy key in its own Anthropic workspace with a monthly limit, an org limit below the tier cap and alerts to both founders. Gemini: paid tier confirmed, project cap, budget alerts, key restricted (or Gemini removed, per D1) | R02 | Michael | S |
| ★ | Grep an engine log that built through the cloud for `hit max_tokens`; read the live `MAX_TOKENS_CAP` and `ALLOWED_GEMINI_MODELS`; raise the cap on Render (env change) | R03 | Michael | S |
| ★ | Freeze and list: no new account in anyone's own name; list every account, who agreed and whose card; pick the parent who will manage the LLC; book a lawyer or a free startup clinic | R09 | Founders, parents | S |
| ★ | Decide D1 (Gemini) and D19 (web search); the other decisions this week | Decisions | Founders | S |
| | Take the Windows button off the site, mark the `windows` release Mac-only, delete `/live/`; windows-sync `publishNext` false | R19 | Adrian | S |
| | Release immutability on, a passkey for 2FA, a single-repo publishing token | R26 | Adrian | S |
| | Sign a one-page interim founders' agreement (both founders and a parent each); stop merging outside pull requests | R25 | Founders, parents | S |
| | Render: Starter or larger with the disk, auto-deploy off for launch week, a second person with access. Anthropic: read the tier and ask for Build or Scale | R16, R39 | Michael | S |
| | Google Auth Platform: scopes, a sign-in test with an unlisted account, Branding, Publish. Supabase: plan, providers, redirect URLs, RLS, signing keys | R20 | Michael | S |
| | Email forwarding (support@, security@, privacy@, copyright@), SPF and DMARC; private vulnerability reporting on both repos | R34 | Adrian, Michael | S |
| | UptimeRobot on `/healthz`, the site and the release asset; status subscriptions | R35 | Michael | S |
| | Verify miyagi.study on GitHub Pages; Porkbun 2FA and auto-renew | R39 | Adrian | S |
| | Both founders open `news.ycombinator.com/showlim` logged in | R43 | Founders | S |
| | Confirm secret scanning and push protection on the team repo | R46 | Michael | S |

### Before private beta (the outreach list installs)

| ★ | What | R | Owner | Effort |
|---|---|---|---|---|
| ★ | Measure one real lesson's cost; server-side dollar caps, a daily new-install cap, a runtime kill switch, alerts | R01 | Michael | L |
| ★ | Allowlist matches D1; cloud mode skips Gemini cleanly if it's off; one cloud build passes | R03 | Michael | M |
| ★ | A frozen launch SHA, CI running the tests, a versioned v2 build, Test 1 R0 on clean macOS 15 and 26 plus the UNVERIFIED pass | R04 | Michael, Adrian | L |
| ★ | Consent screen before the Screen Recording prompt, "AI, can be wrong", providers named | R05 | Adrian, Michael | M |
| ★ | `/privacy` and `/terms` live, app links fixed, Delete my data worded honestly, an "I agree" step | R06 | Adrian, Michael | M |
| ★ | Companion 0.0.7 and the engine key fix (or own-key fields hidden) | R07 | Adrian, Michael | M |
| ★ | Versions, one publisher, the update card, and the cloud's minimum-version answer, in the first outside build | R08 | Adrian, Michael | L |
| ★ | The cloud on `api.miyagi.study` in the same build; the install-limit IP check on staging; the limit raised with plain copy | R12 | Michael, Adrian | M |
| | "Run it for me" shows each command and asks first, blocks the dangerous ones, installs only catalog packages; the cache stays out | R11 | Michael, Adrian | M |
| | D1 implemented in engine, cloud and Settings | R13 | Michael, Adrian | S |
| | `COACH_WEB=0` in the shipped engine env (or disclosed) | R17 | Adrian, Michael | S |
| | The update card's installer URL pinned | R26 | Adrian | S |
| | Beta on curated lessons only; count false fails; E15 and E17 first | R10 | Michael | M |
| | "Start again" label on recent rows; hero lesson folder out of the engine tree | R14 | Adrian | S |
| | Karate Kid cues gone (code "waxon", "wax on, wax off") | R23 | Adrian | S |
| | `MIYAGI_NET_PROBE` set to the cloud host | R31 | Adrian | S |
| | `ORCH_RECORD=0` in the shipped engine | R45 | Adrian, Michael | S |
| | A06's fix before any demo on venue Wi-Fi | R33 | Michael | S |

### Before public launch

| ★ | What | R | Owner | Effort |
|---|---|---|---|---|
| ★ | The grading gate passes: no correct step in the curated lessons stays red after a rerun (E14, E16, E20, E24, E25 too) | R10 | Michael | L |
| ★ | Full Test 1 (all variants) on macOS 15, 26 and 27 with the launch build | R04 | Michael | M |
| ★ | The LLC formed and holding every account, a parent signing for it; lawyer read of the policy and terms | R09, R06 | Founders, parents, lawyer | L |
| ★ | Name decision made | R23 | Founders | S |
| ★ | Code gate off on launch morning; posting account checked, post written by hand | R38, R43 | Adrian, founders | S |
| | Tech E&O, cyber and media insurance bound by the LLC | R24 | Parent, founders | M |
| | Operating agreement with vesting and each founder's IP assignment; outside contributions assigned or rewritten | R25 | Founders, parents, lawyer | M |
| | Unsigned with the first-launch capture check, or signed once the LLC enrolls (D7) | R15 | Michael, Adrian | L |
| | Capacity: tier raised, connection limits, load test, lighter scene looks | R16 | Michael | L |
| | Capture: private apps excluded on every path, secret scrubbing | R18 | Michael | L |
| | Sign-in: copy, button, branding, school-account hint | R20 | Michael, Adrian | M |
| | Age gate before sign-in and the mint, teen safety, a 988 card | R21 | Michael, Adrian | L |
| | D4 (transcripts) implemented | R22 | Michael | S |
| | One official download link and SHA-256s on miyagi.study | R26 | Adrian | S |
| | Per-install `metadata.user_id`; a suspended-key plan | R27 | Michael | S |
| | Server delete, full app erase, unlink on sign-out | R28 | Michael, Adrian | M |
| | Check watchdog and build deadline | R29 | Adrian, Michael | M |
| | Plain errors and mint retry | R30 | Adrian, Michael | M |
| | First-run fixes | R31 | Adrian, Michael | L |
| | The judge can't overrule a failing check (E18) | R32 | Michael | S |
| | Hardening (private), player isolation, Electron bump | R33 | Michael, Adrian | M |
| | security.txt, SECURITY.md, issue form, `/help`, runbook | R34 | Adrian, both | M |
| | Counters, crash path, funnel counts | R35 | Michael, Adrian | M |
| | Copy rewrite, one-take video | R36 | Adrian, both | M |
| | Permission re-ask card, 27.3 copy | R37 | Adrian, Michael | M |
| | Region decision implemented | R40 | Michael | M |
| | Creator content out of the repo, DMCA agent | R41 | Michael, Adrian | M |
| | Site first screen, phone view, click-to-load embed, SRI | R42 | Adrian | M |
| | Engine exits with the app; Mac check of B09 | R44 | Michael, Adrian | M |
| | Log rotation, file modes, scrubbed Copy details | R45 | Michael, Adrian | M |
| | gitleaks in CI, build-time key check, release scans | R46 | Adrian | S |
| | Port 8787 message and Retry | R47 | Adrian | M |

### After launch

Signing once the LLC holds an Apple organization account, then auto-update (R15). Capture only the editor and
tutorial windows (R18). The remaining false passes (R32). Creator-connected captions as the long-term lesson source
(R22). The signed update manifest (R26). EU and UK, if chosen (R40). Licenses and notices (R48). Site polish (R49). The
Windows lane (R19). Everything in [`later.md`](later.md).

## Solutions by risk

### R01
**Anyone can use miyagi-cloud as free AI.** ★ · Michael · L · Before private beta
1. **Measure first.** Run one real lesson (a build and about 40 minutes of work) through the proxy and read its cost
   on `/admin`. Area C's estimate is about $0.50 a lesson, and scene looks alone can be 720 Haiku calls an hour, so
   request-count caps like "10 a minute" or "100 a day" would stop a normal lesson.
2. A persisted limiter in SQLite (survives restarts and redeploys), IPv6 bucketed by /64.
3. `check_quota` caps **dollars, not requests**, counted on the server from the usage table, never from a
   client-set header (the `x-miyagi-role` header is set by the client, so no cap can key on it):
   - per install, about 3× the measured lesson cost a day;
   - per signed-in learner, a little more, across all their installs;
   - a daily cap on **new installs** at `/v1/install` ("miyagi is full today, try tomorrow") instead of a fixed
     daily spend breaker, so a good launch day fills up instead of shutting everyone out;
   - at a global alert line, Haiku only and no new builds.
   The old starting table in `security.md` ($0.25 a day per anonymous install, 100 requests a day) is too low for one
   lesson; don't use it as is.
4. Apply the A02 and A22 fixes from the private notes.
5. A runtime kill flag in SQLite behind an admin POST, so stopping traffic needs no redeploy, kept for abuse rather
   than demand. Disable tokens by creation-time range.
6. Alerts: a Discord or Slack webhook at 50, 80 and 100% of the alert line, for one token over 3× the lesson cost
   in a day, and for an unusual number of mints an hour. A daily cron outside the service (Render cron or a GitHub Actions schedule with the admin token
   as a secret) reads `/admin/usage`, fails loudly when spend passes the alert line, and pings Healthchecks.io so a
   silent cron is noticed.
7. `/healthz` reports the deployed commit, plus `keys_configured` and `db_ok` booleans (no values).
8. App (Adrian): show "miyagi is paused" for the 400 a self-set provider limit returns, and "full today" for the
   new-install cap (part of R30).
9. Trim `cloud/README.md`'s SDK how-to once step 4 lands.
- **Depends on:** nothing. R02 goes first as the backstop.
- **Verify:** a normal measured lesson never hits a cap; on a staging service, a script past each cap gets a 429
  with the right reason; the kill flag stops proxied calls within a minute without a redeploy; each alert reaches
  both founders' phones; a unit test per cap.
- **Decision:** the alert line, the daily new-install cap and the status text users see (D13).

### R02
**No provider-side spend caps or alerts.** ★ · Michael · S · Today
1. **The one real hard stop first:** prepaid credit with auto-reload off on Anthropic (and Gemini, if kept), sized
   to what whoever pays agrees to lose. Provider limits lag and alerts only alert; an empty balance stops.
2. Anthropic Console: move the proxy's key to its own workspace (Default can't have limits); a workspace monthly
   spend limit (about $100 for the private beta, raised on purpose for launch) and ITPM and OTPM limits; an org
   limit below the tier cap; email alerts at about $10, $25 and $40 to both founders.
3. Google, only if D1 keeps Gemini: confirm the project behind `GEMINI_API_KEY` is on a paid tier; prepay $10-20 with
   auto-reload off; AI Studio project spend cap about $20-50 a month; a billing account that holds only miyagi; Cloud
   budget alerts at 50, 90 and 100%; restrict the key to the Generative Language API; AI Studio logging off or 7 days.
   If D1 is "Claude only", unset the key on Render instead.
4. Set `PRICES_JSON` on Render with the real Gemini prices now and again on Jan 1, 2027, price Haiku 5.5 in two
   tiers (prompts over 100k cost 5×), and count web-search fees (C27).
5. Subscribe both founders to status.claude.com and Google AI Studio status.
- **Depends on:** nothing. Set the limits on the accounts as they are today; R09 moves them to the LLC later.
- **Verify:** a screenshot of each limit page goes in the private notes folder; with a deliberately tiny test
  workspace limit, a call returns 400 and the app says "paused".

### R03
**Cloud lesson builds likely fail.** ★ · Michael · M · Before private beta (the cap raised today)
1. Today: on any Mac that has built through the cloud, `grep -n "hit max_tokens\|claude call: model" ~/miyagi/engine/logs/engine.log`,
   and note the largest `out=`. Read the live `MAX_TOKENS_CAP` and `ALLOWED_GEMINI_MODELS` on Render (they may differ
   from `render.yaml`) and the out-token column on `/admin`.
2. Build one video and one text lesson through a local proxy at 4096, then at 32000 (area C repro 4).
3. Fix now, without waiting for R01: raise `MAX_TOKENS_CAP` on Render to what the builder needs, or lower the
   builder's asks with thinking budgets that fit and split long transcripts. R02's prepaid balance is the backstop. A
   per-role cap doesn't work, because the only role signal is the client-set `x-miyagi-role` header
   (`server/config.py:199`), and a per-call cap never bounded abuse anyway (R01 does).
4. Allowlist to match D1. If Gemini stays: add `gemini-4-hydrogen` and set the fallbacks to 3.8-flash and 3.6-flash
   (3.5 and 3.7 flash are retired). If D1 is "Claude only": make cloud mode skip Gemini cleanly, with no 404 round trips.
5. Add a cloud build to `evals/lesson/report.md`.
- **Depends on:** D1 (step 4) and R02. Not on R01.
- **Verify:** a 20-minute tutorial builds through production miyagi-cloud with no key in Settings, and the log has no
  `hit max_tokens`.

### R04
**The launch build is untested.** ★ · Michael, Adrian · L · Before private beta (full run before public launch)
1. Freeze a launch SHA for the app and one for the engine; build the candidate from them (R08) and publish it as a
   draft `vX.Y.Z` with a `.dmg` and SHA-256s.
2. Make CI a regression gate (Adrian): run the engine's pytest suite and the app's existing checks on every PR, drop
   the `|| true` after `ruff`, and fail on merge markers (`.github/workflows/ci.yml:10-19`).
3. Scan both files with gitleaks and on VirusTotal (a bundled Python engine can trip antivirus) (R46).
4. Run Test 1 from `product.md` on clean macOS 15, 26 and 27 VMs (UTM or Tart), as admin and as a Standard user, in
   Safari and Chrome. Record every Gatekeeper dialog, any second dialog naming `python3` or a `.so` (E38), and
   `codesign --verify --deep` on the downloaded app. Add a pass over every main-process feature marked
   "UNVERIFIED in Electron" (14 files in `app/src/main/`, sign-in and the permission prompts first), and remove each
   note once it has run.
5. Rewrite SHIP.md's first-open and test steps for the cloud path, and template the release body: version, what's
   new, the four Open Anyway steps, no right-click > Open, ⌃⌥Q (C39).
6. Make the site's tip, #188 and the canned "Mac won't open" reply match what Test 1 showed.
7. Only then point the site at the new release and set `macVerified: true`.
- **Depends on:** R08 (versioned releases); R10, R03 and R07 in the build.
- **Verify:** Test 1's pass line: a passed calculator step with no Terminal, no key and no developer-tools dialog, at
  most two password prompts, under 5 minutes from first launch to all-green setup.

### R05
**No consent before capture, no AI disclosure.** ★ · Adrian, Michael · M · Before private beta
1. App onboarding: one screen before the macOS Screen Recording prompt (`app/src/renderer/src/features/onboarding/steps.ts`,
   copy at `:23-24`, and the guided flow). Draft, facts to confirm with Michael: "During a lesson, miyagi takes a
   picture of your whole screen every few seconds and reads your code and lesson files. It sends them to Anthropic
   (Claude) through miyagi's server to build and check your steps. Our server doesn't keep them; Anthropic keeps API
   data for a limited time under its own policy. A log of your questions stays on this Mac." Name Google too if D1
   keeps Gemini, and DuckDuckGo if R17 keeps web search on. A link to `/privacy`, and a button whose text matches the
   sentence.
2. One persistent line in onboarding and the lesson panel: "miyagi's coach is AI. It can be wrong."
3. Settings > Privacy (`settings/sections/Privacy.tsx:65-66`): name Anthropic (and Google if D1 keeps Gemini), and say
   every call goes through miyagi's server. Land #199's `facts.ts` rows as listed in `privacy-review.md` (editor "To
   Anthropic", code and files you ask about, a YouTube row, an account-link row, questions you type), with the panel,
   policy and `facts.test.ts` moving together.
4. A pause control on the overlay that stops capture (engine: Michael).
5. Site: replace "miyagi runs on your computer." (`index.html:605`) and add the data line by the downloads from
   `launch.md` section 6, with a privacy link.
- **Depends on:** R06 (the link target), D1 (which providers to name).
- **Verify:** on a clean install the consent screen appears before the system prompt (Test 1 screenshots);
  `facts.test.ts` passes; the site no longer says "runs on your computer".

### R06
**No live privacy policy or terms.** ★ · Adrian, Michael · M · Before private beta (lawyer read before public launch)
1. Finish the policy from #199 with #201's edits, fixing the five points in `privacy-review.md`: the account link,
   the full scope of what goes to Anthropic, the YouTube player (name "YouTube API Services" and link Google's Privacy
   Policy), honest retention (say what is kept and that server deletion is coming, R28), and age text that matches
   R21.
2. Publish `/privacy` (it includes the site section from `cookies.md`) and `/terms` (`web/terms.md`). Footer: privacy ·
   terms · help · support · security.
3. App: point or remove the `/pricing`, `/teams` and `/account` links (`app/src/main/features/account.ts:22-27`).
   And make Delete my data say what it does today: "Removes your keys and settings on this Mac. Your lessons in
   ~/miyagi stay; delete that folder to remove them." (`settings/sections/Privacy.tsx:39, 80`). The full erase is R28.
4. A first-run "I agree" step, also on "Continue without an account", with the button text matching the sentence
   above it; store the policy version and time (locally now, on the cloud once R28 lands). A parent or guardian
   accepts in a separate step for under-18 accounts (a teen can void terms a parent never agreed to); the account ends
   if a minor disaffirms; California courts and small claims, no arbitration (D17).
5. Name who runs miyagi and a contact (R09, privacy@ from R34).
6. Add a release step: re-check the policy against the release commit (`facts.ts`, engine, cloud) before every release.
7. A lawyer reads the final text before public launch.
- **Depends on:** D1, D2, R28's wording, R21's age text, D9 (regions).
- **Verify:** `/privacy` and `/terms` return 200; a script that greps `app/src` for `miyagi.study/` links finds none
  that 404; the "I agree" record exists after a fresh install.

### R07
***Placeholder:* companion configuration and engine key handling.** ★ · Adrian, Michael · S + M · Before private beta
1. A03: the fix in the private notes, with its unit test, shipped as companion 0.0.7 through `integration/live`
   (`bundle-engine.mjs` packs `vscode-ext` from there). Adrian.
2. A04: the engine change in the private notes. Michael.
3. Until A04 ships, hide every own-key field in the launch build, ElevenLabs included (Settings UI;
   `app/src/renderer/src/features/settings/keys.ts`). Adrian.
- **Depends on:** nothing.
- **Verify:** the checks in the private notes; the launch build reports companion 0.0.7.

### R08
**No way to get a fix to installed users.** ★ · Adrian, Michael · L · Before private beta
All of this has to be in the first build anyone outside installs, or those installs can never be reached.
1. Versions: bump `app/package.json` on every build; pin the engine to a SHA (`MIYAGI_ENGINE_REF`), lock Python
   packages with hashes, and write both into the release body and About (C18).
2. One publisher: `ship-mac.sh` creates a draft `vX.Y.Z`, uploads every asset (`.dmg` and `.zip`), then publishes.
   Never delete a published asset; keep stable asset names; the site links to `releases/latest/download/<name>`;
   stop republishing the CI zip artifact to the `mac` release (C16).
3. Ship #189's update card in the build, with the installer URL pinned (R26 step 2). The parser keeps only
   `state === 'uploaded'` assets.
4. A floor in the cloud: the app sends its version on `/v1/install` and every proxied call, the cloud answers 426
   below a floor, and the app shows "Update miyagi" with the download link (C19, D40). Michael (cloud), Adrian (app).
5. Freeze uploads from day -1 to day +3; after that, at most one versioned hotfix a day (D31); windows-sync
   `publishNext` false until the launch build.
- **Depends on:** R12 step 4 (the cloud on our own domain) in the same first build.
- **Verify:** install vN, publish vN+1: the card offers it on relaunch; a build below the floor shows "Update
  miyagi"; vN is still in the release history.

### R09
**No company: the families carry the liability, and the accounts have no proper holder.** ★ · Founders, parents, lawyer or free clinic · L · Before public launch

| Option | For | Against |
|---|---|---|
| **Form a manager-managed California LLC first, then the LLC opens or takes over every account, with a parent signing "for" it** (recommended, per area B's corrected B07) | Contracts, vendor indemnities and debts land on the company, not a parent; Apple organization enrollment becomes possible | A lawyer or clinic; $70 + $20 to file, $800 a year; D-U-N-S takes 1-2 weeks, so signing waits |
| A parent opens the accounts in their own name now (the earlier B07 advice) | Fast; fixes the age clauses | That parent personally owes every vendor's indemnity, and Anthropic's is uncapped. Not recommended |
| Keep the accounts personal | Nothing to do | Breaches Gemini's and probably Render's terms; the founders (and maybe parents) personally liable; no Developer ID |

Steps 1-8 of [`lawsuit-protection.md`](lawsuit-protection.md), in order:
1. Today, **freeze and list**: open no new account in a parent's or founder's own name; list every account (who
   clicked "agree", which terms, whose card); leave existing accounts where they are until the LLC can take them.
   If one truly can't wait, a parent opens only that one, at the lowest spend, on a transfer list.
2. Form the LLC (a lawyer or a free startup clinic such as Stanford, UC Irvine, Santa Clara or Pepperdine):
   manager-managed, a parent as organizer and sole manager, no meeting requirement, each founder's units held by a
   parent as CUTMA custodian, an EIN with the parent as responsible party. A Delaware C-corp only if raising money
   within about a year.
3. The operating agreement and each founder's present-tense IP assignment in the same sitting (R25).
4. An LLC bank account and card, funded with a documented contribution covering several months of bills plus the
   insurance premium; every miyagi bill paid from it.
5. Move every account into the LLC: Anthropic, Google Cloud, Supabase, Render, the domain, a GitHub organization,
   Apple organization enrollment (D-U-N-S is free), a Microsoft Company account. The parent clicks "on behalf of
   [LLC]". Close and reopen, or get the vendor's written transfer.
6. The LLC's name in the terms, privacy policy, site footer, About screen and signing certificate; sign as
   "[Parent], Manager, [LLC]"; never a personal guarantee.
- **Depends on:** nothing; R06, R15 and R24 depend on it.
- **Verify:** the LLC is filed; every vendor console shows the LLC as the customer; the policy names the LLC.

### R10
**Correct work marked wrong.** ★ (a measured gate) · Michael · L · Before public launch
Run the private beta on curated lessons only and count false fails there. Don't post publicly until no correct step
in those lessons stays red after a rerun. E15 and E17 are the cheapest wins; do them first.
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

### R11
**One-click model-written commands; shared cache.** Michael, Adrian · M · Before private beta
1. Gate: don't merge `claude/eng-proxy-cache` for launch. If it merges later, fix A08 first (private notes), and cache
   only content built from the public video, never a learner's goal, screen or code. **Decision D11.**
2. "Run it for me" (A19, B18; OWASP LLM06's "excessive agency" fixes): show the exact command with a plain
   explanation and ask for a confirm on each one (today the card says "Running it" after the fact); allow a short
   list of normal tutorial commands (`python3 <file>`, `pip install` of catalog names, `npm run`) and hard-block
   deletes, `sudo`, pipe-to-shell and anything outside the lesson folder; snapshot the folder first so a mistake can
   be undone; treat tutorial text, frames and descriptions as untrusted and check the command with plain code, not
   the model; install pip packages only by catalog name, never a name the model proposed from the transcript
   (`server/workspace/setup.py:391-393`, slopsquatting); allow brew names only from the catalog, never with `/`
   (`server/orchestrator/session.py:2401-2412,
   7743-7778`; `server/workspace/setup.py:40, 396-399`). Michael (engine), Adrian (the confirm card in
   `renderer/src/features/cards/index.tsx:468-528`).
3. Until step 2 ships: turn "Run it for me" off for under-18s (needs R21's age band), or off for everyone in the
   launch build.
- **Verify:** a step whose command is `curl ... | sh` or `rm -rf ~` is refused; every allowed command shows a confirm
  first; the launch engine SHA doesn't contain the cache.

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
   (`app/src/main/features/cloud.ts:46`) **in the first build outsiders install**, so Cloudflare or a host move later
   needs no app update. Adrian, Michael.
5. Electron `net.fetch` in the main process for mint, auth and updates (system proxy and Keychain roots); the engine
   uses the system trust store (`truststore`). Adrian, Michael.
- **Depends on:** R39 (DNS) for step 4.
- **Verify:** staging logs show each client's own IP; 15 installs from one network in an hour all succeed; the app
  talks to `api.miyagi.study`.

### R13
**Gemini terms vs teens and teen account holders.** Founders decide today; Michael, Adrian · S · Before private beta

| Option | For | Against |
|---|---|---|
| **(a) Claude only for everyone at launch; keep 13+** (recommended) | Removes the breach; the engine already falls back to Claude; simplest | Video lessons are built from transcripts (R22), and R03's cap fix becomes essential |
| (b) 13+, with Gemini only for verified 18+ users | Keeps video watching for adults | The terms bar an app "likely to be accessed by" under-18s, so per-user routing may not cure it; needs a working gate and age on the token |
| (c) 18+ only, Gemini on | Clean under Gemini's terms | Drops the student audience and the founders' peers; the account holder must still be an adult (R09) |
| (d) Vertex AI under Google Cloud terms held by an adult or entity | May allow teens | Minors clause unconfirmed; needs a lawyer read, a new account and engine work |

Steps for (a): remove Gemini from the proxy on Render (Michael, console); make cloud mode skip Gemini (Michael, part of
R03); hide the Gemini own-key field (Adrian, part of R07); the policy says lessons are built with Claude (R06).
Revisit (d) once R09's entity exists.
- **Verify:** Render's env has no Gemini model; `/admin/usage` shows no Gemini calls; a video lesson builds from
  its transcript.

### R14
**Progress and settings get lost.** Adrian, Michael · M · Before public launch (label before private beta)
1. E01 (Adrian): keep the random port (`app/src/main/serve.ts:81`) and move every durable choice (tips, sounds,
   dashboard goals, drawer side, player volume, the "no flow" flag) into main prefs (`common/prefs.ts:30`). Don't use a
   fixed loopback port: another local process could take it first, and the app would load that page with its
   privileged preload. A privileged custom scheme (`protocol.registerSchemesAsPrivileged`, then `protocol.handle`) is
   the alternative, only if YouTube embeds still play from it.
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
| **Unsigned public launch, then sign as soon as the LLC holds an Apple organization account** (recommended) | Doesn't hold the launch on the LLC, D-U-N-S (1-2 weeks) and enrollment | Open Anyway for everyone; every update re-asks permissions. Only acceptable if Test 1 passes on macOS 26 and 27 and step 3 ships |
| Signed and notarized public launch | One normal open; permissions survive updates; auto-update becomes possible; school IT can allow it | Waits for the LLC (R09), D-U-N-S and organization enrollment, then C11's config and Michael's matrix |
| A parent's individual Apple enrollment now | Signing in days | Puts that parent's name on Apple's developer indemnity (area B, `lawsuit-protection.md`). Not recommended |

**If Test 1 shows no Open Anyway on macOS 26 or 27, this becomes P0 and signing (with the LLC in front of it) moves
onto the critical path.**

1. The LLC enrolls as an organization (R09). Today, Michael can already run area C's entitlement test matrix on a copy of the bundled
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
5. After signing: electron-updater from the versioned releases (R08).
- **Depends on:** R09, R04.
- **Verify:** `spctl -a -vv` accepts the app and `stapler validate` passes; numpy imports in a lesson venv; an update
  from vN to vN+1 keeps Screen Recording.

### R16
**miyagi-cloud capacity and plan.** Michael · L · Before public launch (checks today)
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
**Undisclosed DuckDuckGo search in the coach.** Michael, Adrian · S · Before private beta
1. For the launch build, set `COACH_WEB=0` in the engine environment the app starts (Adrian, `app/src/main/localEngine.ts`
   env), unless the founders decide to keep web grounding.
2. If it stays: name DuckDuckGo and the fetched sites in the consent screen and the policy (R05, R06); send an honest
   user agent; strip home paths and usernames from the query; quote fetched page text to the model as untrusted data,
   never instructions (`server/coach/web.py:30-33, 128-134, 278-284`). Michael.
- **Verify:** with the launch build, an error on screen produces no request to `html.duckduckgo.com` (local proxy
  log).

### R18
**Capture takes more than the lesson needs.** Michael · L · Before public launch (window-only capture after) · lawyer before scaling
1. On the fallback capture path, black out (or don't capture) the private apps that the ScreenCaptureKit path
   excludes, and add Slack, WhatsApp, Signal, Mail and banking apps to the list (`server/screen/sck.py:31-34`,
   `reader.py:784-793, 921-947`).
2. Scrub secrets from code and files before upload: skip `.env*` and key files; replace `sk-ant-`, `AIza`,
   `sb_secret_`, JWTs, Bearer values and private keys in buffers, selections and the project scan; strip the home
   path (`server/lesson/workdir.py:39-93`, `server/coach/judge.py:100-111`).
3. A visible capture indicator and the pause control (R05).
4. The policy says exactly what is excluded and when, and claims no blackout the fallback doesn't do.
5. **Decision (D8):** capture only the editor and tutorial windows (a ScreenCaptureKit window filter) instead of the
   whole display. Recommended as the target, after launch.
- **Verify:** with a canary `.env` value and a password-manager window open, a local proxy log of a lesson shows
  neither.

### R19
**Windows download and `/live/`, both live today.** Adrian · S · Today

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
   download (needs R09).
6. Delete `miyagi-site/live/` today (D10). It holds old key fields and talks to the visitor's local engine from our
   domain.
- **Verify:** no Windows download on the site; the release says Mac only; `miyagi.study/live/` returns 404.

### R20
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
   month, paid by the LLC, also ends pausing), or a Google Desktop client with PKCE that hands the ID token to Supabase
   (free, about a day). Don't change `SUPABASE_URL` itself; it would sign everyone out. Then Search Console for
   miyagi.study and Verify Branding (needs R06 live). Michael, Adrian. Decision D15.
5. Until Supabase Pro: a daily heartbeat so the project doesn't pause.
- **Depends on:** R06, R09 (who pays).
- **Verify:** an unlisted Google account signs in; after branding the consent screen says "miyagi"; Supabase shows
  Active.

### R21
**No age gate, teen-safety or crisis safeguards.** Michael, Adrian · L · Before public launch
1. The gate, per the checklist in `privacy-review.md`: neutral month and year pickers before Google sign-in and
   before the app mints its install token (today `cloud.ts` mints at first launch), so nothing is stored first; no hint of the cutoff; generic failure copy; store only an age band (13-15, 16-17, 18+) and the
   month given. Under 13: a flag that survives restarts (app data and Keychain), the same message on every retry,
   sign out, and delete any session, install token and server rows (needs R28). 13-17: Claude only, no own key,
   high-privacy defaults, a parent or guardian accepts the terms.
2. Anthropic's safeguards: the AI disclosure (R05), Anthropic's child-safety system prompt in the coach and build
   prompts, a "report this answer" link, monitoring through R35's counts, and a short public COPPA and teen-safety
   statement on the site.
3. Teen safety (B20): keep the coach on the coding task; on self-harm language, stop coaching and show the 988 crisis
   line, in a way a click can't skip; never a friend, therapist or professional persona; critique the code and the
   steps, never a creator's honesty or skill; no "safe for kids" or accuracy claims (R36). Michael (coach prompts),
   Adrian (copy).
4. Market to "13 and up"; no middle-school outreach.
5. A lawyer reads Anthropic's Commercial Terms ("not for consumer use") against a consumer app.
- **Depends on:** D1, R28.
- **Verify:** an under-13 month and year is refused on every retry and after a relaunch; no birth date is stored; a
  test message with self-harm language gets the 988 card, not coaching.

### R22
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
- **Verify:** the shipped engine has no Bright Data path (`2db52c69` removed it) and no spoofed user agent (fails
  today: `server/coach/web.py:31`, see R17); no transcripts in the repo or on the cloud.

### R23
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

### R24
**No insurance.** Parent, founders · M · Before public launch, after R09
1. After the LLC exists and the P0 privacy fixes are in, buy one combined tech E&O, cyber and media policy, $1M,
   claims-made, through a broker (startup sellers include Vouch, Embroker, Corgi and Founder Shield). The LLC is the
   applicant; the parent signs; the founders answer the security questions.
2. Ask for the earliest retroactive date, no generative-AI exclusion, no "wrongful collection" exclusion (Corvus says
   informed consent and opt-out help, which R05 provides), copyright and trademark named, regulatory defense costs.
3. Disclose truthfully: teen users, screen capture sent to AI vendors, the Miyagi Labs name question. A misstatement
   can void the policy.
4. Never let it lapse; report every letter the day it arrives (the letter runbook in R34).
- **Depends on:** R09; R05 and R18 help with the exclusions.
- **Verify:** a bound policy in the LLC's name, effective before the public post.
- **Decision (D18):** buy it before launch (about $1,500-4,000 a year) or launch uninsured.

### R25
**Nobody holds clean title to the code.** Founders, parents, lawyer · S now, M with the LLC · this week, then before public launch
1. This week: a one-page interim founders' agreement signed by both founders and a parent each: one product for one
   future company, nobody licenses, sells or open-sources it alone, both will assign everything, the split vests,
   what happens if one leaves, ratify at 18. Stop merging outside pull requests; save the MLH, Devpost and SanD Hacks
   rules as PDFs; never squash git history (it's the proof of human authorship).
2. With the LLC (R09): each founder signs a present-tense assignment ("hereby assigns") of all miyagi code, designs,
   names, logos and domains, hackathon work included, in exchange for units, with four-year vesting, a one-year cliff
   and credit for earlier work; parents sign a joinder.
3. Outside contributions: signed assignments for substantive work (a parent co-signs for a minor), or revert and
   rewrite. Then "Copyright (c) 2026 [LLC]. All rights reserved." Don't add MIT or Apache casually; check MLH's
   public-code rule before making a repo private.
4. Each founder signs a short ratification within days of turning 18 (`later.md`).
- **Depends on:** R09 for steps 2-3.
- **Verify:** the signed agreement and assignments are on file; the repos carry the notice.

### R26
**One account controls releases; fake installers.** Adrian, Michael · M · Today (console), Before private beta (pinned URL)
1. Today (console): release immutability on `adrian-erlikhman/miyagi`; a passkey for the account's 2FA; publish
   with a fine-grained single-repo token and revoke broader tokens on the laptop.
2. Before private beta: pin the update card's installer URL to `https://github.com/adrian-erlikhman/miyagi/releases/download/`
   (`app/src/main/features/updates.ts:133-135`, `app/src/main/safeOpen.ts:26`) (A13).
3. Before public launch: one official download link and the SHA-256s on miyagi.study (`/download` or the footer), and
   "only download miyagi from miyagi.study" in the launch posts and `/help`.
4. After launch, not on the critical path: a signed `https://miyagi.study/update/latest.json` (Ed25519 key kept off
   GitHub, public key built into the app) with version, URL, sha256 and `minimumVersion`, the GitHub API only as a
   fallback (C01, C17). Never rename or move the release repo, or change the GitHub username, after the launch build
   ships, unless this is live.
- **Depends on:** R39 (domain verified) for step 4.
- **Verify:** the repo shows immutable releases; a test URL outside the release path isn't offered; the site lists
  the SHA-256s.

### R27
**One shared Anthropic key.** Michael · S · Before public launch
1. The proxy adds a per-install identifier (a prefix of the token hash, nothing personal) as `metadata.user_id` on
   every Anthropic call, so Anthropic can act on one user instead of the whole organization.
2. Keep the free-text goal and "Explain this" on coding topics (a short system-prompt rule and a refusal card).
3. A written plan for a suspended key: who contacts Anthropic, the status text users see, and a second key in a
   separate workspace ready to switch to.
- **Verify:** a proxied call in the staging logs carries `metadata.user_id`.

### R28
**Delete my data doesn't delete; no server deletion.** Adrian, Michael · M · Before public launch
1. The honest button copy is in R06 step 3 (before private beta).
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

### R29
**Spinners and builds with no way out.** Adrian, Michael · M · Before public launch
1. App (Adrian): a renderer watchdog (45-60 s after Check with no answer: clear the press, "No answer yet. Try again.",
   Check back on) (`renderer/src/core/ui/atoms.tsx:125-128`, `core/lesson.ts:385-388`). The socket heartbeat and the
   wake check landed after the area snapshot (`app/src/main/engine.ts:149, 279`); re-test R-E02 against the current
   build before building more.
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

### R30
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

### R31
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
11. Second display (#202 R10): when VS Code's window is on a non-primary display, say "Move VS Code to the main
    display" (the engine knows the window's bounds); later, follow the editor's display (`main/index.ts:61-62`,
    `features/player.ts:60`). Michael (engine), Adrian (card).
- **Verify:** Test 1 variants V1 to V9 pass; with VS Code on a second monitor, the card appears.

### R32
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

### R33
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

### R34
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
   through `scrub()` (R45).
6. A one-page incident runbook (who decides, notice templates, the 30-day California and 72-hour GDPR clocks), using
   the first-hour steps in `security.md`, rehearsed once with a no-downtime key rotation.
7. Both founders' git commit email set to the GitHub noreply address; no phone, school or city in replies; if a sender
   is under 13, answer once and delete the thread.
- **Verify:** a test email to each address arrives; `security.txt` returns 200; private reporting shows on both repos.

### R35
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

### R36
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

### R37
**macOS permission prompts.** Adrian, Michael · M · Before public launch
1. Mac tests: set the clock a month ahead (or wait) with a lesson running; run guided setup on the macOS 27.3 beta.
2. When capture is refused while the grant looks on, pause the lesson with a plain card ("macOS asks again about once
   a month. Click Allow, then come back.") instead of a black frame or a false "Not yet"; poll permissions during
   lessons (`app/src/main/permissions.ts:36-41`, `server/orchestrator/session.py:7038-7074`). Michael, Adrian.
3. Onboarding names the monthly alert before it appears; the Accessibility step is rewritten for 27.3, with a "+"
   fallback in System Settings; later, evaluate `SCContentSharingPicker`. Adrian.
- **Verify:** repro R-E05 shows the card.

### R38
**Download code gate.** Adrian · S · Before public launch

| Option | For | Against |
|---|---|---|
| **Keep it for the private beta, remove it on public launch morning** (recommended) | Marks "not yet" while R01 and R02 land | None, as long as it isn't treated as security |
| Remove it now | One less step for testers | Signals open launch before the spend controls are in |
| Keep it through launch and print the code in every post | — | A barrier HN and Product Hunt penalize |

Until then, one line saying what the code is ("miyagi is in private beta. Ask us for a code."). On launch morning,
link `releases/latest/download/<name>` directly (`miyagi-site/index.html:520-541`).
- **Verify:** a fresh browser downloads with no code on launch day.

### R39
**Personal accounts are single points of failure.** Adrian, Michael · S · Today
1. github.com/settings/pages: add miyagi.study, add the `_github-pages-challenge` TXT at Porkbun, verify; verify again
   under the org before any repo transfer. Adrian.
2. Porkbun: 2FA, auto-renew, a card that won't lapse, more years; once the LLC exists, push the domain to an LLC-owned
   Porkbun account (account-to-account works despite the transfer lock). Adrian.
3. Render: a second person with access (a Pro workspace, or shared credentials in a password manager) and a written
   kill-switch runbook. Michael.
- **Verify:** Pages shows the domain verified; Porkbun shows auto-renew; Adrian can open the Render service.

### R40
**Where miyagi is offered.** Founders, Michael · M · Before public launch

| Option | For | Against |
|---|---|---|
| **US first: block the EEA, UK, Switzerland and Anthropic's unsupported regions at the proxy, with a plain message; say so in the terms** (recommended) | Avoids GDPR representatives, a DPIA and the UK Children's Code until there's an entity | Turns away EU and UK visitors from the HN thread |
| Serve the EU and UK and comply | Bigger launch | Representatives, a DPIA, a full Art. 13 notice, the Children's Code for under-18s, Gemini paid-only |
| Serve everyone and do nothing | — | Exposure under GDPR, and a breach of Anthropic's regions policy |

Anthropic's unsupported and sanctioned regions are blocked in every option. Render passes no country header, so use
Cloudflare's `CF-IPCountry` once R12 puts Cloudflare in front, or a GeoIP lookup. Revisit with a lawyer after R09.
- **Verify:** a request from a blocked region gets the message.

### R41
**Creators' content in the public repo, no DMCA agent.** Michael, Adrian · M · Before public launch
1. Take third-party lesson content out of the public repo (`demo/cache/lessons/`, `evals/lesson/` fixtures that
   transcribe creators' code), or keep only our own examples; add `demo/cache/transcripts/` to `.gitignore`; scrub the
   team member's macOS username from fixture paths. History keeps old copies, so note that in the takedown policy.
   Michael.
2. Register a DMCA agent ($6 for 3 years at copyright.gov; it needs a name and address, so the LLC's, R09) and publish
   a takedown policy using copyright@ (R34). Adrian.
3. Every lesson shows the creator, channel, title and link; steps in our own words; no full transcripts or instructor
   code on screen; a creator opt-out and a per-video kill switch. Michael.
4. A fair-use review before charging (lawyer).
- **Verify:** a search of the repo for a known creator's code finds nothing; the DMCA directory lists miyagi.

### R42
**Site first screen, phones, embed.** Adrian · M · Before public launch
1. One plain sentence under the wordmark, visible without scrolling and not `aria-hidden` (R36's hero line;
   `index.html:420`).
2. Phones: "miyagi is a desktop app (mac)" with a copy-link button instead of the downloads (or #188's phone view).
3. The YouTube embed loads only on a click (or stills only), with nothing drawn over the player (`index.html:893-913`).
   This also settles the cookie-banner question (`cookies.md`).
4. Self-host three.js and Lenis, or add `integrity` hashes to the CDN imports.
- **Verify:** a phone screenshot shows the desktop-app note; no YouTube request
  before a click.

### R43
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

### R44
**Engine keeps running with no UI.** Michael, Adrian · M · Before public launch
1. Mac check (Michael): `kill -9` the app mid-lesson and watch the recording indicator and
   `pgrep -fl server.orchestrator.main`; on the launch build, quit mid-lesson, relaunch, and confirm no capture or
   Claude calls before a lesson starts (B09).
2. Engine (Michael): exit when the parent dies (`getppid()==1`, or an inherited pipe closes) and after N minutes with
   no client. App (Adrian): keep the pid file at quit and SIGKILL the group after about 3 s
   (`app/src/main/localEngine.ts:490-502, 719-729`, `main/index.ts:543-546`).
- **Verify:** after `kill -9` of the app, the engine is gone within a minute.

### R45
**Local logs keep questions, code and paths.** Michael, Adrian · M · Before public launch (`ORCH_RECORD=0` before private beta)
1. Mac check, then `~/miyagi` at 0700 and its files at 0600. Michael.
2. Rotate `engine.log` at 5 MB and cut it to metadata (no question text, OCR or payloads) (`server/orchestrator/hub.py:31-63`).
   Michael.
3. `ORCH_RECORD=0` in the shipped engine (`server/orchestrator/recorder.py:31-36`, the app's engine env). Adrian or
   Michael.
4. "Copy details" goes through `scrub()`, not only `redact()` (`app/src/main/localEngine.ts:215, 305`). Adrian.
5. Delete my data wipes these (R28).
- **Verify:** a 6 MB log rotates; Copy details shows `~` instead of the username.

### R46
**Keep secrets out of the repo and builds.** Michael, Adrian · S · Before public launch (settings today)
1. Today (Michael, repo admin): confirm secret scanning and push protection are on.
2. gitleaks in CI on every PR; a build-time check that refuses `sb_secret_` and any JWT with `role: service_role` in
   `MAIN_VITE_*` (`app/src/main/publicConfig.ts`); scan every release asset before upload. Adrian.
3. Scan the currently published Mac zip and Windows installer once.
- **Verify:** a test PR with a fake key fails CI.

### R47
**Fixed ports.** Adrian, Michael · M · Before public launch
1. Detect a foreign listener on 8787 and say so: "Another app is using miyagi's port (8787), often `wrangler dev`.
   Quit it and press Retry." Retry works without a relaunch (`app/src/main/localEngine.ts:683-688`,
   `features/errors/cards.tsx:112`). Adrian.
2. Later: a port chosen at launch with a handshake (Michael, engine; Adrian, app); fallback ports for the 47217
   sign-in loopback. The security side is R33.
- **Verify:** area C repros 6 and 7 (8787 and 47217 busy).

### R48
**Licenses and third-party notices.** Adrian, Michael · M · After launch
1. Choose a license for miyagi on purpose (or keep "all rights reserved"), after R25's IP assignment.
2. Generate THIRD_PARTY_NOTICES at build time (Vite 8 `build.license`, or `license-checker-rseidelsohn` or
   `cyclonedx-npm`, plus `pip-licenses`) for Mac and Windows, linked from Settings; ship `OFL.txt` with the font.
3. Mac check for Pillow's libimagequant (GPL-3.0) and GNU readline or gdbm in the bundled CPython; if found, this
   becomes P1.
- **Verify:** the notices file lists every shipped package.

### R49
**Site polish.** Adrian · M · After launch
1. Words first and 3D after; skip 3D on small or low-memory devices (D11).
2. Darker small text (`--m-ink-muted`), a skip link, an axe or Lighthouse pass (D12).
3. A download block after the story (D13).
- **Verify:** Lighthouse accessibility 90+; words visible before the 3D loads.

## Decisions only Adrian and Michael can make

The six the brief asked for come first. Each has its options and trade-offs in the row named.

| # | Decision | Recommendation | Risk |
|---|---|---|---|
| D1 | **Gemini's 18+ terms vs our 13+ gate** | Claude only for everyone at launch; keep 13+; Gemini off in the cloud and in Settings. Revisit Vertex AI once an entity holds the account | R13 |
| D2 | **The entity and who signs** | Form a manager-managed California LLC before public launch (a parent as sole manager, each founder's units held by a parent as CUTMA custodian), then move every account into it with the parent signing "for" the LLC. Until then open nothing new in anyone's own name, and don't move existing accounts to a parent (uncapped vendor indemnities). Which parent is the manager is the founders' and parents' call | R09 |
| D3 | **The Miyagi Labs name collision** | Drop every Karate Kid cue now; a clearance opinion before the public post; if it comes back high-risk, rebrand before posting, not after | R23 |
| D4 | **How lessons get transcripts (YouTube scraping)** | Keep the on-device fetch with the four limits for launch, after a short lawyer read; work toward creator-connected captions | R22 |
| D5 | **The Windows download** | Off the site for launch: "mac only for now. windows is next." | R19 |
| D6 | **The download code gate** | Keep it for the private beta; remove it on public launch morning, once R01 and R02 are live | R38 |
| D7 | Signed or unsigned public launch | Unsigned, if Test 1 passes on macOS 26 and 27 and the first-launch capture check ships; sign as soon as the LLC holds an Apple organization account. Not a parent's individual enrollment | R15 |
| D8 | Capture scope | Editor and tutorial windows only, as the post-launch target; before launch, exclude private apps on every path and scrub secrets | R18 |
| D9 | Where miyagi is offered | US first; block the EEA, UK, Switzerland and Anthropic's unsupported regions at the proxy; revisit with an entity | R40 |
| D10 | Account link on sign-out | Unlink on sign-out | R28 |
| D11 | The shared lesson cache at launch | Not at launch | R11 |
| D12 | Own API keys (BYOK) | Hidden in the launch build; Anthropic only, adults only, once A04's fix ships | R07, R13 |
| D13 | How much miyagi may spend, and what happens when it's full | Prepaid credit, auto-reload off, sized to what the payer agrees to lose; per-install dollar caps at about 3× one measured lesson; a daily new-install cap ("full today, try tomorrow") instead of a fixed spend breaker, which would trip on a good launch day (at about $70 a day per 1,000 monthly users, a $100 breaker shuts out a busy launch); the kill switch kept for abuse | R01, R02 |
| D14 | Crash reporting | `/v1/crash` on miyagi-cloud, opt-in, fixed schema; no third-party SDK at launch | R35 |
| D15 | Paying for sign-in branding | Supabase Pro plus the custom domain (about $35 a month) if a parent will pay, since it also ends pausing; otherwise the free Desktop-client route | R20 |
| D16 | Posting account and dates | The founder account that passes `/showlim`; Show HN on a Sunday around 4-5 PM PT; Product Hunt a week later | R43 |
| D17 | Where disputes go | California courts with small claims, no arbitration (mass-arbitration fees run about $8,125 a campaign); a 30-day informal step first | R06 |
| D18 | Insurance before launch | Yes, bought by the LLC before the public post: claims-made policies don't cover acts before their start date | R24 |
| D19 | The coach's web search | Off in the launch build (`COACH_WEB=0`); turn it back on once it's disclosed and its page text is treated as untrusted | R17 |
| D20 | This register on the public repo | Your call. It aggregates weaknesses already in the public area files; exploitable details stay private either way. If you'd rather not, keep `RISKS.md` and `SOLUTIONS.md` off the public repo until R01, R02 and R12 land | — |

## Needs a lawyer

| Item | Why | When | Risk |
|---|---|---|---|
| The LLC: manager-managed with a parent as manager, CUTMA custodial units, operating agreement (indemnity of the manager and members, power to buy insurance, no meeting requirement), and who signs vendor terms. A free startup clinic can do it | Minors' capacity and personal liability decide everything else; the usual templates assume adult founders | Before public launch | R09 |
| Founders' agreement review, present-tense IP assignment with vesting and a parent joinder, contributor assignments, ratification at 18 | Nobody holds clean title to the code today | Agreement this week; the rest when the LLC forms | R25 |
| The warning text at the "Run it for me" button and on grades | Where a product warning has to sit to count | Before public launch | R11, R06 |
| Trademark clearance | Miyagi Labs likely has an earlier claim to the same name in the same space | Before the public post | R23 |
| One read of the final privacy policy and terms | Liability cap and warranty wording, minors' acceptance, the disputes clause, EU and UK rights | Before public launch | R06 |
| The YouTube transcript approach | Terms of Service and the 2026 anti-circumvention rulings | Before the public post, if D4 keeps on-device fetching | R22 |
| Anthropic's Commercial Terms ("not for consumer use") against a consumer app for teens | It's in the vendor contract we rely on most | Before public launch | R21 |
| The screen-capture consent flow | California's all-party consent law and Washington's health-data law are fact-specific, with private plaintiffs | Before scaling | R18, R05 |
| Fair use of the lesson format and any shared cache | Abridgement cases trend against substitutes | Before charging, or before the cache ships | R11, R41 |
| Gemini for under-18s | Only if D1 stays on Google for teens | If needed | R13 |
| An EU or UK launch, school deals, paid plans | Representatives and a DPIA; school data agreements; auto-renewal law | Later | R40 |

## Needs Michael's Mac or consoles

**Consoles**
- Anthropic: tier and real RPM, ITPM and OTPM for Sonnet 5.5 and Haiku 5.5; org spend limit; the proxy key in its own
  workspace with a limit and alerts; spend since the proxy went live (R02, R16).
- Google AI Studio and Cloud Billing: the tier behind `GEMINI_API_KEY`, a project spend cap, budget alerts, key
  restriction, logging (R02, R13).
- Render: instance type and disk; live `MAX_TOKENS_CAP`, `ALLOWED_*`, `PROXY_ENABLED` and whether
  `SUPABASE_JWT_SECRET` is set; the deployed commit; auto-deploy; members and 2FA; billing, card and bandwidth; the
  private-notes items (R02, R03, R12, R16, R20, R39).
- Supabase: plan and Active; providers; redirect URLs; tables and RLS; signing keys; rate limits; team and MFA (R20).
- Google Auth Platform: publishing status, scopes, Branding, Verification Center, a sign-in with an unlisted account
  (R20).
- GitHub (repo admin): secret scanning, push protection, private vulnerability reporting (R34, R46).

**Michael's Mac**
- One real lesson (a build plus about 40 minutes of work) through the proxy, its cost read on `/admin` (R01).
- Test 1 (R0 and V1 to V10) on clean macOS 15, 26 and 27 VMs, as admin and Standard users (R04, R31, R37).
- A pass over every main-process feature marked "UNVERIFIED in Electron", sign-in and the permission prompts first (R04).
- The engine-log grep and one cloud build at 4096 vs 32000 (R03).
- Grading repros R-E14 to R-E23 (R10, R32); R-E01, R-E02, R-E03, R-E09 (R14, R29); R-E05, R-E06 (R37, R15).
- Area C's entitlement test matrix, Mach-O inventory and `otool` check; an update test between two builds
  (permissions, Keychain, session) (R15).
- `kill -9` the app mid-lesson and watch capture (R44); `~/miyagi` file modes (R45); the private-notes checks (R07,
  R33).
- A staging Render service for the install-limit IP (R12); mitmproxy as the system proxy (R12, R31); ports 8787 and
  47217 busy (R47); cloud down, paused mid-build and Supabase unreachable (R30, R20).
