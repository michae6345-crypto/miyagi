# Area B: privacy and legal

Launch-risk research for miyagi, area B of Michael's brief (v2, Nov 21 2026). **Not legal advice.** Written by AI
research agents for two founders who are not lawyers; rows marked "lawyer: yes" need a real one before strangers
install. Status as of 2026-11-21. Laws and vendor terms below changed often in 2025-2026; check the link before relying
on a line.

How this was made: seven research agents read primary sources (statutes, regulator guidance, court opinions, vendor
terms) and three agents read the code on `origin/integration/live` (engine, what the app bundles), `origin/michael/v2-integration`
(app, ships next), `origin/michael/app-privacy` (#199), `origin/claude/eng-proxy-auth` and `origin/claude/eng-proxy-cache`
(miyagi-cloud), `origin/claude/telemetry` and `origin/main`, plus the live miyagi.study. The email agent's first pass
(#202, `docs/legal/RISKS.md` on `origin/adrian/michael-risk-list`) was checked line by line and folded in. Full notes with
every source: [`privacy-legal/sources/`](privacy-legal/sources/).

Code shorthand: `IL:` = `origin/integration/live`, `V2:` = `origin/michael/v2-integration`, `PV:` = `origin/michael/app-privacy`,
`EP:` = `origin/claude/eng-proxy-auth`, `EC:` = `origin/claude/eng-proxy-cache`, `TL:` = `origin/claude/telemetry`.

Two security findings from the code read are not described here (README rule: exploitable details stay out of the public
repo until fixed). They are in area A's hands; see "Handed to area A" below.

## Verdict in one paragraph

The things most likely to get miyagi in real trouble are all in our own product, not in some obscure statute:
the screen capture sends whatever is on screen to Anthropic, Google's Gemini terms forbid an app like ours that teens
use, there is no age gate, no live privacy policy, no way to delete anyone's data on the server, the engine scrapes
YouTube, and nobody old enough to sign contracts owns the accounts. A small startup with no revenue is outside most
privacy statutes (CCPA, most state laws), but CalOPPA, the FTC Act, COPPA and the vendors' own terms apply from user one.
The name is a separate surprise: a YC company called Miyagi Labs launched "AI to turn YouTube content into interactive
courses".

## Register

Severity: **P0** = could leak data, expose a key, run up an unbounded bill, get us sued or block launch; **P1** = hurts
trust or conversion at launch; **P2** = later (one line each in "Later").

| id | area | risk | evidence (link) | applies to miyagi? (where) | severity | fix | owner | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | B | Screen capture sends whatever is on screen (passwords, keys, other people's messages, banking, health) and unredacted code and files to Anthropic. The Microsoft Recall lesson. | [Recall backlash, ICO inquiry](https://www.bbc.com/news/articles/cpwwqp6nx14o); CIPA [Penal Code 631](https://california.public.law/codes/ca_penal_code_section_631); [WA My Health My Data Act](https://app.leg.wa.gov/RCW/default.aspx?cite=19.373); [CJEU C-252/21](https://curia.europa.eu/juris/liste.jsf?num=C-252/21) (one sensitive item can taint a bulk capture) | **Applies.** Coach sends a 1280-px full-screen overview plus a cursor crop (`IL:server/coach/screen.py:326-331`, `IL:server/screen/reader.py:921-947`); private apps are excluded only on the ScreenCaptureKit path, not the fallback (`IL:server/screen/sck.py:31-34`); redaction is text-only (`IL:server/screen/privacy.py:12-42`); editor buffers, selections and a 60,000-char project scan go out with no secret scrubbing (`IL:server/lesson/workdir.py:39-93`, `IL:server/coach/judge.py:100-111`). Setup screens never say screenshots go to Anthropic (`V2:app/src/renderer/src/features/onboarding/steps.ts:23-24`). | P0 | Capture only the editor and tutorial windows; exclude password, messaging, mail and banking apps on every capture path; scrub secrets (`.env`, key patterns) from code and files before upload; visible capture indicator and pause hotkey; a plain consent screen before the macOS Screen Recording prompt; never store captures server side. | Michael (engine), Adrian (consent copy) | open |
| B02 | B | Google's Gemini API terms forbid users under 18 and any app "likely to be accessed by individuals under the age of 18"; account holder must be 18+. Free tier trains on inputs and lets humans read them; EEA/UK/CH must use paid. | [Gemini API Additional Terms, eff. 2026-03-23](https://aistudio.google.com/docs/terms) (verified by four agents independently); [AI Studio logs policy](https://aistudio.google.com/docs/logs-policy) (projects created on or after 2026-10-26 log prompts 55 days by default) | **Applies.** Lesson builds send the YouTube URL, the learner's goal and YouTube page text to Gemini (`IL:server/lesson/gemini.py:312-335`) via the proxy's own key (`EP:cloud/render.yaml:17-20`). 13+ gate planned, student audience, teen founders. Billing tier of the production key unknown (`IL:docs/PLAN.md:83`). Through the cloud only `gemini-3.8-flash` is allowed, so the video-watch model may already 404 and fall back to Claude reading a scraped transcript (`EP:cloud/README.md:230-239`). | P0 | Decide (founders): Claude only for everyone at launch, or Gemini only for verified 18+, or move to Vertex AI under Google Cloud terms held by an adult or entity (check those terms for a minors clause first). Whatever stays: billing-enabled project, AI Studio logging off or 7 days, never the free tier. The email agent's #202 claim is **confirmed**. | Founders decide; Michael (engine, cloud) | decision needed |
| B03 | B | No age gate exists anywhere. COPPA actual-knowledge risk if under-13s get in; Anthropic's minors guidelines apply to any app minors use. | [16 CFR 312](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-312); [FTC COPPA FAQ](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions) (neutral age screen, block retries); [Anthropic guidelines for organizations serving minors](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors) (must disclose AI; should verify age, moderate, publish a COPPA statement); penalty $53,088 per violation | **Applies.** `michael/app-signin-gate` is not on origin; no branch asks for age or birth date; the only "13" is a sentence in `PV:web/privacy.md`. App is filed under Education (`V2:app/electron-builder.yml:19`). | P0 | Neutral month/year entry before any data is stored, no hint of the cutoff, retry flag that survives restarts, delete under-13 data, store an age band (13-15, 16-17, 18+) not the birth date; teen defaults (Claude only, no screenshot retention, no social features); in-app "you're working with an AI"; public COPPA and teen-safety statement. Checklist in `privacy-review.md`. | Michael (gate lane), Adrian (policy) | open |
| B04 | B | No live, accurate privacy policy or terms. The app already links `miyagi.study/privacy` and `/terms`, which don't exist; there is no "I agree" step; Michael's draft says things the code contradicts. CalOPPA applies with no size threshold; the FTC treats a false policy as deception. | [Cal. Bus. & Prof. Code 22575](https://california.public.law/codes/ca_bus_and_prof_code_section_22575); [FTC: AI companies, keep your privacy promises](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/01/ai-companies-uphold-your-privacy-confidentiality-commitments); [Google APIs Terms 3(d)](https://developers.google.com/terms) (policy required); [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies) (policy must name YouTube API Services); [Berman v. Freedom Financial (9th Cir. 2022)](https://cdn.ca9.uscourts.gov/datastore/opinions/2022/03/30/21-16499.pdf) (clickwrap test) | **Applies.** Links: `V2:app/src/renderer/src/features/auth/model.ts:22`, `Login.tsx:258-260`. "Continue without an account" skips even the link. Claim-by-claim check of the draft: `privacy-review.md` (e.g. "not linked to your name" is false once `/v1/link` ships; "the local error log, we do not receive" is false when crash sharing is on; Mac-only wording on a Windows download; the YouTube embed is not disclosed). | P0 | Publish the policy (suggested edits to `web/privacy.md` in #201), `web/terms.md` and the cookie notice; first-run "I agree" button with the sentence above it, log version and time; re-check the policy against the release commit before every release. | Adrian (site, terms), Michael (facts.ts, app) | drafts ready |
| B05 | B | No server-side deletion or retention. The "anonymous" install token gets linked to the Google account and never unlinked; usage, video history and every log line become personal data we can't delete. | [GDPR Art. 17](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng); [COPPA 312.10](https://www.ecfr.gov/current/title-16/part-312/section-312.10) (retention only as long as necessary); [FTC Act Section 5](https://www.law.cornell.edu/uscode/text/15/45) | **Applies.** No DELETE or TTL for `tokens`, `links`, `usage`, `role_usage`, `builds` (`EP:cloud/store.py:17-148`; only shared lessons can be deleted, `EC:cloud/store.py:151-153`). `/v1/link` stores install to Supabase user and sign-out never unlinks (`EP:cloud/store.py:26-33,112-120`; `V2:app/src/main/features/cloudLink.ts:23-25,128-134`); logs carry `user=<id>` (`EP:cloud/app.py:161-162,198`) and the YouTube id (`EC:cloud/app.py:170-171`). Delete my data is local only and misses `install.bin`, `cloud-link.json`, `~/miyagi`, error logs, YouTube cookies (`PV:app/src/main/features/settings/erase.ts`). Supabase account is never deleted. | P0 | A `DELETE /v1/me` (by install and by user: tokens, links, usage, builds, uploader fields) plus Supabase `deleteUser`, wired to Delete my data; retention TTLs (usage 12 months, logs as short as Render allows); unlink on sign-out or say plainly that sign-in links the install; drop `user=` from log lines. | Michael (cloud, app) | open |
| B06 | B | The engine scrapes YouTube (watch pages, caption tracks, results pages; Bright Data unlocker in dev). YouTube's Terms ban automated access; since Oct 2026 courts let creators' anti-circumvention (§1201) claims proceed against yt-dlp-style scraping. | [YouTube Terms of Service](https://www.youtube.com/t/terms) (no automated means, no downloading); [§1201 rulings vs ByteDance, Apple, Runway (secondary)](https://openclassactions.com/lawsuits/runway-ai-youtube-video-scraping-dmca-class-action-lawsuit.php); YouTube CEO: downloading transcripts is "a clear violation" | **Applies.** `IL:server/lesson/transcript.py:3-7,97-122` (watch page, `timedtext`, `youtube-transcript-api`, spoofed UA), `IL:server/finder/sources.py:78-85` (results page). Scraped transcripts go to Anthropic when Gemini is unavailable (`IL:server/lesson/claude.py:368-398`). | P0 | Drop scraping from shipped builds. Legit inputs: Gemini's YouTube-URL input (only where B02 allows), captions from creators who connect their channel (`captions.download`), the YouTube Data API for search and metadata (30-day storage limit), or the learner's own notes. This collides with B02: founders must pick the lesson source for teens. | Founders decide; Michael (engine) | decision needed |
| B07 | B | Founders are minors and there is no entity. Contracts they sign are voidable; vendors require 18+ or authority (Gemini 18+, Render no one under 16, Apple age of majority, Microsoft Services Agreement, Anthropic "authority to bind"); without an entity the founders (and maybe parents) are personally liable. Blocks Developer ID signing and notarization. | [Cal. Fam. Code 6700](https://california.public.law/codes/ca_fam_code_section_6700), [6710](https://california.public.law/codes/ca_fam_code_section_6710); [Apple enrollment](https://developer.apple.com/programs/enroll/); [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms); [Render Terms](https://render.com/terms) | **Applies.** Unsigned DMG today; accounts (Anthropic, Google Cloud, Supabase, Render, GitHub, domain) held by the founders. | P0 | Now: a parent holds and pays for the vendor and developer accounts (Apple individual enrollment by a parent, $99/yr; Microsoft Company account later, Individual can't convert). Next: form an entity with a parent as manager or officer, founders' equity held by a parent as custodian (CUTMA), founders' IP assignment, then move accounts to it. California LLC about $890 in year one. | Adrian, Michael, parents | decision needed, lawyer |
| B08 | B | Name collision: Miyagi Labs (YC W25, miyagilabs.ai) launched "AI to transform YouTube content into interactive courses", likely with earlier common-law rights. Karate Kid cues invite a Sony/Columbia false-association letter. | [YC launch page](https://www.ycombinator.com/launches/Mr9-miyagi-labs-ai-to-transform-youtube-content-into-interactive-courses); [USPTO search](https://tmsearch.uspto.gov/search/search-results) (no live MIYAGI mark in classes 9/41/42; Columbia owns THE KARATE KID, serial 88775511) | **Applies.** Same name, same space. Site download code "waxon", "wax on, wax off" copy (`miyagi-site/index.html`, README). | P0 | Before any public launch push: a lawyer's clearance search (about $1-2k) and a naming decision (keep, composite name, or rebrand). Now: drop Karate Kid cues (change the "waxon" code, no quotes, no Mr./sensei styling). Don't file a trademark until cleared. | Founders decide | decision needed, lawyer |
| B09 | B | The engine may keep capturing and calling Claude for a lesson the app hides after a relaunch, so screen data could leave with no lesson on screen. | `V2:app/src/main/freshStart.ts:1-27` hides a resumed lesson but doesn't end it; `V2:app/agents/fresh-start.md:105-121` says the engine may still run "checks, timers, OCR or Claude calls" | **Likely; unconfirmed.** Engine fix (`claude/eng-no-auto-resume`) not on origin. | P0 | App sends `end_lesson` for a replayed lesson on launch, or the engine stops auto-resuming. Then the policy's "during a lesson" is true. | Michael (engine, app) | needs engine check |
| B10 | B | Google sign-in can't leave Testing (100 listed users) without a live privacy policy and home page on a verified domain; brand verification likely needs a Supabase custom domain because `supabase.co` can't be verified. Shared with area C. | [OAuth app verification help](https://support.google.com/cloud/answer/13464321); [brand verification](https://support.google.com/cloud/answer/15549049) | **Applies.** OAuth app in Testing per brief; consent screen shows `<ref>.supabase.co`. Basic scopes only, so no full app verification. | P0 | Verify miyagi.study in Search Console, publish `/privacy` and `/terms`, fill the consent screen, add a Supabase custom domain (paid add-on, paid by an adult), then Publish. | Adrian (site), Michael (Supabase, Google Cloud) | blocked on B04, B07 |
| B11 | B | Provider customer duties not met in the product: Anthropic requires an AI disclosure "at the beginning of each chat session or in the product interface" and a notice that outputs may be inaccurate; no use from unsupported regions; we're liable for all activity under our account. | [Anthropic Usage Policy, eff. 2026-11-12](https://www.anthropic.com/legal/aup); [Commercial Terms D.3](https://www.anthropic.com/legal/commercial-terms); [Supported Regions Policy](https://www.anthropic.com/supported-countries); Microsoft Store Policies 10.5.2 and 11.16 for the Store build | **Applies.** No AI disclosure line found in onboarding or the overlay; no region checks at the proxy. | P1 | One line in onboarding and the panel ("miyagi's coach is AI and can be wrong"); geo-block unsupported regions at the proxy and sign-up (North Korea, Cuba, Iran, occupied Ukrainian regions, plus Anthropic's list); terms carry the flow-down. | Michael (app, cloud), Adrian (copy) | open |
| B12 | B | Lessons built from creators' tutorials, shared across users and committed to the public repo; no DMCA agent; attribution not guaranteed. Courts keep finding substitutive summaries not fair use (ROSS, 3d Cir. 2026); Course Hero lost about $75M mostly for stripping attribution (§1202). | [17 U.S.C. 107](https://www.law.cornell.edu/uscode/text/17/107); [USCO DMCA agent FAQ](https://copyright.gov/dmca-directory/faq.html) ($6, 3 years); [Quizlet vs Course Hero (secondary)](https://www.thompsoncoburn.com/insights/education-platform-liability-in-the-ai-era-divergent-outcomes-for-quizlet-and-course-hero/) | **Applies.** Shared cache keyed by video id, first upload wins, and its draft is shaped by one learner's goal (`EC:cloud/app.py:608-639`); committed lesson drafts and fixtures transcribe code from Bro Code, Tech With Tim and others (`IL:demo/cache/lessons/`, `IL:evals/lesson/`); root `.gitignore` misses `demo/cache/transcripts/`. | P1 | Make the video central (steps unlock at timestamps), steps in our own words, no full transcripts or instructor code; always show creator, channel, title and link; creator opt-out and kill switch; register a DMCA agent and publish a takedown policy; take third-party lesson content out of the public repo; fair-use review before monetizing. | Michael (engine, cache), Adrian (DMCA, policy) | open |
| B13 | B | EU/UK users: GDPR and UK GDPR likely apply (Art. 3(2)(b) "monitoring", no intent needed); would need EU and UK representatives, a DPIA, a full Art. 13 notice, the UK Children's Code for under-18s; Gemini paid-only there. | [GDPR Art. 3, 8, 13, 27](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng); [ICO Children's Code](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/); Locatefamily fined €525k for no EU representative | **Applies if EU/UK users install** (public download, no geo-block). Anthropic and Supabase transfers rely on SCCs (not DPF). | P1 | Decide (founders): US-only at launch (say so in terms, geo-limit sign-up and the Store listing) or comply (representatives, DPIA, record of processing). Policy draft already has the GDPR section. | Founders decide | decision needed |
| B14 | B | Claims about AI grading ("auto-graded", "real checks") while checks have had false passes; the FTC still pursues overstated AI capability claims. Khanmigo marked right answers wrong. | [FTC: keep your AI claims in check](https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check); [DoNotPay order](https://www.ftc.gov/legal-library/browse/cases-proceedings/donotpay); ROADMAP 1.8 | **Applies** to site and store copy. | P1 | No accuracy or outcome claims without a measured number on file; "grades are practice feedback, not a certificate" in app and terms; keep the AI disclosure. | Adrian (site copy) | open |
| B15 | B | Seen as a cheating tool (the Cluely backlash). Anthropic's Usage Policy bans submitting AI-assisted work without permission; a screen overlay is easy to read that way. | [Anthropic Usage Policy](https://www.anthropic.com/legal/aup) | **Applies** to positioning. | P1 | Terms forbid using miyagi on graded work where AI isn't allowed (in `web/terms.md`); never market for exams or interviews; consider pausing when known proctoring or exam apps are frontmost. | Adrian (positioning) | drafted in terms |
| B16 | B | No license on either public repo and no contributor or IP-assignment terms, so ownership between the founders is undefined; no third-party notices in any build (MIT/BSD/Apache/OFL all require the notice to travel with the copy). No GPL, AGPL, SSPL, BUSL or CC-NC component found in anything shipped. | [`oss_license_inventory.md`](privacy-legal/sources/oss_license_inventory.md); [GitHub: no license means all rights reserved](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) | **Applies.** No LICENSE on any branch of either repo; the app is `private` and the VS Code companion `UNLICENSED`; the next Mac build drops node_modules LICENSE copies; the site's `live/` bundle strips license comments; Google Sans Flex ships as a modified subset without `OFL.txt` in the app; Windows installer plug-ins (nsis7z, StdUtils, UAC, nsProcess, `elevate.exe`) have unknown licenses. To check on a Mac: Pillow's optional libimagequant (GPL-3.0) and GNU readline/gdbm in the bundled CPython. | P1 | Pick a license for miyagi on purpose (or an explicit "all rights reserved") and sign a founders' IP assignment (B07); generate one THIRD_PARTY_NOTICES at build time (Vite 8 `build.license`, `license-checker-rseidelsohn` or `cyclonedx-npm`, `pip-licenses`) for Mac and Windows and link it from Settings; ship `OFL.txt` with the font; check the Mac-only items. | Adrian (app build), Michael (engine bundle) | open |
| B17 | B | Breach readiness: if captures or code with secrets leak, California requires notice within 30 days (AG sample over 500 residents), GDPR within 72 hours to every affected authority. | [Cal. Civ. Code 1798.82](https://california.public.law/codes/ca_civ_code_section_1798.82) | **Applies** to anyone holding personal data. Cloud doesn't store bodies (`EP:cloud/app.py:6-7,160-162`), which helps. | P1 | One-page incident runbook (who decides, notice templates, the clocks), short log retention, no bodies in logs. | Michael (cloud), Adrian (runbook) | open |

## Notes on the big ones

### B01 screen capture
- What leaves today, from code: a 1280-px screenshot of the whole primary display plus a 400-px crop around the cursor on
  every coach diagnose, hint and explain; screen text (OCR and accessibility text) with emails, US SSNs, phones and
  Luhn-valid card numbers replaced; the editor buffer (unsaved edits too), files the judge reads, any "Explain this"
  selection with 12 lines around it, and a scan of the lesson folder (file list plus up to 60,000 characters of file
  contents and the absolute path, which holds the macOS username). Text from 1Password, Bitwarden, Dashlane, LastPass,
  Keychain Access, Passwords and Messages is always dropped; their pixels are kept out only when ScreenCaptureKit works.
  Slack, WhatsApp, Signal, Mail and browsers are not on the list.
- Why it matters legally: CIPA 631's all-party-consent theory for other people's messages on a consenting user's screen
  is untested but litigated hard by plaintiffs' firms; Washington's health-data law has no size threshold and a private
  right of action, and "collect" includes "receive"; a leak of captures with passwords is a notifiable breach; in the EU
  one sensitive item in a capture can make the whole capture special-category data.
- Why it matters for trust: this is exactly what sank Recall's launch.
- Lawyer: yes, before scaling, for the consent flow (the CIPA analysis is fact-specific).

### B02 Gemini and teens
- Exact text (Gemini API Additional Terms, effective 2026-03-23): "You must be 18 years of age or older to use the APIs.
  You also will not use the Services as part of a website, application, or other service ... that is directed towards
  or is likely to be accessed by individuals under the age of 18."
- Anthropic, by contrast, allows teen users through the API if we follow its minors guidelines (B03, B11).
- The clean launch answer is Claude only, which the engine already falls back to, but its fallback reads a scraped
  transcript (B06). So B02 and B06 are one decision: how does a lesson get built for a 15-year-old without Gemini and
  without scraping? Options: Data API metadata plus chapters plus the learner watching the embedded video; creator-
  authorized captions; Vertex AI if its terms allow minors (not confirmed).
- Lawyer: optional, only if staying on Google for teens.

### B07 minors and the entity
- California: a minor can make a contract but can void it before 18 or a reasonable time after (Fam. Code 6710); a minor
  can't grant a "delegation of power" (6701). Vendors' age and authority clauses, quoted in
  `privacy-legal/sources/platforms_business_setup.md`: Gemini 18+; Render "no one under 16"; Apple age of majority;
  Microsoft Services Agreement age of majority or a parent bound; Anthropic, Supabase and Google Cloud require authority
  to bind; GitHub 13+.
- Same rule cuts the other way: teen users can void our Terms, so the liability cap and dispute clauses are weak
  against them. A parent or guardian should accept for under-18s (in `web/terms.md`).
- Apple: only the Account Holder can create a Developer ID certificate; organization enrollment needs an entity and a
  D-U-N-S number. Since macOS Sequoia, Control-click no longer opens un-notarized apps.
- Lawyer: yes (entity, custodial equity, founders' IP assignment, who signs).

### B08 the name
- USPTO search (24 records containing "miyagi"): no live MIYAGI mark for software, education or online services, none
  owned by Sony or Columbia. Live MIYAGI marks are in unrelated goods (eyewear, a pending restaurant MR MIYAGI, bath
  gels, a sake design). WAX ON WAX OFF is registered to an unrelated spa. A 2012 MIYAGI application for children's
  educational software is dead.
- The real conflict is Miyagi Labs: same name, same pitch, earlier use. No USPTO filing by it was found, but unregistered
  rights from earlier use still count.
- Pat Morita's post-mortem publicity rights (Cal. Civ. Code 3344.1) protect his likeness and voice, not the character
  name: no photos, no voice imitation, no "Mr. Miyagi" persona.

## Decisions only Adrian and Michael can make

1. **Teens and Gemini (B02, B06):** Claude only at launch, Gemini for verified adults only, or Vertex AI. And where
   lessons get their transcript once scraping goes.
2. **Who holds the accounts and when an entity is formed (B07):** which parent enrolls with Apple and owns the
   Anthropic, Google Cloud, Supabase, Render and domain accounts.
3. **The name (B08):** pay for clearance and decide keep or rebrand before any launch push; drop "waxon".
4. **Capture scope (B01):** full screen vs. only the editor and tutorial windows (recommended).
5. **Where miyagi is offered (B13):** US only at launch, or EU/UK with representatives.
6. **Account linking (B05):** unlink on sign-out, or keep linking and say so.
7. **The shared lesson cache (B12):** ship it at launch or not, and what may go in it (only content built from the
   public video, never a learner's goal, screen or code).
8. **Bring-your-own-key:** adults only (recommended, because Gemini keys carry the 18+ term).
9. **Disputes:** California courts with small claims (recommended for now) or arbitration later with counsel.

## What needs a real lawyer

| Item | Why | When |
| --- | --- | --- |
| Entity, custodial equity, founders' IP assignment, who signs vendor terms (B07) | Minors' capacity and personal liability decide everything else | Before launch |
| Trademark clearance (B08) | Miyagi Labs has a likely earlier claim to the same name in the same space | Before launch push or spending on the brand |
| One review of the final Privacy Policy and Terms (B04) | Liability cap and warranty wording (Civ. Code 1668, NJ TCCWNA), minors' acceptance, EU/UK mandatory rights | Before launch |
| Screen-capture consent flow (B01) | CIPA 631 all-party consent and Washington MHMDA are fact-specific with private plaintiffs | Before scaling |
| Fair-use review of the lesson and cache format (B12) | Abridgement case law trends against substitutes | Before monetizing |
| Gemini terms for teens (B02) | Only if staying on Google for under-18s | If needed |
| EU/UK launch, school deals, paid plans | Representatives and DPIA; SOPIPA and data agreements; auto-renewal law | Later |

## Launch checklist items (area B)

- [ ] `miyagi.study/privacy`, `/terms` and the cookie notice live, linked from the site footer, the app's login and Settings, and the Google consent screen.
- [ ] The published policy re-checked against the release commit (what `facts.ts` says, what the engine and cloud do).
- [ ] First-run "I agree" step (button text matches the sentence above it), version and time logged; parent acceptance for under-18s.
- [ ] Age gate live: neutral entry, retry block, under-13 deletion, age band stored.
- [ ] Gemini decision implemented; if any Gemini stays: billing-enabled project, AI Studio logging off or 7 days.
- [ ] No YouTube scraping in the shipped engine (or a documented, lawyer-reviewed exception).
- [ ] Capture: consent screen before Screen Recording; private, messaging, mail and banking apps excluded on all paths; secret scrubbing on code and files; pause hotkey and indicator.
- [ ] Engine does not capture for a hidden, resumed lesson (B09 confirmed fixed).
- [ ] miyagi-cloud: delete-my-account endpoint wired to Delete my data, retention TTLs, Supabase user deletion, no `user=` in logs.
- [ ] AI disclosure and "AI can be wrong" in onboarding and the panel; unsupported regions blocked at the proxy.
- [ ] Vendor and developer accounts owned by an adult or the entity; DPAs in place (Anthropic and Supabase incorporated in their terms; Render's DPA; Google's paid-services DPA).
- [ ] `privacy@` and `copyright@` addresses working (a forwarder, since GitHub Pages has no mail).
- [ ] Karate Kid cues removed from site and app; naming decision made.
- [ ] YouTube in the app: `youtube-nocookie.com` player, nothing on top of the player, at least 200x200; policy names YouTube API Services and links Google's Privacy Policy; terms link YouTube's Terms.
- [ ] Third-party notices shipped in the app.
- [ ] Third-party lesson content and team members' local paths removed from the public repo; `demo/cache/transcripts/` ignored.
- [ ] Site: YouTube embed loads only on click (see `cookies.md`).

## Handed to area A (security), details not in this repo

Two findings from the code read are exploitable and were passed to area A outside the repo: one about how freely
miyagi-cloud hands out and honors tokens (a cost and acceptable-use problem under Anthropic's "responsible for all
activity" clause), and one about a local interface on the learner's machine. Both are written up in the shared notes
folder for the area A session and Michael.

## Later (P2, one line each)

- California AB 1043/AB 1856: from 2027-01-01 desktop apps must request the OS age signal; check coverage of direct downloads with counsel.
- California AB 2246 (replaces the AADC, 2027-01-01) and Vermont's design code: "likely accessed by" under-18s; private defaults, no profiling.
- SB 243 / SB 1119 companion-chatbot rules: stay out by keeping the coach task-focused (no friend persona, no relationship memory).
- EU AI Act Art. 50: AI-interaction disclosure (covered by B11) and machine-readable marking of AI text if EU use grows; Annex III high-risk only with credentials or school grading.
- UK DUAA 2025: complaints process with 30-day acknowledgement if UK users are served; ICO fee question.
- Microsoft Store build: 10.5.2 opt-in before sending personal data to third parties, 11.16 generative-AI disclosure and report button, IARC rating, EULA URL in Partner Center.
- Mac App Store (if ever): sandbox, no self-updater, privacy manifest, 5.1.2(i) consent before sending to third-party AI, Sign in with Apple.
- Paid plans: California auto-renewal law (AB 2863) checkout review; FTC click-to-cancel is vacated but restarting.
- Export: free public download is "published" and outside the EAR; keep a one-paragraph memo; no custom crypto.
- VPPA: watch *Salazar v. Paramount* (Supreme Court, argued 2026-10-14); keep video ids out of any third-party analytics.
- Washington MHMDA: add "we don't seek or infer health data and discard incidental captures" to the policy (done in the draft).
- Accessibility: WCAG 2.1 AA on miyagi.study and keyboard support in the overlay; an accessibility contact.
- School deals: FERPA school-official terms, SDPC National Data Privacy Agreement, SOPIPA if marketed for K-12.
- A team member's macOS username sits in about 10 committed fixture paths; scrub when convenient.
- Google OAuth: rotate Supabase's Apple secret every 6 months if Sign in with Apple is ever added.

## Sources

Every row links its primary source. The full research notes, each claim cited with an access date of 2026-11-21:

- [`eu_uk_privacy_ai_act.md`](privacy-legal/sources/eu_uk_privacy_ai_act.md): GDPR, UK GDPR, ePrivacy/PECR, AI Act, EAA, DPF.
- [`us_privacy_consumer_protection.md`](privacy-legal/sources/us_privacy_consumer_protection.md): CCPA, CalOPPA, state laws, MHMDA, breach, CIPA, VPPA, FTC, state AI laws, ADA.
- [`kids_students_minors.md`](privacy-legal/sources/kids_students_minors.md): COPPA 2025 rule, app-store laws, design codes, FERPA, SOPIPA, vendor minors rules, gate design.
- [`youtube_copyright_trademark.md`](privacy-legal/sources/youtube_copyright_trademark.md): YouTube Terms and API policies, transcripts, fair use, DMCA, USPTO search.
- [`platforms_business_setup.md`](privacy-legal/sources/platforms_business_setup.md): Google OAuth, Apple, Microsoft, minors and entities, EIN, contacts, export, sanctions.
- [`vendor_terms_data_handling.md`](privacy-legal/sources/vendor_terms_data_handling.md): Anthropic, Gemini, Supabase, Render, GitHub Pages, jsDelivr retention, training and DPAs.
- [`terms_eula_enforceability.md`](privacy-legal/sources/terms_eula_enforceability.md): clickwrap, minors, liability limits, AI terms compared, BYOK, disputes.
- [`site_cookies_check.md`](privacy-legal/sources/site_cookies_check.md): what miyagi.study stores and loads.
- [`oss_license_inventory.md`](privacy-legal/sources/oss_license_inventory.md): every npm and Python package, font and installer component, by where it ships.

Code facts come from two code-reading notes kept outside the repo because they hold the area-A details; every code
claim above carries its own branch:file:line.
