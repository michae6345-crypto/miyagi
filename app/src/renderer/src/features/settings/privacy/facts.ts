/**
 * Feature: settings. Privacy (ROADMAP 5.4): the ONE list of what miyagi sees and where it goes. Sees.tsx shows it,
 * web/privacy.md says the same lines word for word (facts.test.ts checks both). Honest subset only: every line is
 * what the code does today. Read before changing a line:
 *
 *   screen    engine server/screen/reader.py + privacy.py (OCR text: emails / card / phone numbers scrubbed, text from
 *             password apps and Messages dropped, key- and token-shaped text replaced by server/redact.py). Screenshots
 *             during an active lesson step: server/orchestrator/scene_watch.py (the step check) blacks out private
 *             apps' windows; every screenshot sent blacks out the rows whose text held a key (target.py, coach/screen.py,
 *             describe.py). The pointing path (screen_bridge → target.pick_on_screen → reader.latest_frame →
 *             render_marks) and the help screenshots (coach/screen.py) do NOT black out private apps, so a password app
 *             over the editor is sent. Hence the line claims only the text.
 *   code      server/coach/* (the step's code from the editor buffer or the file, keys replaced by server/redact.py),
 *             Anthropic only. lesson/workdir.py scan (adapt_checks) is sent as is: the policy says so.
 *   editor    server/orchestrator/editor_text.py (the VS Code companion's live buffer, read over localhost)
 *   searches  server/finder/* (YouTube, DuckDuckGo, GitHub, arXiv; Bright Data only with its key; Claude ranks)
 *   videos    server/lesson/gemini.py watch_video (builder.py, progressive.py): the YouTube link, the learner's goal
 *             (what they want to learn) and the YouTube page text (title, description, chapters); step_detail re-sends
 *             the link with a step's title and time range. gemini.adapt_checks would also send the draft steps and a
 *             workdir summary with the learner's own Gemini key, but builder.py calls claude.adapt_checks today (so
 *             those go to Anthropic): if Gemini adapts again, say so here and in the policy.
 *   account   main/features/auth.ts (Google through Supabase; the session in userData/auth.bin, safeStorage)
 *   link      main/features/cloudLink.ts: after sign-in, POST <miyagi-cloud>/v1/link with the install token and the
 *             Supabase access token; the cloud (cloud/app.py on claude/eng-proxy, store.py links table) keeps the
 *             install's token hash with the Supabase user id. Sign-out never unlinks. Local note: userData/cloud-link.json
 *             (user id, no token), removed by Delete my data; the cloud's row stays (no cloud delete yet).
 *   cloud     cloud/app.py + store.py (claude/eng-proxy): passes AI calls on and keeps per-install daily counts
 *             (requests, tokens, cost by model and role, lesson builds by month); never the request or answer bodies
 *   keys      main/features/settings.ts (userData/keys.bin, safeStorage; memory only without secure storage)
 *   progress  server/sessions/store.py, checks/tiger.py (local SQLite under ~/miyagi/state), lesson folders in
 *             ~/miyagi/lessons (server/workspace/core.py)
 *   crash     main/features/telemetry.ts + telemetry/core.ts crashEvent: only {kind, app_version}, the error text stays
 *             here; only with prefs.shareTelemetry on (off by default) and the login gate open
 *   usage     the same switch: telemetry/core.ts EVENT_NAMES / EVENT_PROPS (app_installed, onboarding_done and lesson
 *             and step counts, numbers and enums only; no cost, never code, files or screen text). The cloud
 *             (POST /v1/events) keeps them as daily counts per install.
 *
 * AI calls go through miyagi-cloud (main/features/cloud.ts, the hosted proxy) unless the learner added their own key,
 * which goes straight to its provider (server/config.py). NOT done, so never claimed in the panel: cropping to the work
 * area (5.1), a "see what was sent" log. Key and token redaction (5.2, server/redact.py on integration/live) matches by
 * shape and can miss some, so the panel never promises it; the policy describes it with that caveat.
 *
 * Copy rules: one calm line each, 12 words at most, lowercase "miyagi", no em dashes.
 *
 * D1 (Adrian, Nov 21): Claude only at launch, no Gemini. With GEMINI_ENABLED false the panel names Anthropic only (the
 * Lesson videos row below), like the consent screen (features/onboarding/consentCopy.ts).
 */
import { GEMINI_ENABLED } from '../../../../../common/flags'

export type FactId =
  | 'screen'
  | 'code'
  | 'editor'
  | 'searches'
  | 'videos'
  | 'account'
  | 'link'
  | 'cloud'
  | 'keys'
  | 'progress'
  | 'crash'
  | 'usage'

export type Fact = {
  id: FactId
  label: string
  /** The one line, shown in the panel and quoted in web/privacy.md. */
  line: string
  /** The right side of the row: "On this Mac" or where it goes. */
  where: string
  /** Leaves this Mac (to the place `where` names). */
  leaves: boolean
}

export const STAYS = 'On this Mac'

/**
 * Lesson videos: Anthropic only at launch (D1, Adrian, Nov 21: Claude only, no Gemini; common/flags.ts GEMINI_ENABLED).
 * The Gemini line comes back with the flag. CHECK with Michael that the engine's Claude-only path sends what the line
 * says (the video's page text or captions and the learner's goal).
 */
const VIDEOS: Fact = GEMINI_ENABLED
  ? { id: 'videos', label: 'Lesson videos', line: 'The video link and what you want to learn, to Google Gemini.', where: 'To Google', leaves: true }
  : { id: 'videos', label: 'Lesson videos', line: 'The video’s text and what you want to learn, to Anthropic.', where: 'To Anthropic', leaves: true }

export const FACTS: readonly Fact[] = [
  { id: 'screen', label: 'Your screen', line: 'During a lesson, screenshots and screen text. Text from password apps dropped.', where: 'To Anthropic', leaves: true },
  { id: 'code', label: 'Your code', line: 'The step’s code, when miyagi checks your work or helps.', where: 'To Anthropic', leaves: true },
  { id: 'editor', label: 'Your editor', line: 'miyagi reads VS Code here to follow your step.', where: 'Read on this Mac', leaves: false },
  { id: 'searches', label: 'Your searches', line: 'What you ask to learn goes to search sites and the AI.', where: 'To search sites', leaves: true },
  VIDEOS,
  { id: 'account', label: 'Your sign-in', line: 'Google sign-in through Supabase. The session stays encrypted here.', where: 'To Supabase', leaves: true },
  { id: 'link', label: 'Account link', line: 'When you sign in, miyagi’s server ties this Mac to your account.', where: 'To miyagi', leaves: true },
  { id: 'cloud', label: 'miyagi’s server', line: 'Passes AI calls on. Keeps counts and cost, never your work.', where: 'To miyagi', leaves: true },
  { id: 'keys', label: 'Your API keys', line: 'Locked by your Keychain, sent only to their provider.', where: STAYS, leaves: false },
  { id: 'progress', label: 'Lesson progress', line: 'Lesson folders and progress, kept in ~/miyagi on this Mac.', where: STAYS, leaves: false },
  { id: 'crash', label: 'Crash reports', line: 'Only the kind of error, never its text. Off unless you share.', where: 'To miyagi, if on', leaves: true },
  { id: 'usage', label: 'Usage counts', line: 'Lesson and step counts. Never your code or screen.', where: 'To miyagi, if on', leaves: true }
]

/** The keys line when this Mac has no secure storage (settings.ts keeps them in memory for this run). */
export const KEYS_NO_KEYCHAIN = 'Kept in memory for this run, sent only to their provider.'

/**
 * The Windows build shows these lines about its own machine: "this computer", never "this Mac" or the Keychain
 * (keys there are encrypted with Windows' data protection). The lines above stay as written, word for word with
 * web/privacy.md; this only changes what a Windows screen shows.
 */
export function onThisComputer(text: string, mac: boolean): string {
  if (mac) return text
  return text
    .replace(/Locked by your Keychain/g, 'Kept encrypted on this computer')
    .replace(/this Mac/g, 'this computer')
    .replace(/your Mac/g, 'your computer')
}

/** AI calls: how they travel. Shown under the panel and in the policy. */
export const ROUTE = 'AI calls go through miyagi’s server, or direct with your key.'

/**
 * Delete account (Privacy.tsx's two-step confirm; main account:delete, then settings:delete and auth:sign-out). The
 * policy quotes these too. Exactly what the code erases (age-delete lane, Nov 21; main/features/accountDelete/wipe.ts):
 * the account and this install on miyagi's server first (POST /v1/account/delete), then on this Mac every file and
 * folder miyagi keeps in userData (keys, sign-in, the account link note, the install token, setup, the age step,
 * preferences, reminders, the error log and crash reports, usage state), the app's logs, the browser storage (the
 * YouTube player's cookies included), the engine's caches (searches, lessons, captions), runs, logs and saved progress.
 * ~/miyagi/lessons only when ticked. What stays: VS Code and its extensions, userData/engine.json (which engine to
 * run). Server unreachable: nothing at all is deleted.
 */
export const DELETE = {
  label: 'Delete account and data',
  row: 'Deletes your account and everything miyagi keeps. Cannot be undone.',
  confirmLabel: 'Delete your miyagi account?',
  confirm: 'Deletes your account, what our server keeps, and this Mac’s data.',
  undo: 'Cannot be undone.',
  lessons: 'Also delete my lesson folders in ~/miyagi',
  offline: 'Couldn’t reach miyagi’s server. Nothing was deleted.',
  refused: 'Couldn’t delete your account. Nothing was deleted.',
  done: 'Your account and this Mac’s data are deleted.',
  pending: 'Deleted from this Mac. Your account goes within 30 days.',
  partial: 'Account deleted. Some files on this Mac stayed.',
  restart: 'miyagi starts again in a moment.'
} as const

/** The published policy (opened through the existing external-link path, allowlisted miyagi.study). */
export const POLICY_LINE = 'Everything above, in full, on miyagi.study.'
