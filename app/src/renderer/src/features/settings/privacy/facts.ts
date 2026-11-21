/**
 * Feature: settings. Privacy (ROADMAP 5.4): the ONE list of what miyagi sees and where it goes. Sees.tsx shows it,
 * web/privacy.md says the same lines word for word (facts.test.ts checks both). Honest subset only: every line is
 * what the code does today. Read before changing a line:
 *
 *   screen    engine server/screen/reader.py + privacy.py (OCR text: emails / card / phone numbers scrubbed, text from
 *             password apps and Messages dropped). Screenshots during an active lesson step: server/orchestrator/
 *             scene_watch.py (the step check) blacks out private apps' windows; the pointing path (screen_bridge →
 *             target.pick_on_screen → reader.latest_frame → render_marks) blacks out only miyagi's overlay and other
 *             folders' VS Code windows, so a password app over the editor is sent. Hence the line claims only the text.
 *   code      server/coach/* (the step's code from the editor buffer or the file), Anthropic only
 *   editor    server/orchestrator/editor_text.py (the VS Code companion's live buffer, read over localhost)
 *   searches  server/finder/* (YouTube, DuckDuckGo, GitHub, arXiv; Bright Data only with its key; Claude ranks)
 *   videos    server/lesson/gemini.py watch_video (builder.py, progressive.py): the YouTube link, the learner's goal
 *             (what they want to learn) and the YouTube page text (title, description, chapters); step_detail re-sends
 *             the link with a step's title and time range. gemini.adapt_checks would also send the draft steps and a
 *             workdir summary with the learner's own Gemini key, but builder.py calls claude.adapt_checks today (so
 *             those go to Anthropic): if Gemini adapts again, say so here and in the policy.
 *   account   main/features/auth.ts (Google through Supabase; the session in userData/auth.bin, safeStorage)
 *   keys      main/features/settings.ts (userData/keys.bin, safeStorage; memory only without secure storage)
 *   progress  server/sessions/store.py, checks/tiger.py (local SQLite under ~/miyagi/state), lesson folders in
 *             ~/miyagi/lessons (server/workspace/core.py)
 *   crash     main/features/telemetry.ts + telemetry/core.ts scrubCrash, only with prefs.shareTelemetry on
 *   usage     the same switch: telemetry/core.ts EVENT_NAMES (counts, never code, files or screen text)
 *
 * AI calls go through miyagi-cloud (main/features/cloud.ts, the hosted proxy) unless the learner added their own key,
 * which goes straight to its provider (server/config.py). NOT done, so never claimed: cropping to the work area
 * (5.1), secret redaction of keys and tokens in screen text (5.2), a "see what was sent" log.
 *
 * Copy rules: one calm line each, 12 words at most, lowercase "miyagi", no em dashes.
 */

export type FactId = 'screen' | 'code' | 'editor' | 'searches' | 'videos' | 'account' | 'keys' | 'progress' | 'crash' | 'usage'

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

export const FACTS: readonly Fact[] = [
  { id: 'screen', label: 'Your screen', line: 'During a lesson, screenshots and screen text. Text from password apps dropped.', where: 'To Anthropic', leaves: true },
  { id: 'code', label: 'Your code', line: 'The step’s code, when miyagi checks your work or helps.', where: 'To Anthropic', leaves: true },
  { id: 'editor', label: 'Your editor', line: 'miyagi reads VS Code here to follow your step.', where: 'Read on this Mac', leaves: false },
  { id: 'searches', label: 'Your searches', line: 'What you ask to learn goes to search sites and the AI.', where: 'To search sites', leaves: true },
  { id: 'videos', label: 'Lesson videos', line: 'The video link and what you want to learn, to Google Gemini.', where: 'To Google', leaves: true },
  { id: 'account', label: 'Your sign-in', line: 'Google sign-in through Supabase. The session stays encrypted here.', where: 'To Supabase', leaves: true },
  { id: 'keys', label: 'Your API keys', line: 'Locked by your Keychain, sent only to their provider.', where: STAYS, leaves: false },
  { id: 'progress', label: 'Lesson progress', line: 'Lesson folders and progress, kept in ~/miyagi on this Mac.', where: STAYS, leaves: false },
  { id: 'crash', label: 'Crash reports', line: 'Scrubbed error lines. Sent only when sharing is on.', where: 'To miyagi, if on', leaves: true },
  { id: 'usage', label: 'Usage counts', line: 'Lesson counts and cost. Never your code or screen.', where: 'To miyagi, if on', leaves: true }
]

/** The keys line when this Mac has no secure storage (settings.ts keeps them in memory for this run). */
export const KEYS_NO_KEYCHAIN = 'Kept in memory for this run, sent only to their provider.'

/** AI calls: how they travel. Shown under the panel and in the policy. */
export const ROUTE = 'AI calls go through miyagi’s server, or direct with your key.'

/** Delete my data (Privacy.tsx's two-step confirm, main settings:delete). The policy quotes these too. */
export const DELETE = {
  row: 'Erases keys, settings and sign-in on this Mac. Cannot be undone.',
  confirmLabel: 'Delete keys, settings and sign-in?',
  confirm: 'Signs you out. Lesson folders in ~/miyagi stay. Cannot be undone.',
  partial: 'Keys and settings deleted. Couldn’t clear sign-in.',
  failed: 'Couldn’t delete. Nothing was removed.'
} as const

/** The published policy (opened through the existing external-link path, allowlisted miyagi.study). */
export const POLICY_LINE = 'Everything above, in full, on miyagi.study.'
