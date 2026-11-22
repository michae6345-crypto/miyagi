# DRAFT: miyagi privacy policy

> **DRAFT for Michael and Adrian to review. Not published, not linked from the site. Not legal advice.**
> Adrian's legal pass (#201, stacked on #199) folded in, then re-checked against the engine on
> `origin/integration/live` (742ab87a: key and token redaction landed), the app on `origin/michael/v2-integration`
> (telemetry and the account link merged) and miyagi-cloud on `origin/claude/eng-proxy` (6a84ecae: `/v1/link`,
> `/v1/events`; not deployed yet). Why each change: `research/launch/privacy-review.md` on `adrian/launch-risk` (#204).
> Every quoted line in the first table is the same line the app shows in Settings › Privacy › What miyagi sees
> (`app/src/renderer/src/features/settings/privacy/facts.ts`); a test keeps the two the same. Two "Where it goes"
> cells (editor, searches) say more here than the panel's short label on purpose; they say the same thing.
> **[TBD]** needs a decision or a fact we don't have yet. **[DECIDE]** is a founder decision from the risk register.
> **[CHECK]** must be re-checked against the release build before publishing. Publish nothing with any of the three left.

Effective date: [TBD]. Last updated: [TBD].

## Who we are

miyagi is made by [TBD: the company, once formed; until then, its founders]. You can reach us at
[TBD: privacy@miyagi.study] about anything in this policy (see Contact at the end).

## Who this is for

miyagi is a tutor for your Mac (a Windows version is coming) that follows along while you learn from a tutorial.
It is for people 13 and older. If you are under 13, please do not use miyagi. If you are under 18, a parent or
guardian needs to agree to our [Terms](https://miyagi.study/terms) for you. [CHECK: the Windows build today has no
engine, so it takes no screenshots and reads no code; say so, or drop the Windows mention until it does.]

## The short version

- During a lesson, miyagi sends screenshots of your screen, text on your screen, your code and your questions to
  Anthropic's Claude so it can check your work and help. Anything visible on your screen can be in a screenshot.
- To build a lesson from a video, miyagi sends the video's link, what you want to learn and the video's YouTube page
  text to Google Gemini. [DECIDE: Gemini for adults only, or not at all; see "Children and teens".]
- Videos play in YouTube's own player, so YouTube sees what you watch.
- These AI calls go through miyagi-cloud, our server, which keeps counts (requests, cost) but not your screenshots,
  code or answers. If you add your own API key, calls go straight to that provider.
- Sign-in is optional, through Google and Supabase. If you sign in, miyagi-cloud links this Mac's install to your
  account ID.
- Crash reports and usage counts are off unless you turn them on. A crash report says only what kind of error it was.
- We don't sell your data, we don't use it for ads, and we don't train AI on it.

## What miyagi sees, why, and where it goes

miyagi needs to see your work to help with it. Here is everything it reads, said the way the app says it.

| What | What happens | Where it goes |
| --- | --- | --- |
| Your screen | During a lesson, screenshots and screen text. Text from password apps dropped. | Anthropic |
| Your code | The step’s code, when miyagi checks your work or helps. | Anthropic |
| Your editor | miyagi reads VS Code here to follow your step. | Read on this Mac, then sent as your code |
| Your searches | What you ask to learn goes to search sites and the AI. | Search sites (YouTube first) and Anthropic |
| Lesson videos | The video’s text and what you want to learn, to Anthropic. | Anthropic |
| Your sign-in | Google sign-in through Supabase. The session stays encrypted here. | Supabase |
| Account link | When you sign in, miyagi’s server ties this Mac to your account. | miyagi |
| miyagi’s server | Passes AI calls on. Keeps counts and cost, never your work. | miyagi |
| Your API keys | Locked by your Keychain, sent only to their provider. | On this Mac |
| Lesson progress | Lesson folders and progress, kept in ~/miyagi on this Mac. | On this Mac |
| Crash reports | Only the kind of error, never its text. Off unless you share. | miyagi, if on |
| Usage counts | Lesson and step counts. Never your code or screen. | miyagi, if on |

AI calls go through miyagi’s server, or direct with your key.

### Your screen

- **When.** Only while a lesson step is active. [CHECK: after a relaunch the engine must not keep checking a lesson
  the app no longer shows; register B09.] You can pause or end a lesson at any time. [CHECK: a visible pause.]
- **What.** A picture of your main display, made smaller (1280 pixels wide), and a close-up around your pointer, when
  miyagi checks a step, points at something or answers a question. Text on screen, read on this Mac with Apple's text
  recognition and the macOS accessibility features, and the name of the app in front.
- **What is removed first.** In text read from the screen, email addresses, card numbers, US phone numbers and US
  social security numbers are replaced, and text from password managers (1Password, Bitwarden, Dashlane, LastPass,
  Keychain Access, Passwords) and Messages is dropped. Text that looks like an API key, a token or a password (for
  example `sk-...`, `ghp_...`, `API_KEY=...`, a private key block) is replaced too, and the rows of the screen where
  miyagi found one are blacked out in every screenshot it sends. miyagi finds these by their shape, so it can miss
  some. Password managers and Messages are also kept out of step-check screenshots when macOS's screen capture works
  normally.
- **What is not removed.** Screenshots taken to point at something or to answer a question do not black out password
  managers or Messages. miyagi does not crop screenshots to your work area, and it does not remove names, addresses,
  other chat or email apps, or browser tabs that are visible. **Anything on your screen, including other people's
  messages, can be in a screenshot.** Close or hide anything private, especially other people's information, before a
  lesson.
- **Why.** To tell whether a step is done, to point at the right place, and to answer when you ask for help.

### Your code and your editor

Through the miyagi companion for VS Code, miyagi reads on this Mac: the file you're working on (including changes
you haven't saved), your open tabs, where you're typing and what you've selected, and the commands you run in VS
Code's terminal with the last lines of their output. It sends to Anthropic:

- the step's code and the files a step checks, when miyagi checks your work or helps;
- text you select for "Explain this", with the lines around it and the file's name and path;
- to fit a lesson's checks to your lesson folder: the list of files in it and up to 60,000 characters of their
  contents, plus the folder's path, which includes your Mac username. Files whose names start with a dot (such as
  `.env`, but not `.env.example`) and folders like `node_modules` are skipped. Keys or passwords written inside the
  other files are not removed from this scan;
- the questions you type to miyagi.

Before the step's code, "Explain this" text and your questions are sent, text that looks like an API key, a token or
a password is replaced, and the values in files like `.env` are hidden (their names are kept). The lesson-folder scan
above is sent as it is.

[CHECK: whether the engine forwards terminal output to Anthropic; if so, list it above.]

### Lesson videos and YouTube

- **Building a lesson.** Google Gemini gets the video's link (Google fetches the video itself), what you want to
  learn, and the text of the video's YouTube page (title, description and chapters), and may get a step's title and
  time to watch that part again. Gemini gets nothing from your screen or your code. [DECIDE: Gemini for adults only,
  or replace it; register B02.]
- **[DECIDE, register B06]** Today miyagi also reads the video's YouTube page and captions from your Mac. We plan to
  stop. Delete this bullet once the engine no longer does it.
- **Playing videos.** miyagi plays tutorials with YouTube's embedded player. YouTube (Google) receives your IP address,
  the video you watch and how you play it, and keeps its own cookies in the miyagi app until you delete them.
  miyagi uses YouTube API Services: see the [Google Privacy Policy](https://policies.google.com/privacy) and the
  [YouTube Terms of Service](https://www.youtube.com/t/terms). [CHECK: switch the app's player to
  youtube-nocookie.com, then say so.]
- **Searches.** When you ask miyagi to find something to learn, the words you type go to YouTube's search and to
  Anthropic, which may use its web search to find and rank sources. When you ask for other kinds of sources, they also
  go to DuckDuckGo, GitHub and arXiv.

### Your account (optional)

If you sign in, Google tells Supabase, our sign-in provider, your name, email address, profile picture and Google
account ID. Supabase also records when you sign in and the IP address and browser used to sign in. On this Mac the session
is stored encrypted with a key from your Keychain. You can continue without an account.

### miyagi-cloud, our server

- On first launch the app gets an install token from miyagi-cloud and sends the app version, the macOS version and the
  chip type. The token is stored encrypted on this Mac.
- **If you sign in, miyagi-cloud links this install to your account.** The app sends your install token and your
  Supabase sign-in token; miyagi-cloud checks the sign-in token and keeps your account ID (not your name or email)
  next to this install, so your usage limits can follow you. Signing out does not unlink it; if someone else signs in
  on this Mac, the link moves to their account. The app keeps a note of the link on this Mac (your account ID, no
  token). [DECIDE: unlink on sign-out, or keep "signing out does not unlink it".]
- miyagi-cloud passes your screenshots, code and questions to the AI provider and returns the answer. **It does not
  store them.** It stores: for each install, the token's fingerprint, app version, platform and start date; for each
  day, how many requests were made and their size and cost, by AI model and feature; which videos the install built
  lessons from, by month; the account link; and, only if you turned on crash and usage sharing, daily counts of those
  events. Its request log lines show the time, the kind of request, the AI
  model, sizes, a short install ID and, if you signed in, your account ID. [CHECK: drop the account ID from logs.]
- miyagi-cloud sees your IP address to stop abuse. It uses it in memory to limit how often new installs are made,
  and does not store it.
- **[DECIDE, register B12] Shared lessons.** A lesson built for a public video may be saved on miyagi-cloud and reused
  for other learners who pick the same video. It is built from the video, never from your screen or code.
  [CHECK: the cached lesson must not carry the goal you typed.]

### Crash reports and usage counts

Off for everyone unless you turn on "Share crash reports and usage" in Settings › Privacy, and nothing is sent
before you are past sign-in and setup. When on, miyagi sends:

- that the app was installed (with the app version, the system (macOS) and the chip type) and that setup finished;
- lesson counts: a lesson was built (how many steps, how it was built), a step passed or failed its check, a hint was
  used, a lesson was finished (steps passed and skipped, minutes) or left (a one-word reason);
- for each crash, only what kind of error it was and the app version. The error text stays on this Mac.

Never your code, files, screen text, file paths or anything you typed. They go to miyagi-cloud with your install
token, which keeps them only as daily counts per install, so they are tied to this install (and to your account if you
signed in). Turning the switch off stops sending at once and drops anything not sent yet. [CHECK: miyagi-cloud's
`/v1/events` must be deployed, with its retention, before the switch ships.]

### Other connections

- **Updates.** The app checks GitHub for a new version about every 6 hours; GitHub sees your IP address and the app
  version.
- **VS Code extensions.** During setup miyagi installs its companion extension and Microsoft's Python and Jupyter
  extensions from the VS Code Marketplace. Those extensions follow VS Code's own telemetry setting.
- **Downloads in a lesson.** If a tutorial links starter files (on GitHub or Google Drive), miyagi downloads them into
  your lesson folder.

### What stays on this Mac

Your API keys, your sign-in session, your install token, the note of your account link and your settings (encrypted
where they're secret); your
lesson folders (~/miyagi/lessons) and lesson progress (~/miyagi/state); cached searches, lessons and video captions;
the engine's log; and the local error log and crash reports, which never leave this Mac (crash sharing sends only the
kind of error). We don't receive these.

## Who receives your data

| Who | What they get | Why | How long they keep it |
| --- | --- | --- | --- |
| Anthropic (Claude API) | Screenshots, screen text, code, files and questions, through miyagi-cloud | Check your work, coach, build and rank lessons | Deleted within 30 days by default; if flagged for a safety review, inputs and outputs up to 2 years and safety scores up to 7 years. Not used to train models. |
| Google (Gemini API) | Video link, what you want to learn, YouTube page text | Build lessons from videos | [CHECK: on our paid Gemini project, kept up to 55 days for abuse monitoring and not used to train or improve Google's models; AI Studio logging turned off.] |
| Supabase | Your Google sign-in details, sign-in times, IP address, browser | Sign-in | Until you delete your account, plus Supabase's log retention for our plan [TBD]. |
| Render | Everything that passes through miyagi-cloud, while it passes; miyagi-cloud's stored counts and logs | Hosts miyagi-cloud | Logs for 7 to 30 days depending on our plan [TBD: our plan]; stored data until deleted (see below). |
| YouTube (Google) | Your IP address and the videos you watch in the app | Plays videos | Under Google's own Privacy Policy. |
| GitHub | Your IP address and app version (updates, downloads, this website) | Updates and hosting | Under GitHub's own Privacy Statement. |

Anthropic, Google (for the paid Gemini API), Supabase and Render process this data for us under their data
processing terms. YouTube and GitHub act on their own.

**If you use your own API key,** calls go straight from your Mac to that provider under your own agreement with them,
and their terms decide how long they keep it and whether they train on it. On Google's free tier, Google may use what
you send to improve its products, and people may read it.

## What we do not do

- We do not sell your data or share it for advertising, and nothing in miyagi tracks you across other sites. Because we
  don't track you, we don't change anything when your browser or system sends Do Not Track or Global Privacy Control.
- We do not train AI models on your screen, code or searches, and our AI providers don't either under the API terms
  we use. [CHECK: holds only if our Gemini project is on the paid tier.]
- We don't look for health, money or other sensitive information. If a screenshot catches some, it is used only to
  answer that request and is not kept by us.

## How long we keep it

| Where | What | How long |
| --- | --- | --- |
| Your Mac | Everything in "What stays on this Mac" | Until you delete it (see below). |
| miyagi-cloud | Install record, daily counts, lesson-build history, account link | [TBD, proposed: counts and history for 12 months, then deleted; the rest until you delete your data.] Today there is no automatic deletion. |
| miyagi-cloud logs (at Render) | Request log lines | [TBD: 7 to 30 days, by our Render plan.] |
| Supabase | Your account | Until you delete your account. |
| Anthropic, Google | What the AI calls carried | See "Who receives your data". |

## Deleting your data

In Settings › Privacy, Delete my data:

> Erases keys, settings and sign-in on this Mac. Cannot be undone.

Before it deletes, it asks once more:

> Signs you out. Lessons and progress in ~/miyagi stay. Cannot be undone.

It also removes the note of your account link on this Mac. It does not yet remove your install token, the account
link kept on miyagi-cloud, the app's YouTube cookies, cached searches and lessons, the engine log or crash reports, or
the VS Code extensions. To remove everything on your Mac: quit miyagi, delete the
app, delete the `miyagi` folder in your home folder, and remove the miyagi extension from VS Code. [CHECK: list the
app-data folder for Mac and Windows.]

To delete your account and anything kept on miyagi-cloud, email us (see Contact). We'll confirm and finish within 30
days. [TBD: in-app account deletion needs a miyagi-cloud endpoint; register B05.]

## Your choices and rights

Anyone, wherever they live, can ask us to tell them what we hold about them, correct it, or delete it. Email us; we
answer within 30 days.

- **California:** we follow California's online privacy law (CalOPPA). We don't sell or share personal information
  for advertising.
- **Europe and the UK:** [DECIDE, register B13: if miyagi is offered there, add the controller's identity and EU and UK
  representatives, the legal basis for each use (providing the lessons you ask for; your consent for crash and usage
  sharing), your rights to access, correct, delete, restrict, object and move your data, how to complain to your data
  protection authority, and how data reaches the US (Standard Contractual Clauses for Anthropic and Supabase; the
  EU-US Data Privacy Framework for Google and Render). If it isn't, say "miyagi is offered in the US" and stop.]

## Children and teens

- miyagi is for people 13 and older. We don't knowingly collect personal information from children under 13. When
  you start, miyagi asks for your age, and it does not continue for anyone under 13. [CHECK: the age step must exist
  before this sentence is true.]
- If we learn that a child under 13 used miyagi, we delete their account and data. Parents can tell us at the
  address below.
- For users 13 to 17: [DECIDE, register B02: "lessons use Claude only, never Gemini", or adults only]. We keep the
  same privacy defaults for everyone: crash and usage sharing off, no public profile, no ads.
- Parents and guardians can ask us to see or delete their teen's data.
- miyagi's coach is an AI. It can be wrong, and it tells you so in the app.

## Security

Secrets on your Mac (keys, sign-in, install token) are encrypted with your system's secure storage. Everything miyagi
sends travels over HTTPS. miyagi-cloud stores only a fingerprint of your install token, not the token itself, and
doesn't store screenshots, code or answers. No system is perfectly secure; if a breach affects your personal
information, we will tell you as the law requires.

## The miyagi.study website

The website sets no cookies and has no analytics, ads or tracking. If you unlock the downloads, your browser
remembers the code you typed (localStorage key `miyagi-code`) until you clear this site's data. Some parts of the page
load from other companies' servers, which see your IP address and browser like any website you visit:

| Server | Run by | What it sends | When |
| --- | --- | --- | --- |
| miyagi.study | GitHub Pages | The page and its fonts (GitHub logs visitor IP addresses for security) | Every visit |
| `cdn.jsdelivr.net` | jsDelivr | Code for the 3D bonsai and smooth scrolling | Every visit [CHECK: gone once self-hosted] |
| `i.ytimg.com` | YouTube (Google) | Thumbnails in "see it work" | Every visit [CHECK: gone once replaced with our stills] |
| `www.youtube.com`, `www.youtube-nocookie.com` | YouTube (Google) | The tutorial video in "see it work", in YouTube's privacy-enhanced mode | [CHECK: only after you click play, once that change ships] |
| `github.com` | GitHub | The download files | When you download |

You can clear or block this site's data in your browser; the site still works.

## Where your data goes

miyagi is run from the United States. miyagi-cloud runs on Render and our AI and sign-in providers process data in
the US and other countries.

## Changes

If this policy changes, we'll update the dates at the top and say what changed in the app before the change applies.
If a change would let us use your data in a new way, we'll ask you first; it won't apply to data collected before.

## Contact

[TBD: privacy@miyagi.study, and a postal address once the company exists.] For copyright notices, see our
[Terms](https://miyagi.study/terms).
