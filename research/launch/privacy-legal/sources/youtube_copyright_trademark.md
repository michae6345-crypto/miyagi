# YouTube terms, copyright and fair use for AI-built lessons, DMCA safe harbor, and the "miyagi" trademark (status as of 2026-11-21)

Scope: YouTube and IP only (privacy law is covered in a separate note). Every link was accessed 2026-11-21 unless marked otherwise. "Not re-fetched" means the source is cited for standard statutory or case text that I did not open in this session. Pending cases are flagged **[PENDING]**. Aggregator or law-firm summaries are labeled as secondary.

---

## 1. YouTube Terms of Service: Permissions and Restrictions (accessing, downloading, automated access)

### Takeaway
The current YouTube ToS (effective 2023-12-15) bars reproducing, downloading or otherwise using any Content except "as expressly authorized by the Service", and bars "any automated means (such as robots, botnets or scrapers)". Playing videos through YouTube's own embeddable player is expressly allowed. Downloading transcripts or video for an app's own processing is not.

### Cited Findings
- The ToS shown at youtube.com/t/terms is dated and effective **December 15, 2023**. The page links a 2022 archived version and shows no later "last modified" date — [YouTube Terms of Service, eff. 2023-12-15; accessed 2026-11-21](https://www.youtube.com/t/terms)
- Opening grant: "You may access and use the Service as made available to you, as long as you comply with this Agreement and applicable law." — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- Restriction 1: you may not "access, reproduce, download, distribute, transmit, broadcast, display, sell, license, alter, modify or otherwise use any part of the Service or any Content except: (a) as expressly authorized by the Service" (the other exception is prior written permission from YouTube and, if applicable, the rights holders; this second exception is from my reading of the full text and was not in the fetch summary) — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- Restriction 2: you may not "circumvent, disable, fraudulently engage with, or otherwise interfere with any part of the Service". — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- Restriction 3: you may not "access the Service using any automated means (such as robots, botnets or scrapers)". The full text has exceptions for public search engines that follow robots.txt and for YouTube's prior written permission (from my reading, not the fetch summary; the Developer Policies repeat the robots.txt carve-out). — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- Restriction 4: you may not "collect or harvest any information that might identify a person (for example, usernames or faces)". — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- Embedding is expressly allowed: "You may also show YouTube videos through the embeddable YouTube player." — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- The license uploaders grant to other users covers use of their content "only as enabled by a feature of the Service (such as video playback or embeds)". It grants no right to use Content independently of the Service. — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- The ToS text I fetched says nothing explicit about AI or ML use of Content. — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
- YouTube's help page on its creator AI-training setting says "YouTube's Terms of Service prohibits content from unauthorized use, such as unauthorized downloads and scraping." It also says YouTube "can't control what a third-party company does". — [YouTube Help, "Your content & third-party training" (undated; ©2026); accessed 2026-11-21](https://support.google.com/youtube/answer/15509945?hl=en)
- Since December 2024 creators can opt in to letting named third-party AI companies train on their videos. The setting is off by default, and the first list had 18 companies, including Anthropic, OpenAI, Apple and Meta. — [TechCrunch, 2024-12-16; accessed 2026-11-21](https://techcrunch.com/2024/12/16/youtube-will-let-creators-opt-out-of-third-party-ai-training); [YouTube Help; accessed 2026-11-21](https://support.google.com/youtube/answer/15509945?hl=en)
- YouTube CEO Neal Mohan on OpenAI/Sora: the ToS "does not allow for things like transcripts or video bits to be downloaded and that is a clear violation of our TOS." This is from a 2024 Bloomberg interview; the syndicated source does not give the exact date. — [Yahoo/syndicated report; accessed 2026-11-21](https://ca.news.yahoo.com/does-google-train-ai-youtube-194449512.html)

### Inferences
- Playing a tutorial in YouTube's official embedded player inside the Electron window fits the ToS's "expressly authorized" embed feature and the uploader's license to other users. That is the safest way to show the video.
- Fetching transcripts or media outside YouTube's official surfaces (timedtext/innertube endpoints, yt-dlp, headless browsers) conflicts with Restrictions 1 and 3, whether done on miyagi's servers or inside the user's client. YouTube's CEO has called transcript downloading specifically "a clear violation".
- A creator opting in to "third-party training" covers model training by listed AI companies, not an app downloading transcripts. It does not authorize miyagi's pipeline.

### Gaps
- I found no 2025 or 2026 revision of the main ToS. If YouTube published one after 2023-12-15, the youtube.com/t/terms page did not show it on 2026-11-21.
- The exact date of the Mohan interview was not confirmed in the fetched source (contemporaneous reporting places it in April 2024).

---

## 2. YouTube API Services Terms and Developer Policies: embedded player, privacy policy, storage, derivative data, AI, audits

### Takeaway
An app that uses the embedded player or IFrame Player API is an "API Client" bound by the API Services ToS, the Developer Policies and the Required Minimum Functionality (RMF) rules. The main rules are:
- Nothing may overlay or obscure the player.
- The viewport must be at least 200x200 px.
- Autoplay only once the player is more than half visible.
- No separating audio from video.
- No downloading, caching or storing of audiovisual content without written approval.
- API data may be stored for at most 30 days.
- The app must have a privacy policy that links the YouTube ToS and Google's Privacy Policy.
- The player request must send an HTTP Referer.

No fetched API document mentions AI, ML or model training. A formal compliance audit is required only to get more Data API quota, but YouTube may audit any client at any time.

### Cited Findings
**Who is bound**
- The RMF page says "API Clients that use the YouTube embedded player (including the YouTube IFrame Player API) must provide identification through the HTTP Referer request header". So embed-only apps count as API Clients. — [YouTube RMF (no date shown); accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)

**Embedded-player rules (RMF and Developer Policies)**
- "Embedded players must have a viewport that is at least 200px by 200px." YouTube recommends 16:9 players be at least 480x270. — [YouTube RMF; accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)
- "You must not display overlays, frames, or other visual elements in front of any part of a YouTube embedded player", and must not use them "to obscure any part of an embedded player". — [YouTube RMF; accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)
- Autoplay: the app "must not initiate an automatic playback until the player is visible and more than half of the player is visible". A screen may not have more than one autoplaying YouTube player at once. — [YouTube RMF; accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)
- "You must not make changes to the YouTube player that are not explicitly described by the API documentation." — [YouTube RMF; accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)
- WebViews: "use one of the OS-provided WebView types when available." — [YouTube RMF; accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)
- Referer rules:
  - API Clients "must not use the `noreferrer` feature", and YouTube recommends the `strict-origin-when-cross-origin` Referrer-Policy.
  - Failure "might result in reduced functionality in the YouTube embedded player".
  - Source: [YouTube RMF; accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)
- In practice, a missing Referer shows as player "Error 153".
  - Reported in Chrome-extension pages that send no Referer (Sept 2025) and in WebView apps; a December 2025 write-up fixed it by allowing a Referer.
  - I found no Electron-specific official guidance.
  - Sources: [Chromium extensions group thread, 2025; accessed 2026-11-21](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/OUJad0q-d_g); [Simon Willison, 2025-12-01; accessed 2026-11-21](https://simonwillison.net/2025/Dec/1/youtube-embed-153-error/)
- Developer Policies prohibitions:
  - Don't "modify, build upon, or block any portion or functionality of a YouTube player".
  - Don't "modify, interfere with, replace, or block advertisements".
  - Don't "separate, isolate, or modify the audio or video components".
  - Don't play from "a background player, meaning a player that is not displayed".
  - Don't "interfere with or obscure any attribution provided by YouTube".
  - Don't charge users to watch embedded content or require subscribing or liking.
  - Source (as rendered on 2026-11-21; the page shows no last-updated date, only a reference to "June 01, 2026"): [YouTube API Services Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)

**Privacy policy and terms requirements (Developer Policies III.A)**
- The app must "display a link to YouTube's Terms of Service", and its terms must state that users are bound by the YouTube ToS. — [Developer Policies III.A.1; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- The privacy policy must:
  - be "prominently displayed and easily accessible to users at all times";
  - "notify users that the API Client uses YouTube API Services";
  - "reference and link to the Google Privacy Policy".
  - Source: [Developer Policies III.A.2; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- The API Services ToS §7 says each API Client "will provide and adhere to a published privacy policy" that "clearly and accurately describes" what user information it accesses. — [YouTube API Services ToS (no last-updated date shown); accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service)

**Downloading, caching, storage and derived data**
- API Clients must not "download, import, backup, cache, or store copies of YouTube audiovisual content" without YouTube's prior written approval (III.E.1.a). — [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- Storage limits (III.E.4):
  - Non-Authorized Data (data available without user credentials): only "limited amounts" for "not longer than 30 calendar days".
  - Authorized Data: delete or refresh within 30 days.
  - On user request, delete within 7 days.
  - Source: [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- Clients may not use API Data "to create new or derived data or metrics" (III.E.4.h) or to gain insights into YouTube's usage or revenue (III.E.2.b). — [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- Clients may not "sell, purchase, lease, lend, convey, redistribute, or sublicense" API services or audiovisual content (III.G.1.a). — [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- Scraping: clients "must not, and must not encourage, enable, or require others to, directly or indirectly, scrape" (III.E.6). — [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- The API ToS §16.3 grants "no rights or licenses ... to reproduce or distribute audiovisual content". "YouTube Property" includes "all derivative works" of it (§16.1). — [API Services ToS; accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service)

**AI and ML**
- The words "artificial intelligence", "machine learning" and "train" do not appear in the fetched API Services ToS. The fetched Developer Policies likewise do not mention AI, ML or model training. — [API Services ToS; accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service); [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)

**Audits, monitoring, termination, liability**
- §6: YouTube may "monitor, review and inspect your API Client(s)" and audit use "at any time and without further notice to you". — [API Services ToS; accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service)
- A formal "API Compliance Audit" is required for quota extensions, and approved quota is limited to the audited use case (III.D.3). YouTube may also require accounts for compliance review (III.H). — [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
- Data API default quota is 10,000 units/day. More quota requires the quota extension request form. — [YouTube Data API "Getting started"; accessed 2026-11-21](https://developers.google.com/youtube/v3/getting-started)
- §24.2: YouTube may suspend or terminate access, and "we have no obligation" to give notice. — [API Services ToS; accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service)
- §21: the developer indemnifies YouTube. — [API Services ToS; accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service)
- §20.1: YouTube's liability is capped. — [API Services ToS; accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service)
- §2.3: changes take effect "no sooner than 30 calendar days after posting". — [API Services ToS; accessed 2026-11-21](https://developers.google.com/youtube/terms/api-services-terms-of-service)

### Inferences
- An "overlay" product design collides directly with the RMF overlay rule when the YouTube player sits in miyagi's own window. Lesson panels, highlights, cursors or grading toasts must sit beside or outside the player, never on top of it.
- If the overlay instead floats over youtube.com in the user's normal browser, it is not an embedded-player API Client for that playback. The YouTube ToS still applies to any reading of the page (DOM scraping or caption interception counts as "automated means").
- Electron is bundled Chromium, not an "OS-provided WebView". The RMF says to use OS WebViews "when available", which is ambiguous for desktop Electron.
- A practical approach: load the player from an https page on miyagi.study inside the Electron window. That supplies a real Referer identifying the app and avoids Error 153 from `file://` or custom-protocol origins. This should be tested, not assumed.
- If miyagi uses only the IFrame player and oEmbed (no Data API key), no quota audit is triggered. The privacy policy and ToS-link duties still apply, and YouTube can still review the client.
- The 30-day storage rule covers API Data (titles, thumbnails, statistics from the Data API). Cached lesson records keyed by video ID that also store such metadata should refresh or re-fetch it at least every 30 days.
- Generated lessons are not "API Data" if the transcript was not obtained through the Data API. But III.E.4.h's ban on "derived data" is a reason not to build lessons from Data API outputs.
- Silence on AI in YouTube's API documents is not permission. The general bans on downloading, caching and scraping do the work.

### Gaps
- None of the fetched API pages shows a "last updated" date. The revision history page was not reviewed line by line.
- I did not find official guidance on whether an Electron BrowserWindow or `<webview>` counts as an acceptable "WebView" under RMF.

---

## 3. Transcripts: legitimate routes, ToS risk of each, enforcement and lawsuits

### Takeaway
There are three routes, in descending order of safety:
1. **Gemini API's native YouTube-URL input.** Google's own documented feature for public videos; it is "Preview", free, and capped at 8 h/day on the free tier.
2. **Data API `captions.download`.** Requires OAuth from someone who can edit the video, so it works only for creators who opt in.
3. **Unofficial timedtext/innertube endpoints, `youtube-transcript-api` or yt-dlp.** These break the ToS. YouTube now actively blocks them with cloud-IP bans and proof-of-origin tokens.

In October 2026, three federal courts let YouTube creators' DMCA §1201 anti-circumvention claims proceed against AI companies that allegedly bypassed those measures with yt-dlp. That raises the stakes of route 3 beyond contract breach.

### Cited Findings
**Route A: Gemini API YouTube URL**
- "Preview: The YouTube URL feature is in preview and is available at no charge." Also: "Pricing and rate limits are likely to change." — [Gemini API video understanding docs (no date shown); accessed 2026-11-21](https://aistudio.google.com/docs/video-understanding)
- Limits:
  - "You can only upload public videos (not private or unlisted videos)."
  - Free tier: no more than "8 hours of YouTube video per day". The paid tier has no length-based limit.
  - Gemini 2.5 and later: up to 10 videos per request.
  - About 100 tokens per second of video at default resolution.
  - Up to about 3 hours of video per request with 1M-context models at low resolution.
  - Source: [Gemini video docs; accessed 2026-11-21](https://aistudio.google.com/docs/video-understanding)
- The page does not mention YouTube's Terms of Service. — [Gemini video docs; accessed 2026-11-21](https://aistudio.google.com/docs/video-understanding)
- Gemini API Additional Terms (effective 2026-03-23):
  - "You must be 18 years of age or older to use the APIs."
  - Services may not be used in API Clients "directed towards or is likely to be accessed by individuals under the age of 18".
  - On unpaid tiers Google uses submitted content and responses to "provide, improve, and develop" products, and human reviewers may read them. Paid tiers are excluded.
  - Source: [Gemini API Additional Terms, eff. 2026-03-23; accessed 2026-11-21](https://aistudio.google.com/docs/terms)

**Route B: YouTube Data API captions.download**
- "This method requires the user to have permission to edit the video." It needs `youtube.force-ssl` or `youtubepartner` scope and costs 200 quota units. A 403 means "The permissions associated with the request are not sufficient to download the caption track." — [YouTube Data API captions.download; accessed 2026-11-21](https://developers.google.com/youtube/v3/docs/captions/download)

**Route C: unofficial endpoints and libraries**
- The `youtube-transcript-api` README warns that YouTube "has started blocking most IPs that are known to belong to cloud providers (like AWS, Google Cloud Platform, Azure, etc.)", producing `RequestBlocked`/`IpBlocked`. It suggests rotating residential proxies. — [jdepoix/youtube-transcript-api (GitHub); accessed 2026-11-21](https://github.com/jdepoix/youtube-transcript-api)
- Secondary (developer blog): YouTube's caption requests now need a BotGuard-generated Proof-of-Origin (PO) token. Without one the timedtext endpoint returns an empty response. — [DEV Community post, 2026; accessed 2026-11-21](https://dev.to/jamhimself/why-your-youtube-transcript-scraper-started-returning-empty-strings-and-how-to-fix-it-in-2026-20ed); [library issue on PO tokens; accessed 2026-11-21](https://github.com/jdepoix/youtube-transcript-api/issues/592)

**Enforcement and litigation over YouTube scraping**
- **"YouTube Subtitles" dataset** (Proof News with Wired, July 2024): subtitles from 173,536 videos on 48,000+ channels. The dataset was in EleutherAI's "The Pile" and used by Apple, Nvidia, Anthropic, Salesforce and others. Anthropic said YouTube's terms "cover direct use of its platform, which is distinct from use of The Pile dataset." — [Proof News, July 2024; accessed 2026-11-21](https://www.proofnews.org/apple-nvidia-anthropic-used-thousands-of-swiped-youtube-videos-to-train-ai/); [Engadget, July 2024; accessed 2026-11-21](https://www.engadget.com/apple-nvidia-and-anthropic-reportedly-used-youtube-transcripts-without-permission-to-train-ai-models-170827317.html)
- **Millette v. OpenAI** (N.D. Cal. No. 5:24-cv-04710, filed 2024-08-02) **[PENDING / status unconfirmed]**:
  - Putative class action by a YouTuber alleging OpenAI trained on YouTube transcripts without consent; claims were unjust enrichment and UCL, not copyright.
  - OpenAI moved to dismiss in Sept 2024 and again in Dec 2024, arguing Copyright Act preemption.
  - A companion case, Millette v. Google (No. 5:24-cv-04708), was briefed in Feb 2025.
  - I could not confirm any ruling.
  - Sources: [TechCrunch, 2024-08-05; accessed 2026-11-21](https://techcrunch.com/2024/08/05/youtuber-files-class-action-suit-over-openais-scrape-of-creators-transcripts/); [Bloomberg Law; accessed 2026-11-21](https://news.bloomberglaw.com/ip-law/openai-seeks-dismissal-of-carbon-copy-youtube-scraping-lawsuit); [Justia docket, Millette v. Google; accessed 2026-11-21](https://dockets.justia.com/docket/california/candce/5:2024cv04708/433672)
- **2025–2026 wave of DMCA §1201 suits by YouTube creators.** Parallel putative class actions were filed Nov 2025 to Apr 2026 against Nvidia, Meta, ByteDance, Snap, Apple, OpenAI, Amazon and Runway. The alleged measures circumvented were YouTube's "rolling cipher", IP blocking and rate limits, session-bound URLs, CAPTCHAs and PO tokens. The alleged tool was yt-dlp. — [openclassactions.com (secondary); accessed 2026-11-21](https://openclassactions.com/lawsuits/runway-ai-youtube-video-scraping-dmca-class-action-lawsuit.php)
  - *Ted Entertainment v. ByteDance* (N.D. Cal. No. 3:25-cv-10933, Corley J.) **[PENDING]**:
    - Motion to dismiss the §1201(a) claim denied on 2026-10-02.
    - The court held creators whose works the measures protect may sue under §1203. Injury was plausibly alleged, including lost ad revenue from retrievals with no ad impressions.
    - It relied on *Disney v. VidAngel* (9th Cir. 2017) for the point that a measure can control both access and copying.
    - Source: [Trademark Lawyer Magazine, 2026-10 (secondary); accessed 2026-11-21](https://trademarklawyermagazine.com/bytedance-must-face-youtubers-ai-training-suit-over-alleged-youtube-scraping/)
  - *Ted Entertainment v. Apple* (N.D. Cal. No. 3:26-cv-02936, Seeborg J.) **[PENDING]**:
    - Motion to dismiss denied on 2026-10-09.
    - A measure qualifies if it gives "some degree of control over access". The alleged rolling cipher, IP blocking and session-bound URLs were enough at the pleading stage.
    - Source: [Center Consulting AI library (secondary); accessed 2026-11-21](https://www.centerconsulting.com/ai-library/milestones/2026-ted-entertainment-v-apple-dmca-ruling); [MacRumors, 2026-07-02; accessed 2026-11-21](https://www.macrumors.com/2026/07/02/apple-responds-to-youtuber-ai-lawsuit/)
  - *Ace Cam, Inc. v. Runway AI* (S.D.N.Y. No. 1:26-cv-01362, Kaplan J.) **[PENDING]**:
    - Motion to dismiss denied on 2026-10-30.
    - The court said "the public nature of content that has been uploaded to YouTube does not render it unprotected."
    - Source: [openclassactions.com (secondary); accessed 2026-11-21](https://openclassactions.com/lawsuits/runway-ai-youtube-video-scraping-dmca-class-action-lawsuit.php)
  - The Nvidia case **[PENDING]**: the motion to dismiss was argued 2026-07-23. Ted Entertainment withdrew its own claims on 2026-10-27, and plaintiff Matt Fisher remains. A separate report says a January 2026 ruling let the §1201 claim proceed; this conflicts with other sources and is unconfirmed. — [openclassactions.com (secondary); accessed 2026-11-21](https://openclassactions.com/news/ai/ted-entertainment-h3-drops-nvidia-ai-scraping-lawsuit.php); [Tyz Law (secondary); accessed 2026-11-21](https://www.tyzlaw.com/insights-archive/beyond-infringement-the-rise-of-dmca-claims-in-ai-litigation)
  - All of these are pleading-stage rulings that accept the allegations as true. No court has found that anyone actually circumvented YouTube's measures, and no class is certified. — [Center Consulting; accessed 2026-11-21](https://www.centerconsulting.com/ai-library/milestones/2026-ted-entertainment-v-apple-dmca-ruling); [openclassactions.com; accessed 2026-11-21](https://openclassactions.com/lawsuits/runway-ai-youtube-video-scraping-dmca-class-action-lawsuit.php)
- Civil remedies for §1201 violations include statutory damages of $200 to $2,500 "per act of circumvention". — [17 U.S.C. §1203(c)(3)(A), LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/1203)

### Inferences
- **Gemini YouTube-URL input is the lowest-risk way to "watch" and analyze a video.** Google retrieves the video inside its own systems, and miyagi never downloads media or captions. Three caveats:
  - It is "Preview", so it could change or disappear.
  - It covers public videos only.
  - The 18+/not-directed-at-minors clause in the Gemini API terms is a real problem for a student-facing app. The privacy and minors researcher should reconcile it.
- **Gemini input does not license the creator's copyright.** It only removes the YouTube-ToS acquisition problem (see section 4).
- **`captions.download` is the cleanest legal route but only for opted-in creators.** It fits a "creator partner" program, not arbitrary tutorials.
- **Unofficial transcript scraping is now both a ToS breach and a plausible §1201 theory** if it involves reusing PO tokens, rotating IPs or proxies, or deciphering signatures, which is what yt-dlp and residential-proxy setups do. The 2026 rulings involve mass video downloading for model training, which is far from fetching one caption track per user request. Still, the access-control reasoning (PO tokens, session-bound URLs) is not limited to video files.
- **A lightweight "user's own browser fetches the captions" design still uses automated access** under ToS Restriction 3. It may also hit the same PO-token gate.

### Gaps
- I did not locate a ruling in *Millette v. OpenAI* or *Millette v. Google*. I also could not verify a separate 2024 "Millette v. Nvidia" case in this session.
- The 2026 §1201 rulings were read through secondary summaries (aggregators and law-firm alerts), not the opinions.
- I found no public enforcement action (lawsuit or cease-and-desist) by YouTube or Google itself against a transcript tool. Enforcement appears to be technical (IP blocks, PO tokens).

---

## 4. Copyright: AI-generated lessons as derivative works vs. unprotectable methods; fair use and the 2025–2026 AI rulings; market substitution; code in tutorials

### Takeaway
How-to steps, facts and programming methods are not protected (17 U.S.C. §102(b)). Short, functional code is also weakly protected (merger, scènes à faire). But a tutorial's expressive selection, sequencing, wording and examples are protected. Close step-by-step "lessons" can look like abridgments or summaries, which courts have repeatedly found not fair use when they substitute for the original:
- *Twin Peaks* (1993)
- *Castle Rock* (1998)
- *Penguin Random House v. Colting* (2017)
- *In re OpenAI* summaries (2025)

In May 2025 the Copyright Office said RAG-style outputs that "summarize or provide abridged versions of retrieved copyrighted works" are less likely to be transformative. The first appellate AI fair-use ruling (*Thomson Reuters v. ROSS*, 3d Cir., Sept 2026) went against the AI developer on a competing-product theory.

The decisive facts for miyagi are factor 4 (does the lesson replace watching the video?) and how much of the tutorial's expression the lesson carries.

### Cited Findings
**Statute and Supreme Court framework**
- §102(b): copyright does not "extend to any idea, procedure, process, system, method of operation, concept, principle, or discovery". — [17 U.S.C. §102, LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/102)
- §107 sets out four factors: purpose and character (including commercial vs. nonprofit educational), nature of the work, amount and substantiality, and effect on the potential market. — [17 U.S.C. §107, LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/107)
- *Campbell v. Acuff-Rose* (1994) set the transformative-use and market-substitution framework. — [510 U.S. 569, govinfo; accessed 2026-11-21](https://www.govinfo.gov/content/pkg/USREPORTS-510/pdf/USREPORTS-510-569.pdf)
- *Google v. Oracle* (2021) held that copying the Java API declaring code to build a new platform was fair use; it did not decide copyrightability. — [593 U.S. 1, Justia (not re-fetched); accessed 2026-11-21](https://supreme.justia.com/cases/federal/us/593/18-956/)
- *Andy Warhol Found. v. Goldsmith* (2023): when the original and the secondary use serve the same or highly similar purpose and the use is commercial, factor 1 tends to weigh against fair use. — [598 U.S. 508, Justia (not re-fetched); accessed 2026-11-21](https://supreme.justia.com/cases/federal/us/598/21-869/)
- Statutory damages run $750–$30,000 per work, up to $150,000 if willful. They are available only for timely registered works. — [17 U.S.C. §504(c), LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/504); [17 U.S.C. §412, LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/412)

**Summaries, abridgments and derivative markets**
- *Castle Rock v. Carol Publishing* (2d Cir. 1998): a 643-question Seinfeld trivia book was not fair use. It usurped a derivative market the owner could exploit even if it had no plans to. — [Copyright Office fair-use summary; accessed 2026-11-21](https://www.copyright.gov/fair-use/summaries/castlerock-carolpubl%E2%80%99g-2dcir1998.pdf); [Copyright Alliance case page; accessed 2026-11-21](https://copyrightalliance.org/copyright-cases/castle-rock-ent-v-carol-publishing)
- The Copyright Office's Part 3 report cites three further cases (p. 46 fn. 266): — [USCO Part 3 pre-publication PDF, May 2025; accessed 2026-11-21](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-3-Generative-AI-Training-Report-Pre-Publication-Version.pdf)
  - *Twin Peaks v. Publications Int'l* (2d Cir. 1993): detailed plot synopses were essentially "abridgments".
  - *Penguin Random House v. Colting*, 270 F. Supp. 3d 736 (S.D.N.Y. 2017): children's abridgments were not fair use.
  - *Nihon Keizai Shimbun v. Comline* (2d Cir. 1999): news "abstracts" were "not in the least 'transformative'".
- *In re OpenAI Copyright Litigation* (S.D.N.Y., Stein J., 2025-10-27) **[PENDING]**:
  - Denied OpenAI's motion to dismiss the output-infringement claim.
  - A detailed ChatGPT summary of *A Game of Thrones* could be found substantially similar by a "discerning observer".
  - Fair use was not reached.
  - Sources: [IPWatchdog, 2025-10-28 (secondary); accessed 2026-11-21](https://ipwatchdog.com/2025/10/28/openai-loses-bid-dismiss-multi-district-class-action-chatgpt-outputs/); [Publishers Weekly (secondary); accessed 2026-11-21](https://www.publishersweekly.com/pw/by-topic/digital/copyright/article/98961-authors-class-action-lawsuit-against-openai-moves-forward)

**US Copyright Office, Part 3 (Generative AI Training), pre-publication version, May 2025**
- Status:
  - Still labeled "pre-publication" on copyright.gov.
  - A July 2026 commentary ties its future to a Supreme Court order in *Blanche v. Perlmutter*, No. 25A478 (2026-06-30), after the Register's May 2025 removal.
  - Sources: [copyright.gov/ai; accessed 2026-11-21](https://copyright.gov/ai/); [Lowenstein Sandler, 2026-07-07; accessed 2026-11-21](https://www.lowenstein.com/news-insights/publications/client-alerts/scotus-ruling-re-opens-the-door-on-the-copyright-office-s-ai-training-report-ai)
- On RAG (p. 46): "The use of RAG is less likely to be transformative where the purpose is to generate outputs that summarize or provide abridged versions of retrieved copyrighted works, such as news articles, as opposed to hyperlinks." — [USCO Part 3 PDF; accessed 2026-11-21](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-3-Generative-AI-Training-Report-Pre-Publication-Version.pdf)
- On market substitution (p. 62): RAG outputs "may be more likely to contain protectable expression, including derivative summaries and abridgments". A user whose need the augmented response satisfies "will not pay to obtain it in the marketplace." — [USCO Part 3 PDF; accessed 2026-11-21](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-3-Generative-AI-Training-Report-Pre-Publication-Version.pdf)
- The report endorses "market dilution" (flooding markets with works of the same kind) as a cognizable harm while calling it "uncharted territory". It finds fair use "highly fact-specific". — [Sidley summary, 2025-05-28 (secondary); accessed 2026-11-21](https://datamatters.sidley.com/2025/05/28/generative-ai-meets-copyright-scrutiny-highlights-from-the-copyright-offices-part-iii-report/)

**AI decisions, 2025–2026**
- *Thomson Reuters v. ROSS Intelligence* (3d Cir. No. 25-2153, decided 2026-09-29; affirmed D. Del. Feb 2025):
  - 2,243 Westlaw headnotes, which are short editorial summaries of opinions, were original enough to be protected.
  - ROSS's copying to train a competing, non-generative legal-research tool was not fair use. Factors 1, 3 and 4 went against ROSS; factor 2 slightly favored it.
  - The court rejected the "intermediate copying" analogy because copying was easier but not necessary.
  - It found harm in both the existing research market and a "rapidly developing" AI-training-data market.
  - It left generative AI open. It is the first federal appellate ruling on AI-training fair use.
  - Sources: [Ballard Spahr, 2026-10-02; accessed 2026-11-21](https://www.ballardspahr.com/insights/alerts-and-articles/2026/10/third-circuit-addresses-fair-use-in-ai-training-but-leaves-generative-ai-questions-unresolved); [IPWatchdog, 2026-09-30; accessed 2026-11-21](https://ipwatchdog.com/2026/09/30/third-circuit-affirms-revised-fair-use-ruling-against-ross-ai-legal-research-platform-in-sealed-opinion/); [Authors Alliance critique, 2026-10-02; accessed 2026-11-21](https://www.authorsalliance.org/2026/10/02/third-circuit-affirms-in-thomson-reuters-v-ross-the-court-gets-merger-wrong-and-does-a-disservice-to-fair-use/)
- *Bartz v. Anthropic* (N.D. Cal.):
  - Alsup J.'s 2025-06-23 order held training on books "exceedingly transformative" and fair use, but building a library from pirated copies was not.
  - The class settlement of about $1.5B got final approval on 2026-07-20.
  - Appeals, including of the fee award, were reported in the Ninth Circuit **[PENDING]**.
  - Sources: [Skadden, July 2025; accessed 2026-11-21](https://www.skadden.com/insights/publications/2025/07/fair-use-and-ai-training); [Authors Alliance, 2026-07-21; accessed 2026-11-21](https://www.authorsalliance.org/2026/07/21/bartz-v-anthropic-settlement-receives-final-approval/); [Authors Guild; accessed 2026-11-21](https://authorsguild.org/news/court-grants-final-approval-anthropic-copyright-settlement/)
- *Kadrey v. Meta* (N.D. Cal., Chhabria J., 2025-06-25):
  - Summary judgment for Meta on fair use, but on the record presented. The judge said plaintiffs might have won with market-dilution evidence.
  - The case continued in 2026, with an amended claim about BitTorrent distribution **[PENDING]**.
  - Sources: [Skadden; accessed 2026-11-21](https://www.skadden.com/insights/publications/2025/07/fair-use-and-ai-training); [National Law Review (secondary); accessed 2026-11-21](https://natlawreview.com/article/ai-vs-authors-update-court-approves-historic-anthropic-settlement-while-meta)

**Edtech-specific 2026 outcomes**
- *Barkley & Assocs. v. Quizlet* (C.D. Cal., SJ 2026-07-14):
  - Users, not Quizlet, supplied the volitional conduct for AI study tools run on user-uploaded sets: "the AI is the user's tool".
  - In the alternative, Quizlet qualified for §512(c), after removing 3,881 study sets on notice.
  - Source: [Thompson Coburn, 2026 (secondary); accessed 2026-11-21](https://www.thompsoncoburn.com/insights/education-platform-liability-in-the-ai-era-divergent-outcomes-for-quizlet-and-course-hero/)
- *Post University v. Learneo (Course Hero)* (D. Conn., verdict 2026-03-04):
  - The jury rejected §512(c) safe harbor on all works.
  - It awarded about $75.4M, almost entirely for DMCA §1202 violations: removing the university's copyright management information and replacing it with Course Hero branding. Infringement damages on five registered works were $114.85.
  - Source: [Thompson Coburn (secondary); accessed 2026-11-21](https://www.thompsoncoburn.com/insights/education-platform-liability-in-the-ai-era-divergent-outcomes-for-quizlet-and-course-hero/)
- §1202 statutory damages are $2,500–$25,000 per violation. — [17 U.S.C. §1203(c)(3)(B), LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/1203)

**Code in tutorials**
- *Computer Associates v. Altai* (2d Cir. 1992) set out the abstraction-filtration-comparison test. It filters out ideas, merger material, scènes à faire, public-domain material, and elements dictated by efficiency, compatibility or standard programming technique. — [Wikipedia summary (secondary); accessed 2026-11-21](https://en.wikipedia.org/wiki/Abstraction-Filtration-Comparison_test)
- Words and short phrases (names, titles, slogans) are not copyrightable. — [37 C.F.R. §202.1(a), LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/cfr/text/37/202.1)

### Inferences
**What a lesson actually carries over**
- The underlying method ("install X, create file Y, write a loop that does Z") is unprotected under §102(b).
- What can be protected is:
  - the narration's wording (in the transcript);
  - a distinctive selection and order of steps;
  - the author's original example project;
  - longer, non-trivial code written for the video.
- A lesson that re-expresses the method in its own words and checks the user's own code is much safer than one that reproduces transcript passages, the instructor's full example code, or a scene-by-scene structure.

**Fair use, factor by factor**
- **Factor 1.** Interactive grading of the learner's own code adds a new function, which helps. But under *Warhol*, teaching the same skill to the same audience is the same purpose. A free product helps, but caching and sharing across users at scale, plus any future monetization, cuts the other way.
- **Factor 4 decides most of it.** If miyagi requires and drives playback of the creator's video in the official embed (ads, views and watch time still go to the creator), the lesson works as a complement. If the lesson lets users skip the video, it substitutes. That is the *Castle Rock*, *Colting* and Copyright Office RAG concern.
- **Comparison with ROSS.** miyagi's facts are better than ROSS's: it does not train a model or build a rival video product. But *ROSS* shows appellate willingness to find that even short summaries are protected, and to weigh emerging licensing markets.

**Shared cache and attribution**
- Caching one generated lesson per video and serving it to every user makes miyagi, not each user, the "publisher" of the derived lesson. That weakens the *Quizlet* "user's tool" defense, which depended on user-uploaded materials and user-initiated AI runs.
- Course Hero's $75M §1202 verdict shows that stripping attribution can cost far more than the infringement itself. Lessons should always carry the creator's name, channel, video title and link.

### Gaps
- No case yet addresses AI-generated interactive lessons built from video tutorials specifically.
- I did not read the full ROSS opinion; its public version followed redactions.
- I found no reported suits by coding-tutorial creators against "YouTube-to-course" AI products.

---

## 5. Embedding: server test vs. SDNY rejection; embedding via YouTube's own player

### Takeaway
In the Ninth Circuit (which covers California), embedding content hosted on someone else's server is not a "display" under the server test (*Perfect 10*, 2007; *Hunley v. Instagram*, 2023; *McGucken v. Valnet*, 2024). SDNY courts have rejected the test (*Goldman v. Breitbart*, 2018; *McGucken v. Newsweek*). For miyagi this matters less: embedding through YouTube's official player is a use the uploader licensed under the YouTube ToS, provided the uploader left embedding on.

### Cited Findings
- *Hunley v. Instagram* (9th Cir. 2023-07-17, 73 F.4th 1060) reaffirmed the *Perfect 10 v. Amazon* server test outside search engines: a site embedding content stored on another server does not "display" it. — [Justia opinion; accessed 2026-11-21](https://law.justia.com/cases/federal/appellate-courts/ca9/22-15293/22-15293-2023-07-17.html); [DWT, 2023-08; accessed 2026-11-21](https://dwt.com/insights/2023/08/server-test-instagram-case-ninth-circuit)
- *McGucken v. Valnet* (9th Cir. 2024-12-19, No. 24-511, unpublished memo) applied *Hunley* to embedded Instagram posts on a travel site. — [9th Cir. memorandum; accessed 2026-11-21](https://cdn.ca9.uscourts.gov/datastore/memoranda/2024/12/19/24-511.pdf)
- *Goldman v. Breitbart* (S.D.N.Y. 2018-02-15) found embedded tweets showing a photo infringed the display right, calling server-test adoption "scattered". The Second Circuit declined an interlocutory appeal. — [EFF, 2018-02; accessed 2026-11-21](https://www.eff.org/deeplinks/2018/02/federal-judge-says-embedding-tweet-can-be-copyright-infringement); [Proskauer; accessed 2026-11-21](https://www.proskauer.com/blog/new-york-court-rebuffs-ninth-circuits-copyright-server-test-finds-embedded-tweet-displaying-copyrighted-image-to-be-infringement)
- Later SDNY decisions such as *McGucken v. Newsweek* also declined the server test. — [Weil, 2021-08-09; accessed 2026-11-21](https://www.weil.com/-/media/mailings/2021/q2/ip-media-alert-august-9-2021embedding-the-server-test-rift-sdny-decision-bucks-ninth-circuit-once-ag.pdf)
- The YouTube ToS license runs to other users "only as enabled by a feature of the Service (such as video playback or embeds)". The ToS also states "You may also show YouTube videos through the embeddable YouTube player." — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)

### Inferences
- Playing tutorials through YouTube's official player, when the uploader allows embedding, is low copyright risk in any circuit because it rests on a license, not only the server test. The app should respect the "embedding disabled" state (the player errors) rather than working around it.
- Embedding covers only the video playback. It does not cover miyagi's separately generated and cached lesson text.

### Gaps
- No Supreme Court or en banc ruling has settled the server-test split as of 2026-11-21, as far as these sources show.

---

## 6. DMCA §512 safe harbor for the shared lesson cache; agent registration; repeat-infringer policy; takedown workflow

### Takeaway
§512(c) protects material stored "at the direction of a user". Lessons that miyagi's own pipeline generates, caches and serves to everyone are at best a gray area and plausibly miyagi's own content. The Course Hero jury denied safe harbor to a platform that transformed and rebranded content. Even so, registering a DMCA agent costs $6, lasts 3 years, and is a precondition for any §512 protection. Adding a repeat-infringer policy and a fast takedown process is cheap insurance and also the practical way to handle creator complaints.

### Cited Findings
- §512(c)(1) covers infringement "by reason of the storage at the direction of a user". It requires:
  - no actual or "red flag" knowledge;
  - no direct financial benefit where the provider has the right and ability to control the activity;
  - expeditious removal on proper notice.
  - Source: [17 U.S.C. §512, LII; accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/512)
- §512(c)(2): the provider must designate an agent, post the agent's contact details publicly, and file them with the Copyright Office. — [17 U.S.C. §512, LII; accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/512)
- §512(i)(1)(A): the provider must have "adopted and reasonably implemented" a policy for terminating repeat infringers in appropriate circumstances, and must tell users about it. §512(i)(1)(B) requires accommodating standard technical measures. — [17 U.S.C. §512, LII; accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/512)
- §512(g): after a valid counter-notice, the provider restores the material "not less than 10, nor more than 14, business days" later unless the claimant sues. §512(f) creates liability for knowing material misrepresentation. — [17 U.S.C. §512, LII; accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/17/512)
- Agent designation must be filed electronically and lists the provider's legal name and street address plus the agent's mail address, phone and email. "A service provider's designation will expire and become invalid three years after it is registered". — [37 C.F.R. §201.38, LII; accessed 2026-11-21](https://www.law.cornell.edu/cfr/text/37/201.38)
- Fee: "The current fee is $6 per designation, amendment, or resubmission." Renewal is done by amending or resubmitting. A lapse can lose §512 protection. An individual or a job title can be the agent. A P.O. box is allowed for the agent's address. — [Copyright Office DMCA Directory FAQ; accessed 2026-11-21](https://copyright.gov/dmca-directory/faq.html); [DMCA Designated Agent Directory; accessed 2026-11-21](https://www.copyright.gov/dmca-directory/)
- Courts have not settled whether model-generated output counts as "stored at the direction of a user". In *Warner Bros. Discovery v. Midjourney* (C.D. Cal. No. 2:25-cv-08376), §512 was pleaded as a defense with no ruling found **[PENDING]**. — [Brooklyn Sports & Ent. Law blog (secondary); accessed 2026-11-21](https://sports-entertainment.brooklaw.edu/?p=4833)
- Quizlet got §512(c) protection (in the alternative) for user-uploaded sets that its AI tools processed. Course Hero was denied safe harbor, plausibly because it transformed, rebranded and paywalled the content. — [Thompson Coburn (secondary); accessed 2026-11-21](https://www.thompsoncoburn.com/insights/education-platform-liability-in-the-ai-era-divergent-outcomes-for-quizlet-and-course-hero/)

### Inferences
**Whether §512(c) covers the lesson cache**
- The user only picks a public video URL. miyagi's servers decide to fetch, analyze, generate, store and redistribute the lesson. That is weaker than Quizlet's user-uploaded sets.
- If users can edit or publish their own lesson variants, those user-authored parts fit §512(c) better than the base AI lesson.

**Minimum compliance kit**
1. Register an agent with the Copyright Office ($6; calendar a renewal before 3 years) and post the agent's details on miyagi.study.
2. Publish a copyright/DMCA policy with a notice address, counter-notice procedure and repeat-infringer policy.
3. Build a per-video "kill switch" that purges the cached lesson and blocks regeneration for that video ID or channel.
4. Offer a creator opt-out form and honor it quickly. Respond within 1–2 business days ("expeditious" is undefined; this is a practical target).
5. Keep a takedown log.
6. Never strip creator attribution from lessons (the §1202 risk).

### Gaps
- No court has decided §512(c) for AI-generated, operator-cached derivative content.
- The Quizlet and Course Hero facts come from a secondary law-firm summary.

---

## 7. Trademark risk of "miyagi": registrations, confusion, dilution, publicity rights, geographic/surname issues, other "Miyagi" companies, costs

### Takeaway
USPTO's search (run 2026-11-21) shows **no live MIYAGI mark for software, education or SaaS (classes 9/41/42) and no MIYAGI-formative mark owned by Sony or Columbia Pictures**. Columbia does own a live THE KARATE KID registration in classes 9 and 41. The serious conflict is in the market, not the register: **Miyagi Labs (Y Combinator W25, miyagilabs.ai)** launched "AI to transform YouTube content into interactive courses". That is nearly the same name for nearly the same service, so it likely holds earlier common-law rights. The Karate Kid connection (the name, the "waxon" download code, and per project notes a bonsai logo) adds a lower but real false-endorsement risk with Sony. It also undercuts any argument that the name is just a Japanese place or surname.

### Cited Findings
**USPTO Trademark Search, query "miyagi" (24 results; run 2026-11-21 via [tmsearch.uspto.gov](https://tmsearch.uspto.gov/search/search-results); accessed 2026-11-21)**

| Mark | Serial | Owner | Class / goods | Status |
|---|---|---|---|---|
| MIYAGI | 85530487 | Individual (USA) | 9: children's educational software; computer game programs | DEAD (abandoned) |
| MIYAGI EYEWEAR | 76249357 | H & H International Corp. (CA) | 9: eyeglasses, sunglasses | LIVE (registered) |
| MR MIYAGI | 99275655 | MR MIYAGI LLC (DE) | 43: restaurant and bar services | LIVE (pending) |
| MIYAGI DOKARATE | 97838655 | Fuzhou Taijiang Baiyi Trade Co. (China) | 3: bath and shower gels | LIVE (registered) |
| MIYAGI | 85712614 | Individual (Colombia) | 18: bags | DEAD (cancelled) |
| MIYAGI | 98378065 | Miyagi Cosmetics LLC (IL) | 3: lash serums | DEAD (abandoned) |
| MIYAGI | 90281124 | Individual | 25: hats, T-shirts | DEAD |
| MR. MIYAGI | 85173485 | NutraGenomics MFG (GA) | 3: herbal incense | DEAD |
| M MIYAGI | 77701509 | Individual (Colombia) | 28: action figures | DEAD |
| SENSEI MIYAGI | 88024197 | Individual | 41: live music entertainment | DEAD |
| MIMI MIYAGI | 77707156 / 75581092 | Individual / Mimi Miyagi Inc. | 41: entertainment | DEAD |
| MIYAGI'S (x5) | 76074692, 76010950-52, 78421701 | Crystal Ventures; Consolidated Diversified | 21, 25, 29, 42 (restaurant), 3 | DEAD |
| MIYAGI SUSHI BAR & GRILL; MIYAGIDOUGH | 77065666; 97701747 | restaurants | 43 | DEAD |
| MIYAGI CONCENTRATES; MIYAGI US | 88280826; 90218315 | individuals | 5; 25 | DEAD |
| Design marks (sake) | 86358550 (+2 dead) | SAURA Co. (Japan) | 33: sake | LIVE (one registered) |

No record lists Sony Pictures, Columbia Pictures or a Cobra Kai production company as owner. — [USPTO Trademark Search; accessed 2026-11-21](https://tmsearch.uspto.gov/search/search-results)

**Related USPTO searches (same day)**
- "karate kid": THE KARATE KID, Serial 88775511, owned by **Columbia Pictures Industries, Inc.**, classes 9 and 41 (pre-recorded DVDs and related entertainment), LIVE (registered). Also KARATE KID, Serial 99544594 (martial-arts instruction, class 41), LIVE (pending), owned by an unrelated Florida LLC. — [USPTO Trademark Search; accessed 2026-11-21](https://tmsearch.uspto.gov/search/search-results)
- "wax on": WAX ON WAX OFF, Serial 85305174 (class 44 spa services), and WAX ON, Serials 76076101 and 85341377, LIVE (registered), owned by WAX ON IP, LLC (WA). WAX ON YOGA (class 41 yoga instruction) is LIVE (pending). Several car-care WAX ON WAX OFF marks are dead. No Sony or Columbia owner appears. — [USPTO Trademark Search; accessed 2026-11-21](https://tmsearch.uspto.gov/search/search-results)

**WIPO Global Brand Database ("miyagi", 2026-11-21)**
- 146 records worldwide contain "miyagi"; I could review only about 11 because of UI limits. The site showed a 2026-11-20 banner about problems with its anti-bot protections.
- Seen:
  - Indonesia: MIYAGI, class 9, registered 2017 (IDM000580743), individual owner.
  - France: MIYAGI, class 25, registered (5034867).
  - Australia: Miyagi, class 5, registered (2257595).
  - Malaysia: MIYAGI, class 12, pending.
  - Peru: MIYAGI, classes 28 and 35, ended.
  - Israel: miyagi, class 43, expired.
- Source: [WIPO Global Brand Database; accessed 2026-11-21](https://branddb.wipo.int/en/similarname/results)

**Other "Miyagi" businesses in edtech**
- **Miyagi Labs**: Y Combinator Winter 2025, founded 2025, team of 2, New York, website miyagilabs.ai.
  - Its YC launch post is titled "Miyagi Labs: AI to transform YouTube content into interactive courses". It generated quizzes, AI feedback and an AI voice tutor from YouTube videos, and claimed "100+ courses with top professors and creators".
  - Its current YC one-liner is "AI tutors for exam prep".
  - Sources: [YC company page; accessed 2026-11-21](https://www.ycombinator.com/companies/miyagi-labs); [YC launch page; accessed 2026-11-21](https://www.ycombinator.com/launches/Mr9-miyagi-labs-ai-to-transform-youtube-content-into-interactive-courses); [Launch HN mirror "Miyagi (YC W25) turns YouTube videos into online, interactive courses"; accessed 2026-11-21](https://hnews-reader.vercel.app/new/43972425)
- The USPTO "miyagi" search above returned no application by Miyagi Labs as of 2026-11-21. — [USPTO Trademark Search; accessed 2026-11-21](https://tmsearch.uspto.gov/search/search-results)

**Franchise ownership**
- The Karate Kid franchise is owned by Columbia Pictures / Sony Pictures Entertainment, including Sony Pictures Television for *Cobra Kai*. "Wax on, wax off" originated with screenwriter Robert Mark Kamen. — [Wikipedia, The Karate Kid (franchise); accessed 2026-11-21](https://en.wikipedia.org/wiki/The_Karate_Kid_(franchise)); [Wikipedia, Daniel LaRusso; accessed 2026-11-21](https://en.wikipedia.org/wiki/Daniel_LaRusso)

**Legal standards**
- Federal dilution requires a mark "widely recognized by the general consuming public of the United States as a designation of source of the goods or services of the mark's owner". — [15 U.S.C. §1125(c)(2)(A), LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/15/1125)
- §43(a) false endorsement and false association also appear in §1125(a). — [15 U.S.C. §1125, LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/15/1125)
- Registration bars include "primarily geographically descriptive" (§2(e)(2)) and "primarily merely a surname" (§2(e)(4)). Likelihood of confusion (§2(d)) is assessed with the *du Pont* factors. — [15 U.S.C. §1052, LII (not re-fetched); accessed 2026-11-21](https://www.law.cornell.edu/uscode/text/15/1052)
- California's post-mortem publicity statute (Cal. Civ. Code §3344.1):
  - Covers a deceased personality's "name, voice, signature, photograph, or likeness" used on or in products, merchandise or goods, or to advertise or sell them.
  - Damages are the greater of $750 or actual damages, plus profits.
  - Rights last 70 years after death.
  - Successors cannot recover damages for uses before they register their claim with the Secretary of State.
  - Plays, books, audiovisual and similar works are exempt unless the use is "so directly connected with a product" that it is advertising.
  - A newer digital-replica provision sets $10,000 minimum damages.
  - Source: [Cal. Civ. Code §3344.1, FindLaw; accessed 2026-11-21](https://codes.findlaw.com/ca/civil-code/civ-sect-3344-1/)
- Pat Morita, who played Mr. Miyagi, died November 24, 2005. — [Wikipedia, Pat Morita (not re-fetched); accessed 2026-11-21](https://en.wikipedia.org/wiki/Pat_Morita)

**Costs**
- USPTO fees, from a page marked "Effective January 19, 2025 (Last revised November 1, 2026)":
  - base application $350 per class (electronic);
  - insufficient-information surcharge $100 per class;
  - $200 per extra 1,000 characters of free-form ID text;
  - Statement of Use or Amendment to Allege Use $150 per class;
  - each 6-month SOU extension $125 per class;
  - Section 8 declaration $325 per class; Section 9 renewal $325 per class.
  - Source: [USPTO fee schedule; accessed 2026-11-21](https://www.uspto.gov/learning-and-resources/fees-and-payment/uspto-fee-schedule)
- A comprehensive clearance search with attorney opinion typically costs about $1,000–$2,000. Large firms charge $1,500–$3,500+. One firm's fixed fee (schedule effective 2025-01-18) is $1,500 for search plus opinion. These are law-firm marketing figures. — [GleanMark 2026 guide; accessed 2026-11-21](https://gleanmark.com/insights/trademark-attorney-cost-complete-fee-guide); [Jaburg Wilk pricing; accessed 2026-11-21](https://www.jaburgwilk.com/services/intellectual-property-law/trademark/trademark-pricing); [USPTO on clearance searches; accessed 2026-11-21](https://www.uspto.gov/trademarks/search/comprehensive-clearance-search-similar-trademarks)

### Inferences
**Likelihood of confusion (du Pont factors)**
- **Against registered marks:** none of the live USPTO MIYAGI marks are close in goods. MIYAGI EYEWEAR is class 9 but covers eyeglasses; the others are restaurants, cosmetics and sake. A USPTO §2(d) refusal on the current register looks unlikely, though a live pending MR MIYAGI exists in class 43.
- **Against Miyagi Labs, under §43(a) common law:** the marks are nearly identical ("Miyagi" vs. "Miyagi Labs"). The services overlapped directly ("YouTube videos to interactive courses"). The channels overlap too: students, YC and Hacker News audiences, education buyers. If Miyagi Labs has used the name continuously since early 2025, it likely has priority. Its pivot to exam prep reduces but does not remove relatedness.
- **Against Sony/Columbia:** "Mr. Miyagi" is a famous film character. But Sony has no MIYAGI registration, and fame as a character name is not obviously fame "as a designation of source". Federal dilution looks weak.
- **Where Sony's risk is real:** §43(a) false association and endorsement, plus copyright in the films and stills. That risk grows if marketing leans on the franchise: the "waxon" code, "wax on, wax off" or "Mr. Miyagi" phrasing, bonsai or karate imagery, or a "sensei" persona styled after the character.
- **Short phrases:** a phrase like "wax on, wax off" is not copyrightable (37 C.F.R. §202.1). Trademark and false-endorsement exposure remains, and an unrelated live WAX ON WAX OFF registration exists in class 44.

**Right of publicity**
- Pat Morita died in 2005, so §3344.1 rights run to about 2075 if successors registered. They cover his name, voice and likeness, not the fictional surname "Miyagi".
- The risk arises only if miyagi uses Morita's image, film stills, a voice imitating him (including AI voice; note the digital-replica clause), or his name.

**Registrability**
- "Miyagi" is a Japanese prefecture and a surname. For software, US buyers make no goods-place association, so §2(e)(2) is unlikely. The well-known non-surname meaning (the film character) cuts against a §2(e)(4) surname refusal.
- That same character association is what creates the false-association risk. The name is legally "arbitrary" for software but not commercially neutral.

**Cost of an intent-to-use filing**
- For classes 9 (downloadable software) and 41 (educational services), or 42 (SaaS):
  - minimum government fees about $700 to file (2 × $350, using ID Manual entries to avoid surcharges);
  - plus $300 for the SOU;
  - plus $125 per class for each extension.
- Add roughly $1,000–$2,000 for a clearance search with opinion if outsourced.
- Who can be the applicant (company vs. minors), and whether a state-law entity is needed, is a question for counsel.

### Gaps
- I could not read TSDR detail pages (filing and registration dates, full ID text) or EUIPO eSearch. The WIPO view was partial, so EU, UK and Japanese MIYAGI marks in classes 9/41/42 are unverified. Of particular interest: a UK journal entry with EUIPO origin covering classes 9/41/42 (WO0000001881786, 2025), whose word element I could not see.
- I did not check state trademark registers, common-law use beyond Miyagi Labs, app stores, or domain portfolios. That is part of a professional clearance search.
- No source found on Sony ever enforcing "Miyagi" or "Miyagi-Do" against third parties. Unlicensed "Miyagi-Do" merchandise is widely sold, but that is not evidence of tolerance.
- Whether Pat Morita's successors registered a §3344.1 claim with the California Secretary of State was not checked.

---

## Implications for miyagi

### Takeaway
The biggest legal risks are how transcripts are obtained (avoid scraping) and the name collision with Miyagi Labs. Copyright exposure from the lessons is manageable if the product is designed as a companion to the video, with attribution and a takedown and opt-out process. Embedded-player compliance is a checklist. Sony risk is mostly self-inflicted through Karate Kid references.

### Cited Findings
- See sections 1–7 for sources. Key anchors:
  - YouTube ToS Restrictions 1 and 3 — [YouTube ToS; accessed 2026-11-21](https://www.youtube.com/t/terms)
  - RMF overlay, size and Referer rules — [RMF; accessed 2026-11-21](https://developers.google.com/youtube/terms/required-minimum-functionality)
  - Developer Policies privacy, storage and download rules — [Developer Policies; accessed 2026-11-21](https://developers.google.com/youtube/terms/developer-policies)
  - Gemini YouTube URL preview and the 18+ term — [Gemini video docs; accessed 2026-11-21](https://aistudio.google.com/docs/video-understanding); [Gemini API terms; accessed 2026-11-21](https://aistudio.google.com/docs/terms)
  - 2026 §1201 rulings — [openclassactions.com; accessed 2026-11-21](https://openclassactions.com/lawsuits/runway-ai-youtube-video-scraping-dmca-class-action-lawsuit.php)
  - USCO RAG passage — [USCO Part 3; accessed 2026-11-21](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-3-Generative-AI-Training-Report-Pre-Publication-Version.pdf)
  - Course Hero §1202 verdict — [Thompson Coburn; accessed 2026-11-21](https://www.thompsoncoburn.com/insights/education-platform-liability-in-the-ai-era-divergent-outcomes-for-quizlet-and-course-hero/)
  - DMCA agent $6 / 3 years — [USCO FAQ; accessed 2026-11-21](https://copyright.gov/dmca-directory/faq.html)
  - USPTO search results — [tmsearch; accessed 2026-11-21](https://tmsearch.uspto.gov/search/search-results)
  - Miyagi Labs — [YC launch; accessed 2026-11-21](https://www.ycombinator.com/launches/Mr9-miyagi-labs-ai-to-transform-youtube-content-into-interactive-courses)

### Inferences
Risk register. Likelihood and severity are judgments for a small, free, US-based app at hackathon or early scale.

| # | Risk | Who could act | Likelihood | Severity | Concrete mitigation | Lawyer? |
|---|---|---|---|---|---|---|
| 1 | **Transcript or media scraping** (timedtext/innertube, `youtube-transcript-api`, yt-dlp, proxies, PO-token reuse) breaches ToS Restrictions 1 and 3, and could support §1201 claims after the Oct 2026 ByteDance, Apple and Runway rulings | Google/YouTube (IP blocks, API or key termination, C&D); creators (§1201 suits at $200–$2,500 per act) | Technical blocking: high (already happening). Lawsuit against a small app: low, but rising | High | App: remove any scraper or yt-dlp path. Use Gemini's YouTube-URL input (public videos only) for analysis; offer `captions.download` only to creators who connect their channel; let users paste their own notes or transcript as a fallback. Never rotate IPs or reuse tokens. Doc: an internal "no scraping" engineering rule | Not needed if scraping is dropped. **Yes** if any scraping path stays: §1201 exposure needs advice |
| 2 | **Embedded-player non-compliance** (overlay covering the player, player under 200x200, autoplay when hidden, no Referer causing Error 153, background play, hiding branding or ads) | Google/YouTube | Medium (automatic "reduced functionality"; possible review) | Medium (the player breaks; possible API Client termination) | App: lesson panel and grading UI beside the player, never on top; player at least 480x270; no autoplay unless more than 50% visible; load the embed from an https miyagi.study page so a Referer is sent (no `noreferrer`); don't pause or mute ads or play hidden; respect "embedding disabled". Doc: a compliance checklist in the repo | No |
| 3 | **Missing YouTube-required legal text** (privacy policy that names YouTube API Services and links Google's Privacy Policy; terms that bind users to the YouTube ToS and link it) | Google/YouTube | Medium (checked in any audit or review) | Low–medium | Doc: add a YouTube clause to the privacy policy and EULA with links to youtube.com/t/terms and the Google Privacy Policy; show it in-app before first use; deletion within 7 days on request. Coordinate with the privacy researcher | No (template-level), but have it reviewed with the overall privacy policy |
| 4 | **Data API storage limits** (titles, thumbnails, statistics kept over 30 days; "derived data") | Google/YouTube | Low–medium (only if the Data API is used) | Low–medium | App: prefer oEmbed or the IFrame player for metadata; if the Data API is used, refresh or delete within 30 days; keep the lesson cache keyed by video ID without long-lived API metadata. Note the quota audit applies only above 10,000 units/day | No |
| 5 | **Gemini API terms: 18+ and "not directed to or likely accessed by" under-18s; free-tier data use** | Google (Gemini API) | Medium (a student-built, student-facing app) | Medium (key suspension; loss of the key analysis route) | App or process: adult-only age gate, or route under-18 users only through a provider whose terms allow it; use the paid tier so inputs aren't used for training. Flag for the minors/privacy researcher | **Yes**, together with the minors/privacy review |
| 6 | **Copyright: cached lessons as derivative works or abridgments** that substitute for the video (*Castle Rock*, *Colting*, USCO RAG passage, *ROSS*, *In re OpenAI*) | Tutorial creators (most likely a takedown request first; lawsuits need registered works for statutory damages) | Low at current scale; rises with users, monetization, or popular-creator content | Medium–high (statutory damages per registered work; forced removal) | App: make playback of the official embed central to the lesson (steps unlock at timestamps, the user watches and then does); write steps and checks in miyagi's own words; don't show or store full transcripts; don't copy the instructor's full example code (short idiomatic snippets are fine); keep lessons short relative to the video; per-creator opt-out and kill switch. Process: a "creator partners" path via `captions.download` and permission. Doc: a fair-use rationale memo | **Yes, before monetizing or scaling**: a short fair-use review of the actual lesson format |
| 7 | **DMCA §1202: removing or altering creator CMI** (the Course Hero verdict was ~$75M, mostly §1202) | Creators | Low if attribution is kept | High if it happens | App: every lesson shows the creator name, channel link, video title and a link to the video; never replace with miyagi branding; keep attribution in shared and exported lessons | No |
| 8 | **No §512 safe harbor or takedown process** for the shared cache | Creators | Medium that a complaint arrives at some point | Medium (§512 may not apply to AI lessons anyway, but without an agent it surely doesn't) | Process: register a DMCA agent ($6; renew before 3 years); publish a DMCA, counter-notice and repeat-infringer policy; build an admin purge plus channel blocklist; log notices; respond within 1–2 business days | Optional (template-level); **yes** if a real claim arrives |
| 9 | **Trademark: Miyagi Labs** (YC W25, same name, launched "YouTube to interactive courses") likely has earlier common-law rights | Miyagi Labs | Medium if miyagi gains visibility (same space, same name) | High (forced rebrand, domain and app-store changes, injunction) | Process: commission a full clearance search (~$1–2k) before investing more in the brand; consider a distinct composite name, or a coexistence agreement if keeping "miyagi"; don't file an ITU until cleared. Doc: a naming decision memo | **Yes**: clearance opinion and any coexistence approach |
| 10 | **Sony/Columbia false association or endorsement** from Karate Kid cues (the "waxon" code, "wax on, wax off", "Mr. Miyagi", karate or bonsai styling, quotes, stills) | Sony Pictures / Columbia Pictures Industries (owns THE KARATE KID marks in classes 9 and 41) | Low for the bare name; medium if marketing trades on the films | Medium (C&D, takedown of marketing, rebrand pressure) | App/marketing: change the "waxon" download code to something neutral; drop Karate Kid quotes, imagery and character references; don't use "Mr."/"sensei" styling tied to the character; consider a footer disclaimer ("not affiliated with Sony Pictures or The Karate Kid"); never use film stills or clips | Only if a C&D arrives |
| 11 | **Right of publicity (Pat Morita, died 2005; Cal. Civ. Code §3344.1 runs to about 2075)** | Morita's successors, if registered | Very low unless his likeness or voice is used | Medium | App: no Morita photos, voice imitation or AI voice "Miyagi" persona; the system voice is fine | No, unless a voice or likeness feature is planned |
| 12 | **Registration and foreign marks** (unknown EU, UK and Japan MIYAGI marks in 9/41/42; Indonesia MIYAGI class 9 registered) | Foreign owners; USPTO examiner | Low in the US; unknown abroad | Low–medium | Include international databases (EUIPO, UKIPO, JPO) in the clearance search before any non-US launch; budget USPTO about $350 per class plus $150 SOU per class | Yes, as part of clearance |

**Overall: what needs a lawyer.**
- Before scaling or monetizing, a short engagement for three things: (a) trademark clearance and naming advice (Miyagi Labs); (b) a fair-use review of the lesson-and-cache design; (c) the age and API-terms issue (with the privacy and minors review).
- Everything else (scraping removal, player compliance, policy text, DMCA agent, attribution, dropping Karate Kid references) the team can do now.

### Gaps
- Likelihood ratings are judgments, not sourced statistics.
- miyagi's actual current transcript method was not inspected in code for this note. If it already uses `youtube-transcript-api`, yt-dlp or timedtext calls, risk 1 is live, not hypothetical.
- Commencement dates of Miyagi Labs' use, and of miyagi.study's own first use, decide priority and were not established.
