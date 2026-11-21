# Must be true before we post publicly

The five areas' launch checklists, merged and deduped. Each item links to its risk in [`RISKS.md`](RISKS.md); the steps
are in [`SOLUTIONS.md`](SOLUTIONS.md). Not legal advice.

- **Blockers** are the critical path: the P0 risks plus the launch-morning gates. Don't post until every one is ticked.
- **Should be true** are the P1 fixes planned for "before public launch". Posting with one open is a choice to make out
  loud, not by accident.
- Items that need Michael's Mac or a console say so in brackets.

## Blockers

### Money
- [ ] Anthropic: the proxy key in its own workspace with a monthly spend limit, an org limit below the tier cap, alerts
      to both founders' phones, auto-reload off. Gemini: paid tier, project spend cap, budget alerts, key restricted
      (or Gemini removed, per D1). [consoles] ([R02](RISKS.md#r02))
- [ ] miyagi-cloud enforces per-install, per-user and global caps, counted on the server and persisted, with a runtime
      kill switch and alerts; the private A02 and A22 fixes are in. ([R01](RISKS.md#r01))
- [ ] The kill-switch dollar line and the status text users see are written down. ([R01](RISKS.md#r01), D13)
- [ ] The install limit reads the real client IP on Render (staging test) or Cloudflare is in front; the per-IP limit
      is raised for classrooms, with plain copy when it trips. [Render] ([R12](RISKS.md#r12))

### Data and legal
- [ ] Before the macOS Screen Recording prompt, a screen says what's captured and that it goes to Anthropic through
      our server; the app says "miyagi's coach is AI. It can be wrong."; Settings > Privacy names the providers; the
      site no longer says "miyagi runs on your computer" and has the data line. ([R03](RISKS.md#r03))
- [ ] `miyagi.study/privacy` and `/terms` are live, linked from the site footer, the app's sign-in and Settings, and
      the Google consent screen; every miyagi.study link the app opens resolves; a first-run "I agree" step with its
      version and time saved; a parent or guardian accepts for under-18s. ([R04](RISKS.md#r04))
- [ ] The published policy was re-checked against the release commit (`facts.ts`, engine, cloud), and a lawyer has
      read the policy and terms. ([R04](RISKS.md#r04))
- [ ] The Gemini decision (D1) is made and implemented in the cloud, the engine and Settings. ([R09](RISKS.md#r09))
- [ ] An adult holds and pays for the Anthropic, Google Cloud, Render, Supabase and Porkbun accounts (and Apple, if
      signing), with their DPAs accepted; a lawyer consult on the entity is done. ([R11](RISKS.md#r11))
- [ ] *Placeholder* fixes A03 (companion 0.0.7) and A04 are in the launch build, checked against the private notes, or
      own-key fields are hidden until A04 ships. ([R08](RISKS.md#r08))

### Product
- [ ] On a curated lesson, correct work goes green: own names, random and typed-in output, a fixed-then-rerun error,
      a Terminal.app run; a deliberate real mistake is still caught. [Mac] ([R05](RISKS.md#r05))
- [ ] The coach can say "your code works", so a check bug never becomes a wrong instruction. ([R05](RISKS.md#r05))
- [ ] The token-cap question is answered from logs, and a cloud build of a 20-minute tutorial succeeds on a clean Mac
      with no key in Settings, one video lesson and one text lesson. [Mac, Render] ([R07](RISKS.md#r07))

### Release and install
- [ ] The public files are the launch build, under a versioned `vX.Y.Z` release with a `.dmg`, SHA-256s listed,
      scanned with gitleaks and VirusTotal, the version bumped and the engine SHA pinned in the notes.
      ([R06](RISKS.md#r06), [R10](RISKS.md#r10), [R41](RISKS.md#r41))
- [ ] Test 1 passed on clean macOS 15, 26 and 27 VMs (not just a new user account), downloaded from the live site and
      opened with our own written steps, all variants recorded; SHIP.md, the release body, the site tip and #188 match
      what really happened. [Mac] ([R06](RISKS.md#r06))
- [ ] A broken build can be fixed for people who already installed it: the update card works with a pinned installer
      URL, the signed manifest is on miyagi.study, and the cloud answers builds below the floor with "Update miyagi".
      ([R10](RISKS.md#r10))
- [ ] Release immutability on, 2FA with a passkey, a single-repo publishing token; uploads frozen from day -1 to day
      +3; no release moved, renamed or transferred after the launch build ships. ([R10](RISKS.md#r10))

### Launch morning
- [ ] Anyone can download without a code (the gate is off). ([R33](RISKS.md#r33))
- [ ] No Windows download on the site; the `windows` release says lessons need a Mac. ([R13](RISKS.md#r13))
- [ ] The name decision is made and every Karate Kid cue is gone ("waxon", "wax on, wax off"). ([R22](RISKS.md#r22))
- [ ] The posting HN account passes `/showlim`; the title, post, first comment and every reply are written by hand;
      both founders have the first 8-12 hours blocked, with roles. ([R38](RISKS.md#r38))
- [ ] T-30 minutes: monitors green, `/healthz` shows `proxy_enabled: true`, downloads work without a code, the inbox
      auto-reply is on. ([R30](RISKS.md#r30), [R29](RISKS.md#r29))

## Should be true

### Cloud and spend
- [ ] Render Starter or larger with the disk attached; auto-deploy off for launch week; a second person can reach the
      service and flip the kill switch. [Render] ([R16](RISKS.md#r16), [R34](RISKS.md#r34))
- [ ] Anthropic tier raised to Build or Scale; a mock-upstream load test passes; scene looks skip identical frames.
      ([R16](RISKS.md#r16))
- [ ] Capacity, provider-down and cloud-unreachable each show one calm message; a failed first mint retries on its
      own. ([R25](RISKS.md#r25))
- [ ] The cloud's default host is our own domain (`api.miyagi.study`), and the main process uses `net.fetch`.
      ([R12](RISKS.md#r12))
- [ ] The shared lesson cache isn't in the launch build (or A08 is fixed first). ([R20](RISKS.md#r20))

### Privacy and legal
- [ ] Private, messaging, mail and banking apps are excluded on every capture path; code and files are scrubbed of
      secrets before upload; a pause control and a capture indicator are visible. ([R17](RISKS.md#r17))
- [ ] The age gate is live: neutral month and year before sign-in, retry blocked across restarts, under-13 data
      deleted, only an age band stored; teens on Claude only; a public COPPA and teen-safety statement.
      ([R19](RISKS.md#r19))
- [ ] Delete my data does what it says: app erase, `DELETE /v1/me`, Supabase user deletion, retention limits, no
      `user=` in cloud logs, unlink on sign-out (D10). ([R23](RISKS.md#r23))
- [ ] The transcript decision (D4) is implemented: no Bright Data or spoofed user agent in the shipped engine, no
      transcripts stored, shared or committed, the creator credited in every lesson. ([R21](RISKS.md#r21))
- [ ] Anthropic's unsupported and sanctioned regions are blocked at the proxy, and the region decision (D9) is in the
      terms. ([R35](RISKS.md#r35))
- [ ] Third-party lesson content and team members' local paths are out of the public repo;
      `demo/cache/transcripts/` is ignored; a DMCA agent is registered and the takedown policy is published.
      ([R36](RISKS.md#r36))
- [ ] YouTube in the app: nothing drawn over the player, at least 200×200; the policy names YouTube API Services and
      links Google's Privacy Policy; the terms link YouTube's Terms. ([R28](RISKS.md#r28), [R04](RISKS.md#r04))

### Product
- [ ] The renderer origin is the same across relaunches: a dismissed tip stays dismissed after ⌘Q and reopen.
      ([R14](RISKS.md#r14))
- [ ] Continue opens a saved lesson at its saved step with the learner's files in place, for the current save, an
      ended one and a recent one; the hero lesson's folder survives an app update. ([R14](RISKS.md#r14))
- [ ] No spinner in the app outlives 60 s without a message and a way out; a build that fails or hangs after the
      placeholder ends in the build-failed card within 3 minutes. ([R24](RISKS.md#r24))
- [ ] A lesson keeps working after sleep and wake, and after the monthly Screen Recording re-prompt. [Mac]
      ([R24](RISKS.md#r24), [R32](RISKS.md#r32))
- [ ] Check works on a network that blocks api.anthropic.com; the first suggested lesson needs nothing a fresh Mac
      lacks; declining Accessibility doesn't lock Home. ([R26](RISKS.md#r26))
- [ ] On Check, the judge can't turn a failing machine check into a pass. ([R27](RISKS.md#r27))

### Release and install
- [ ] Signed and notarized (D7), or, if unsigned: after installing an update over an old build, the first lesson
      either works or the app says exactly how to re-grant. [Mac] ([R15](RISKS.md#r15))
- [ ] The site says school-managed Macs may not install miyagi, and the first-open steps match macOS 15 and later
      exactly. ([R15](RISKS.md#r15), [R06](RISKS.md#r06))
- [ ] miyagi.study is verified on GitHub Pages; Porkbun has 2FA, auto-renew and a card that won't lapse.
      ([R34](RISKS.md#r34))
- [ ] Google sign-in: the app is published "In production" and tested with an unlisted account, the consent screen is
      branded (or D15's free route), the button uses Google's colors, the wait mentions school accounts; Supabase on Pro
      or a heartbeat running; the Supabase console checked. [consoles] ([R18](RISKS.md#r18))

### Local security
- [ ] A05, A06, A12 and area C's app-to-engine item are fixed per the private notes; the YouTube player runs without
      the app bridge; Electron is on the latest 45.x. [Mac] ([R28](RISKS.md#r28))
- [ ] Mac checks done: capture stops when the app is killed, and the engine exits with it; no capture or model calls
      for a lesson the app didn't start. [Mac] ([R39](RISKS.md#r39))
- [ ] `~/miyagi` is 0700 with 0600 files; `engine.log` rotates and holds metadata only; `ORCH_RECORD=0`; Copy details
      is scrubbed. [Mac] ([R40](RISKS.md#r40))
- [ ] Secret scanning and push protection confirmed on; gitleaks runs in CI; a build check refuses secret Supabase
      keys. ([R41](RISKS.md#r41))
- [ ] The 8787 message names the other app and Retry works without a relaunch. ([R42](RISKS.md#r42))

### Site, support and launch
- [ ] support@, security@, privacy@ and copyright@ reach a shared team inbox with an auto-reply; SPF and DMARC
      published; no personal emails on the site. ([R29](RISKS.md#r29))
- [ ] SECURITY.md and private vulnerability reporting on both public repos; `security.txt` live; the incident runbook
      rehearsed once, including a key rotation with no downtime. ([R29](RISKS.md#r29))
- [ ] A bug form with no uploads and a "this is public" warning, `/help` with canned answers, a pinned "Known issues
      and status" issue. ([R29](RISKS.md#r29))
- [ ] Uptime monitors on `/healthz`, the site and the download; status subscriptions; some crash or error signal
      beyond email; server-side usage and setup-funnel counts with no content. ([R30](RISKS.md#r30))
- [ ] No crash or analytics SDK ships without the allowlist config, opt-in consent and a passing canary test.
      ([R30](RISKS.md#r30))
- [ ] The first screen says what miyagi is in one plain, screen-reader-visible sentence; phones get "miyagi is a
      desktop app"; `/live/` is gone; the story's YouTube embed loads only on a click; CDN imports have integrity
      hashes. ([R37](RISKS.md#r37))
- [ ] No "anything" or "any tutorial"; "type", not "say"; "checks each step" and "can be wrong"; "Free while in beta.
      Usage limits apply."; #188's claims checked. ([R31](RISKS.md#r31))
- [ ] The demo video is one honest take on a real tutorial, including a failed check; the site story is labeled an
      illustration; no DEMO-mode output shown as live. ([R31](RISKS.md#r31))
- [ ] Outreach asks for feedback, not votes, and carries a postal address and an opt-out. ([R38](RISKS.md#r38))

## Left off on purpose

These were on an area's checklist but wait until after launch:
- Third-party notices in every build (B): moved to P2, [R43](RISKS.md#r43). Missing permissive notices are rarely
  enforced; it becomes a blocker only if the Mac check finds GPL code in the bundle.
- Commented-out code and a missing call must not pass (E, part of the R-E21 repro): a false pass, [R27](RISKS.md#r27).
  Only the judge-overrule fix (E18) is kept above.
