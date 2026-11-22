# Review of Michael's draft privacy policy (#199)

Area B. Reviews `web/privacy.md` on `origin/michael/app-privacy` at `0efcfe90` (Nov 21, 12:16 PM) against the code that
ships next and the law that applies. **Not legal advice.** The suggested rewrite is on #201 (`adrian/legal-privacy`,
stacked on #199): it keeps every line `facts.test.ts` requires, word for word.

Code shorthand: `IL:` engine on `origin/integration/live`, `V2:` app on `origin/michael/v2-integration`, `PV:` #199,
`EP:`/`EC:` miyagi-cloud on `origin/claude/eng-proxy-auth` / `eng-proxy-cache`, `TL:` `origin/claude/telemetry`.

## Short version

The draft is honest in tone and gets a lot right (telemetry off by default, keys locked and sent only to their
provider, the app itself never calls the AI providers, the redaction it describes really happens to screen text). But
it describes a branch that predates two merges, and in places it says less than the code does. Five fixes matter
most:

1. **"Not linked to your name" is false** once `/v1/link` ships: after every sign-in the app sends the Supabase token to
   miyagi-cloud, which stores install to account and never unlinks (`V2:app/src/main/features/cloudLink.ts:128-134`,
   `EP:cloud/store.py:26-33`).
2. **It understates what goes to Anthropic.** The full-screen overview, the editor buffer with unsaved edits, any
   "Explain this" selection from any file, typed questions, and a project scan of up to 60,000 characters of file
   contents with the folder path (which contains the macOS username) (`IL:server/lesson/workdir.py:17-19,39-93`).
   "A summary of that folder" is not what happens.
3. **It doesn't disclose the YouTube player**, which runs from `www.youtube.com` (not youtube-nocookie), keeps
   YouTube's cookies in the app, and sends `miyagi.study` as the Referer (`V2:app/src/renderer/src/features/player/store.ts:461-490`,
   `V2:app/src/main/index.ts:368-375`). YouTube's Developer Policies require the policy to say the app uses YouTube API
   Services and to link Google's Privacy Policy.
4. **Retention and deletion are [TBD] because the server can't delete anything.** No code path deletes `tokens`,
   `links`, `usage` or `builds` (`EP:cloud/store.py`). The policy can't promise deletion until `DELETE /v1/me` exists
   (register B05).
5. **It promises a 13+ rule with no mechanism**, and says nothing about teens, Gemini's 18+ term, or a parent's rights
   (register B02, B03).

## Wrong: the code does otherwise

| Draft says | What the code does | Evidence | Suggested fix |
| --- | --- | --- | --- |
| The install token "is not linked to your name" | Linked to the Supabase account after every sign-in; sign-out never unlinks; logs carry `user=<id>` | `V2:app/src/main/features/cloudLink.ts:23-25,128-134`; `EP:cloud/store.py:26-33,112-120`; `EP:cloud/app.py:161-162,198` | Say it plainly ("if you sign in, miyagi-cloud links this install to your account id"), or unlink on sign-out |
| "the local error log. We do not receive them." | Crash sharing sends exactly those lines when on | `TL:app/src/main/features/telemetry.ts:9-12,87,115-116` | "...the local error log, which is sent only if you turn on crash sharing" |
| "a tutor that runs on your Mac"; "Locked by your Keychain"; "on this Mac" throughout | A Windows installer is public; keys and sign-in use Windows data protection there | `V2:app/electron-builder.yml:63-70`; `V2:app/src/main/features/settings.ts:4-6` | Say Mac and Windows; "Keychain on Mac, Windows data protection on Windows" |
| "If you add a Bright Data key, the search may also go through Bright Data" | The next app can't supply that key; only a developer `.env` can | `V2:app/src/renderer/src/features/settings/keys.ts:12-15`; `IL:server/config.py:56-66` | Drop Bright Data from the policy (and from shipped engines) |
| Searches go to "YouTube, DuckDuckGo, GitHub and arXiv" | Default is the YouTube results page plus Anthropic's web search; the others only for non-video searches | `IL:server/finder/core.py:239,307-322`; `IL:server/finder/sources.py:78-85,155-245` | Describe the default and the optional sources separately |
| "Screenshots taken to check a step black out those windows" | True only when macOS's ScreenCaptureKit path works; the fallback capture keeps password apps; help and pointing screenshots aren't masked (the draft says the second part) | `IL:server/screen/sck.py:31-34`; `IL:server/screen/reader.py:784-793,921-947` | Say "when macOS's capture works"; better, fix the fallback (register B01) |
| "On this Mac: until you delete it (see below)" | Delete my data removes keys, sign-in and `prefs.json` only; most local data has no in-app delete | `PV:app/src/main/features/settings/erase.ts`; `V2:app/src/main/localEngine.ts:400-407` | List what stays and how to remove it |
| Crash reports and usage "go to miyagi-cloud" | No `/v1/events` route exists on any cloud branch yet | `TL:app/src/main/features/telemetry/core.ts:54-58`; `EP:cloud/app.py` (no route) | Fine to describe the intent, but ship the backend with retention before turning the switch on |

## Missing: not disclosed anywhere

- **The YouTube embed** (above), and that the engine fetches the video's YouTube page and captions from the Mac
  (`IL:server/lesson/transcript.py:97-122`). The second should go away with register B06.
- **Typed questions to the coach** go to Anthropic (`V2:app/src/renderer/src/features/launcher/Launcher.tsx:639`,
  `IL:server/coach/explain.py:126-130`).
- **The VS Code companion's reach.** It starts with every VS Code window, posts every terminal command with up to 40
  lines of output to the local engine, can read any file by path when asked, and "Explain this" sends any selection plus
  12 lines around it and the file path (`vscode-ext/extension.js:22-28,197-249,799-941` on `IL`).
- **Accessibility text** of other apps is read, not just OCR (`IL:server/screen/privacy.py:1-2`).
- **What miyagi-cloud stores:** token hash, app version, platform, creation date; daily request, token and cost counts
  per model and feature; which videos an install built lessons from, by month (`EC`); the account link
  (`EP:cloud/store.py:17-47`; `EC:cloud/store.py:54-68`). It does not store prompts, screenshots or answers.
- **What Supabase stores:** email, name, avatar URL, Google identity, sign-in times, IP address and user agent in auth
  logs (vendor notes, `privacy-legal/sources/vendor_terms_data_handling.md`).
- **The shared lesson cache** (`EC:cloud/app.py:608-639`), if it ships: lessons reused across learners, and today's
  draft can carry one learner's typed goal (register B12).
- **Update checks** to GitHub every 6 hours with the app version (`V2:app/src/main/features/updates.ts:118-129`).
- **VS Code Marketplace installs** of Microsoft's Python and Jupyter extensions, which have their own telemetry
  (`V2:app/src/main/features/onboarding.ts:53,243-260`).
- **Who we are and how to reach us** (CalOPPA and GDPR need a contact; the draft's is [TBD]).

## Missing: things the law or our vendors require in the policy

| Requirement | Source | In the draft? |
| --- | --- | --- |
| Categories of personal information and of third parties it's shared with | [Cal. Bus. & Prof. Code 22575(b)(1)](https://california.public.law/codes/ca_bus_and_prof_code_section_22575) | Partly (no third-party list) |
| How users can review and request changes to their data | 22575(b)(2) | No |
| How we notify users of material changes | 22575(b)(3) | [TBD] |
| Effective date | 22575(b)(4) | [TBD] |
| How we respond to Do Not Track signals; whether third parties track across sites | 22575(b)(5)-(6) | No |
| That the app uses YouTube API Services, with links to Google's Privacy Policy (and the YouTube Terms in our terms) | [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies) | No |
| A privacy policy describing what we collect and share with Google | [Google APIs Terms 3(d)](https://developers.google.com/terms) | Partly |
| Users are told they're dealing with AI and that outputs may be wrong | [Anthropic Usage Policy](https://www.anthropic.com/legal/aup), [Commercial Terms D.3](https://www.anthropic.com/legal/commercial-terms) (belongs in the app and terms; one line in the policy helps) | No |
| A public statement on COPPA and teen safeguards | [Anthropic minors guidelines](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors) ("should") | One sentence only |
| Retention periods or criteria | GDPR Art. 13(2)(a); COPPA 312.10 written retention policy | [TBD] |
| Identity and contact of the controller, legal bases, rights, complaint route, transfers (only if EU/UK users are served) | [GDPR Art. 13](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng) | No |

## Checklist for the #199 privacy panel (for Michael; described, not edited)

1. **`facts.ts` lines to revisit** (each needs the panel, the policy and the test to move together):
   - `editor`: `where` is "Read on this Mac", but what it reads is what the code row sends. Suggest: line "miyagi reads
     VS Code and its terminal to follow your step." and `where` "To Anthropic" with `leaves: true` (the test allows
     any `To ...`).
   - `code`: add "and files you ask about" or similar; the project scan and "Explain this" are wider than "the step's code".
   - `keys`: "Locked by your Keychain" is Mac only; the Windows build needs its own line (DPAPI).
   - Add a row for **YouTube**: "Videos play in YouTube's player, which sees what you watch." `where` "To YouTube".
   - Add a row for **your account link** once `/v1/link` ships: "Signing in links this install to your account."
   - Add a row for **questions you type**, or fold it into `code`.
2. **`facts.test.ts`:** the ban on "token" and "redact" in fact lines stops the panel from saying the honest thing
   ("keys and tokens on screen are not removed"). Suggest narrowing it to forbid claims ("redacts", "removes keys")
   rather than the words. The DRAFT-on-line-1 check has to flip when the policy is published.
3. **Delete my data:** add `install.bin`, `cloud-link.json`, the error log and crash reports, `onboarding.json`, the
   other settings files and the app's browser storage (YouTube cookies) to the erase list, call the server delete once
   `DELETE /v1/me` exists, and revoke the Supabase session with `scope=global` or delete the Supabase user. Keep
   `~/miyagi` as an explicit second choice ("Also delete my lesson folders").
4. **Before the macOS prompts:** one screen that says what's captured and where it goes ("During lessons, miyagi
   sends screenshots and screen text to Anthropic to check your work"), with a link to the policy. Microsoft Store
   policy 10.5.2 needs the same opt-in on Windows.
5. **AI disclosure:** one persistent line in the panel and onboarding: "miyagi's coach is AI. It can be wrong."
6. **A pause control** that stops capture, visible from the overlay.
7. **Policy link + acceptance:** the login screen link becomes an "I agree" step (button text matches the sentence
   above it), shown also on "Continue without an account".

## Checklist for the 13+ gate (`michael/app-signin-gate`, not on origin yet)

1. Ask before Google sign-in completes or anything is stored; if OAuth must come first, hold the session in memory
   until the age step passes.
2. Empty month and year pickers, no default; don't say "13" anywhere on the screen or in the error; generic failure
   copy ("miyagi isn't available for this account right now").
3. Store only an age band (13-15, 16-17, 18+) and the month it was given; never the birth date.
4. Under 13: write a flag that survives restarts (app data plus Keychain/credential store), show the same message on
   every retry, sign out and delete any session, install token and server rows already created.
5. 13-17: Claude only (no Gemini, register B02), no BYOK, high-privacy defaults, parent can ask for deletion; a
   parent or guardian accepts the terms.
6. A "report an underage user" route (the privacy address is enough at launch) and a delete-within-days process.
7. Keep marketing to "13 and up"; no middle-school outreach.
8. Plan for California's OS age signal (AB 1043/AB 1856, from 2027-01-01): read it when macOS and Windows offer one,
   and treat it as actual knowledge.

Sources for this review: `privacy-legal.md` and `privacy-legal/sources/` (kids, vendor and US notes).
