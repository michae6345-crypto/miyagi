# DRAFT: miyagi privacy policy

> **DRAFT for Michael and Adrian to review. Not published, not linked from the site.**
> Items marked **[TBD]** need a decision before this goes live at https://miyagi.study/privacy.
> Every quoted line below is the same line the app shows in Settings › Privacy › What miyagi sees
> (`app/src/renderer/src/features/settings/privacy/facts.ts`); a test keeps the two the same.

Last updated: [TBD]

## Who this is for

miyagi is a tutor that runs on your Mac and follows along while you learn from a tutorial. It is for people
13 and older. If you are under 13, please do not use miyagi.

## What miyagi sees, why, and where it goes

miyagi needs to see your work to help with it. Here is everything it reads, said the way the app says it.

| What | What happens | Where it goes |
| --- | --- | --- |
| Your screen | During a lesson, screenshots and screen text. Password apps blacked out. | Anthropic |
| Your code | The step’s code, when miyagi checks your work or helps. | Anthropic |
| Your editor | miyagi reads VS Code here to follow your step. | Read on this Mac |
| Your searches | What you ask to learn goes to search sites and the AI. | Search sites |
| Lesson videos | The video’s link goes to Google Gemini to build the lesson. | Google |
| Your sign-in | Google sign-in through Supabase. The session stays encrypted here. | Supabase |
| Your API keys | Locked by your Keychain, sent only to their provider. | On this Mac |
| Lesson progress | Lesson folders and progress, kept in ~/miyagi on this Mac. | On this Mac |
| Crash reports | Scrubbed error lines. Sent only when sharing is on. | miyagi, if on |
| Usage counts | Lesson counts and cost. Never your code or screen. | miyagi, if on |

AI calls go through miyagi’s server, or direct with your key.

### More detail

- **Why we send your screen and code.** To tell whether a step is done, to point at the right place, and to
  answer when you ask for help. Screenshots are taken only while a lesson step is active. Before text read from
  the screen is used, email addresses, card numbers, phone numbers and US social security numbers are replaced,
  and windows of password managers (1Password, Bitwarden, Dashlane, LastPass, Keychain Access, Passwords) and
  Messages are left out or blacked out. miyagi does not yet crop screenshots to your work area, and it does not
  yet remove API keys or tokens that are visible on screen, so keep those out of view during a lesson.
- **The AI providers.** Screen and code go to Anthropic (Claude). The link of a lesson video goes to Google
  Gemini, which watches the video to build the lesson; Gemini gets nothing else. By default these calls go
  through miyagi-cloud, our server, so we can pay for them and keep usage within limits. If you add your own API
  key in Settings, calls with that key go straight to that provider instead. Each provider handles what it
  receives under its own API terms.
- **Searches.** When you ask miyagi to find something to learn, the words you type are sent to YouTube,
  DuckDuckGo, GitHub and arXiv to find sources, and to Anthropic to rank them. If you add a Bright Data key, the
  search may also go through Bright Data.
- **Sign-in.** If you sign in, Google tells Supabase (our sign-in provider) who you are, for example your name and
  email address. On this Mac the session is stored encrypted with a key from your Keychain. Signing in is
  optional: you can continue without an account.
- **miyagi-cloud.** To use our server, the app gets an anonymous install token on first launch. It is stored
  encrypted on this Mac and is not linked to your name.
- **Crash reports and usage counts.** Off unless you turn on "Share crash reports and usage" in Settings ›
  Privacy. When on, miyagi sends error lines with usernames, quoted text and keys removed, and counts such as
  lessons searched, built and finished, steps passed, hints used and AI cost. Never your code, files or screen.
  They go to miyagi-cloud.
- **What stays on this Mac.** Your lesson folders (~/miyagi/lessons), lesson progress (~/miyagi/state), your
  settings, and the local error log. We do not receive them.

## What we do not do

- We do not sell your data or use it for advertising.
- We do not train AI models on your screen, code or searches. [TBD: confirm against each provider's API terms.]

## How long we keep it

- **On this Mac:** until you delete it (see below).
- **On miyagi-cloud:** [TBD: retention for request logs, crash reports and usage counts.]
- **At Supabase (sign-in):** until you ask us to delete your account. [TBD: confirm.]
- **At Anthropic and Google:** as set by their API terms. [TBD: link the current terms.]

## Deleting your data

In Settings › Privacy, Delete my data:

> Erases keys, settings and sign-in on this Mac. Cannot be undone.

Before it deletes, it asks once more:

> Signs you out. Lesson folders in ~/miyagi stay. Cannot be undone.

Your lesson folders are your own work, so the app leaves them. To remove them too, delete the `miyagi` folder in
your home folder. To delete your account and anything kept on miyagi-cloud, contact us (below). [TBD: in-app
account deletion needs a miyagi-cloud endpoint.]

## Changes

If this policy changes, we will update the date at the top and say what changed. [TBD: how we tell users.]

## Contact

[TBD: privacy contact address.]
