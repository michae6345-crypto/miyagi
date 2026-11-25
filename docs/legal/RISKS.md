# miyagi legal and privacy risk list

Draft, 2026-11-21. Desk research by an AI assistant for the miyagi team.

**Not legal advice.** This is a research summary written by people (and an AI) who are not lawyers, for two high school founders who have not formed a company. It is meant to make a first conversation with a real lawyer shorter and cheaper, not to replace it. Laws and vendor terms change often (several cited below changed in 2025 and 2026); check the linked source before relying on any line. Where the list says "lawyer: yes", do not ship to strangers until one has looked.

What was checked in code: `app/` on the integration worktree (`wt/michael-risk-v2ref`, commit 5f04f998), the engine on `origin/main` (`server/`), the lane brief `app/agents/privacy.md` and `Privacy.tsx` on `origin/michael/app-privacy`, and the site clone `miyagi-site` (commit b3c867b). The miyagi-cloud proxy code is not in this repo, so anything about what it stores is unverified.

## Do first (top 5)

1. **Stop sending under-18 users' data to the Gemini API, or get Google's written OK.** The Gemini API terms say the developer must be 18+ and that you may not use the API in an app "directed towards or is likely to be accessed by individuals under the age of 18" ([Gemini API Additional Terms](https://aistudio.google.com/docs/terms)). miyagi has a 13+ gate and is aimed at students. Options: route lesson building for everyone through Claude only, or raise the age floor to 18 for any Gemini path. This is the biggest surprise in the list (risk 1).
2. **Put the vendor accounts in an adult's name.** Gemini requires the account holder to be 18; Apple requires the age of majority; Anthropic's commercial terms are for businesses with authority to bind. A parent or the 18+ founder should own the Anthropic, Google Cloud, Supabase, Render, Apple and domain accounts until an LLC exists (risks 2 and 9).
3. **Fix the YouTube data path before public launch.** The engine fetches watch pages, caption tracks and comments, sometimes through Bright Data's Web Unlocker specifically to get past YouTube rate limits (`server/lesson/transcript.py`, `server/finder/youtube.py`). YouTube's ToS bans automated access and circumventing the service. Prefer Gemini's own YouTube URL input (an official Google feature) or the YouTube Data API, and drop the unlocker (risk 3).
4. **Publish a privacy policy and terms at miyagi.study/privacy and /terms that match the code**, using `DRAFTS.md`. Google brand verification, Anthropic's minors guidelines, COPPA and every state law hang on this page existing and being true (risks 4, 5, 6).
5. **Add screen-capture guards before strangers install.** Full screenshots (an overview plus a 400x400 crop around the cursor, `server/coach/screen.py`) go to Anthropic. Text redaction (`server/screen/privacy.py`) only cleans OCR and accessibility text, not the images, and the private-app list (1Password, Messages, etc.) is only consulted in `scene_watch.py`. Pause capture when a private app is frontmost and say so in the policy (risk 5).

## Ranked risks

### 1. Gemini API terms forbid apps likely used by minors. HIGH

**What.** Google's Gemini API Additional Terms: "You must be 18 years of age or older to use the APIs," and no API Client "directed towards or is likely to be accessed by individuals under the age of 18" ([source](https://aistudio.google.com/docs/terms)). miyagi's lesson builder calls Gemini to "watch the video" (`server/lesson/gemini.py`, it passes the YouTube URL as `file_data`). A tutor for students with a 13+ gate is plainly "likely to be accessed" by under-18s. Separately, a minor founder cannot accept these terms personally.

**Also.** On unpaid (free tier) Gemini, Google "uses the content you submit ... to provide, improve, and develop" its products and "human reviewers may read" inputs and outputs (same source). The engine code mentions free-tier per-model daily caps (`gemini.py`, `fallback_models`), so the free tier may be in use. For the EEA, Switzerland and UK, only Paid Services may be used (same source).

**Why high.** Google can cut off the key with no notice; and if a learner's data went to the free tier, the privacy policy would have to say "may be used to train Google models and read by human reviewers", which is a hard sell for a kids' product and may conflict with COPPA's third-party disclosure rules.

**What to do.**
- Decide one of: (a) Gemini only for users who confirm 18+, Claude for everyone else; (b) drop Gemini from shipped builds; (c) ask Google in writing (unlikely to be granted to minors).
- Whatever is kept: use a paid (billing-enabled) Gemini project, so prompts are not used for training. Note the YouTube URL feature is "in preview and is available at no charge" ([video docs](https://aistudio.google.com/docs/video-understanding)); confirm the paid project still gets paid-tier data terms for it [VERIFY with Google].
- What Gemini receives today is a public YouTube URL plus prompts, not learner screenshots (from code reading; [VERIFY] the proxy does not add anything). That lowers the privacy harm but does not fix the terms problem.

**Lawyer.** Not needed to decide; it is a product choice. Needed only if you want to argue the terms do not apply.

### 2. Minor founders cannot reliably sign vendor contracts, and no entity exists. HIGH

**What.** In California a minor can make contracts but can disaffirm most of them before 18 or within a reasonable time after (Cal. Family Code §§ 6700, 6710, [leginfo](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=FAM&sectionNum=6710)). Vendors know this and write age or authority clauses: Gemini (18+), Apple (age of majority, [enroll page](https://developer.apple.com/programs/enroll/)), Anthropic Commercial Terms ("not for consumer use", business with authority to bind, [source](https://www.anthropic.com/legal/commercial-terms)), Supabase ("right, power, and authority", [source](https://supabase.com/terms)). The same voidability cuts the other way: miyagi's own Terms of Service accepted by minor users are also voidable, so the liability cap in our ToS is weaker against a teen user than against an adult.

**Without an entity**, each founder is personally liable for everything miyagi does (sole proprietors or a general partnership by default).

**What to do.**
- Now: a parent (or the 18+ founder) opens and owns the vendor accounts and pays the bills, with the founders as collaborators. Write a one-page founders' agreement (who owns the code, the name, the domain; what happens if one leaves) and have parents co-sign.
- Before revenue or a public launch: form an entity. California LLC statutes do not bar minor members, but a minor's signature on the operating agreement is voidable, so the usual pattern is parent as initial member/manager or a custodial arrangement, with interests moved later. A lawyer should set this up (California LLC filing is $70 plus the $800 annual franchise tax, [CA SOS](https://www.sos.ca.gov/business-programs/business-entities/forms), [FTB](https://www.ftb.ca.gov/file/business/types/limited-liability-company/index.html); check the first-year rules).
- Hackathon IP: check SanD Hacks / MLH rules on who owns code written at the event ([MLH Code of Conduct and rules](https://mlh.io/code-of-conduct); [VERIFY] event-specific rules).

**Lawyer.** Yes, for the entity and founder IP assignment. Low cost relative to the risk.

### 3. YouTube scraping, transcripts and comments. HIGH

**What the code does.** `server/lesson/transcript.py` gets title, description, chapters and caption tracks from the watch page, first through Bright Data Web Unlocker ("YouTube rate-limits caption endpoints per IP ... which is what (1) is for"), then plain HTTPS with a spoofed Safari user agent and a `CONSENT=YES+1` cookie, then `youtube-transcript-api`. `server/finder/youtube.py` parses search result pages and scans comments fetched via Bright Data. Lessons built from videos are cached and committed (`demo/cache/lessons/raw/*.json`) and the bundle ships git-tracked engine source including `demo/` (`app/scripts/bundle-engine.mjs`).

**The rules.** YouTube ToS forbids accessing the service "using any automated means (such as robots, botnets or scrapers)", downloading content without permission, and circumventing any part of the service ([YouTube ToS](https://www.youtube.com/static?template=terms)). Rate-limit evasion through an unlocker is the clearest kind of circumvention. Copyright: captions are the creator's (or YouTube's auto-generated) text; storing and redistributing transcripts and derived step lists is copying. Fair use for a transformative teaching aid is arguable ([17 U.S.C. § 107](https://www.law.cornell.edu/uscode/text/17/107); [Copyright Office fair use index](https://www.copyright.gov/fair-use/)) but untested here, and a ToS breach claim does not need copyright at all.

**Why high.** It is the most likely source of a cease-and-desist (from Google or a creator) and of an API key ban, and it is the part judges and press will ask about.

**What to do.**
- Use the official paths: Gemini's YouTube URL input (Google processes the video itself; public videos only) and the YouTube Data API v3 for search and metadata ([API Services Terms](https://developers.google.com/youtube/terms/api-services-terms-of-service), [Developer Policies](https://developers.google.com/youtube/terms/developer-policies)). Note the Data API does not give third-party caption text without the owner's authorization; plan around that.
- Remove Bright Data unlocker and the spoofed UA/consent cookie from shipped builds. Keep `youtube-transcript-api` out of shipped builds too (it uses the same unofficial endpoints).
- Do not ship cached transcripts in the app bundle; keep cached lessons as short paraphrased steps with timestamps and a link to the video, not caption text.
- Always show the video through the official embedded player, credit the creator and link to the original. Add a takedown path (risk 10).
- Comments: the code keeps only text and likes (`parse_comments`), good; keep it that way (the ToS bans harvesting identifying info like usernames).

**Lawyer.** Yes, briefly, if you keep any transcript storage after launch. Not needed to make the engineering change.

### 4. COPPA and the 13+ gate. HIGH (if the gate is weak) / MEDIUM (if solid)

**What.** COPPA applies to services "directed to children" under 13 or with actual knowledge of collecting from under-13s. A general-audience tool with a neutral age screen that blocks under-13s is usually outside it, but a tutoring product marketed to students risks being seen as mixed-audience. The amended COPPA Rule took effect June 23, 2025 with full compliance due April 22, 2026 ([Federal Register](https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule)); it adds separate parental consent for disclosing children's data to third parties, a written information security program, and a written retention policy ([Davis Polk summary](https://www.davispolk.com/insights/client-update/ftc-prioritizes-coppa-enforcement-new-compliance-obligations-take-effect), [Loeb summary](https://www.loeb.com/en/insights/publications/2025/05/childrens-online-privacy-in-2025-the-amended-coppa-rule)). Sending an under-13's screen to Anthropic is a third-party disclosure.

**Code check.** I could not find the 13+ gate in the app code on the integration branch (searched `app/src/renderer` for age prompts) [VERIFY where it lives].

**Anthropic adds its own rule:** products giving minors (under 18) direct access must follow the minors guidelines: age verification suited to the product, content filtering and monitoring, the child-safety system prompt where provided, COPPA compliance "clearly stated" on the website, and disclosure that users are talking to an AI ([AUP](https://www.anthropic.com/legal/aup), [guidelines](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors)).

**What to do.**
- Neutral age screen at first run (ask birth year, do not hint the right answer), block under-13 with no data sent, and do not let them retry immediately (store a flag).
- Do not market to elementary or middle school; say "13 and up" on the site.
- If an under-13 is discovered: delete their data and account, documented in the policy.
- For 13 to 17: follow Anthropic's minors guidelines (system prompt, AI disclosure, a report button, a public COPPA/minors statement in the policy).
- Write the retention policy and a short security program now; they are cheap and the amended rule expects them.

**Lawyer.** Yes if you ever want to allow under-13s or sell to schools.

### 5. Screen capture of third-party and sensitive data. HIGH

**What.** miyagi captures the screen during lessons and sends images to Anthropic via miyagi-cloud. The screen can show passwords, API keys, `.env` files in the editor, bank pages, and other people's messages and emails. OCR and accessibility text get regex redaction of emails, SSNs, phone and card numbers (`server/screen/privacy.py`), but the screenshots themselves are sent as is (`server/coach/screen.py`), and API keys or passwords are not covered by the regexes at all.

**Law.** Federal and California wiretap laws (CIPA § 631, two-party consent for confidential communications under § 632) target interception in transit and recording of communications; a screenshot of a message already received is not a classic interception, so this is a lower wiretap risk than chat widgets that have been the focus of 2025 to 2026 CIPA suits ([Jones Walker overview](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/the-chatbot-on-the-witness-stand-part-1-how-a-1967-wiretapping-law-became-an-a.html)). The bigger exposure is ordinary: a data breach notification duty if screenshots leak (Cal. Civ. Code § 1798.82, [leginfo](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1798.82)), negligence claims, and GDPR controller duties for third parties' data if EU users install. A video call on screen with audio would be a real § 632 issue; the code does not capture audio from other apps as far as I saw [VERIFY].

**What to do.**
- Capture only while a lesson is running and show a visible indicator (the app already says "Lessons only" in Privacy settings; make the overlay show it too).
- Do not capture when a private app is frontmost (wire `is_private_app` into the capture path, not just `scene_watch`); add browsers on known banking or mail domains if feasible.
- Mask editor tabs named `.env`, `*.pem`, `id_rsa`, and lines matching common key formats (`sk-`, `AKIA`, `ghp_`, `AIza`) before the image leaves; the roadmap calls this 5.1/5.2 and it is not done, so the policy must not claim it.
- Do not store screenshots on miyagi-cloud; pass them through only [VERIFY the proxy does not log bodies].
- ToS: user must not use miyagi to capture others' private data and must have the right to show what is on screen.

**Lawyer.** Not to start; yes if a breach ever happens.

### 6. Privacy policy truthfulness and subprocessors (FTC Act § 5, CalOPPA). HIGH until a policy exists

**What.** Any US company is bound by what its privacy policy says (FTC deception authority, [FTC privacy guidance](https://www.ftc.gov/business-guidance/privacy-security)). California's CalOPPA requires any commercial website or online service collecting personal info from Californians to post a policy, with no size threshold (Cal. Bus. & Prof. Code § 22575, [leginfo](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=BPC&sectionNum=22575)). Anthropic's minors guidelines and Google brand verification also need a live policy.

**Subprocessors to name (from code):** Anthropic (screenshots, code, editor text, prompts; via miyagi-cloud), Google Gemini API (YouTube URLs and lesson prompts), Supabase (Google sign-in; name, email, tokens), Render (hosts miyagi-cloud; sees every proxied request and the install token), Google (OAuth identity), YouTube (video playback in the app and on the site), GitHub Pages and jsDelivr (site hosting and scripts, see visitors' IPs). Possibly Bright Data and Tiger Data/Timescale (engine has code for both; [VERIFY] whether shipped builds use them), and whatever receives crash reports when "Share crash reports and usage" is on [VERIFY destination; `telemetry.ts` is not on the integration branch].

**Vendor data terms.** Anthropic commercial API: no training on customer content ([Commercial Terms](https://www.anthropic.com/legal/commercial-terms)); Anthropic keeps API inputs/outputs for a limited period for safety [VERIFY current retention on Anthropic's privacy center]. Gemini paid: no training, limited logging; Gemini free: training and human review ([Gemini terms](https://aistudio.google.com/docs/terms)). Supabase DPA: [supabase.com DPA](https://supabase.com/legal/customer-resources/data-processing-addendum). Render DPA and subprocessor list: [render.com/dpa](https://render.com/dpa), [render.com/trust](https://render.com/trust).

**What to do.** Publish `DRAFTS.md`'s policy after every [VERIFY] is checked. Accept the Anthropic, Supabase and Render DPAs in the account settings (in the adult's name). Keep `facts.ts` (planned in the privacy lane) and the policy in sync.

**Lawyer.** Recommended for one review of the final policy.

### 7. Anthropic usage policy obligations. MEDIUM

**What.** Beyond the minors rules in risk 4: the Commercial Terms require telling users that factual claims in outputs should not be relied on without checking ([source](https://www.anthropic.com/legal/commercial-terms)); the AUP lists prohibited uses that our ToS acceptable-use section should pass down ([AUP](https://www.anthropic.com/legal/aup)). Anthropic audits and can suspend.

**What to do.** AI disclosure line in onboarding ("miyagi's hints come from AI and can be wrong"), the same in ToS. Mirror the AUP's prohibited-use categories in our ToS. Use the child-safety system prompt if Anthropic provides one for your account.

**Lawyer.** No.

### 8. Google OAuth leaving Testing mode. MEDIUM (blocks launch, low legal risk)

**What.** In Testing, only listed test users (max 100) can sign in. Sign-in uses only basic scopes through Supabase (Google sign-in for name and email, `app/src/main/features/auth.ts`); non-sensitive scopes do not need full app verification, but showing the app name and logo on the consent screen needs brand verification: a homepage on a domain you verify in Search Console, a privacy policy on the same domain that matches the one linked on the consent screen, and a homepage that is not just a login page ([Verification requirements](https://support.google.com/cloud/answer/13464321), [OAuth App Verification](https://support.google.com/cloud/answer/9110914)).

**Also.** Supabase's consent screen will show the `*.supabase.co` domain unless you set a custom domain; Google may ask that authorized domains include it. The Google Cloud project owner must be an adult account (risk 2).

**What to do.** Verify `miyagi.study` in Google Search Console (DNS TXT record), publish /privacy and /terms, fill the consent screen (app name, support email, logo, homepage, privacy, terms links), submit for brand verification, then press Publish.

**Lawyer.** No.

### 9. Apple notarization and developer enrollment. MEDIUM (blocks Mac distribution)

**What.** Developer ID signing and notarization need the Apple Developer Program ($99/yr); individuals must be the age of majority, and the parent route is the parent enrolling and supervising ([Apple enroll](https://developer.apple.com/programs/enroll/); [forum thread on minors](https://developer.apple.com/forums/thread/704235)). An organization enrollment needs a legal entity and a D-U-N-S number. Guideline 4.8 (offer Sign in with Apple when using third-party login) applies only to App Store apps ([App Review Guidelines 4.8](https://developer.apple.com/app-store/review/guidelines/#login-services)); a notarized direct download does not need it.

**What to do.** A parent (or the 18+ founder) enrolls as an individual now; the app shows that person's name as the developer. Move to an organization account once the LLC and D-U-N-S exist. Windows: the Microsoft Store branch (`adrian/windows-store`) has similar identity needs; app-store age laws in Texas and Utah put duties on developers who distribute through stores (age rating, honoring parental consent signals), and Texas's law is in effect after a 2026 stay ([MoFo](https://www.mofo.com/resources/insights/251111-texas-targets-app-stores-with-new-accountability-law), [FPF comparison](https://fpf.org/blog/comparing-enacted-app-store-accountability-acts/)) [VERIFY whether Microsoft Store is covered].

**Lawyer.** No.

### 10. Copyright notices: DMCA agent and takedown path. MEDIUM

**What.** miyagi stores and displays content derived from other people's videos and runs a site with a public repo. The DMCA § 512 safe harbor only protects a service that has registered a designated agent with the Copyright Office ($6, renew every 3 years, [DMCA directory](https://www.copyright.gov/dmca-directory/), [renewal](https://blogs.loc.gov/copyright/2019/10/it-may-be-time-to-renew-your-dmca-agent-registration/)) and lists the agent on its site. Whether § 512 even covers lesson summaries generated by miyagi (not uploaded by users) is doubtful; it mainly helps for user-supplied content.

**What to do.** Register an agent (adult's name or the entity; use a PO box or business address, not a home address, since the directory is public). Add a copyright/takedown section to the ToS and a `copyright@` or `[CONTACT EMAIL]` address. Honor creator opt-out requests quickly (delete their cached lessons and block their channel ID).

**Lawyer.** No.

### 11. Trademark: the name "miyagi". MEDIUM

**What.** "Mr. Miyagi" is the Karate Kid character owned by Columbia Pictures / Sony, and the site leans on the reference ("Wax on, wax off" in the og:image alt text and the download code "waxon"). Aggregator searches found no live "MIYAGI" word mark in software or education; a dead MIYAGI application for children's educational software (serial 85530487, [Markinton](https://markinton.com/trademark/miyagi-85530487)), abandoned MIYAGI'S marks ([Justia](https://trademark.justia.com/760/10/miyagi-s-76010950.html)), and Columbia's THE KARATE KID and COBRA KAI marks ([Justia owner page](https://trademark.justia.com/owners/columbia-pictures-industries-inc-2506647)). These are not official records; search the [USPTO Trademark Search](https://tmsearch.uspto.gov/) in classes 9, 41 and 42. Miyagi is also a Japanese prefecture and surname, which helps a little (a surname/geographic word is not exclusive to Sony). The risk is less infringement of a registration and more a studio letter claiming false association, plus "Wax on, wax off" being a famous film quote.

**What to do.** Run the USPTO search yourselves; stop using "Wax on, wax off" and Karate Kid imagery in marketing (keep the bonsai, which is generic); do not file a trademark application until the entity exists, then consider a clearance search by a lawyer before filing (USPTO base fee is $350 per class since January 2025, [USPTO fees](https://www.uspto.gov/trademarks/fees)).

**Lawyer.** Yes before spending money on the brand or filing.

### 12. Open-source license compliance for the bundle. MEDIUM

**What.** The Mac app ships Electron (MIT, plus Chromium's many licenses), a standalone CPython 3.12 (python-build-standalone, PSF plus bundled libs such as OpenSSL and SQLite), and the engine's packages: fastapi, uvicorn, websockets, pydantic, httpx, anthropic, google-genai, jsonschema, watchdog, rapidfuzz, Pillow, PyObjC, psycopg (`server/pyproject.toml`, `bundle-engine.mjs` SMOKE line). Notable licenses: **psycopg 3 is LGPL-3.0** ([psycopg license](https://github.com/psycopg/psycopg/blob/master/LICENSE.txt)); certifi is MPL-2.0; most others are MIT/BSD/Apache. LGPL in Python is usually fine if the library stays a separate, user-replaceable module and you include the license text and offer the source; it is not fine if you modify it without sharing changes. The bundle prunes `psycopg_binary` but keeps `psycopg` [VERIFY whether the shipped app needs psycopg at all; it is only for the Tiger Data path].

**The repo itself has no LICENSE file** (checked `git ls-files`). A public repo with no license is "all rights reserved" by default ([GitHub docs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository#choosing-the-right-license)); others may view and fork on GitHub under GitHub's terms but cannot legally reuse it. That is fine if intended; just decide it on purpose. Also check that the repo contains no secrets and no Supabase service-role key (the publishable key in `publicConfig.ts` is public by design).

**What to do.** Generate a third-party notices file at build time (e.g. `pip-licenses --with-license-file` for the Python side, `license-checker` or electron-builder's bundled `LICENSES.chromium.html` for the JS side), ship it in the app's Resources and link it from About. Drop psycopg from shipped builds if Tiger is demo-only. Add a LICENSE (or a short "All rights reserved" note) to the repo.

**Lawyer.** No, unless you pick a copyleft license for miyagi itself.

### 13. US state comprehensive privacy laws (CCPA/CPRA and others). LOW today

**What.** CCPA applies to for-profit businesses with over $26,625,000 revenue (2025 adjusted), or that buy, sell or share data of 100,000+ California consumers or households a year, or get 50%+ of revenue from selling or sharing ([CPPA thresholds](https://www.cppa.ca.gov/regulations/cpi_adjustment.html)). A pre-revenue startup with a few hundred users is out, unless it "shares" data for cross-context ads (it does not). Most other state laws (Virginia, Colorado, Oregon, etc.) have 100,000 or similar consumer thresholds. Exceptions to watch: Texas and Nebraska apply to non-small-businesses and still require consent to sell sensitive data even for small ones; Connecticut's 2025 amendment (effective July 1, 2026) lowered thresholds and added minors' duties such as no design features meant to extend minors' use and no targeted ads to minors ([Hunton](https://www.hunton.com/privacy-and-information-security-law/connecticut-amends-the-connecticut-data-privacy-act), [FPF](https://fpf.org/blog/the-connecticut-data-privacy-act-gets-an-overhaul-again/)) [VERIFY whether the minors sections have any threshold]. Kids' design codes (Maryland, Vermont, Nebraska; California's AADC is enjoined in large part) are worth a lawyer's look once miyagi has real users.

**What to do.** Do the things these laws all want anyway: no selling or ad sharing, no streaks or engagement tricks aimed at teens, honor deletion requests from anyone, collect the minimum. Revisit at 10,000 users or first revenue.

**Lawyer.** Not now.

### 14. GDPR / UK GDPR for EU and UK users. LOW to MEDIUM

**What.** GDPR applies to a non-EU business that offers services to people in the EU (Art. 3(2), [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj)). A free public download with no geo-block counts. Duties: lawful basis, a policy with Art. 13 contents, data subject rights, DPAs with processors, transfer mechanisms (Anthropic, Render and Supabase have DPAs with SCCs or the EU-US Data Privacy Framework; Render says it is DPF certified, [render.com/security](https://render.com/security)), and an EU/UK representative under Art. 27 unless processing is occasional and low risk. Child consent age for online services is 13 to 16 depending on the country (Art. 8). Gemini: only paid services for EEA/UK/Swiss users ([Gemini terms](https://aistudio.google.com/docs/terms)).

**What to do.** Simplest: say in the ToS that miyagi is offered in the US for now and do not market abroad; if EU/UK users are welcome, use a 16+ floor for them, paid Gemini or no Gemini, include the GDPR section in the policy (drafted), and appoint a representative once usage is more than occasional.

**Lawyer.** Yes before deliberately launching in the EU/UK.

### 15. Website cookies and storage (miyagi.study). LOW

**What the site does (checked in `miyagi-site/index.html`).** No analytics, no ad tags, no cookie set by miyagi's own code. It uses `localStorage` key `miyagi-code` to remember the download code the visitor typed. It loads three.js and lenis from cdn.jsdelivr.net, thumbnails from i.ytimg.com, and the YouTube iframe API from www.youtube.com with the player on youtube-nocookie.com, started automatically when the story reaches a video part (not on click). Fonts are self-hosted.

**Law.** US: no general cookie consent law; CalOPPA requires disclosing how the site responds to Do Not Track and whether third parties collect data. EU ePrivacy Art. 5(3) needs consent for storing or reading anything on the device unless strictly necessary for a service the user asked for ([EDPB guidelines 2/2023](https://www.edpb.europa.eu/our-work-tools/documents/public-consultations/2023/guidelines-22023-technical-scope-art-53-eprivacy_en)). The download-code memory is arguably user-requested; the auto-loaded YouTube player is not (YouTube stores identifiers even on the nocookie domain).

**What to do.** Add the cookie notice in `DRAFTS.md` to the site footer. Change the YouTube player to load only after a click on the poster frame (the stills already exist, so the story still works). Then no banner is needed. Optionally self-host three.js and lenis to drop jsDelivr.

**Lawyer.** No.

### 16. FERPA and student data laws (school use). LOW unless you sell to schools

**What.** FERPA binds schools that get federal funds, not miyagi, unless a school shares education records with miyagi under the "school official" exception. California SOPIPA applies only to operators who know the service is used primarily for K-12 school purposes and was designed and marketed for them (Bus. & Prof. Code § 22584, [text](https://california.public.law/codes/ca_bus_and_prof_code_section_22584)); a general self-learning tool is outside it ([FPF](https://fpf.org/wp-content/uploads/2016/03/FPF-Boot-Camp-SOPIPA-Presentation.pdf)). Marketing "for your CS class" or pitching districts changes that, and then SOPIPA bans targeted ads, profiling and selling student data, and requires security and deletion on school request; districts will also ask for a signed data privacy agreement (e.g. the [Student Data Privacy Consortium](https://privacy.a4l.org/) template).

**What to do.** Market to learners, not schools, for now. ToS: "not for use by a school on behalf of students without a separate written agreement".

**Lawyer.** Yes before any school or district deal.

### 17. AI output, liability and acceptable use in the ToS. LOW to MEDIUM

**What.** miyagi tells people what to type and run. Wrong advice could delete files or break a setup; a "Run" step that executes commands raises this further. Disclaimers and liability caps are standard and usually enforced against adults, weaker against minors (risk 2) and against consumers in some states and the EU.

**What to do.** In the app: confirm before any command miyagi runs on the user's machine, never run destructive commands without showing them, and tell users to keep backups. In the ToS: AI disclaimer, as-is warranty disclaimer, liability cap, acceptable use, no reliance for safety-critical work (drafted).

**Lawyer.** Recommended for one review of the final ToS.

### 18. California companion chatbot law (SB 243). LOW

**What.** Effective January 1, 2026, SB 243 regulates "companion chatbots" (AI that sustains a relationship across sessions to meet social needs), with extra duties for known minors and a private right of action ([NatLawReview](https://natlawreview.com/article/when-ai-feels-human-californias-sb-243-opens-door-private-lawsuits)). A coding tutor that gives task hints is likely outside the definition, but a chatty "sensei" persona with memory moves toward it.

**What to do.** Keep miyagi task-focused (no relationship or emotional companionship features), keep the "this is AI" disclosure. Revisit if a persistent chat persona is added.

**Lawyer.** No.

## Things checked that are not problems

- Sign-in uses the system browser with PKCE and a loopback redirect, tokens encrypted with the OS keychain, and the renderer never sees tokens (`app/src/main/features/auth.ts`). Good basis for the security statements in the policy.
- The cloud install token is random, encrypted at rest, never logged (`app/src/main/features/cloud.ts`).
- Crash reports and usage are off by default (`Privacy.tsx`).
- The site sets no tracking cookies and has no analytics.
- No ElevenLabs field is shown in the app; voice uses the system voice (team rule). The engine still has an `ELEVENLABS_API_KEY` slot (`server/config.py`); if a user's text could ever go to ElevenLabs, add it to the subprocessor list [VERIFY it is unreachable in shipped builds].

## Contact and paperwork checklist

- `[CONTACT EMAIL]` for privacy (e.g. privacy@miyagi.study) and copyright, forwarded to both founders and a parent.
- DMCA agent registration ($6).
- Founders' agreement, parents co-sign.
- Vendor accounts in an adult's name; DPAs accepted.
- Google Search Console domain verification for miyagi.study.
- Written retention policy and short security program (COPPA amended rule; also good practice).
