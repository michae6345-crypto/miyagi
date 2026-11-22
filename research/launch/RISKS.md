# miyagi launch risks: the ranked register

One register for all five areas of Michael's launch-risk brief (Nov 21, 2026). It merges the 170 rows in
`security.md` (A01-A23), `privacy-legal.md` (B01-B21), `distribution.md` (C01-C44), `launch.md` (D01-D41) and
`product.md` (E01-E41), plus four risks the independent review found, into 49 risks, re-judges every severity, and
ranks them. The fix for each one is in [`SOLUTIONS.md`](SOLUTIONS.md). The pre-launch list is
[`launch-checklist.md`](launch-checklist.md), the parked items are in [`later.md`](later.md), and
[`risks.json`](risks.json) is the same register as data for the visual map.

- Built from the area files on `adrian/launch-risk` as of `ad1115fb` (Nov 21, 1:46 PM): area C's first full pass
  and area B's update (rows B18-B21, a corrected B07 and [`lawsuit-protection.md`](lawsuit-protection.md)). Rows that
  rest on C are marked **(C)**.
- Code: the area files read the app at `d959e0e9`/`958f58af` and the engine at `ddecb79c`/`b0659978`, and their line
  numbers come from there. During this pass the app moved to `736479ba` and the engine to `f91f0dde`; claims the
  review re-checked at those heads say so. Where two areas disagreed, the code was read again; see
  [Where the areas disagreed](#where-the-areas-disagreed).
- Offline only. Nothing was run against miyagi-cloud and no paid API was called.
- **Public repo.** Rows marked *placeholder* are exploitable today. Their details are only in Michael's private notes
  (sent on Nov 21 at 1:00 PM), and this file uses the same wording as `security.md`.
- Not legal advice. Rows that need a lawyer say so.

## How to read it

| Field | Meaning |
|---|---|
| Severity | **P0** only if it truly blocks launch, leaks user data, exposes a key, risks an unbounded bill or a likely lawsuit. **P1** if it hurts trust or conversion at launch. **P2** if it can wait. A row that is P1 today but turns P0 on a known condition says "P0 if". |
| Likelihood | **High**: happens at launch unless fixed (or is true today). **Medium**: needs a common trigger. **Low**: needs an unusual trigger or a motivated attacker. **Unknown**: a console or Mac check decides it. |
| Owner | Who does the fix. Engine and cloud work is Michael's (written as plans). App, companion and site work is Adrian's. "Founders" means a decision for both. |
| Phase | The deadline for the whole fix: Today, Before private beta, Before public launch, After launch. Earlier steps inside a fix are in `SOLUTIONS.md`. |
| Status | `open` (work to do), `partial` (some fix steps landed; see "Fixes so far" in `SOLUTIONS.md`), `check` (needs a console or Michael's Mac first), `decision` (founders choose first), `drafts` (text exists, not live), `verify` (fixed in code, needs a Mac check), `gate` (don't post publicly until it passes), `done` (shipped and checked). Statuses as of Nov 21, 9 PM. |
| Sources | The area rows merged into this risk. Every one of the 170 area rows is mapped in [Coverage](#coverage). |

## Top 10

| Rank | Risk | Sev | Why it's here | One-line solution | Owner |
|---|---|---|---|---|---|
| 1 | [R01](#r01) Anyone can use miyagi-cloud as free AI | P0 | Live today, from a public repo, and resold AI access is a known business (LLMjacking). Unbounded bill, then an outage for everyone | Measure one real lesson, then server-side dollar caps per install and per user, a daily new-install cap, a runtime kill switch and alerts | Michael |
| 2 | [R02](#r02) No provider spend caps or alerts | P0 | Until R01 ships, the provider side is the only brake, and nobody knows if it's set | Today: prepaid credit with auto-reload off as the hard stop, an Anthropic workspace limit and alerts, a Gemini cap | Michael |
| 3 | [R03](#r03) Lesson builds through miyagi-cloud likely fail | P0 | The proxy caps every reply at 4096 tokens while the builder asks for 32000, and the video model isn't allowlisted. It's the core flow for every learner without a key | Raise the cap (or lower the builder's ask) now with R02 as the backstop; match the allowlist to the Gemini decision | Michael |
| 4 | [R04](#r04) The launch build is untested | P0 | The public files are the old app, 14 main-process files say "UNVERIFIED in Electron" (sign-in, permissions), and CI runs no tests | Freeze a launch SHA, make CI run the tests, and run Test 1 plus a pass over every UNVERIFIED feature on clean macOS 15, 26 and 27 | Michael, Adrian |
| 5 | [R05](#r05) Learners aren't told before capture that their screen and code go to Anthropic | P0 | Undisclosed sharing of screen contents is the FTC and Recall problem, and Anthropic requires an AI disclosure | A plain consent screen before the Screen Recording prompt, an "AI, can be wrong" line, and the providers named in the app and on the site | Adrian, Michael |
| 6 | [R06](#r06) No live privacy policy or terms | P0 | The app already says users accept them and links to 404s, and "Delete everything on this Mac?" deletes only keys. CalOPPA applies from the first user | Publish the corrected drafts at `/privacy` and `/terms`, fix the app's links and the delete wording, add an "I agree" step | Adrian, Michael |
| 7 | [R07](#r07) *Placeholder:* companion configuration and engine key handling | P0 | Two private findings that can expose learner data or keys in the shipping companion and for learners with their own key | The fixes in the private notes: companion 0.0.7 and the engine change (or hide own-key fields until it ships) | Adrian, Michael |
| 8 | [R08](#r08) No way to get a fix to people who installed | P0 | Launch week is fix week, and today no fix reaches an installed copy | Versioned releases from one publisher, the update card, and a minimum-version answer from the cloud, in the first build outsiders install | Adrian, Michael |
| 9 | [R09](#r09) No company: the families carry the liability | P0 | Two minors are most likely a default partnership, personally liable, holding accounts with uncapped indemnities | Freeze and list accounts today; form a manager-managed LLC with a parent as manager; move every account into it | Founders, parents, lawyer |
| 10 | [R10](#r10) Correct work gets "Not yet", then the coach says to change working code | P1 | The top P1: the product's core claim failing in front of the launch thread. It's a gate, not a blocker | Beta on curated lessons only, count false fails; grade the newest output, check shape not literals, let the coach say "your code works" | Michael |

The top 10 is ranked by severity first, then by how likely it is and how much of the launch it takes down. There are
9 P0s, so the 10th is the top P1.

## What changed from the area files

- **55 area rows were P0 or "P0 if".** After merging duplicates, judging strictly and the independent review, **9
  risks are P0**, 38 are P1 and 2 are P2.
- **Moved down to P1**, with the reason in each row: grading false fails (E14-E17, now a measured gate), Gemini's
  terms (B02, C07, D20; "P0 if" the key is free tier), new installs refused (A07, C05; "P0 if" the staging test
  fails), "Run it for me" (B18), the age gate (B03), server-side deletion (B05), YouTube scraping (B06), the name
  (B08), the hidden-lesson capture (B09, fixed in code), Google sign-in (B10, corrected by C42), Windows (C06, D01),
  the Pages domain check (C10), update integrity (C01), the download code (D03), HN's Show limits (D15), the security
  contact (D27), crash-SDK defaults (D38, kept as a rule), lost progress (E01, E03, E29), stuck spinners (E02, E09),
  permissions lost on update (E06), the school-network check (E28), local access on shared Macs (A05), dev and demo
  engines (A06), the shared lesson cache (A08, kept as a gate) and the first signed build (C11).
- **Moved down to P2:** licenses and third-party notices (B16).
- **Moved into a P0:** "Delete everything on this Mac?" (A16's wording) joins R06, because it's the same false-promise
  problem as the policy.
- **Added by the review:** an untested launch build (folded into R04), no cost model behind the caps (folded into
  R01 and R02), the undisclosed DuckDuckGo search (R17), one shared Anthropic key (R27) and fake installers (folded
  into R26).
- **Merged:** for example R01 (A01, A02, A11, A22, C02, D18), R05 (B01, B11, D04), R08 (C15, C16, C18, C19, D31,
  D40) and R10 (seven grading rows). Each row lists its sources.

## Register summary

| R | Risk | Sev | Likelihood | Owner | Phase | Status | Sources |
|---|---|---|---|---|---|---|---|
| [R01](#r01) | Anyone can use miyagi-cloud as free AI | P0 | High | Michael | Before private beta | partial | A01, A02, A11, A22, C02, C38, D18 |
| [R02](#r02) | No provider spend caps or alerts | P0 | High | Michael | Today | partial | A10, C02, C27, D19 |
| [R03](#r03) | Cloud lesson builds likely fail | P0 | High | Michael | Before private beta | open | C03, C26, E08 |
| [R04](#r04) | Launch build untested (clean Mac, Electron, CI) | P0 | High | Michael, Adrian | Before private beta | open | C39, D02, D39, E38, E41 |
| [R05](#r05) | No consent before capture, no AI disclosure | P0 | High | Adrian, Michael | Before private beta | partial | B01, B11, D04 |
| [R06](#r06) | No live privacy policy or terms | P0 | High | Adrian, Michael | Before private beta | partial | A16, B04, B10, C31, D05 |
| [R07](#r07) | *Placeholder:* companion configuration and engine key handling | P0 | Medium | Adrian, Michael | Before private beta | partial | A03, A04 |
| [R08](#r08) | No fix path to installed users | P0 | High | Adrian, Michael | Before private beta | open | C15, C16, C18, C19, D31, D40 |
| [R09](#r09) | No company: families carry the liability | P0 | Medium | Founders, parents, lawyer | Before public launch | decision | B07, C12, C37 |
| [R10](#r10) | Correct work marked wrong | P1 | High | Michael | Before public launch | open | E14, E15, E16, E17, E20, E24, E25 |
| [R11](#r11) | One-click model-written commands; shared cache | P1 | Medium | Michael, Adrian | Before private beta | partial | A08, A19, B12, B18 |
| [R12](#r12) | New installs may be refused | P1 | Unknown | Michael, Adrian | Before private beta | partial | A07, A20, C05, C23, C38 |
| [R13](#r13) | Gemini terms vs teens | P1 | Medium | Founders, Michael, Adrian | Before private beta | decision | B02, C07, C08, D20 |
| [R14](#r14) | Progress and settings get lost | P1 | High | Adrian, Michael | Before public launch | open | E01, E03, E13, E29 |
| [R15](#r15) | Unsigned Mac app | P1 | High | Parent, Michael, Adrian | Before public launch | partial | C09, C11, C12, C13, E06 |
| [R16](#r16) | miyagi-cloud capacity and plan | P1 | Medium | Michael | Before public launch | partial | A23, C04, C21, C22, C24, C25, C41, D24, D25 |
| [R17](#r17) | Undisclosed DuckDuckGo search in the coach | P1 | High | Michael, Adrian | Before private beta | partial | the review |
| [R18](#r18) | Capture takes more than the lesson needs | P1 | High | Michael | Before public launch | partial | B01 |
| [R19](#r19) | Windows download and `/live/`, live today | P1 | High | Adrian | Today | done | C06, C37, C38, D01, D10, D14 |
| [R20](#r20) | Google sign-in and Supabase not launch-ready | P1 | Medium | Michael, Adrian | Before public launch | open | A18, B10, C29, C30, C31, C32, C42, D35 |
| [R21](#r21) | No age gate, teen-safety or crisis safeguards | P1 | Medium | Michael, Adrian | Before public launch | open | B03, B20, C28, C33 |
| [R22](#r22) | YouTube scraping | P1 | Medium | Founders, Michael | Before public launch | decision | B06 |
| [R23](#r23) | Name collision with Miyagi Labs | P1 | Medium | Founders, lawyer | Before public launch | decision | B08 |
| [R24](#r24) | No insurance | P1 | Medium | Parent, founders | Before public launch | decision | B21 |
| [R25](#r25) | Nobody holds clean title to the code | P1 | Medium | Founders, parents, lawyer | Before public launch | open | B16, B19 |
| [R26](#r26) | Release integrity and fake installers | P1 | Low | Adrian, Michael | Before private beta | open | A13, C01, C17 |
| [R27](#r27) | One shared Anthropic key | P1 | Medium | Michael | Before public launch | open | the review |
| [R28](#r28) | Delete my data; no server deletion | P1 | High | Adrian, Michael | Before public launch | partial | A16, B05 |
| [R29](#r29) | Spinners and builds with no way out | P1 | Medium | Adrian, Michael | Before public launch | partial | E02, E09, E10, E11 |
| [R30](#r30) | Raw or wrong errors when the cloud fails | P1 | High | Adrian, Michael | Before public launch | partial | C20, D25, E12, E40 |
| [R31](#r31) | First run on a real student's Mac | P1 | Medium | Adrian, Michael | Before public launch | open | E28, E30, E31, E32, E33, E34, E35, E36, E37, E39 |
| [R32](#r32) | Wrong work marked right | P1 | Medium | Michael | Before public launch | partial | E18, E19, E21, E22, E23 |
| [R33](#r33) | Local access hardening (mostly *placeholder*) | P1 | Low | Michael, Adrian | Before public launch | partial | A05, A06, A12, A14, C38, C40 |
| [R34](#r34) | No support, security or privacy contact | P1 | High | Adrian, Michael | Before public launch | open | A17, B17, C34, D06, D26, D27, D28 |
| [R35](#r35) | Launch-day blindness | P1 | High | Michael, Adrian | Before public launch | partial | C22, D21, D22, D23, D38, E04 |
| [R36](#r36) | Copy over-promises; cheating read | P1 | High | Adrian | Before public launch | open | B14, B15, D07, D14, D29, D30, D34, E26 |
| [R37](#r37) | macOS permission prompts | P1 | Medium | Adrian, Michael | Before public launch | check | C14, E05, E07 |
| [R38](#r38) | Download code gate | P1 | High | Adrian | Before public launch | open | D03 |
| [R39](#r39) | Personal accounts are single points of failure | P1 | Low | Adrian, Michael | Today | open | C10, C22, C35 |
| [R40](#r40) | Where miyagi is offered | P1 | Medium | Founders, Michael | Before public launch | decision | B11, B13 |
| [R41](#r41) | Creators' content in the repo, no DMCA agent | P1 | Low | Michael, Adrian | Before public launch | open | B12 |
| [R42](#r42) | Site doesn't say what miyagi is | P1 | High | Adrian | Before public launch | partial | D08, D09, D11 |
| [R43](#r43) | Launch channel rules | P1 | Medium | Founders | Before public launch | check | D15, D16, D17, D32, D33, D36 |
| [R44](#r44) | Engine keeps running with no UI | P1 | Low | Michael, Adrian | Before public launch | partial | A15, B09 |
| [R45](#r45) | Local logs keep questions, code and paths | P1 | High | Michael, Adrian | Before public launch | open | A21, D28 |
| [R46](#r46) | Keep secrets out of the repo and builds | P1 | Low | Michael, Adrian | Before public launch | open | A09 |
| [R47](#r47) | Fixed ports (8787, 47217) | P1 | Medium | Adrian, Michael | Before public launch | open | C36, D41 |
| [R48](#r48) | Licenses and third-party notices | P2 | Low | Adrian, Michael | After launch | open | B16 |
| [R49](#r49) | Site polish: load, accessibility, a second download button | P2 | Medium | Adrian | After launch | open | D11, D12, D13 |

## P0: blocks launch, leaks data, exposes a key, or an unbounded bill

### R01
**Anyone can use miyagi-cloud as free AI.** P0 · High · Michael · partial
- **Fix status (Nov 21, 9 PM):** Dollar caps per install, linked user, network and day, counted and reserved on the server, are in `claude/eng-proxy-sec2` (`cba57786`, via #222), which isn't deployed. Missing: a measured lesson, a daily new-install cap instead of the $25 global breaker, a runtime kill flag, alerts. One extra cap keys on the client-set `x-miyagi-role` header and stops normal lessons.
- **What goes wrong:** miyagi-cloud forwards Claude and Gemini calls for any install, and there is no server-side
  spend cap yet (C02). Area A holds more cost-control findings privately (A01, A02, A22). Stopping abuse takes a
  redeploy and nobody is told (A11). And nobody has measured what one real lesson costs through the proxy, so any cap
  is a guess: area C estimates about $0.50 a lesson, and scene looks alone can be up to 720 small Haiku calls an hour
  (`IL:server/orchestrator/scene_watch.py:77-78`). Caps set too low stop normal lessons, and a fixed daily breaker
  trips on a good launch day, so the kill switch itself becomes the outage. A busy launch day, or one person reselling
  access, can spend the provider caps in hours, and then every learner gets errors until the 1st of the month.
- **Evidence:** Sysdig LLMjacking ([May 6, 2024](https://sysdig.com/blog/llmjacking-stolen-cloud-credentials-used-in-new-ai-attack/), over $46k a day); a 3-person startup billed [$82,314](https://www.theregister.com/2026/03/03/gemini_api_key_82314_dollar_charge/) for an abused Gemini key (Mar 2026); Clicky's open proxy, [#34](https://github.com/farzaa/clicky/issues/34) (Apr 2026); cost per lesson in `distribution.md`.
- **Where:** `cloud/` on the live service (`/healthz` reports `proxy_enabled: true`); `cloud/app.py:60` (`PROXY_ENABLED` read at startup).
- **Why P0:** an unbounded bill on a service that is reachable today.

### R02
**No provider-side spend caps or alerts.** P0 · High · Michael · partial
- **Fix status (Nov 21, 9 PM):** Server-tool and cache-write prices landed (`cba57786`); Gemini prices are still placeholders, so the dollar caps undercount Gemini. The console steps are unconfirmed.
- **What goes wrong:** until R01 ships, the provider caps are the only brake, and nobody knows whether they are set.
  If they aren't, the first stop is the default tier cap (about $500 a month on Anthropic Start, about $250 on
  Gemini Tier 1), after which every learner gets 429 until the 1st. Gemini's project cap lags about 10 minutes, and
  Cloud budgets only alert. Nobody is paged when spend climbs; the admin page is pull-only. The proxy's own price
  table is wrong for Gemini (gemini-3.8-flash is $0.75 / $3.75 per 1M tokens, not $0.30 / $2.50, and it doubles on
  Jan 1, 2027), so `/admin/usage` under-reports **(C)**.
- **Evidence:** [Claude API rate and spend limits](https://platform.claude.com/docs/en/api/rate-limits) (a self-set limit answers 400, the tier cap 429); [Gemini billing](https://aistudio.google.com/docs/billing) (2026-03-23); [Gemini pricing](https://aistudio.google.com/docs/pricing).
- **Where:** the Anthropic Console, AI Studio and Cloud Billing; `cloud/app.py:76-86` (`PRICES`), `:494-561` (admin page).
- **Why P0:** it's the only thing between a leak and an unbounded bill today, and it is free and takes an hour.

### R03
**Lesson builds through miyagi-cloud likely fail.** P0 · High · Michael · open
- **Fix status (Nov 21, 9 PM):** Not addressed: `MAX_TOKENS_CAP` is still 4096 and the video model still isn't allowlisted.
- **What goes wrong:** the proxy cuts every Claude reply to 4096 output tokens, thinking included. The lesson builder
  asks for 32000 with adaptive thinking and raises on a cut reply; starter files ask for 16000. Video watching asks
  for `gemini-4-hydrogen`, which isn't on the proxy's allowlist (only `gemini-3.8-flash`), so every video lesson
  falls back to Claude reading a transcript (which raises R22) and videos with no captions fail. The build timings on
  file used direct keys, not the proxy. If the cap bites, a learner with no key of their own can't build a lesson
  from their own link.
- **Evidence:** checked Nov 21: `MAX_TOKENS_CAP` is `"4096"` in `cloud/render.yaml` on both `integration/live` and `claude/eng-proxy`, applied at `cloud/app.py:438` (`:476` on eng-proxy); `server/lesson/claude.py:173-176` asks for 32000 with adaptive thinking and `:225-226` raises on `max_tokens`; `server/lesson/gemini.py:25` defaults to `gemini-4-hydrogen`. [Anthropic: extended thinking and max_tokens](https://platform.claude.com/docs/en/api/errors).
- **Where:** `cloud/render.yaml:27-30`; `IL:server/workspace/scaffold.py:413`; `evals/lesson/report.md` (direct-key timings).
- **Why P0:** the configuration is certain, and it's the core flow for every learner without a key. One log grep
  or one build confirms it; neither is needed to start the fix.

### R04
**The launch build is untested: never installed on a clean Mac, much of it never run in Electron, and no tests in CI.** P0 · High · Michael, Adrian · open
- **Fix status (Nov 21, 9 PM):** Only the site's Mac tip changed (now Open Anyway). 15 main-process files still say UNVERIFIED (new code too), CI still runs no tests, and Test 1 hasn't run.
- **What goes wrong:** the public `mac` and `windows` releases are the pre-v2 app (`1b6ddcb`, Nov 19-20: no cloud,
  no sign-in, needs an Anthropic key), and `windows-sync/state.json` says `macVerified: false`: nobody has opened the
  public Mac file on a real Mac. In an Aug 2026 test on macOS 26.6.1, an ad-hoc-signed app launched from quarantine
  was offered only "Move to Trash"; whether Open Anyway still works for our build there is untested. Whether
  Gatekeeper lets the bundled Python's `.so` files run after Open Anyway is unknown (E38). A Standard (non-admin)
  school account may not get through at all (E41). SHIP.md and the release body describe steps that no longer exist
  (right-click > Open, ⌥Q) **(C)**. Beyond the install, 14 files in the app's main process say "UNVERIFIED in
  Electron", among them the Google sign-in round trip (`features/auth.ts:50`), the macOS permission prompts and
  relaunch (`features/onboarding.ts:48`) and the packaged build (`index.ts:415`). CI only typechecks and lints the app
  and runs `ruff ... || true` on the engine; no engine test or app check runs. `michael/v2-integration` took over 850
  commits in the week to Nov 21, and merge markers were once committed to it (`29ca3fd0`, "fix merge markers").
  (Found by the independent review.)
- **Evidence:** [Eclectic Light, Aug 11, 2026](https://eclecticlight.co/2026/08/11/how-can-you-run-code-that-hasnt-been-notarised/); [Apple, Aug 6, 2024](https://developer.apple.com/news/?id=saqachfa) (Control-click bypass removed).
- **Where:** releases on `adrian-erlikhman/miyagi`; `app/scripts/ship-mac.sh:55-57`; `app/SHIP.md`; `docs/CLEAN-TEST.md:11`; `.github/workflows/ci.yml:10-19`; the `UNVERIFIED` notes in `V2:app/src/main/`.
- **Why P0:** if the first open, sign-in or the permission flow fails on a real Mac, nobody gets in. None of it has
  been run end to end.

### R05
**Learners aren't told before capture that their screen and code go to Anthropic, and nothing says it's AI.** P0 · High · Adrian, Michael · partial
- **Fix status (Nov 21, 9 PM):** The privacy panel now names Anthropic, Google, Supabase and miyagi (`8e1522e5`). Still no consent screen, AI line or pause. New since the register: push-to-talk is on in the build (`PTT_ENABLED = true`), listening to the mic and the keyboard once granted, and nothing discloses it; Site v2's FAQ says what miyagi watches without saying it goes to Anthropic.
- **What goes wrong:** during a lesson the engine sends a 1280-px screenshot of the whole display, a crop around the
  cursor, screen text, the editor buffer (unsaved edits too), any "Explain this" selection and a scan of up to
  60,000 characters of lesson files to Anthropic through miyagi-cloud. Setup asks for Screen Recording without saying
  so. Settings > Privacy says only "Sent to the AI provider". The site says "miyagi runs on your computer." Nothing in
  the app or on the site says the coach is AI or that it can be wrong.
- **Evidence:** [FTC: AI companies, uphold your privacy and confidentiality commitments](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/01/ai-companies-uphold-your-privacy-confidentiality-commitments) (omissions count); [Anthropic Usage Policy](https://www.anthropic.com/legal/aup) (in-product AI disclosure, eff. 2026-11-12); Microsoft Recall made opt-in and pulled from launch ([Jun 7, 2024](https://blogs.windows.com/windowsexperience/2024/06/07/update-on-the-recall-preview-feature-for-copilot-pcs/)).
- **Where:** `V2:app/src/renderer/src/features/onboarding/steps.ts:23-24`; `V2:.../settings/sections/Privacy.tsx:65-66`; `miyagi-site/index.html:605`; `IL:server/coach/screen.py:326-331`; `IL:server/lesson/workdir.py:39-93`. Checked Nov 21: no onboarding file on `michael/v2-integration` names Anthropic, and no line says "can be wrong".
- **Why P0:** undisclosed sharing of whatever is on screen with a third party is the classic deception case, the first
  HN question, and a breach of a provider rule we must follow.

### R06
**No live privacy policy or terms.** P0 · High · Adrian, Michael · partial
- **Fix status (Nov 21, 9 PM):** The policy draft fixed three of the five review points (`8e1522e5`) but is unpublished; the panel's new policy link opens a 404; the draft claims an age step the app doesn't have. New: Site v2's FAQ says "you can delete your data any time in settings", which isn't true yet.
- **What goes wrong:** the sign-in screen says users accept the Terms and Privacy Policy and links to
  `miyagi.study/terms` and `/privacy`, which return 404, as do `/pricing`, `/teams` and `/account`. "Continue without
  an account" skips even the link, and there is no "I agree" step. CalOPPA requires a posted policy with no size
  threshold, and a policy that says what the code doesn't do is deception. The draft (#199, with suggested edits in
  #201) and `web/terms.md` exist, but the draft contradicts the code in places ("not linked to your name" is false
  once `/v1/link` ships; the YouTube player isn't disclosed; retention is [TBD] because the server can't delete).
  The app already makes one false promise of the same kind: Settings asks "Delete everything on this Mac?" but deletes
  only keys and prefs (A16; the server side is R28).
- **Evidence:** [Cal. Bus. & Prof. Code 22575](https://california.public.law/codes/ca_bus_and_prof_code_section_22575); [Google APIs Terms 3(d)](https://developers.google.com/terms); [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies) (the policy must name YouTube API Services); claim-by-claim check in [`privacy-review.md`](privacy-review.md).
- **Where:** `V2:app/src/renderer/src/features/auth/model.ts:22`; "By continuing you accept the Terms" at `V2:app/src/renderer/src/features/account/SignIn.tsx:77`; `app/src/main/features/account.ts:22-27`; `settings/sections/Privacy.tsx:80` and `main/features/settings.ts:168-180`; the site footer.
- **Why P0:** a legal requirement from the first user, already promised in the app.

### R07
***Placeholder:* VS Code companion configuration, and engine handling of learner-provided keys.** P0 · Medium · Adrian, Michael · partial
- **Fix status (Nov 21, 9 PM):** Companion 0.0.7 sends events only to this Mac (`b0e51c59`), and more launches strip secrets (`a61ef766`, `57118618`). Partial; the remaining gaps are in the private notes.
- **What goes wrong:** two findings held privately (A03, A04; sent to Michael on Nov 21). One is in the shipping
  VS Code companion (0.0.6), one affects learners who add their own key. Both can expose learner data or keys.
- **Evidence and where:** in the private notes. Checked Nov 21: `integration/live` still ships companion 0.0.6, so
  A03 is still open.
- **Why P0:** leaks user data or a key.

### R08
**No way to get a fix to people who installed.** P0 · High · Adrian, Michael · open
- **Fix status (Nov 21, 9 PM):** Not addressed: no versions, no update card in the build, no minimum-version answer from the cloud.
- **What goes wrong:** every build is `0.1.0`. Releases are a rolling `mac` tag uploaded with `--clobber` (no history
  or rollback, about 30 s of 404s per upload), fed from two places (the CI zip artifact from `main` and `ship-mac.sh`
  from any branch). The update card (#189, still open) needs a `.dmg` and a parseable version, so it can never offer
  anything today, and the 18 people who already downloaded have no update checker at all. There's no "update
  required" answer from the cloud, and Electron's auto-updater needs a signed app. So a launch-week fix can't reach
  anyone who installed, and old builds keep calling the cloud. Builds aren't reproducible (the engine is whatever
  `integration/live` is at build time), and the windows-sync agent can replace a public file mid-launch. The other
  half of the release channel, who can push a file to every install, is R26.
- **Evidence:** [Electron autoUpdater](https://www.electronjs.org/docs/latest/api/auto-updater) ("must be signed"); [gh release upload](https://cli.github.com/manual/gh_release_upload).
- **Where:** `app/scripts/ship-mac.sh:80-88`; `V2:app/src/renderer/src/features/updates/manifest.ts:185, 209, 217`; `app/package.json`; `.github/workflows/ci.yml` (artifact upload).
- **Why P0:** with R10, R03 and R07 open, launch-week fixes are certain, and today none of them would reach an
  installed copy. The first build outsiders install has to carry the update path, or those installs can never be
  reached.

### R09
**The founders are minors with no company, so their families carry the liability, and the vendor accounts have no proper holder.** P0 · Medium · Founders, parents, lawyer · decision
- **What goes wrong:** two people co-owning a project they plan to make money from are most likely a California
  partnership by default, each personally liable, and a minor is civilly liable for his own wrongs; a judgment can be
  collected for 10 to 20 years. Contracts a minor signs are voidable, and the vendors require 18+ or authority to
  bind (Gemini 18+, Apple the age of majority, Render no one under 16, Microsoft the age of majority, Anthropic and
  Google Cloud authority to bind). Whoever clicks "I agree" becomes the customer and owes the vendor's indemnities,
  and Anthropic's customer indemnity sits outside its liability cap, so moving the accounts into a parent's own name
  would put that parent on the hook for anything miyagi does. Apple's organization enrollment, and so a Developer ID
  in a company's name, needs an entity and a D-U-N-S number. The privacy policy has no proper "who runs miyagi".
- **Evidence:** [Cal. Corp. Code 16202](https://california.public.law/codes/corporations_code_section_16202) (default partnership); [Cal. Fam. Code 6600, 6710](https://california.public.law/codes/ca_fam_code_section_6710); [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (K.2 indemnity, excluded from the cap by L.3, per area B); [Apple enrollment](https://developer.apple.com/programs/enroll/); [`lawsuit-protection.md`](lawsuit-protection.md).
- **Where:** every vendor account (Anthropic, Google Cloud, Supabase, Render, GitHub, Porkbun), held by the founders
  today; no Apple account yet.
- **Why P0:** the families carry any bill or claim from the first user, which is personal exposure to an unbounded
  bill while R01 and R02 are open, and R06 (who operates miyagi), R15 (signing) and R24 (insurance) can't close
  without a company. (The Gemini age breach is counted in R13, not here.)

## P1: hurts trust or conversion at launch

### R10
**Correct work gets "Not yet", then the coach tells the learner to change working code.** P1 · High · Michael · open · a measured gate before public launch
- **Fix status (Nov 21, 9 PM):** Mostly not addressed. A ^C'd run no longer counts as an error and a run's output window ends at the next command line (`e06234a9`), but the "No errors" row still reads the whole visible terminal, the coach has no "looks correct" outcome, and E14, E16, E20, E24, E25 are untouched. New bug: a transient regex timeout drops a check from the saved lesson for good.
- **What goes wrong:** several checks fail correct learners. "No errors in the terminal" reads the whole visible
  terminal, so a learner who hits an error, fixes it and reruns still fails while the old traceback is on screen
  (E15). Run checks match the model's guessed last line exactly, so random numbers, `input()`, dates and floats fail
  (E14). Lesson-mode checks are token-exact, so typing your own name or renaming a function fails (E16). A run in
  Terminal.app, iTerm or Warp, or as `python3 -m`, never counts (E20). Fallback patterns cut at 80 characters can
  never match (about 17% of long lines, E24). A judge timeout reads as "Not yet" (E25). Then the coach, whose prompt
  assumes the code failed and has no "your code is fine" answer, tells a correct learner what to change (E17).
- **Evidence:** Khanmigo marked a correct answer wrong until it was entered three times ([Hechinger Report](https://hechingerreport.org/proof-points-combat-ai-hallucinations-math/), Aug 26, 2024); an offline probe of the engine's pure check functions reproduced E14-E16, E19-E21 and E24 (`product.md`).
- **Where:** `IL:server/checks/evaluator.py:534-549`; `IL:server/lesson/textlesson.py:782-791`; `IL:server/lesson/coverage.py:51-76, 220-330`; `IL:server/orchestrator/code_gate.py:150-208`; `IL:server/orchestrator/session.py:6892-6915`; `IL:server/lesson/builder.py:1249-1264`; `IL:server/coach/judge.py:142-149`; `IL:server/coach/diagnose.py:48-102`.
- **Why P1 (E said P0; this draft said P0 until the review):** "it told me my correct code was wrong" breaks the one
  claim miyagi makes and would be the top comment of the launch thread, but by the register's own rule that is a trust
  hit, not a blocked launch, a leak or a bill. How often it happens rests on an offline probe, not a measured rate.
  So it's the top P1 and a **gate**: run the private beta on curated lessons, count false fails, and don't post
  publicly until no correct step in those lessons stays red after a rerun.

### R11
**One-click commands written by a model from someone else's video, and a shared lesson cache that could feed them.** P1 · Medium · Michael, Adrian · partial
- **Fix status (Nov 21, 9 PM):** Mostly done on `integration/live` (`57118618`, `35cb1a17`): an engine-enforced confirm per command, an allow-list, no shell, refusals for metacharacters, `rm`, `sudo`, `curl` and paths outside the folder, a curated pip list, untrusted-text fencing. Missing: what an allowed command runs isn't checked (details private), no folder snapshot, off-list pip names install on a second press.
- **What goes wrong:** "Run it for me" runs a model-written shell command with one click: it types it into VS Code's
  terminal or runs it through `/bin/sh -c`, and the card says "Running it" only after the fact (checked Nov 21). The
  lesson text comes from a stranger's tutorial, so a video built to steer the model, or a model that simply gets a
  command wrong, can run something harmful on a learner's Mac, and the learner may be 15. No injection is even
  needed: a tutorial that says "run `curl ... | sh`" becomes a one-click step, and since the finder picks videos for
  the learner, an attacker only has to rank one. Package names the model proposes install with one press
  (`IL:server/workspace/setup.py:391-393`), which is how "slopsquatting" (registering a package name models
  hallucinate) reaches a Mac. Install names allow third-party Homebrew taps (A19). Courts now let design-defect claims against AI apps proceed, and an LLC doesn't
  shield the founder who built the feature (B18). The shared lesson cache on `claude/eng-proxy-cache` (not merged,
  no engine client on any branch) has a placeholder finding that must be fixed before it ships (A08), and its first
  upload, shaped by one learner's goal, becomes everyone's lesson (B12).
- **Evidence:** prompt injection to action is how the [Hacktron Cluely chain](https://hacktron.ai/blog/hacking-cluely) started (Feb 14, 2026); [OWASP LLM06:2025 excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/); Replit's agent deleted a live database ([The Register](https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident), Jul 2025); [`lawsuit-protection.md`](lawsuit-protection.md).
- **Where:** `IL:server/orchestrator/session.py:2401-2412, 7743-7778`; `IL:server/workspace/setup.py:40, 396-399`; `V2:app/src/renderer/src/features/cards/index.tsx:468, 528`; `EC:cloud/app.py:608-639`.
- **Why P1 (A19 said P1, B18 P0; the review said P1, Medium):** the harm needs a malicious or wrong command, not a
  normal lesson, and the fix is small, so it goes in before the private beta rather than up a level. It is the
  founders' largest personal-liability item (B18). **P0 if the cache merges before A08 is fixed.**

### R12
**New installs may be refused on launch day.** P1 · Unknown · Michael, Adrian · partial
- **Fix status (Nov 21, 9 PM):** Persisted mint limits, 20 an hour and 60 a day per network, in `cba57786` (not deployed). The staging check of the client IP isn't done; the app side is untouched.
- **What goes wrong:** `/v1/install` allows only a few new installs per network per hour (C05). A classroom, club or
  judging hall runs out quickly, and the app says "Couldn't set up access. Check your
  connection." Whether the limit reads the real client IP behind Render's proxy is unverified; if it doesn't, new
  installs could be refused for everyone. The cloud host is hard-coded as `miyagi-cloud.onrender.com`, which school
  filters often block, and the main process uses Node's `fetch`, which ignores the macOS proxy settings, so putting
  Cloudflare in front or moving hosts would need every user to update first.
- **Evidence:** Render doesn't document how it treats a client-sent `X-Forwarded-For` ([unofficial thread](https://feedback.render.com/features/p/send-the-correct-xforwardedfor)); [Electron net.fetch](https://www.electronjs.org/docs/latest/api/net) **(C)**.
- **Where:** `cloud/app.py:68, 222-239`; `app/src/main/features/cloud.ts:46` (`DEFAULT_CLOUD_URL`); Node `fetch` in `cloud.ts`, `auth.ts`, `updates.ts`.
- **Why P1 (A07 said "P0 until verified"):** treated like the other unverified rows. **P0 if the staging test shows
  the limit doesn't see each client's own IP**, because then nobody new gets in on launch day. The test is on the
  critical path; the fix may not be.

### R13
**Gemini's terms bar under-18 users and under-18 account holders.** P1 · Medium · Founders, Michael, Adrian · decision (today)
- **Fix status (Nov 21, 9 PM):** The cloud now narrows Gemini to YouTube-only file input (`cba57786`), but the decision isn't made and Gemini is still on.
- **What goes wrong:** the Gemini API Additional Terms say "You must be 18 years of age or older to use the APIs" and
  forbid use in an app "directed towards or is likely to be accessed by individuals under the age of 18". miyagi
  plans a 13+ gate, is built for students, and its founders are minors who hold the key. Through the proxy, Gemini
  gets the video URL, the learner's typed goal and the video's YouTube page text (never the screen or code). If the
  production key is on the free tier, those inputs can train Google's models and be read by human reviewers, and the
  free tier can't serve the EEA, UK or Switzerland. A breach can get the key or project suspended, which stops video
  builds for everyone. Settings also offers a Gemini own-key field.
- **Evidence:** [Gemini API Additional Terms](https://aistudio.google.com/docs/terms) (eff. 2026-03-23, read by four agents); [AI Studio logs policy](https://aistudio.google.com/docs/logs-policy).
- **Where:** `IL:server/lesson/gemini.py:312-335` (`watch_video`); `cloud/render.yaml:19-20, 27-28`; `V2:app/src/renderer/src/features/settings/keys.ts:15`.
- **Why P1 (B02, C07 and D20 said P0; this draft said P0 until the review):** the realistic cost of the breach is
  the Gemini key, and video builds already fall back to Claude when Gemini fails (R03). Through the cloud only the
  per-step detail pass reaches Gemini today (`gemini-3.8-flash`; the watch model isn't allowlisted). The account
  holders being minors is counted in R09. **P0 if the production key is on the free tier**, because then learners'
  inputs train Google's models. Decide today; it is one decision with R22 (where lessons come from without Gemini).

### R14
**Progress and settings get lost.** P1 · High · Adrian, Michael · open
- **What goes wrong:** the built app serves its windows from a new random port each launch, so everything kept in
  localStorage resets on every relaunch: goals, dismissed tips, sounds, drawer side, player volume, the live network
  view, and the "no flow" flag, so Home flashes a blank frame (E01, confirmed: `main/serve.ts:81` listens on port 0).
  Home's **Continue** on a lesson the learner ended, or one a newer lesson replaced, restarts at step 1 and moves the
  learner's files into a hidden `.miyagi-previous/<time>/` folder, and since Nov 21 Continue is the only way back
  (E03, suspected from code paths, one Mac repro needed). The hero PINN lesson keeps its folder inside the engine
  source, so the next app update wipes it (E29). The lesson cache is written in place, so a crash mid-write breaks
  every later build of that video (E13).
- **Evidence:** [MDN: localStorage is per origin](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage); Mimo and Duolingo churn over lost progress (`product.md`).
- **Where:** `V2:app/src/main/serve.ts:81`; `IL:server/orchestrator/main.py:743-786`; `IL:server/orchestrator/session.py:2108-2123`; `IL:server/workspace/paths.py:13, 71-92`; `IL:server/lesson/builder.py:258, 286`.
- **Why P1, not P0 (E said P0 for E01, E03, E29):** nothing leaves the Mac, lesson progress kept by the engine
  survives, and E03's files are moved, not deleted. It's the top P1 because lost progress is the loudest churn
  complaint in tutoring apps.

### R15
**The Mac app is unsigned.** P1 · High · Parent, Michael, Adrian · partial
- **Fix status (Nov 21, 9 PM):** Nine Electron fuses are in the build config (`f2ea2c21`); no signing or notarization, and the fuse test reads the config, not the built app.
- **What goes wrong:** no Developer ID and no notarization, so every install goes through Open Anyway (open the app,
  System Settings, Open Anyway within about an hour, password). Every ad-hoc update is a new app to macOS: Screen
  Recording is asked again, Accessibility silently stops, the Keychain likely prompts (Deny signs the learner out),
  and the engine may grade a black frame while the toggle still looks on. School MDM can't pre-grant Screen Recording
  for an ad-hoc app. The first Developer ID build will break as configured: `codesign --deep` never reaches
  `Contents/Resources`, the hardened runtime makes the bundled Python refuse pip-installed native wheels in lesson
  venvs, and electron-builder would sign every `.pyc` **(C)**. Electron fuses aren't set.
- **Evidence:** [Apple forum 795739](https://developer.apple.com/forums/thread/795739) (ad-hoc code has no stable designated requirement); [disable-library-validation](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation); [Apple PPPC payload](https://support.apple.com/guide/deployment/dep9ddb7e0b5/web).
- **Where:** `app/electron-builder.yml` (`identity: null`); `app/scripts/ship-mac.sh:56`; `app/SHIP.md` "Known gaps"; `main/features/updates.ts:2`.
- **Why P1 (E06 said P0, C13 P1):** the first install works if Test 1 (R04) shows Open Anyway still works, and an
  app-side check (a test capture on the first launch of a new version, then re-grant steps) makes updates
  recoverable. It becomes **P0 if Test 1 shows no Open Anyway on macOS 26 or 27**.

### R16
**miyagi-cloud capacity, provider tiers and plan.** P1 · Medium · Michael · partial
- **Fix status (Nov 21, 9 PM):** In-flight and body caps and a read timeout landed (`cba57786`, not deployed); SQLite still runs on the event loop and there's no load test.
- **What goes wrong:** the Render plan and disk are unconfirmed; on Free the service sleeps (the app gives up minting
  after 10 s) and every restart wipes all install tokens and usage (C04). It's one instance with a disk, so every
  deploy is downtime, and a modest number of simultaneous builds exhausts its upstream connections for everyone
  (C21). The default Anthropic tier caps spend at about $500 a month (about day 7 at 1,000 monthly
  users) and its per-minute limit holds about 90 learners at once on Start, because scene looks run every 5 s on
  Haiku; new orgs can start in an unpublished Evaluation tier with ramp limits (C24, D25). Anthropic posts an
  incident naming our models every 1 to 2 weeks (C25). Screenshots count as Render bandwidth (C41). One capacity item
  is held privately (A23) **(C)**.
- **Evidence:** [Render free instances](https://render.com/docs/free); [Render disks](https://render.com/docs/disks); [Anthropic rate limits](https://platform.claude.com/docs/en/api/rate-limits); [status.claude.com history](https://status.claude.com/history.rss).
- **Where:** `cloud/render.yaml:6` (`plan: starter`); `cloud/app.py` (`lifespan`, `forward`, `MAX_GEMINI_BODY`); `IL:server/orchestrator/scene_watch.py:77-79`.
- **Why P1:** a busy hour degrades into errors for everyone, but it recovers and R30 can say so plainly.
  **P0 if the live service is on Free.**

### R17
**The coach now searches DuckDuckGo and reads web pages by default, and nothing discloses it.** P1 · High · Michael, Adrian · partial
- **Fix status (Nov 21, 9 PM):** Fetched pages are fenced as untrusted and queries drop detected secrets (`e93c67ea`). Still on by default with a Chrome user agent, and typed questions go to DuckDuckGo too.
- **What goes wrong:** since `2db52c69` (on `integration/live`, after the area snapshots), the coach detects the
  library and symbol from any error on screen and searches DuckDuckGo's HTML endpoint with a Chrome browser user
  agent, then fetches docs and Stack Overflow, GitHub and Reddit pages and puts their text into the coach prompt. It's
  on unless `COACH_WEB=0`, and the app doesn't set it. So the error line on screen (paths include the macOS username)
  goes to a third party nobody has disclosed, the spoofed user agent repeats R22's problem, and stranger-written page
  text becomes coach input, a new prompt-injection path into R11. (Found by the independent review.)
- **Evidence:** [OWASP LLM01:2025 prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) (instructions in "a web page or file").
- **Where:** `IL:server/coach/web.py:30-33` (`DDG_URL`, `BROWSER_UA`), `:139-143` (on unless `COACH_WEB=0`); `IL:server/coach/README.md:184`; no `COACH_WEB` in `V2:app/src/`.
- **Why P1:** it's a small extra flow of error text, not screens or code. **P0 the moment a privacy policy that names
  only Anthropic goes live**, because then the policy is false.

### R18
**Screen capture takes more than the lesson needs.** P1 · High · Michael · partial · lawyer before scaling
- **Fix status (Nov 21, 9 PM):** Redaction now covers coach requests, screen text, selections, `.env` step files and secret rows in screenshots (`e93c67ea`). The project scan sent to lesson builds isn't redacted, the private-app list wasn't extended, and several key formats are missed (private).
- **What goes wrong:** the coach sends the whole primary display, not the editor and the tutorial. Password managers,
  Keychain and Messages are blacked out only when ScreenCaptureKit works; the fallback capture keeps them. Slack,
  WhatsApp, Signal, Mail and browsers are never excluded. Redaction is text-only (emails, SSNs, phones, card
  numbers). Code goes out with no secret scrubbing: the project scan skips dotfiles such as `.env`
  (`IL:server/lesson/workdir.py:85-87`), but secrets in `credentials.json`, YAML or `.py` files go, and so does any
  file open in the editor, `.env` included. Paths hold the macOS username.
- **Evidence:** [ICO statement on Recall](https://ico.org.uk/about-the-ico/media-centre/news-and-blogs/2024/05/statement-in-response-to-microsoft-recall-feature/) (May 2024); [Cal. Penal Code 631](https://california.public.law/codes/ca_penal_code_section_631) (all-party consent theory for other people's messages); [WA My Health My Data Act](https://app.leg.wa.gov/RCW/default.aspx?cite=19.373).
- **Where:** `IL:server/screen/reader.py:921-947`; `IL:server/screen/sck.py:31-34`; `IL:server/screen/privacy.py:12-42`; `IL:server/lesson/workdir.py:39-93`; `IL:server/coach/judge.py:100-111`.
- **Why P1 (B01 said P0):** once R05's consent ships, this is disclosed processing by our provider, not a leak. It's
  still the biggest trust question on launch day and the policy must not claim a blackout the fallback doesn't do.

### R19
**Two problems live on the site right now: a Windows download that can't run a lesson, and an old app build at `/live/`.** P1 · High · Adrian · done
- **Fix status (Nov 21, 9 PM):** **Done** (site `67a40f0`): the Windows button is off, `/live/` is deleted, phones and tablets see "runs on a Mac for now", the windows release says Mac-only, windows-sync `publishNext` is false. #188 still has Windows steps.
- **What goes wrong:** miyagi.study shows "download for windows" as an equal button, but the engine is macOS only
  (`localEngine.ts:214` returns "not macOS"), so a Windows install can't build or check a lesson. The installer is
  unsigned, and Smart App Control blocks it outright with no per-app override (it's on, enforcing, on Adrian's own
  laptop). The published Windows build is the pre-v2 app and has one more issue held privately (C38; P1 for today's
  build). Signing for a later Windows lane needs an entity (R09). Separately, `miyagi.study/live/` is an old web build
  of the app with key fields for Anthropic, Gemini, Bright Data, ElevenLabs and Tiger Data, and it opens a WebSocket to
  the visitor's own `localhost:8787` from our domain (D10; the engine side is held privately, R33).
- **Evidence:** [Smart App Control FAQ](https://support.microsoft.com/en-us/topic/what-is-smart-app-control-285ea03d-fa88-4d56-882e-6698afdb7003); [SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).
- **Where:** `miyagi-site/index.html:445`; `miyagi-site/live/`; the `windows` release (11 downloads); #188's Windows steps; `V2:app/src/main/localEngine.ts:214, 946`.
- **Why P1, not P0 (C06 and D01 said P0):** it doesn't block the Mac launch, leak data or start a lawsuit; it sends
  Windows visitors to a dead end and leaves a stale app on our domain. Both are live today and take minutes to fix,
  so they're in the Today plan.

### R20
**Google sign-in and Supabase aren't launch-ready.** P1 · Medium · Michael, Adrian · open
- **Fix status (Nov 21, 9 PM):** Not addressed, and worse: since `f2ea2c21`, pressing Cancel in Google sign-in leaves a silent 5-minute wait that ends in "ask to be added as a tester".
- **What goes wrong:** the Google consent screen will say "continue to `wssdpsdbaqtnfhoyimit.supabase.co`", which
  looks like phishing to a parent or school IT, and brand verification can't pass with that domain. The app isn't
  published "In production", the privacy and terms pages are 404, the homepage links neither, the domain isn't in
  Search Console, and the one-color G button breaks Google's branding rules. School accounts designated under 18 are
  blocked by default, and miyagi then waits 5 minutes before "timed out". Supabase Free pauses after a week idle, and
  its console settings (providers, redirect URLs, RLS, signing keys) haven't been checked **(C)**.
- **Evidence:** [Manage App Audience](https://support.google.com/cloud/answer/15549945) (basic scopes are the exception to the test-user list); [brand verification](https://support.google.com/cloud/answer/15549049); [unconfigured apps for under-18 users](https://support.google.com/a/answer/13288950); [Supabase free project pausing](https://supabase.com/docs/guides/platform/free-project-pausing).
- **Where:** `V2:app/src/main/publicConfig.ts` (`SUPABASE_URL`); `features/account/ui.tsx` (`GoogleGlyph`); `main/features/auth.ts:157` ("Ask to be added as a tester").
- **Why P1 (B10 said P0):** sign-in is optional, and Testing mode doesn't block basic scopes (see the disagreements).
  **P0 the day sign-in becomes required** (for example for the age gate or the spend budget).

### R21
**No age gate, teen-safety or crisis safeguards.** P1 · Medium · Michael, Adrian · open
- **Fix status (Nov 21, 9 PM):** Not addressed; the policy draft claims an age step that doesn't exist.
- **What goes wrong:** no branch asks for age (checked Nov 21: no age or birth-date code in the v2 app; the planned
  `michael/app-signin-gate` isn't on origin), though the policy draft says 13+. Anthropic lets an app serve minors
  only if it **must** disclose AI and **should** verify age, moderate, monitor and publish a COPPA statement, and it
  audits. Google's User Data Policy wants the age question before Google sign-in in a mixed-audience app. Anthropic's
  Commercial Terms say the service isn't for consumer use, which needs a legal read **(C)**. State attorneys general
  are suing AI chat apps over minors (Kentucky v. Character.AI, Jan 2026; eight states v. OpenAI, Oct 2026), and about
  40 of them listed what they expect, including crisis protocols that can't be clicked through; miyagi's coach has no
  crisis response (B20).
- **Evidence:** [16 CFR 312](https://www.ecfr.gov/current/title-16/part-312); [FTC COPPA FAQ](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions) (neutral age screen); [Anthropic guidelines for organizations serving minors](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors); AG suits in [`ai_product_liability.md`](privacy-legal/sources/ai_product_liability.md).
- **Where:** onboarding and sign-in (`V2:app/src/renderer/src/features/onboarding/`, `features/auth/`); the coach
  prompts (`IL:server/coach/`); `PV:web/privacy.md`.
- **Why P1 (B03 said P0, B20 P1):** COPPA turns on actual knowledge or a child-directed service, and miyagi is
  neither yet; the coach is a coding tutor, not a companion. **P0 if outreach reaches middle schools, or once anyone
  learns a user is under 13.**

### R22
**The engine scrapes YouTube for transcripts.** P1 · Medium · Founders, Michael · decision · lawyer if kept past beta
- **Fix status (Nov 21, 9 PM):** Bright Data is gone (`2db52c69`); browser user agents remain in five engine files, and the decision is open.
- **What goes wrong:** the engine fetches watch pages, caption tracks (`timedtext`, `youtube-transcript-api`, a
  browser user agent) and results pages from the learner's Mac, and sends the transcript to Anthropic when Gemini
  isn't used, which per R03 is every video build through the proxy today. Since Nov 21 the coach also searches
  DuckDuckGo with a Chrome user agent (R17). YouTube's Terms ban automated access, and
  since Oct 2026 courts have let creators' anti-circumvention claims proceed against yt-dlp-style scraping. YouTube
  can also simply block scripted caption fetches, which breaks builds.
- **Evidence:** [YouTube Terms of Service](https://www.youtube.com/t/terms); [§1201 rulings against ByteDance, Apple and Runway](https://openclassactions.com/lawsuits/runway-ai-youtube-video-scraping-dmca-class-action-lawsuit.php) (secondary).
- **Where:** `IL:server/lesson/transcript.py:3-7, 97-122`; `IL:server/finder/sources.py:78-85`; `IL:server/lesson/claude.py:368-398`.
- **Why P1 (B06 said P0):** it runs on the learner's own machine for a video they picked, at human scale, while the
  §1201 cases target bulk training-data scraping. The likely first consequence is a block or a letter, not a suit.
  It's one decision with R13: without Gemini, this is the only lesson source.

### R23
**Name collision: Miyagi Labs, and Karate Kid cues.** P1 · Medium · Founders, lawyer · decision
- **What goes wrong:** Miyagi Labs (YC W25, miyagilabs.ai) launched "AI to transform YouTube content into
  interactive courses", with its own Launch HN; its current one-liner is "AI tutors for exam prep". Same name, same
  students and the same HN audience, with likely earlier common-law rights, though no USPTO filing was found. The
  "waxon" download code and "wax on, wax off" invite a Sony false-association letter. There's no live MIYAGI mark in
  software or education.
- **Evidence:** [YC launch page](https://www.ycombinator.com/launches/Mr9-miyagi-labs-ai-to-transform-youtube-content-into-interactive-courses); [USPTO search](https://tmsearch.uspto.gov/search/search-results) (24 records, Nov 21).
- **Where:** the name everywhere; `miyagi-site/index.html` ("wax on, wax off", the "waxon" code).
- **Why P1 (B08 said P0):** the likely outcome is a letter once the launch gets attention, not a suit. But a forced
  rebrand costs far more after the public post, so the decision is on the critical path.

### R24
**No insurance, so the families pay for any defense.** P1 · Medium · Parent, founders · decision
- **What goes wrong:** with no policy, every letter or suit is paid for by the founders' families, and a parent's
  homeowner's policy excludes business liability. A combined tech E&O, cyber and media policy ($1M, claims-made) costs
  about $1,500-4,000 a year by sellers' estimates. Claims-made means only acts after the retroactive date are covered,
  so a policy bought after launch doesn't cover the launch. Even a good policy won't pay fines, punitive damages, most
  teen-harm claims or a fight between the founders, and AI and "wrongful collection" exclusions are spreading (B21).
- **Evidence:** [`insurance.md`](privacy-legal/sources/insurance.md); [NAIC on home-business coverage](https://content.naic.org/article/consumer-insight-working-home-your-insurance-coverage); [`lawsuit-protection.md`](lawsuit-protection.md).
- **Where:** nothing exists; the LLC (R09) would be the insured.
- **Why P1:** it changes who pays, not whether something goes wrong. It's a cost decision for the founders and
  parents, and it has to wait for the LLC.

### R25
**Nobody holds clean title to miyagi's code.** P1 · Medium · Founders, parents, lawyer · open
- **What goes wrong:** with no paperwork, each founder owns the code he wrote, the two are probably a partnership by
  default, either could walk off with his half or (if it's one joint work) license all of it to anyone, outside
  contributors keep rights in a repo with no license, and papers signed as minors stay voidable until ratified at 18.
  No repo has a license, a contributor agreement or a founders' agreement (B19, B16). The best-known student-founder
  suits were brought by an early collaborator with no written deal (Snapchat settled for $157.5M).
- **Evidence:** [17 U.S.C. 201, 204](https://www.law.cornell.edu/uscode/text/17/201); [Cal. Corp. Code 16202](https://california.public.law/codes/corporations_code_section_16202); [`founder_ip_disputes.md`](privacy-legal/sources/founder_ip_disputes.md).
- **Where:** both public repos; every merged outside pull request; the hackathon entries (MLH and Devpost terms).
- **Why P1:** it doesn't hurt users at launch, but it gets harder to fix the longer it waits, and the first step costs
  nothing.

### R26
**One personal account controls what every install is offered, and nothing tells a real download from a fake.** P1 · Low · Adrian, Michael · open
- **Fix status (Nov 21, 9 PM):** Not addressed: the update card still accepts any github.com installer URL.
- **What goes wrong:** the update channel trusts whoever controls `adrian-erlikhman/miyagi` or the token that
  publishes to it (the windows-sync agent publishes from this laptop): release immutability is off, the update card
  accepts any `github.com` URL, and the sha256 it shows comes from the same API as the file (A13, C01). Every build
  hardcodes that repo and asks the unauthenticated GitHub API, so a rename or transfer strands installs and a username
  change lets a stranger claim the path (C17). And an unsigned app, "Open Anyway" instructions and launch attention
  are the setup for trojanized "miyagi" downloads that users can't tell from ours (review).
- **Evidence:** [GitHub immutable releases](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/immutable-releases); five OVHcloud CLI releases hijacked ([Oct 20, 2026](https://thehackernews.com/2026/10/hackers-hijack-five-ovhcloud-cli.html)); [Doyensec on update signature bypasses](https://blog.doyensec.com/2020/02/24/electron-updater-update-signature-bypass.html).
- **Where:** `V2:app/src/renderer/src/features/updates/manifest.ts:54, 225`; `app/src/main/features/updates.ts:133-135`; `app/src/main/safeOpen.ts:26`; the repo's release settings.
- **Why P1 (C01 said P0, A13 P1):** nothing installs by itself, and the site download has the same exposure today.
  The console fixes are free and go today; the update card ships only with the pinned installer URL.

### R27
**One shared Anthropic key: a few abusive users could get miyagi suspended for everyone.** P1 · Medium · Michael · open
- **Fix status (Nov 21, 9 PM):** Not addressed: the cloud's request allowlist drops `metadata` and adds no user id.
- **What goes wrong:** every install's calls go out under one Anthropic organization key. Launch-day visitors will
  try to make a teen-built tutor say something worth a screenshot, through the free-text goal or "Explain this", and
  Anthropic's enforcement acts on the organization. Nothing tells Anthropic which end user sent a request (no
  `metadata.user_id` in `cloud/` or `server/`), so one bad actor looks like all of miyagi, and there's no backup plan.
  (Found by the independent review.)
- **Evidence:** [Anthropic Usage Policy](https://www.anthropic.com/legal/aup); [Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (responsible for all activity under the account).
- **Where:** `cloud/app.py` (the Anthropic route); `IL:server/lesson/claude.py`, `server/coach/` (no `user_id` metadata).
- **Why P1:** an enforcement action is unlikely in week one, but it would stop every lesson at once.

### R28
**Delete my data is misleading, and nothing can be deleted on the server.** P1 · High · Adrian, Michael · partial
- **Fix status (Nov 21, 9 PM):** Delete my data now removes the sign-in files and matches its copy (`8e1522e5`). No server delete on any cloud branch, `user=` still in cloud logs, and the cloud now keeps each token's minting network with no expiry.
- **What goes wrong:** the button asks "Delete everything on this Mac?" but removes only API keys and prefs. The
  learner stays signed in, the install stays linked to their account on the cloud, and lessons, transcripts, logs and
  file backups stay in `~/miyagi`. The cloud has no delete or retention for tokens, links, usage or builds, sign-out
  never unlinks, and log lines carry the Supabase user id. On a shared Mac the next person's usage is credited to the
  last learner.
- **Evidence:** [GDPR Art. 17](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng); [COPPA 312.10](https://www.ecfr.gov/current/title-16/section-312.10).
- **Where:** `V2:app/src/main/features/settings.ts:168-180`; `Privacy.tsx:39, 80`; `V2:app/src/main/features/cloudLink.ts:23-25, 128-134`; `EP:cloud/store.py:17-148`; `EP:cloud/app.py:161-162, 198`.
- **Why P1 (A16 said P1, B05 P0):** see the disagreements. **P0 if the policy promises deletion, if EU or UK users
  are served, or once the age gate has to delete an under-13 account.**

### R29
**Spinners and builds with no way out.** P1 · Medium · Adrian, Michael · partial
- **Fix status (Nov 21, 9 PM):** The app restarts a crashed or hung engine and handles sleep (`efb2ce41`); the engine drops a stalled client (`bb74206c`). No Check watchdog, model-call timeouts or build deadline.
- **What goes wrong:** "Checking" has no client timeout, so an engine that hangs leaves Check dead until quit (E02).
  Since the area snapshot the app gained a socket heartbeat that drops a half-open socket on sleep or a network change
  (`V2:app/src/main/engine.ts:279`), which covers part of E02; a hung engine that still answers pings isn't covered. After the 8 s placeholder step, nothing times out the
  rest of a build; if it fails, the learner sits on a placeholder that can never pass, and a quit saves it as the
  lesson (E09). The build bar sits at 95% from about 43 s while builds take 45 to 95 s (E10). Check waits silently
  behind any running Explain or Hint for up to 45 s (E11).
- **Where:** `V2:app/src/main/engine.ts:219-275`; `renderer/src/core/ui/atoms.tsx:125-128`; `IL:server/lesson/builder.py:78, 123-204`; `IL:server/orchestrator/modules.py:284-301`; `IL:server/orchestrator/main.py:110, 1031-1048`.
- **Why P1 (E said P0 for E02, E09):** End and quit are ways out and the triggers are narrower than a normal run. E09
  gets much more likely if R03 is real.

### R30
**When the cloud or a provider fails, learners see raw or wrong errors, and the first setup never retries.** P1 · High · Adrian, Michael · partial
- **Fix status (Nov 21, 9 PM):** The proxy returns fixed messages for credential, billing, rate and server errors (`cba57786`). A pause still blocks new installs, engine raw errors are untouched, and new technical refusal text reaches learners.
- **What goes wrong:** engine exceptions show as raw text ("check_step: KeyError ...", E12). Spend-limit, allowlist
  and 5xx errors pass through as provider text, and one shared rate limit hits everyone at once (D25). Paused, 429,
  502 and timeouts during a build all read "Couldn't read this video: both engines failed"; text lessons show the
  internal `miyagi_paused:` code; the kill switch also blocks `/v1/install`, so a pause reads "Check your
  connection"; a learner with their own key is still blocked when the mint fails (C20). The first mint has a 10 s
  timeout and only retries on Try again or the next engine connect (E40) **(C)**.
- **Where:** `IL:server/orchestrator/session.py:5570-5579`; `IL:server/lesson/builder.py:619-629`; `IL:server/config.py:248-252`; `V2:app/src/main/features/cloud.ts:38-46, 198-235, 256-259`; `rows.ts:106-108`.
- **Why P1:** every outage or cap becomes a confusing dead end, which reads as "broken" on launch day.

### R31
**First run on a real student's Mac.** P1 · Medium · Adrian, Michael · open
- **What goes wrong:** a school filter that blocks api.anthropic.com makes the engine decide it's offline, so Check
  waits for a network it doesn't need (E28; the app never sets `MIYAGI_NET_PROBE`). "You're ready" suggests whichever
  cached lesson is newest, and 7 of 8 need tools a fresh Mac lacks (E30). Declining Accessibility locks Home (E31).
  VS Code opened from Downloads reads as missing (E32). Answering No to VS Code's trust dialog quietly breaks the
  lesson's `.venv` (E33). Homebrew Python hits PEP 668 (E34). Read-only setup checks pop the developer-tools dialog
  and then call the stub "installed" (E35). The bundled Python has no tkinter or turtle (E36). A system proxy or PAC
  file reads as "No internet" and breaks the mint (E37). HTTPS from a lesson venv may fail certificate checks (E39). And the engine watches only the primary display, so
  VS Code dragged to a second monitor goes unseen and its checks and off-track judgement fail (#202 R10).
- **Where:** `IL:server/orchestrator/system_status.py:21, 48, 110`; `renderer/src/features/onboarding/store.ts:159-166`; `steps.ts:73-75`; `main/localEngine.ts:795-805`; `IL:server/workspace/setup.py:368-377, 680-721`; `app/scripts/bundle-engine.mjs:104-105`; `V2:app/src/main/index.ts:61-62` ("the engine watches the PRIMARY display only"), `features/player.ts:60`.
- **Why P1 (E28 said P0 for school networks):** each one stops part of the audience, not the launch, and most fixes
  are small. E28's fix is one env var, so it's on the checklist.

### R32
**Wrong work marked right.** P1 · Medium · Michael · partial
- **Fix status (Nov 21, 9 PM):** Small fixes (`e06234a9`); E18, E21, E22, E23 untouched. New bug: a regex timeout can pass a "no errors" row once.
- **What goes wrong:** pressing Check in a video lesson lets one Haiku call (confidence 0.6+) overrule failing machine
  checks, even with a traceback on screen, and text in the learner's file can count as evidence (E18). A run passes
  on any exit code 0 and output checks read the whole terminal, so an earlier correct run passes a wrong new one
  (E19). Commented-out code, code in a string or only the `def` pass the code gate (E21). Text read from any VS Code
  window (Copilot ghost text, the tutorial file) is latched as a pass, and "Code" also matches Xcode (E22). "Looks
  done?" then Yes skips the code gate (E23).
- **Evidence:** false passes harm learning more than false fails ([arXiv 2601.00765](https://arxiv.org/html/2601.00765v1), Jan 2026).
- **Where:** `IL:server/coach/judge.py:249-262`; `IL:server/orchestrator/terminal_run.py:62-67`; `IL:server/orchestrator/code_gate.py:176, 194`; `IL:server/orchestrator/session.py:5638-5660, 6692-6716`.
- **Why P1:** it hurts learning more than launch trust, except E18, which a reviewer will notice.

### R33
**Local access hardening for the engine, companion and app (mostly *placeholder*).** P1 · Low · Michael, Adrian · partial
- **Fix status (Nov 21, 9 PM):** Fuses, DevTools off and a debug-flag quit in the app (`f2ea2c21`); the engine's cloud URL is pinned and dev routes are gated (`fd443938`). The YouTube player still runs with the app bridge, Electron is still 45.3.2, and the rest is in the private notes.
- **What goes wrong:** held privately: engine and companion local access control (A05), engines started outside the
  app in dev and demo setups (A06), packaged-app configuration (A12), and one app-to-engine connection item (C38).
  Public: the YouTube IFrame API loader runs inside the app's own origin with the full `window.tut` bridge, so a
  compromised YouTube script could send engine commands (A14). The app is on Electron 45.3.2; 45.4.1 (Nov 18) carries
  Chromium and V8 security backports, and the app loads remote YouTube content (C40).
- **Evidence:** [Electron security checklist](https://www.electronjs.org/docs/latest/tutorial/security); [Electron 45.4.1](https://releases.electronjs.org/release/v45.4.1); localhost precedents: [CVE-2019-13450](https://nvd.nist.gov/vuln/detail/CVE-2019-13450), [CVE-2025-49596](https://nvd.nist.gov/vuln/detail/CVE-2025-49596).
- **Where:** `V2:app/src/renderer/src/features/player/youtube.ts:80`; `main/serve.ts:41`; `main/index.ts:84-90`; `preload/index.ts:23`; `app/package-lock.json`.
- **Why P1 (A05 said P0 on shared Macs, A06 P0 when used):** the common launch user isn't on a shared Mac or running
  a hand-started engine. **A06 is P0 for any demo at a venue.**

### R34
**No support, security or privacy contact.** P1 · High · Adrian, Michael · open
- **Fix status (Nov 21, 9 PM):** Not addressed. The site's early-access and "ask us" links open a founder's personal address: needs a domain address.
- **What goes wrong:** the only contacts on the site are two minors' personal Gmail addresses; miyagi.study has no MX,
  SPF or DMARC, so there's no support@ and anyone can spoof the domain (C34, D06). There's no in-app report, issue
  form or help page (D26). There's no `security.txt`, no SECURITY.md, and private vulnerability reporting is off on
  both public repos (A17, D27), and no breach plan with the legal clocks (B17). Public bug reports will carry
  learners' secrets in pasted logs and screenshots (D28).
- **Evidence:** [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116); [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository); 5,881 verified secrets in issue reports ([arXiv 2410.23657](https://arxiv.org/html/2410.23657v3)); [Cal. Civ. Code 1798.82](https://california.public.law/codes/ca_civ_code_section_1798.82).
- **Where:** `miyagi-site/index.html:476-489`; DNS for miyagi.study; both repos' security settings.
- **Why P1 (D27 said P0):** once R01 and R02 bound the bill, a public report is an embarrassment and a race, not an
  unbounded bill. The personal Gmails of minors on a launch page are a safety issue on their own.

### R35
**Launch-day blindness.** P1 · High · Michael, Adrian · partial
- **Fix status (Nov 21, 9 PM):** Opt-in counts and crash kinds, off by default and disclosed in the panel and policy (`5724db80`, merged though #221 is a draft). The cloud drops most event fields, events tie to the account, and there's no `unhandledRejection` handler or wire-level canary.
- **What goes wrong:** no crash upload, no usage counts and no uptime check, so on launch day nobody knows installs,
  activation, where setup stops or that the cloud is down (D21, D22, D23, E04). The app has no `unhandledRejection`
  handler and drops renderer errors in packaged builds. Adding Sentry or PostHog with default settings would upload
  screenshots, code, prompts, paths and IPs (D38, the Clicky mistake). Only Michael can see Render (C22).
- **Evidence:** [Sentry Electron options](https://docs.sentry.io/platforms/javascript/guides/electron/configuration/options/) (defaults collect); [Clicky #34](https://github.com/farzaa/clicky/issues/34).
- **Where:** `V2:app/src/main/features/errors.ts`; `cloud/app.py:494-561`; `/healthz`.
- **Why P1:** it doesn't break anything by itself; it makes every other failure slower to see. D38 is a rule, not a
  risk, until someone adds an SDK.

### R36
**Site and launch copy over-promise, the demo is scripted, and a screen-seeing tutor can read as a cheating tool.** P1 · High · Adrian · open
- **Fix status (Nov 21, 9 PM):** Not addressed, and wider: Site v2 says "turns any tutorial into a lesson", "any app on your screen" and "ask anything".
- **What goes wrong:** "ask for anything", "learn anything" and "any tutorial", while lessons are coding tutorials in
  VS Code on Apple-silicon Macs (D07). "It checks your work as you type" while R10 and R32 are open, and "say what
  you want to learn" while voice is off (D claims table, B14). #188's FAQ makes unverified claims ("install in 30
  seconds", "used only to guide your lesson") (D14). The site story is scripted and the demo lesson runs in DEMO mode
  (D29). "Free" with no conditions (D34). Lesson mode hands out full code early (E26). And Cluely's "cheat on
  everything" backlash and Recall show how a screen-seeing overlay gets read (D30, B15).
- **Evidence:** [FTC: keep your AI claims in check](https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check); Devin's month of real use, 3 of 20 tasks ([Answer.AI](https://www.answer.ai/posts/2025-01-08-devin), Jan 2025); [16 CFR 251.1](https://www.ecfr.gov/current/title-16/part-251).
- **Where:** `miyagi-site/index.html:604-611`; #188 `web/download/index.html`; launch posts.
- **Why P1:** reviewers test the claim, not the roadmap; an AI-capability claim with no measured number is also an
  FTC target.

### R37
**macOS permission prompts.** P1 · Medium · Adrian, Michael · check
- **What goes wrong:** macOS 15 and later re-ask for Screen Recording about once a month; the app's row still says
  granted while the engine meets a refusal, and the toast sends the learner to a switch that's already on (E05, C14).
  macOS 27.3 (beta, Nov 16) changes how Accessibility is granted, and on 27.3 beta 2 the capture request shows no
  prompt and doesn't list the app (E07, C14). Nobody publishes grant rates (E04).
- **Evidence:** [TidBITS, Aug 19, 2024](https://tidbits.com/2024/08/19/apple-reduces-excessive-sequoia-permission-requests-shifts-to-monthly); [Apple developer news, Nov 16, 2026](https://developer.apple.com/news?id=oqng0zjk); [Apple forum 858698](https://developer.apple.com/forums/thread/858698).
- **Where:** `main/permissions.ts:36-41`; `IL:server/screen/sck.py:41-48`; `IL:server/orchestrator/session.py:7038-7074`; onboarding copy.
- **Why P1:** it hits new installs on 27.3 and every learner monthly, with a confusing message.

### R38
**The download code gate.** P1 · High · Adrian · open
- **Fix status (Nov 21, 9 PM):** Unchanged: Site v2 keeps downloads behind early access.
- **What goes wrong:** the first click swaps the buttons for "enter the code to download", with nothing saying what
  the code is or how to get one. Show HN asks for no barriers, and Product Hunt doesn't feature closed betas. It
  isn't access control either: the code is guessable from the page and the releases are public on GitHub.
- **Evidence:** [Show HN guidelines](https://news.ycombinator.com/showhn.html) ("ideally without barriers such as signups or emails"); [Product Hunt featuring guidelines](https://help.producthunt.com/en/articles/9883485-product-hunt-featuring-guidelines).
- **Where:** `miyagi-site/index.html:520-541`.
- **Why P1 (D03 said P0 on launch day):** printing the code in the post, or removing the gate on launch morning, takes
  minutes.

### R39
**Personal accounts are single points of failure.** P1 · Low · Adrian, Michael · open
- **What goes wrong:** miyagi.study isn't verified with GitHub Pages, so during the planned repo move someone else
  could serve our domain and its download button (C10). The domain is on Adrian's personal Porkbun account and
  expires 2027-11-14 (C35). Render Hobby has one seat, so only Michael can flip the kill switch or rotate a key (C22)
  **(C)**.
- **Evidence:** [Verifying a Pages custom domain](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages); [Porkbun account push](https://kb.porkbun.com/article/72-how-to-push-a-domain-into-another-account).
- **Where:** DNS (no `_github-pages-challenge` TXT); Porkbun; Render workspace.
- **Why P1 (C10 said P0):** the takeover needs Pages to be unlinked while DNS still points at GitHub, which happens
  only during a transfer. All three fixes are console steps for today.

### R40
**Where miyagi is offered.** P1 · Medium · Founders · decision
- **What goes wrong:** the download is public with no region limit. GDPR and UK GDPR likely apply to EU and UK
  users of a screen-monitoring app, with EU and UK representatives, a DPIA, a full notice and the UK Children's Code
  for under-18s; Gemini is paid-only there (B13). Anthropic bars use from unsupported regions, and the proxy has no
  region check (B11).
- **Evidence:** [GDPR Art. 3, 27](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng) (Locatefamily fined €525k for no EU representative); [ICO Children's Code](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/); [Anthropic supported regions](https://www.anthropic.com/supported-countries).
- **Where:** `cloud/app.py` (no region check); terms and policy drafts.
- **Why P1:** enforcement against a free app run by minors is unlikely at launch, but HN brings EU users on day one.

### R41
**Creators' content sits in the public repo, and there's no DMCA agent.** P1 · Low · Michael, Adrian · open
- **What goes wrong:** committed lesson drafts and fixtures transcribe code from Bro Code, Tech With Tim and others,
  and the root `.gitignore` misses `demo/cache/transcripts/`. There's no registered DMCA agent or takedown policy, and
  attribution to the creator isn't guaranteed in lessons. A team member's macOS username sits in about 10 fixture
  paths.
- **Evidence:** [USCO DMCA agent FAQ](https://copyright.gov/dmca-directory/faq.html) ($6 for 3 years); Course Hero's loss mostly for stripped attribution ([secondary](https://www.thompsoncoburn.com/insights/education-platform-liability-in-the-ai-era-divergent-outcomes-for-quizlet-and-course-hero/)).
- **Where:** `IL:demo/cache/lessons/`; `IL:evals/lesson/`; root `.gitignore`.
- **Why P1:** a takedown or a creator's complaint is plausible once lessons are visible; the fix is cheap.

### R42
**The site doesn't say what miyagi is, and phones get desktop downloads.** P1 · High · Adrian · partial
- **Fix status (Nov 21, 9 PM):** Phones and tablets see "runs on a Mac for now" (#225), Site v2 has no YouTube embed so no consent question (`fbe3d6f`), and the CDN imports carry integrity hashes (`93b8df2`). The plain hero sentence is left.
- **What goes wrong:** the first screen is a 3D tree with "watching isn't learning", and the lines that describe
  miyagi are `aria-hidden`; on a phone it's the tree and "scroll" (D08). Phones get the desktop buttons and could
  download a 130 MB desktop file (D09). The YouTube embed in the story autoplays (muted) under a drawn cursor and
  callouts, which YouTube's API rules forbid and EU consent rules may catch (`cookies.md`). The CDN imports have no
  integrity hashes (D11). (`/live/` moved to R19.)
- **Evidence:** [YouTube required minimum functionality](https://developers.google.com/youtube/terms/required-minimum-functionality); [EDPB Guidelines 2/2023](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-22023-technical-scope-art-53-eprivacy-directive_en); [`cookies.md`](cookies.md).
- **Where:** `miyagi-site/index.html:420, 434-445, 893-913`.
- **Why P1:** visitors who can't tell what it is don't download, and Google's brand check wants a homepage that says
  what the app does.

### R43
**Launch channel rules.** P1 · Medium · Founders · check
- **What goes wrong:** HN is restricting Show HNs from accounts "who aren't yet familiar with the site" with no
  published threshold (D15). HN asks for no generated text, and most copy here is drafted with Claude (D16). Asking
  for votes, rings or mass DMs gets launches penalized, and friend reviews without disclosure are an FTC issue (D17).
  Two founders can't staff HN and Product Hunt on the same day (D32); link posts from small X accounts get little
  reach (D33); a launch can bring spam to the repo (D36).
- **Evidence:** [news.ycombinator.com/showlim](https://news.ycombinator.com/showlim); [HN guidelines](https://news.ycombinator.com/newsguidelines.html); [FTC Consumer Review Rule, 16 CFR 465](https://www.ecfr.gov/current/title-16/part-465).
- **Where:** the posting accounts; the outreach plan.
- **Why P1 (D15 said P0 for HN):** it can sink the HN channel, not the launch; X and Product Hunt remain.

### R44
**The engine keeps running with no UI.** P1 · Low · Michael, Adrian · partial
- **Fix status (Nov 21, 9 PM):** Restart now escalates to SIGKILL (`efb2ce41`). New bug: quit still sends plain SIGTERM and deletes the pid file, so a hung engine survives quit and the next launch can't reclaim it.
- **What goes wrong:** after a crash or force quit the engine keeps running, detached. Per the code, screen capture
  pauses 3 s after the app goes, but the file watcher, the VS Code poll, any build in flight (spend) and keys in
  memory stay alive until the next launch; a clean quit sends SIGTERM with no escalation (A15). B09 (the engine kept
  capturing for a lesson the app hid after a relaunch) is fixed in code, see the disagreements.
- **Where:** `V2:app/src/main/localEngine.ts` (at `736479ba` a stale engine is stopped with SIGTERM, then SIGKILL after 5 s, `:632`; a crashed app leaves its engine running until the next launch); `IL:server/orchestrator/session.py:4375, 4541-4554`; `V2:app/src/main/freshStart.ts`.
- **Why P1:** it would be P0 if capture kept going; the code says it doesn't, and a Mac check confirms it.

### R45
**Local logs keep questions, code and paths forever.** P1 · High · Michael, Adrian · open
- **Fix status (Nov 21, 9 PM):** Not addressed: the run recorder still defaults on.
- **What goes wrong:** `~/miyagi/engine/logs/engine.log` keeps the first 60 characters of every question and query,
  card titles, OCR'd code and failed payloads; it's append-only, never rotated and 0644 by default, and the run
  recorder is on by default. Keys and tokens aren't logged (A21). The engine's "Copy details" text goes through
  `redact()`, not `scrub()`, so the macOS username and possibly a Bearer value survive into what learners paste
  publicly (D28).
- **Evidence:** Clicky [#44](https://github.com/farzaa/clicky/issues/44) (logs held transcripts).
- **Where:** `IL:server/orchestrator/hub.py:31-63`; `IL:server/orchestrator/recorder.py:31-36`; `V2:app/src/main/localEngine.ts:215, 286, 305, 493`.
- **Why P1:** local only, but it's what a shared-Mac user or a public bug report exposes.

### R46
**Keep secrets out of the repo and the builds.** P1 · Low · Michael, Adrian · open
- **Fix status (Nov 21, 9 PM):** CI actions are pinned to commits (`a61ef766`); gitleaks, the build check and release scans are still missing.
- **What goes wrong:** a key committed to a public repo or built into an app is harvested within minutes. The Nov 21
  scan of all 1,907 commits, every branch and PR ref, the site repo, a fresh build and the Windows `app.asar` found
  nothing live, but nothing stops the next one: secret scanning and push protection are unconfirmed, there's no
  gitleaks in CI, no build check against a secret Supabase key, and the published Mac zip and Windows installer
  weren't scanned.
- **Evidence:** Clicky [#22](https://github.com/farzaa/clicky/issues/22) (an Anthropic key in the first commit); [Rabbit's timeline](https://rabbit.tech/security-investigation-062524); [GitHub supported secret patterns](https://docs.github.com/en/code-security/secret-scanning/introduction/supported-secret-scanning-patterns).
- **Where:** both repos' settings; `.github/workflows/`; `V2:app/src/main/publicConfig.ts`.
- **Why P1:** clean today; this is about keeping it that way during a fast launch with many agents committing.

### R47
**Fixed ports 8787 and 47217.** P1 · Medium · Adrian, Michael · open
- **What goes wrong:** port 8787 is also the default of Cloudflare's `wrangler dev`, which many HN readers run; the
  app then treats the listener as an external engine and tells a normal user to "Start the engine in Terminal" until
  relaunch (C36, D41). The security side is held privately (R33). A busy 47217 ends sign-in with no fallback.
- **Evidence:** [wrangler dev](https://developers.cloudflare.com/workers/wrangler/commands/workers/) ("localhost:8787").
- **Where:** `V2:app/src/main/localEngine.ts:406-411, 683-688`; `features/errors/cards.tsx:112`; `main/features/auth.ts:64` (`PORT = 47217`).
- **Why P1:** it stops a real slice of the HN audience with a wrong instruction.

## P2: can wait

### R48
**No license choice and no third-party notices.** P2 · Low · Adrian, Michael · open
- **What goes wrong:** neither public repo has a license, the companion is `UNLICENSED`, and no build ships the
  notices that MIT, BSD, Apache and OFL require (the Mac build drops node_modules LICENSE copies, the font ships
  without `OFL.txt`). No GPL, AGPL, SSPL, BUSL or CC-NC component was found in anything shipped; Pillow's optional
  libimagequant and GNU readline in the bundled CPython need a Mac check.
- **Evidence:** [`oss_license_inventory.md`](privacy-legal/sources/oss_license_inventory.md).
- **Why P2 (B16 said P1):** missing permissive notices are rarely enforced and fixed by a build step. Ownership
  between the founders moved to R25. **P1 if the Mac check finds GPL code in the bundle.**

### R49
**Site polish: first-load weight, accessibility, no download button after the story.** P2 · Medium · Adrian · open
- **What goes wrong:** about 300 KB and 1.2 MB of JS before the words show, with a 6 s fallback (D11); the hero lines
  are `aria-hidden`, small notes are 3.0:1 contrast, no skip link (D12); no download button after the 15-screen story
  (D13).
- **Evidence:** [WCAG 2.2](https://www.w3.org/TR/WCAG22/).
- **Why P2:** it costs some visitors on slow links and screen readers; lawsuit risk is low for a free, no-revenue
  site.

## Where the areas disagreed

| Question | One area | Another area | What the code or source says | Holds |
|---|---|---|---|---|
| Does Google's Testing mode block sign-in? | B10, brief: P0, can't leave Testing without a policy | C42: Testing doesn't block anyone for basic scopes | Google's Manage App Audience page makes name, email and profile "the only exception" to the test-user list; Supabase asks for email and profile only (no `scopes=` in `auth.ts`) | **C.** Confirm with one Google account not on the test list. Publishing and branding still need the policy (R20) |
| What does Gemini get? | B02: URL, goal and YouTube page text | D: YouTube links only (`server/config.py:243-245`) | `watch_video` sends the URL, puts the learner's goal in the prompt and adds the page's title, description and chapters (`IL:server/lesson/gemini.py:312-335`); text-only Gemini calls never go through the cloud (`gemini_text_ok`) | **Both, in part.** B on content; D that screen and code never go to Gemini |
| Does the engine still capture for a hidden, resumed lesson? | B09: likely, fix not on origin | E: `0d7de5ca` turns auto-resume off | `0d7de5ca` ("every launch starts fresh: no auto-resume unless ORCH_AUTO_RESUME=1") is merged into `integration/live` at `b0659978` (Nov 21, 12:24 PM); the app's `freshStart.ts` guard is on `michael/v2-integration` | **E.** Fixed in code; one Mac check on the launch build (R44) |
| How bad is update integrity? | A13: P1 (nothing installs itself) | C01: P0 (one account controls every install) | Both agree on the facts | **A.** P1 (R26). Its console fixes go today, and the update card ships only with the pinned installer URL |
| How bad is the missing security contact? | A17: P1 | D27: P0 (a public report means an unbounded bill) | The unbounded bill is R01 and R02 | **A**, once R01 and R02 are done |
| How bad is no server-side deletion? | A16: P1 | B05: P0 | CCPA's thresholds aren't met; GDPR applies only if EU or UK users are served (R40); COPPA retention applies to under-13 data, which the gate keeps out | **A**, with the P0 triggers in R28 |
| Do updates that drop permissions block launch? | E06: P0 until signed | C13: P1 | Both agree on the mechanism | **C**, if a first-launch test capture and re-grant steps ship before the first update (R15) |
| Is Windows a P0? | C06, D01: P0 | — | Strict rule: no lawsuit, no data, doesn't block the Mac launch | **P1**, fixed today (R19) |
| Is "Run it for me" a P0? | B18: P0 (design-defect exposure that an LLC doesn't shield) | A19: P1; the review: P1, Medium | It runs a model-written command with no preview (`IL:server/orchestrator/session.py:7743-7778`); harm needs a wrong or malicious command | **P1, Medium**, but done before the private beta (R11) |
| Which cloud is deployed? | A: `integration/live` (inferred) | D read `claude/eng-proxy` | `/healthz` reports `0.1.0` for every build, so it can't be told from outside | **Unknown.** Render console (R02, R16); A11's fix puts the commit in `/healthz` |
| Should a parent hold the vendor accounts now? | B07 (first version) and this register's first draft: yes, a parent holds and pays for them | B07 (corrected) and `lawsuit-protection.md`: no, form the LLC first | Whoever accepts the terms is the customer and owes the indemnities; area B reads Anthropic's customer indemnity (Commercial Terms K.2) as excluded from the cap (L.3) | **Corrected B07.** Freeze and list today, LLC first, then move the accounts (R09) |
| Does the app have a cloud client? | C's engine-cost notes, finding 2: no | C's own README: that finding read `app/` on the engine branch | `V2:app/src/main/features/cloud.ts` exists | **The README.** Finding 2 is ignored |

## Checked and doesn't apply

- **Traffic takes the site or downloads down (D37).** Under 1 MB a visit fits GitHub Pages' 100 GB soft limit many
  times over, and release assets have no bandwidth cap. Recheck only once miyagi charges (later.md).
- **Demo lessons replay a recorded run (E27).** DEMO shows only in a dev build or with a local flag; the packaged
  engine starts without `DEMO=1`.
- **Google's 100-user cap and 7-day refresh expiry (part of C42).** Apply only to sensitive scopes.
- **Leaked keys today (A09).** None found; R46 keeps it that way.

## Coverage

Every area row and where it went. "later" means [`later.md`](later.md).

| Area | Rows → risk |
|---|---|
| A | A01, A02, A11, A22 → R01 · A03, A04 → R07 · A05, A06, A12, A14 → R33 · A07, A20 → R12 · A08, A19 → R11 · A09 → R46 · A10 → R02 · A13 → R26 · A15 → R44 · A16 → R06, R28 · A17 → R34 · A18 → R20 · A21 → R45 · A23 → R16 |
| B | B01 → R05, R18 · B02 → R13 · B03 → R21 · B04 → R06 · B05 → R28 · B06 → R22 · B07 → R09 · B08 → R23 · B09 → R44 · B10 → R20, R06 · B11 → R05, R40 · B12 → R41, R11 · B13 → R40 · B14, B15 → R36 · B16 → R48, R25 · B17 → R34 · B18 → R11 · B19 → R25 · B20 → R21 · B21 → R24 |
| C | C01, C17 → R26 · C15, C16, C18, C19 → R08 · C02 → R01, R02 · C03, C26 → R03 · C04, C21, C24, C25, C41 → R16 · C05, C23 → R12 · C06 → R19 · C07, C08 → R13 · C09, C11, C12, C13 → R15 · C10, C35 → R39 · C14 → R37 · C20 → R30 · C22 → R16, R35, R39 · C27 → R02 · C28, C33 → R21 · C29, C30, C31, C32, C42 → R20 · C34 → R34 · C36 → R47 · C37 → R19, R09 · C38 → R01, R12, R19, R33 · C39 → R04 · C40 → R33 · C43, C44 → later |
| D | D01, D10, D14 → R19 · D02, D39 → R04 · D03 → R38 · D04 → R05 · D05 → R06 · D06, D26, D27, D28 → R34 · D07, D14, D29, D30, D34 → R36 · D08, D09 → R42 · D11 → R42, R49 · D12, D13 → R49 · D15, D16, D17, D32, D33, D36 → R43 · D18 → R01 · D19 → R02 · D20 → R13 · D21, D22, D23, D38 → R35 · D24 → R16 · D25 → R30, R16 · D28 → R45 · D31, D40 → R08 · D35 → R20 · D37 → checked · D41 → R47 |
| E | E01, E03, E13, E29 → R14 · E02, E09, E10, E11 → R29 · E04 → R35 · E05, E07 → R37 · E06 → R15 · E08 → R03 · E12, E40 → R30 · E14, E15, E16, E17, E20, E24, E25 → R10 · E18, E19, E21, E22, E23 → R32 · E26 → R36 · E27 → checked · E28, E30-E37, E39 → R31 · E38, E41 → R04 |

### From #202

The email agent's first pass (#202, branch `origin/adrian/michael-risk-list`) had its own ids. The left side is #202's
id; the right side is this register's risk, or `later` for [`later.md`](later.md), where each line carries its #202 tag.

| #202 file | Rows → risk |
|---|---|
| `docs/BUG-RISKS.md` | #202 R01 → R14 · R02 → R29 · R03 → later · R04 → R44 · R05 → later · R06 → R44 · R07 → later · R08 → later · R09 → later · R10 → R31 · R11 → later · R12 → R15 · R13 → R28 · R14 → R30 · R15 → R29 · R16 → later · R17 → later · R18 → later · R19 → later · R20 → later · R21 → later · R22 → later · R23 → later · R24 → later · R25 → later · R26 → R37 · R27 → later · R28 → R45 · R29 → later · R30 → later · R31 → later · R32 → R14 |
| `docs/legal/RISKS.md` | 1 Gemini terms → R13 · 2 minor founders, no entity → R09 · 3 YouTube scraping → R22 · 4 COPPA and the 13+ gate → R21 · 5 screen capture → R05, R18 · 6 policy truthfulness → R06 · 7 Anthropic usage policy → R05, R21, R40 · 8 Google OAuth → R20 · 9 Apple notarization → R15 · 10 DMCA agent → R41 · 11 trademark → R23 · 12 open-source licenses → R48 · 13 state privacy laws → later · 14 GDPR and UK GDPR → R40 · 15 site cookies → R42 · 16 FERPA → later · 17 AI output and the ToS → R06, R36 · 18 SB 243 → later |

## Review

After the first draft, a fresh reviewer got only this file, `SOLUTIONS.md` and the repo (not the area files and
not the drafting notes) and was asked to knock down the rankings and solutions and add missing risks. It checked 30
code claims against the branch heads: most held, four line numbers had moved, and three claims didn't hold. Below is
what changed and what didn't.

**Rankings it moved, and they moved**
- Cloud builds (R03) went from Unknown to High and from 7th to 3rd: the 4096 cap and the 32000 ask are both
  certain, so the grep confirms it and doesn't decide it.
- Grading false fails (R10) went from P0 to the top P1, as a measured gate before public launch. By the register's
  own rule it's a trust hit, and "most beginners" rested on an offline probe.
- Gemini's terms (R13) went from P0 to P1, "P0 if" the key is free tier. The engine already survives losing Gemini,
  and the minors-as-account-holders breach was being counted twice.
- New installs refused (R12) went from P0 to "P1, P0 if the staging test fails", the same treatment as other
  unverified rows. The test stays on the critical path.
- Release channel (R08) was split. The fix path stays P0 and moves to before private beta. Integrity became R26 (P1),
  and the signed manifest left the critical path.
- "Run it for me" (R11) went from Low to Medium likelihood and to before private beta. No injection is needed, and
  model-proposed package names install with one press.
- Windows and `/live/` (R19) moved to Today, because both are live now. `/live/` moved out of R42 so the phase fits.
- The misleading "Delete everything on this Mac?" moved into the P0 policy row (R06). The server half stays P1
  (R28).

**Solutions it fixed, and they changed**
- R01: the old cap table would have stopped normal lessons (scene looks alone run up to 720 an hour). The caps are now
  dollars, set from one measured lesson.
- D13: a fixed $100 daily breaker would trip on a good launch day. It's now a daily new-install cap, and R02's
  prepaid balance with auto-reload off comes first as the only real hard stop.
- R03: a per-role cap can't work, because the role header is set by the client. The token cap is raised now, with R02
  as the backstop, and R03 no longer waits for R01.
- R08 and R12: the update path and the own-domain cloud URL must be in the first build outsiders install.
- R14: the fixed loopback port option was dropped (another process could take the port). Durable choices move into
  main prefs.
- R05: the consent draft now says "whole screen", provider retention, the local log and any other recipient.
- R21: the age gate comes before the install-token mint.
- R29: the socket heartbeat landed after the snapshot; re-test first.
- R08: CI uploads a workflow artifact, not a release; the step was corrected.
- R18: the project scan skips dotfiles, but open editor buffers and non-dot secret files still go; the claim was
  corrected.
- Effort: R08, R16 and R21 are L, and R45 is M.

**Missing risks it found**
- An untested launch build: 14 "UNVERIFIED in Electron" features, no tests in CI, over 850 commits in a week. This is
  folded into R04, with a frozen SHA, CI tests and an UNVERIFIED pass.
- No cost model behind the caps: folded into R01 and R02.
- The undisclosed DuckDuckGo search: new on `integration/live` since the snapshot, R17.
- One shared Anthropic key with no per-user metadata: R27.
- Fake installers: folded into R26.

**What I kept, and why**
- R01 stays first and R02 second. The reviewer put R02 first, but the two are one money risk. R02 is the backstop
  and is first in the Today plan either way.
- The untested build and the cost model are folded into R04 and R01, not made into new P0 rows. The fixes are the
  same lanes, and separate rows would split them.
- R11 stays P1, not P0 as area B's B18 asked. The harm needs a wrong or malicious command, the area A row and the
  reviewer both said P1, and the fix lands before the beta anyway.
- The accounts stay where they are until the LLC exists. The reviewer suggested the private beta could run under a
  parent; area B's corrected B07 says moving accounts to a parent first only puts the parent on the hook in between.
- The reviewer suggested keeping this register off the public repo until R01, R02 and R12 land. It's pushed as the
  brief asked, because the facts it ranks are already in the public area files and the exploitable details stay
  private. The wording here was softened where it pointed at how to cause harm (the per-IP number, the pool size, the
  README hint). Whether to keep it public is decision D20.
- The reviewer also listed some security notes. They match items already in Michael's private notes (A01, A02, A05,
  A06, A22) and stay out of this file.
