# reminders

**Status:** first pass done (stage verified; Electron not run, cost freeze) · **Port:** 5614 · **Branch:** `michael/app-reminders`

## Goal
Gentle, opt-in reminders that bring people back without nagging. Off by default. Offered once, right after the first
finished lesson: "Want a nudge when a review is due?" (Yes / Not now). When on: at most one macOS notification a day
at the learner's time (default 6:00 PM local), only when something is due, with a calm, specific line ("2 skills ready
for a quick review: pandas groupby, numpy arrays"). A click opens Home.

## Owns
- `app/src/main/features/reminders.ts`: settings file, the daily look, the Electron `Notification`
- `app/src/renderer/src/features/reminders/`
  - `logic.ts` pure rules shared by main and the renderer (decide, what is due, compose, time helpers)
  - `store.ts` settings from main, the one-time offer, the in-app toast, the daily goal reported to main
  - `Offer.tsx` the island card (priority 41) · `Toast.tsx` the notification stand-in (overlay layer z 92)
  - `Settings.tsx` `<RemindersGroup />` for Settings > General, and the stage preview
  - `web.ts` browser-stage stand-ins (localStorage, the same scheduler, toast instead of a notification)
- `app/mock/scenarios/reminders.json`

## How it behaves
- **Offer:** armed when a lesson's completion card closes in this session; it grows from the island at the next idle
  moment (no other card, nothing building, no other lesson running). Yes, Not now or Esc answers it for good.
  Yes turns reminders on; the pill always confirms it ("Reminders on. 6:00 PM, only when something is due."), so the
  choice is confirmed even if macOS permission is denied, banners are off or Focus is on. The first time ever, main
  also sends one welcome notification ("Reminders are on. One a day at 6:00 PM, only when something is due."), so the
  learner sees what one looks like and macOS asks for permission in context.
  **Gate:** the offer stays hidden until the settings lane calls `reachableInSettings()` (Core request 1), because its
  copy promises "Change the time or turn it off in Settings". The stage's offer views set it themselves.
- **Daily look (main, every 30 s and on wake):** only when on, not snoozed, not resting (the dashboard's rhythm pause),
  from the chosen time to 3 hours after it, once per local day. Quiet hours skip the day silently. A running lesson
  only defers the look until it ends (still inside the 3-hour window). "Running" means a lesson event (`lesson.*`,
  `step.*`, `check.updated`, `offtrack`) in the last 20 minutes; `lesson.ended`, the `complete` card, a failed build or
  an engine disconnect end it at once. (The engine keeps a finished lesson loaded, so "a lesson is loaded" is never
  the test.) Rules: `logic.ts` `lessonSignal` / `lessonRunning`, shared by main and the stage.
  It asks the engine `progress.get` (when listed), else uses the last answer if under 6 hours old; if neither, it tries
  again every 5 minutes inside the window and never guesses.
- **What is due:** the dashboard's own reader (`readDashboard` + `dueItems`), so Home and the notification agree.
  Reviews first (1, 2, or "3 skills ... and 1 more"); otherwise reps left for today's goal, only when the engine counts
  activity. The goal is the learner's own (dashboard prefs, re-read from localStorage `miyagi.dashboard.prefs`, the
  source of truth, when reported), then the engine's, then 3. A prefs change is reported by the window where it was
  made; an engine settings change only by the island window, so one change makes one write.
  Nothing due: nothing sent.
- **Turned on (any time of day):** only the first time ever (nothing sent before) is there a welcome note; it counts
  as today's notification (`lastSentAt` and `lastDay` set), so the first look is tomorrow. Turning reminders off and
  on again later sends nothing and leaves the day as it was, so the switch can never add a second notification to a
  day. `logic.ts` `turnOn` does it for main and the stage alike.
- **Settings:** Review reminders (on/off with an exact "Next: tomorrow at 6:00 PM ..." caption), Time (a native
  picker of half-hour slots), Quiet hours (on/off, and right under it the from/to pickers, 10:00 PM to 8:00 AM by
  default; a time inside them says no reminder will come), Pause (Not today / For a week, Resume).
- **Development never posts a real notification:** an unpackaged build sends the note to the overlay as the in-app
  toast (`MIYAGI_REAL_NOTIFICATIONS=1` opts in). The browser stage always uses the toast.

## Test
`npm run dev:web -- --port 5614 --strictPort`
- `http://localhost:5614/?scenario=reminders` a 2-step lesson finishes; Esc the completion card: the offer grows out
  of the island. Yes shows the welcome toast; Esc / Not now shows the pill line.
- `&reminders=offer` (with `?scenario=full`) the offer at once · `?scenario=full&reminders=toast&hold` the reminder
  now from the mock's review queue (click opens Home) · `?scenario=full&reminders=settings` the Settings group.
- Screens: `/Users/tripi/sand hacks/miyagi-v2/screens/round3/reminders-*.jpg`

## Core requests
1. **settings lane (merge gate):** mount `<RemindersGroup />` (`features/reminders/Settings.tsx`) in Settings >
   General, after "Look and startup" (it renders nothing until main answers), and call
   `reachableInSettings()` (`features/reminders/store.ts`) once at that module's top level. Without that call the
   one-time offer never shows (on purpose: its copy promises the Settings controls). Ship both in the same release.
   Same for the shell's Settings page if it renders its own General.
2. **library / shell lane (optional):** the home window is opened with args `{ page: 'home', from: 'reminder' }` on a
   notification click; Home could greet that (for example scroll to Review). Nothing breaks if it is ignored.
3. **electron-builder.yml (later, with Apple signing):** notification actions (Snooze on the banner itself) need a
   signed app with `NSUserNotificationAlertStyle: alert`. Until then, snooze lives in Settings.
4. **real-app lane, `main/index.ts` (Windows):** call `app.setAppUserModelId(<appId from electron-builder.yml>)` early
   in startup on Windows. Without it, Electron `Notification` can fail silently on Windows builds (no reminder, no
   welcome). The in-app pill line on Yes still confirms the choice either way.
5. **engine (later):** a real review scheduler with `review.items[].dueAt` and per-day `activity`. Today only fixture
   data has them; with neither, reminders stay quiet (by design).

## Notes
- Every window loads the store; only the overlay (and the stage) shows the offer and the toast.
- In `?scenario=full`, finishing any lesson arms the offer too (it is the product behavior); answer it once and the
  stage's localStorage keeps it answered.
- Not verified in Electron: the real `Notification` click, `powerMonitor` resume, and the macOS permission prompt.
