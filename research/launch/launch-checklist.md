# Must be true before we post publicly

The five areas' launch checklists, merged and deduped, and matched to the final register (49 risks after the
independent review). Each item links to its risk in [`RISKS.md`](RISKS.md); the steps are in
[`SOLUTIONS.md`](SOLUTIONS.md). Not legal advice.

- **Blockers** are the critical path: the nine P0 risks, plus the gates the register holds the launch on (the grading
  gate R10, the install-limit test R12, the Gemini decision R13) and the launch-morning items. Don't post until every
  one is ticked.
- **Should be true** are the P1 fixes planned for "before public launch". Posting with one open is a choice to make out
  loud, not by accident.
- Items that need Michael's Mac or a console say so in brackets.

## Blockers

### Money
- [ ] Prepaid credit with auto-reload off on every provider, sized to what the payer agrees to lose; the proxy key in
      its own Anthropic workspace with a monthly limit, an org limit below the tier cap, and alerts to both founders'
      phones. Gemini on a paid tier with a project cap and budget alerts, or removed (D1). [consoles] ([R02](RISKS.md#r02))
- [ ] One real lesson's cost measured through the proxy; miyagi-cloud caps dollars per install and per user at about
      3× that, counted on the server and persisted, with a daily new-install cap, a runtime kill switch and alerts; the
      private A02 and A22 fixes are in. ([R01](RISKS.md#r01))
- [ ] The alert line, the new-install cap and the status text users see are written down (D13). ([R01](RISKS.md#r01))

### Data and legal
- [ ] Before the macOS Screen Recording prompt, a screen says the whole screen and the code go to Anthropic through our
      server (and anyone else per D1 and D19); the app says "miyagi's coach is AI. It can be wrong."; Settings >
      Privacy names the providers; the site no longer says "miyagi runs on your computer" and has the data line.
      ([R05](RISKS.md#r05))
- [ ] `miyagi.study/privacy` and `/terms` are live, linked from the site footer, the app's sign-in and Settings, and
      the Google consent screen; every miyagi.study link the app opens resolves; Delete my data says what it really
      deletes; a first-run "I agree" step with its version and time saved; a parent or guardian accepts separately for
      under-18s. ([R06](RISKS.md#r06))
- [ ] The published policy was re-checked against the release commit (`facts.ts`, engine, cloud), and a lawyer has
      read the policy and terms. ([R06](RISKS.md#r06))
- [ ] The LLC exists and holds the Anthropic, Google Cloud, Render, Supabase, GitHub and Porkbun accounts, a parent
      signing for it; nothing sits in a parent's own name; the policy names the LLC. ([R09](RISKS.md#r09))
- [ ] The Gemini decision (D1) is made and implemented in the cloud, the engine and Settings. ([R13](RISKS.md#r13))
- [ ] *Placeholder* fixes A03 (companion 0.0.7) and A04 are in the launch build, checked against the private notes,
      or own-key fields are hidden until A04 ships. ([R07](RISKS.md#r07))

### Product
- [ ] The proxy's token cap fits the builder, and one video lesson and one text lesson build through production
      miyagi-cloud on a clean Mac with no key in Settings; the engine log has no `hit max_tokens`. [Mac, Render]
      ([R03](RISKS.md#r03))
- [ ] **Grading gate:** the private beta ran on curated lessons, false fails were counted, and no correct step in those
      lessons stays red after a rerun (own names, random and typed-in output, a fixed-then-rerun error, a Terminal.app
      run); a deliberate real mistake is still caught; the coach can say "your code works". [Mac]
      ([R10](RISKS.md#r10))

### Release and install
- [ ] A frozen launch SHA for the app and the engine; CI runs the engine tests and the app checks on every PR, with no
      `|| true`. ([R04](RISKS.md#r04))
- [ ] The public files are the launch build, under a versioned `vX.Y.Z` release with a `.dmg`, SHA-256s listed,
      scanned with gitleaks and VirusTotal, the version bumped and the engine SHA pinned in the notes.
      ([R04](RISKS.md#r04), [R08](RISKS.md#r08), [R46](RISKS.md#r46))
- [ ] Test 1 passed on clean macOS 15, 26 and 27 VMs (not just a new user account), downloaded from the live site and
      opened with our own written steps, all variants recorded, and every "UNVERIFIED in Electron" feature run at least
      once; SHIP.md, the release body, the site tip and #188 match what really happened. [Mac] ([R04](RISKS.md#r04))
- [ ] The first build anyone outside installed already had the update card, the cloud's "Update miyagi" answer below a
      minimum version, and the cloud on `api.miyagi.study`. ([R08](RISKS.md#r08), [R12](RISKS.md#r12))
- [ ] The install limit was tested on a staging Render service and sees each client's own IP (or Cloudflare is in
      front); the per-network limit is raised, with plain copy when it trips. [Render] ([R12](RISKS.md#r12))
- [ ] Uploads frozen from day -1 to day +3; no release moved, renamed or transferred after the launch build ships.
      ([R08](RISKS.md#r08))

### Launch morning
- [ ] Anyone can download without a code (the gate is off). ([R38](RISKS.md#r38))
- [ ] The name decision is made and every Karate Kid cue is gone ("waxon", "wax on, wax off"). ([R23](RISKS.md#r23))
- [ ] The posting HN account passes `/showlim`; the title, post, first comment and every reply are written by hand;
      both founders have the first 8-12 hours blocked, with roles. ([R43](RISKS.md#r43))
- [ ] T-30 minutes: monitors green, `/healthz` shows `proxy_enabled: true`, downloads work without a code, the inbox
      auto-reply is on. ([R35](RISKS.md#r35), [R34](RISKS.md#r34))

## Should be true

### Today, already
- [x] No Windows download on the site; the `windows` release says lessons need a Mac; `/live/` is gone (site `67a40f0`, Nov 21).
      ([R19](RISKS.md#r19))
- [ ] Release immutability on, 2FA with a passkey, a single-repo publishing token. ([R26](RISKS.md#r26))
- [ ] miyagi.study is verified on GitHub Pages; Porkbun has 2FA and auto-renew; a second person can reach the Render
      service and flip the kill switch. [Render] ([R39](RISKS.md#r39))
- [ ] An interim founders' agreement is signed by both founders and a parent each. ([R25](RISKS.md#r25))

### Cloud and coach
- [ ] Render Starter or larger with the disk attached; auto-deploy off for launch week. [Render] ([R16](RISKS.md#r16))
- [ ] Anthropic tier raised to Build or Scale; a mock-upstream load test passes; scene looks skip identical frames.
      ([R16](RISKS.md#r16))
- [ ] Capacity, provider-down and cloud-unreachable each show one calm message; a failed first mint retries on its
      own. ([R30](RISKS.md#r30))
- [ ] The coach's web search is off in the launch build, or disclosed with an honest user agent and fetched pages
      treated as untrusted. ([R17](RISKS.md#r17))
- [ ] Every proxied call carries an anonymous per-install `metadata.user_id`; a plan exists for a suspended key.
      ([R27](RISKS.md#r27))
- [ ] "Run it for me" shows each command and asks first, blocks deletes, `sudo` and pipe-to-shell, installs only
      catalog packages; the shared lesson cache isn't in the launch build. ([R11](RISKS.md#r11))

### Privacy, legal and company
- [ ] Private, messaging, mail and banking apps are excluded on every capture path; code and open files are scrubbed
      of secrets before upload; a pause control and a capture indicator are visible. ([R18](RISKS.md#r18))
- [ ] The age gate is live: neutral month and year before sign-in and before the install token is minted, retry
      blocked across restarts, under-13 data deleted, only an age band stored; teens on Claude only; a 988 crisis card;
      a public COPPA and teen-safety statement. ([R21](RISKS.md#r21))
- [ ] Delete my data does it all: app erase, `DELETE /v1/me`, Supabase user deletion, retention limits, no `user=` in
      cloud logs, unlink on sign-out (D10). ([R28](RISKS.md#r28))
- [ ] The transcript decision (D4) is implemented: no spoofed user agent in the shipped engine, no transcripts stored,
      shared or committed, the creator credited in every lesson. ([R22](RISKS.md#r22))
- [ ] Insurance bound by the LLC before the post, with no AI or wrongful-collection exclusion (D18).
      ([R24](RISKS.md#r24))
- [ ] The operating agreement and each founder's IP assignment are signed; outside contributions are assigned or
      rewritten. ([R25](RISKS.md#r25))
- [ ] Anthropic's unsupported and sanctioned regions are blocked at the proxy, and the region decision (D9) is in the
      terms. ([R40](RISKS.md#r40))
- [ ] Third-party lesson content and team members' local paths are out of the public repo;
      `demo/cache/transcripts/` is ignored; a DMCA agent is registered and the takedown policy is published.
      ([R41](RISKS.md#r41))
- [ ] YouTube in the app: nothing drawn over the player, at least 200×200; the policy names YouTube API Services and
      links Google's Privacy Policy; the terms link YouTube's Terms. ([R33](RISKS.md#r33), [R06](RISKS.md#r06))

### Product
- [ ] Durable choices survive a relaunch: a dismissed tip stays dismissed after ⌘Q and reopen.
      ([R14](RISKS.md#r14))
- [ ] Continue opens a saved lesson at its saved step with the learner's files in place, for the current save, an
      ended one and a recent one; the hero lesson's folder survives an app update. ([R14](RISKS.md#r14))
- [ ] No spinner in the app outlives 60 s without a message and a way out; a build that fails or hangs after the
      placeholder ends in the build-failed card within 3 minutes. ([R29](RISKS.md#r29))
- [ ] A lesson keeps working after sleep and wake, and after the monthly Screen Recording re-prompt. [Mac]
      ([R29](RISKS.md#r29), [R37](RISKS.md#r37))
- [ ] Check works on a network that blocks api.anthropic.com; the first suggested lesson needs nothing a fresh Mac
      lacks; declining Accessibility doesn't lock Home. ([R31](RISKS.md#r31))
- [ ] On Check, the judge can't turn a failing machine check into a pass. ([R32](RISKS.md#r32))

### Release and install
- [ ] Unsigned with a first-launch capture check and re-grant steps (D7), or signed once the LLC holds an Apple
      organization account. [Mac] ([R15](RISKS.md#r15))
- [ ] The site says school-managed Macs may not install miyagi, and the first-open steps match macOS 15 and later
      exactly. ([R15](RISKS.md#r15), [R04](RISKS.md#r04))
- [ ] The update card's installer URL is pinned to our release path; one official download link and the SHA-256s are
      on miyagi.study. ([R26](RISKS.md#r26))
- [ ] Google sign-in: the app is published "In production" and tested with an unlisted account, the consent screen is
      branded (or D15's free route), the button uses Google's colors, the wait mentions school accounts; Supabase on Pro
      or a heartbeat running; the Supabase console checked. [consoles] ([R20](RISKS.md#r20))

### Local security
- [ ] A05, A06, A12 and area C's app-to-engine item are fixed per the private notes; the YouTube player runs without
      the app bridge; Electron is on the latest 45.x. [Mac] ([R33](RISKS.md#r33))
- [ ] Mac checks done: capture stops when the app is killed, and the engine exits with it; no capture or model calls
      for a lesson the app didn't start. [Mac] ([R44](RISKS.md#r44))
- [ ] `~/miyagi` is 0700 with 0600 files; `engine.log` rotates and holds metadata only; `ORCH_RECORD=0`; Copy details
      is scrubbed. [Mac] ([R45](RISKS.md#r45))
- [ ] Secret scanning and push protection confirmed on; gitleaks runs in CI; a build check refuses secret Supabase
      keys. ([R46](RISKS.md#r46))
- [ ] The 8787 message names the other app and Retry works without a relaunch. ([R47](RISKS.md#r47))

### Site, support and launch
- [ ] support@, security@, privacy@ and copyright@ reach a shared team inbox with an auto-reply; SPF and DMARC
      published; no personal emails on the site. ([R34](RISKS.md#r34))
- [ ] SECURITY.md and private vulnerability reporting on both public repos; `security.txt` live; the incident and
      letter runbook rehearsed once, including a key rotation with no downtime. ([R34](RISKS.md#r34))
- [ ] A bug form with no uploads and a "this is public" warning, `/help` with canned answers, a pinned "Known issues
      and status" issue. ([R34](RISKS.md#r34))
- [ ] Uptime monitors on `/healthz`, the site and the download; status subscriptions; some crash or error signal
      beyond email; server-side usage and setup-funnel counts with no content. ([R35](RISKS.md#r35))
- [ ] No crash or analytics SDK ships without the allowlist config, opt-in consent and a passing canary test.
      ([R35](RISKS.md#r35))
- [ ] The first screen says what miyagi is in one plain, screen-reader-visible sentence; phones get "miyagi is a
      desktop app"; the story's YouTube embed loads only on a click; CDN imports have integrity hashes.
      ([R42](RISKS.md#r42))
- [ ] No "anything" or "any tutorial"; "checks each step" and "can be wrong"; "Free while in beta. Usage limits
      apply."; #188's claims checked. ([R36](RISKS.md#r36))
- [ ] The demo video is one honest take on a real tutorial, including a failed check; the site story is labeled an
      illustration; no DEMO-mode output shown as live. ([R36](RISKS.md#r36))
- [ ] Outreach asks for feedback, not votes, and carries a postal address (a PO box or the LLC's) and an opt-out.
      ([R43](RISKS.md#r43))

## Left off on purpose

These were on an area's checklist but wait until after launch:
- Third-party notices in every build (B): moved to P2, [R48](RISKS.md#r48). Missing permissive notices are rarely
  enforced; it becomes a blocker only if the Mac check finds GPL code in the bundle.
- Commented-out code and a missing call must not pass (E, part of the R-E21 repro): a false pass, [R32](RISKS.md#r32).
  Only the judge-overrule fix (E18) is kept above.
- A signed update manifest on miyagi.study (C): after launch, [R26](RISKS.md#r26). Immutable releases, a passkey and
  the pinned installer URL cover the launch.
