# miyagi UI package

The whole app UI in one place so we build it the same way. Visual version with every screenshot: https://claude.ai/artifact/BwgPtNw5jkDYDjLMiWhfBK

- Branch `adrian/app-redraft`, PR #231, head `901a5abc`.
- Screens were captured from the browser stage (`npm run dev:web`, mock engine). Paths below are under `app/src/renderer/src/features/` unless they start with `app/` or `core/`.
- Stage URLs: start from `http://localhost:5173/?size=1440x900&clean&os=mac&appearance=dark` and add the part shown for each screen (`dev:web` prints the port).

## What changed tonight

- **Every clickable list.** Home, Lessons, Progress and Account rows share one chevron that sits at half strength and wakes up on hover, so anything that opens something looks the same everywhere.
- **Home.** The bonsai, the Continue card and the ask field read as one group; the lists below are evenly spaced. Continue is one row with progress as a hairline on its bottom edge. The ask field is taller, led by the bonsai, and brightens on hover and focus. The chips sit inside it and are personal: the skills you are ready for next. While a lesson builds, the card shows a spinner and the build status under the title.
- **Lessons.** Ready to run rows have the chevron, hover and hairlines under the text. In progress rows share one progress-line width and matching Continue buttons. Paste a YouTube link reads as the last row.
- **Lesson preview.** One centered column with Start under the title, a single back button, a "7 steps" heading, tools as plain text, and no reassurance copy under the button.
- **Skills.** Each track name has a ring that fills as its skills are mastered (green once all are), with no "N of M" count. Ghost nodes from other tracks are gone; the header says "Builds on Loops in Python" instead. Quieter legend, larger labels, more air between tracks.
- **Progress.** Its own page now instead of repeating the Skills graphs: Review (due and upcoming), Up next with a quiet Start, each track with its ring and next skill, Finished lessons, Milestones.
- **Account.** One grouped list: Plan with a quiet Upgrade, Help this month with a slim meter and "6 left · resets December 1", Your own key, then Sign out on its own. Avatars show the initial.
- **Sidebar.** Keeps the Ready status in mid-size windows and narrows to 196 px below 1100 px wide, so a 1024 by 700 window fits.
- **Setup on Windows.** Sign in, VS Code, engine (Screen Recording and Accessibility are Mac-only). Copy says "this computer", the same word as Michael's Windows work. A missing engine shows "Not running" in gray instead of blocking setup.
- **Guided tour.** A sample panel built like the real lesson panel, five short marks, keys that follow the computer.
- **Settings.** Every control traced to its main-process handler and clicked through. Text at 14 and 13 px. Your own key shows Test and Save only when they can act. Windows shows only the rows that apply.
- **Lesson panel and drawer.** Drawer labels in sentence case like everything else, no repeated step count, no one-word orphan lines. A pending check shows only the eye, so narrow check rows stop wrapping.
- **Overlay cards.** Off track keeps its options and Do it for me on one row. Lesson complete is shorter: the check beside the title, plain skill checks, no "N of M mastered". The building card is left-aligned with one line of reassurance.
- **Island notices.** Error, review and reminder cards share one header (bonsai, label, Esc) and end in one button pair, quiet first and the white primary last. No gray chips on the black island, no icon tiles.
- **Sign in.** A failed sign-in reads as a state with Try again; when Google sign-in is not set up, it offers Continue without an account.

## Theme

Source of truth: `core/theme.ts` (tokens) and `app/brand/BRAND.md` (rules).

| Token | Dark | Light | In code | Use |
|---|---|---|---|---|
| Window | `rgb(21,20,18)` | `rgb(238,236,231)` | `l-base` | Every app window and the sidebar |
| Raised | `rgb(30,29,27)` | `rgb(251,250,248)` | `l-raised` | The one content panel |
| Card, sheet | `rgb(40,39,36)` | `#FFFFFF` | `l-overlay` | Lifted cards, sheets, menus |
| Notch black | `#000000` | `#000000` | `hud.notch` | The island and its cards only, in both themes |
| Text | `#F4F4F5` | `#141414` | `c-text` |  |
| Label | `rgba(255,255,255,.6)` | `rgba(20,20,20,.62)` | `c-label` | Secondary text |
| Faint | `rgba(255,255,255,.42)` | `rgba(20,20,20,.42)` | `c-faint` | Hints, numbers |
| Hairline | `rgba(255,255,255,.12)` | `rgba(20,20,20,.10)` | `c-hairline` | Dividers |
| Ring | `rgba(255,255,255,.28)` | `rgba(20,20,20,.28)` | `f-ring` | Field edges, hollow rings |
| Primary button | `#F4F4F5` | `#141414` | `c-accent` | White on dark, ink on light |

**Status:** watching = gray dot `#8E8E93`; checking = spinner, no color; Not yet = hollow white ring, no hue; passed = `#30D158` (`#22A24B` on light), the only green.

**Options, the only pastels** (solid pastel + ink text on buttons; 16% wash + pastel text for chips on dark): Explain sky `#C5E4F9`, Hint pink `#F9C5D5`, Show me lilac `#D9D2FF`, Diagram seafoam `#BFEBE6`, Watch peach `#FBD5BE`.

**Brand:** Bark #5A4433, #A07A5C on dark, Clay #B5603F, #C2694A on dark, Pads, pass #30D158, Ink #141414, Paper #F6F6F3.

**Type:** system font (SF Pro on a Mac, Segoe UI on Windows). Scale: 20 xl (Card titles), 17 lg (The ask field), 15 body (Body), 14 md (Row titles), 13 sm (Lines under titles), 12 xs (Captions, section labels), 11 micro (Keycaps). Google Sans Flex only for the wordmark and marketing.

**Radii:** keycap 6, control 8, row 10, card 12, chip 14, group 16, panel 20, sheet 24, launcher 28.

**Motion:** one spring (stiffness 420, damping 34, mass 0.9); leaving uses damping 38. Fades 0.08 / 0.12 / 0.18 / 0.24 s, 0.4 s for a line drawing itself, ease out `cubic-bezier(.23,1,.32,1)`. Press scales to 0.97; list rows rise 6 px, 35 ms apart, capped at 8. Reduced motion: crossfades.

## Components

- `PrimaryButton`: The ONE primary action on a surface. White on dark, ink on light. Can carry a keycap.
- `QuietButton`: Secondary actions. Neutral, never a hue.
- `OptionButton`: Explain, Hint, Show me, Diagram, Watch. Solid pastel, ink text, keycap on 10% ink. Shows the spinner while miyagi answers.
- `Keycap`: Labels come only from the platform: ⌃⌥E on a Mac, Alt+E on Windows. Never typed by hand.
- `StatusGlyph`: Watching, checking, Not yet, passed. The same four everywhere: pill, panel, rows.
- `Row`: A list row: hover fill, spring press, a chevron when it opens something.
- `Progress`: StepBar or the hairline progress line. Ink and white only.
- `MiyagiMark`: The bonsai, always in color. Picks its cut by size. Replaces every sparkle.
- `Card`: One lifted surface per page: l-overlay, hairline edge, raised shadow.
- `RowChevron` (shell/ui.tsx): the one "this row opens something" mark, last child of a `Row`.
- `TrackRing` (dashboard/Constellation.tsx): a track's mastery ring, green once every skill is mastered.

## Rules

- Green only ever means passed. Off track has no hue: a white ring and "Not yet". No red, yellow, blue or purple.
- Pastels only for options, and the same action is the same color everywhere. Never pastel for status or chrome.
- One white primary button per surface. Navigation and chrome stay neutral.
- No gradients, glows, sparkles, emoji, icon tiles or tool pills on rows. Type, spacing and one raised surface do the work.
- Every overlay surface is born from the notch island and goes back into it. Nothing pops up mid-screen.
- The brand is lowercase: miyagi. Teaching copy keeps sentence case. About 12 words per card. No em dashes.
- Keycaps only from the platform. Actions go through sendAction or triggerShortcut. A pressed option shows the spinner until the answer lands.
- Nothing lesson-specific in UI code. Labels come from the data.
- One spring for everything that moves. Animate transform and opacity only. Reduced motion gets crossfades.

## Mac and Windows

| | Mac | Windows |
|---|---|---|
| Open miyagi, ask | ⌥Space | Ctrl+Shift+Space |
| Explain, Diagram, Show me, Hint | ⌃⌥E, ⌃⌥D, ⌃⌥S, ⌃⌥H | Alt+E, Alt+D, Alt+S, Alt+H |
| Back | ⌃⌥← | Alt+← |
| Push to talk | hold fn ⌃ (or ⌃⌥) | Not on Windows yet (the setting is hidden) |
| Settings | ⌘, | Ctrl+, |
| Where the island sits | In the notch, or below the menu bar | Top center of the screen (the setting is hidden) |
| Setup steps | Sign in, Screen Recording, Accessibility, VS Code, engine | Sign in, VS Code, engine |
| The computer in copy | "this Mac", Terminal, Keychain | "this computer", PowerShell, "Encrypted on this computer" |
| Engine | Bundled in the app, starts by itself | None yet: setup says "Not running" and does not block |
| Font | SF Pro | Segoe UI |

- The VS Code step is one click on a Mac (VS Code's own command-line tool installs the bundled companion plus the Python and Jupyter extensions). On Windows that install is not wired up yet.
- Copy helpers: onboarding/device.ts (thisDevice, shellName, needsGrants) and settings/here.ts. New copy that names the computer should go through them.

## Screen by screen

### First launch

One window. The setup flow covers the home window until sign-in and setup are done, on every launch while either is still open.

**01. Intro**  
- The bonsai grows in, then "Learn by doing, in the apps you already use."
- Any key skips it. Shown once per Mac.
- Under the hood: Renderer only (features/onboarding Intro). main remembers that it was seen.
- Code: `onboarding/Intro.tsx`, `shell/flow/FlowLayer.tsx`
- Stage: `&scenario=home-dashboard&window=library&flow=1&step=intro`
- Screens: `screens/intro.webp`

**02. Sign in**  
- Continue with Google is the one button. "Continue without an account" is always there, with Terms and Privacy under it.
- A failed sign-in reads as a state: the Not yet ring and plain words ("The browser sign-in timed out.") with Try again.
- When Google sign-in is not set up, it says so and offers Continue without an account instead of Try again.
- Under the hood: Google runs in the system browser: OAuth with PKCE through Supabase, back to a loopback port on this computer (127.0.0.1:47217). The session is saved encrypted in auth.bin.
- Code: `auth/Login.tsx`, `auth/store.ts`
- Stage: `&scenario=home-dashboard&window=library&flow=1&step=login (&auth=fail, &auth=unset)`
- Screens: `screens/login.webp`, `screens/login-fail.webp`, `screens/login-unset.webp`

**03. Screen Recording (Mac)**  
- "Let miyagi see your screen." A drawing of the System Settings row to switch on.
- Allow opens the macOS prompt, then the settings pane. macOS needs a relaunch after it.
- Mac only. Windows has no such permission, so this step does not exist there.
- Under the hood: The engine reads the screen to know which step you are on and where to point (ScreenCaptureKit, Apple Vision OCR).
- Code: `onboarding/Guided.tsx`, `onboarding/steps.ts`, `onboarding/Illustration.tsx`
- Stage: `&scenario=home-dashboard&window=library&flow=1&step=screen`
- Screens: `screens/screen.webp`

**04. Accessibility (Mac)**  
- "Let miyagi point at buttons." Open System Settings.
- The row turns green on its own once you switch it on.
- Mac only, like Screen Recording.
- Under the hood: Accessibility gives the engine the real positions of controls (VS Code's Run button, a notebook cell), so the spotlight lands on them.
- Code: `onboarding/Guided.tsx`, `onboarding/steps.ts`
- Stage: `&scenario=home-dashboard&window=library&flow=1&step=access`
- Screens: `screens/access.webp`

**05. Connect VS Code**  
- One click, not automatic: Install in VS Code.
- The row turns green once the engine sees the companion connect: "Done. Connected to VS Code."
- Without VS Code on the computer: Get VS Code, or Skip.
- Under the hood: On a Mac the app runs VS Code's own command-line tool to install the bundled miyagi companion plus the Python and Jupyter extensions. On Windows that install is not wired up yet: the tool lookup is Mac-only and the extension file only ships in the Mac build.
- Noticed: The Windows install path for the companion still has to be built.
- Code: `onboarding/rows.ts`, `onboarding/device.ts`, `app/src/main/features/onboarding.ts`
- Stage: `&scenario=home-dashboard&window=library&flow=1&step=vscode (&os=win)`
- Screens: `screens/vscode.webp`, `screens/vscode-win.webp`

**06. Getting miyagi ready**  
- Two rows: Engine on this Mac (Running) and Access for this Mac (Setting up). Nothing to click; it moves on by itself.
- On Windows the rows say "this computer". With no engine there, the row reads "Not running" in gray with Retry and Copy details, and setup is not blocked.
- Under the hood: The Mac app starts its own bundled engine and asks miyagi-cloud for an install token, so a new user needs no API key. The Windows build has no engine yet.
- Code: `onboarding/rows.ts`, `onboarding/Illustration.tsx`
- Stage: `&scenario=home-dashboard&window=library&flow=1&step=engine (&os=win)`
- Screens: `screens/engine.webp`, `screens/engine-win.webp`

**07. You're ready**  
- "miyagi is set up on this Mac" (or "this computer").
- Sample lesson: "A one-minute tour. Nothing real starts."
- Skip goes home; Show me around starts the tour. The footer teaches the open key for that computer.
- Under the hood: Setup state lives in main (onboarding.json). The progress dots match the steps: five on a Mac (sign in, two permissions, VS Code, ready), three on Windows.
- Code: `onboarding/Ready.tsx`, `shell/flow/Strip.tsx`
- Stage: `&scenario=home-dashboard&window=library&flow=1&step=ready`
- Screens: `screens/ready.webp`, `screens/ready-win.webp`

**08. Guided tour**  
- Five marks over a sample panel built like the real lesson panel: This is miyagi, One step at a time, Check my work, Stuck?, Ask anytime.
- Each is one short line. Keys come from the computer it runs on.
- Skip or Next on each; Esc ends it.
- Under the hood: features/tips. It draws its own sample panel and never starts a real lesson. The old fifth mark pointed at an End lesson button the real panel does not have; it is now "Ask anytime".
- Code: `tips/TourLayer.tsx`, `tips/tourMarks.ts`, `tips/tourStore.ts`
- Stage: `&scenario=full&tour=1 (1-5)`
- Screens: `screens/tour1.webp`, `screens/tour3.webp`, `screens/tour5.webp`

### The home window

The app window from the Dock or the menu bar. Sidebar on the left, one raised panel on the right.

**09. Home**  
- Bonsai centered on top, then the Continue card: "Continue · Step 4 of 7", the lesson, the step you are on, the button on the right, and progress as a hairline along its bottom edge.
- The ask field, led by the bonsai, with suggestion chips centered inside the same frame. The chips are the skills you are ready for next.
- "2 skills to review", then Up next: three saved lessons as plain rows.
- Sidebar: New lesson, Home, Lessons, Skills, Progress. At the foot: engine status (Ready), Settings, your account chip.
- Under the hood: All of it comes from the engine: library.list, progress.get and health.get over the socket. This is layout A, Adrian's pick (Nov 21).
- Code: `library/Home.tsx`, `library/homeModel.ts`, `shell/ui.tsx`
- Stage: `&scenario=home-dashboard&window=library (core-v2 = new user)`
- Screens: `screens/home.webp`, `screens/home-light.webp`, `screens/home-narrow.webp`

**10. Lessons**  
- Search at the top right.
- In progress: each lesson with the same-width progress line and a Continue button (only the first is white).
- Ready to run, filtered by tool (All, VS Code, Jupyter, Terminal). Each row has the chevron and hover and opens its preview. Paste a YouTube link is the last row.
- Under the hood: These are lessons saved on this computer. Starting one sends library.start, which costs no model calls.
- Code: `library/Library.tsx`, `library/store.ts`
- Stage: `&scenario=home-dashboard&window=library&page=lessons`
- Screens: `screens/lessons.webp`, `screens/lessons-light.webp`

**11. Lesson detail**  
- One back button ("Lessons"), then one centered column: "Lesson from the library", the title, Jupyter, VS Code · 7 steps · About 25 min.
- Start lesson right under the title.
- A "7 steps" heading: the steps open one at a time, each checked before the next.
- Under the hood: library.get for the details, library.start to begin.
- Noticed: There is still no step-by-step preview before the lesson starts.
- Code: `library/Detail.tsx`
- Stage: `&scenario=home-dashboard&window=library&id=hd_mnist`
- Screens: `screens/detail.webp`

**12. Skills**  
- One graph per track: Python basics, numpy, and one per lesson you took.
- Each track name has a ring that fills as its skills are mastered, green once all are. No counts.
- A track that builds on another says so in its header ("Builds on Loops in Python") instead of drawing ghost nodes.
- Node states in a quiet legend: Mastered, Practicing, Ready to learn, Locked, Review due.
- Under the hood: Built from the progress message the engine sends. A finished lesson sends a skill map with no model call.
- Code: `dashboard/Constellation.tsx`, `dashboard/model.ts`, `shell/pages/SkillsPage.tsx`
- Stage: `&scenario=home-dashboard&window=library&page=skills`
- Screens: `screens/skills.webp`

**13. Progress**  
- Review: each skill that is due or coming up, with its date. Start review shows only when the engine can review.
- Up next: three lessons with what they unlock and a quiet Start.
- Skills: one row per track with its ring and the next skill; opens Skills.
- Finished lessons and Milestones at the foot.
- Under the hood: Same progress data as Skills, read as a list of what to do next rather than the graphs.
- Code: `dashboard/Overview.tsx`, `shell/pages/ProgressPage.tsx`
- Stage: `&scenario=home-dashboard&window=library&page=progress`
- Screens: `screens/progress.webp`

**14. Settings**  
- Tabs: General, Permissions, Privacy, Your own key, Shortcuts.
- General on a Mac: Appearance, Island, Launch at login, Push to talk with its shortcut, Microphone, Input monitoring, Works with, Set up miyagi, Show me around.
- On Windows: no Island, Push to talk or Mac permission rows. Permissions shows only the VS Code companion and "Windows asks for nothing extra." Keys read "Encrypted on this computer".
- Your own key shows Test only when there is something to test, and Save key only once a field changed.
- Under the hood: Every control was traced to its main-process handler and clicked through: Appearance switches the theme and sticks after a reload, the toggles persist, Delete my data confirms then signs out. None are stage-only and none are missing a handler. Keys are encrypted by main (Keychain on a Mac, Windows protected storage on a PC) and sent to the engine as config.keys.
- Code: `settings/sections/*.tsx`, `settings/here.ts`, `shell/pages/SettingsPage.tsx`, `app/src/main/features/settings.ts`
- Stage: `&scenario=home-dashboard&window=library&page=settings`
- Screens: `screens/settings-general.webp`, `screens/settings-permissions.webp`, `screens/settings-privacy.webp`, `screens/settings-account.webp`, `screens/settings-shortcuts.webp`, `screens/settings-general-win.webp`, `screens/settings-permissions-win.webp`, `screens/settings-narrow.webp`

**15. Account**  
- The initial avatar, name and email, then one grouped list: Plan (Free, a quiet Upgrade), Help this month with a slim meter and "6 left · resets December 1", Your own key.
- Sign out on its own below.
- Under the hood: Plans and usage are mock data in this preview. In the real app they sit behind a flag that is off, and the account lookup returns nothing until a backend exists.
- Noticed: What you see here is not live in the app yet.
- Code: `shell/pages/AccountPage.tsx`, `shell/AccountSheet.tsx`, `account/model.ts`
- Stage: `&scenario=home-dashboard&window=library&page=account`
- Screens: `screens/account.webp`

### Starting a lesson

Everything starts from the notch. ⌥Space on a Mac, Ctrl+Shift+Space on Windows.

**16. The launcher**  
- Grows out of the notch, never mid-screen.
- Type a goal. Two ways to learn it: Watch a video, or Just teach me. Tab switches.
- The highlight starts on Just teach me when the goal sounds like building something.
- Under the hood: Enter sends learn {query, mode}. A pasted YouTube link skips the search and sends learn_url. A Demo chip exists only in dev builds.
- Code: `launcher/Launcher.tsx`, `launcher/Rows.tsx`, `launcher/parts.tsx`
- Stage: `&scenario=home-dashboard, then Ctrl+K`
- Screens: `screens/launcher.webp`

**17. Search results**  
- The first row is always Just teach me.
- Video rows stream in. The top match says Best.
- Build lesson at the bottom right.
- Under the hood: The engine runs a Claude web search and YouTube's results page in parallel, checks each link resolves, scores each 0 to 100, and streams search.result rows, then search.done.
- Code: `launcher/Rows.tsx`, `launcher/store.ts`
- Stage: `&scenario=home-dashboard, Ctrl+K, type a topic, Enter`
- Screens: `screens/results.webp`

**18. Building the lesson**  
- The card grows from the island, left-aligned: Finding the steps, Writing the checks, Ready to start.
- One line under the meter: "Only built once." and the time left.
- Stop building or Keep working, at the right.
- Under the hood: Claude reads the video's transcript, title and chapters and writes the steps and a check for each, then fits the checks to your folder. The result is cached, so the same video never builds twice. Long videos build in parts.
- Code: `building/Card.tsx`, `pill/index.tsx`
- Stage: `&scenario=home-dashboard, Ctrl+K, a build goal, Enter`
- Screens: `screens/building.webp`

### A "Just teach me" lesson

No video. miyagi writes the lesson and the panel docks on the right, beside your editor.

**19. The pill**  
- It wraps the notch: the bonsai on the left, status on the right.
- Gray dot watching. Spinner checking. White ring Not yet. Green check passed.
- Mini (last): the panel folded into the pill, with the step title and "2 of 6". Click to open it again.
- Right-click opens the miyagi menu. Hovering in a video lesson shows the step card.
- Under the hood: Status comes from engine status, check.updated and step.passed. Green only ever means passed; off track has no hue.
- Code: `pill/index.tsx`, `pill/parts.tsx`, `core/Island.tsx (Michael)`
- Stage: `&scenario=lesson-panel&panel=working|checking|notyet|passed|mini`
- Screens: `screens/pill-working.webp`, `screens/pill-checking.webp`, `screens/pill-notyet.webp`, `screens/pill-passed.webp`, `screens/pill-mini.webp`

**20. Lesson panel**  
- Docked at the right edge, 360 wide. Header: lesson title, step dots, Step 2 of 6.
- The step: title, one line, "Type this in the new cell" with Copy, then how to run it.
- One white button: Check my work.
- Need help: Explain, Hint, Show me, Diagram, Watch. Three over two, one keycap each (⌃⌥E on a Mac, Alt+E on Windows). Footer: Esc hide, ask miyagi, Back.
- Under the hood: Tells the engine where it is (panel.state) so VS Code is kept beside it. Every help button was checked: it sends its action, shows the spinner, then the answer. It stays this simple on purpose.
- Code: `drawer/v2/LessonPanel.tsx`, `drawer/v2/StepBody.tsx`, `drawer/v2/Help.tsx`, `drawer/v2/KeysRow.tsx`
- Stage: `&scenario=lesson-panel&panel=working`
- Screens: `screens/panel-full.webp`, `screens/panel-working.webp`, `screens/panel-working-win.webp`

**21. Checking**  
- The button turns to Checking, with what it is looking at: "Looking at x_train and x_test".
- Nothing else moves.
- Under the hood: action check_step. The engine re-runs the step's checks on your screen text, files and run output. When those can't tell, a small Claude model judges from the text.
- Code: `drawer/v2/LessonPanel.tsx`, `drawer/v2/states.tsx`
- Stage: `&scenario=lesson-panel&panel=checking`
- Screens: `screens/panel-checking.webp`

**22. Not yet**  
- A white ring and "Not yet", no color.
- What is wrong in plain words: "x_train still has values up to 255. Only x_test was divided."
- The missing line is marked in the code. Check again.
- Under the hood: check.updated fail, then a step card from the engine.
- Code: `drawer/v2/states.tsx`
- Stage: `&scenario=lesson-panel&panel=notyet`
- Screens: `screens/panel-notyet.webp`

**23. Hint**  
- The hint sits above the code, never in place of it.
- "1 of 2", then Another hint ⌥H.
- Under the hood: action hint. The engine walks a hint ladder; the last level shows the exact fix.
- Code: `drawer/v2/states.tsx`, `drawer/v2/Help.tsx`
- Stage: `&scenario=lesson-panel&panel=hint`
- Screens: `screens/panel-hint.webp`

**24. Explain**  
- A card grows out of the island: "Why divide by 255".
- Two lines, then it goes. ✕ or Esc closes it.
- Under the hood: action explain, answered by a card {kind: explain}.
- Code: `cards/index.tsx`, `cards/Clamp.tsx`
- Stage: `&scenario=lesson-panel&panel=working, click Explain`
- Screens: `screens/explain.webp`

**25. Ask about this step**  
- ⌥Space during a lesson opens Ask about this step.
- Continue goes back to the lesson. "Try asking" offers questions about this step.
- End lesson is a quiet link in the footer, two taps, no key reaches it.
- Under the hood: action ask {text}; the answer comes back as a card. Push to talk (hold fn ⌃) asks the same way, with speech turned into text on the Mac.
- Code: `launcher/Launcher.tsx`, `launcher/questions.ts`
- Stage: `&scenario=lesson-panel&panel=working, Ctrl+K`
- Screens: `screens/ask.webp`

**26. Step done**  
- A green check, "Step done." and what it proved: "Both sets now top out at 1.0".
- Up next with the next step's title. Next step.
- Under the hood: step.passed, then the engine starts the next step.
- Code: `drawer/v2/states.tsx`
- Stage: `&scenario=lesson-panel&panel=passed`
- Screens: `screens/panel-passed.webp`

**27. Mini**  
- Esc or the collapse arrow folds the panel into the pill.
- The editor gets the whole screen back. Click the pill to open the panel again.
- Under the hood: Renderer only. The lesson keeps running and checks keep coming.
- Code: `drawer/v2/LessonPanel.tsx`, `pill/index.tsx`
- Stage: `&scenario=lesson-panel&panel=mini`
- Screens: `screens/mini.webp`

### A video lesson

A YouTube tutorial turned into steps. The video waits at the end of each step until your checks pass.

**28. Video lesson layout**  
- Left: the steps drawer. Every step with its video time, the current one with its checks (Watching, Passed), and the sources.
- Right: the player. "Waiting for your checks" with Check my work, Replay, Skip step, and the chapters.
- Bottom: the shortcut bar. ask miyagi, Back, Explain, Diagram, Show me, Hint, Check my work, Skip step, End lesson.
- The spotlight dims the screen around the code you need.
- Under the hood: step.started carries the video segment. The player pauses at its end until step.passed, then plays on. spotlight {rect} comes from the engine reading the screen.
- Noticed: Drawer, player, bar and spotlight are all up at once here.
- Code: `drawer/Drawer.tsx`, `player/Player.tsx`, `shortcut-bar/ShortcutBar.tsx`, `spotlight/Spotlight.tsx`
- Stage: `&scenario=full, Ctrl+K, a topic, Enter, Enter`
- Screens: `screens/video.webp`

**29. Hover the pill**  
- Point at the pill and it opens into the step card: thumbnail, "Step 5 of 7", the title, live checks.
- It folds back when the pointer leaves.
- Under the hood: Renderer only, from the lesson state it already has.
- Code: `overview/index.tsx`
- Stage: `&scenario=full video lesson, point at the pill`
- Screens: `screens/hover.webp`

**30. Diagram**  
- Diagram opens a flyout from the drawer's edge: here the network, with a one-line caption.
- Network and gradient diagrams draw from your real runs.
- Under the hood: action diagram, answered by diagram {kind, data, caption}. The app only draws what the engine sends.
- Code: `drawer/Flyout.tsx`, `diagrams/*`
- Stage: `&scenario=full video lesson, click Diagram`
- Screens: `screens/diagram.webp`

**31. Off track**  
- "Not yet" with a white ring. The title says what happened: "Loss is flat at 0.25".
- A guiding question and where it comes from (a paper here).
- Right side: yours vs expected, the failing value, the curve.
- Explain, Show me, and at the last hint level, Do it for me.
- Under the hood: The engine waits before it says anything (a failed run, the same failure twice, or you being stuck, never while you type). Then Claude diagnoses it and sends offtrack plus a spotlight. Do it for me sends apply_fix, with undo.
- Code: `cards/index.tsx`, `cards/Evidence.tsx`, `cards/Curve.tsx`
- Stage: `&scenario=offtrack (wait about 10 s)`
- Screens: `screens/offtrack.webp`

### After a lesson

Quiet cards from the island. Never mid-lesson.

**32. Lesson complete**  
- The green check beside "Lesson complete", then the time taken, what you built and the result of your run (loss 0.82 → 0.0009).
- Every step checked and the skills you gained as plain checks, new ones marked. No mastered count.
- Next up, then Done or Start next lesson.
- Under the hood: One card from the engine with the skill map and result. No model call. History goes to ~/miyagi/state/history.json.
- Code: `complete/Panel.tsx`
- Stage: `&scenario=complete (wait about 9 s)`
- Screens: `screens/complete.webp`

**33. Review reminder**  
- Spaced review, with the bonsai and Esc: "Time to review Functions. 2 quick checks in your own code. Due today."
- Later, then Start review (or Open Progress when the engine cannot run reviews yet).
- Under the hood: Shows at launch with no lesson running.
- Noticed: The schedule is fixture data until a real scheduler exists.
- Code: `progress/ReviewReminder.tsx`
- Stage: `&scenario=full&review`
- Screens: `screens/review.webp`

**34. Update ready**  
- "A new miyagi is ready." What's new, Later, Download.
- Under the hood: main checks on launch and every 6 hours. Download opens the browser; nothing installs itself. Never during a lesson.
- Code: `updates/Card.tsx`
- Stage: `&scenario=updates&upd=available`
- Screens: `screens/update.webp`

### When something goes wrong

Every stall is said calmly from the island, with one way out.

**35. Engine stopped responding**  
- After 5 tries: "miyagi stopped responding. Your place in the lesson is saved."
- Restart miyagi, Copy details. The panel greys out until it is back.
- Under the hood: main keeps retrying the socket (every second for 30 s, then slower). The card is a UI threshold on top of that.
- Code: `errors/cards.tsx`, `errors/startup.ts`
- Stage: `&scenario=errors&err=engine-offline`
- Screens: `screens/err-offline.webp`

**36. Build failed**  
- "This video could not become a lesson" with the reason.
- Try transcript only, or start a library lesson instead.
- Under the hood: lesson.building ends in an error and the island shows this card.
- Noticed: The engine ignores "transcript only" today, so that button retries the same way.
- Code: `errors/cards.tsx`
- Stage: `&scenario=errors&err=build-failed`
- Screens: `screens/err-build.webp`

## Still open

- Lesson detail has no step-by-step preview yet.
- The Account page (plan, usage, Upgrade to Pro) is mock data. The live app has no account backend yet.
- Apple and GitHub sign-in are placeholders that say "coming soon".
- In a video lesson, the drawer, player, shortcut bar and spotlight are all on screen at once.
- Voice is switched off in code (VOICE_ENABLED = false). Push to talk is on, Mac only.
- Windows still has no engine and no VS Code companion install, so past setup it is UI only.

