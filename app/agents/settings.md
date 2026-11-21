# settings

**Status:** v2 (A4) implemented on `michael/app-settings`, typecheck green, stage-verified (headless shots below); Electron unrun · **Priority:** P1 · **Port:** 5189 · **Branch:** `michael/app-settings` · **PR:** #164 (draft, into `adrian/shell`)

## v2 (A4, miyagi-v2 BUILD-PLAN)
Mockups: Set-General, Set-Permissions, Set-Privacy, Set-Account (BYOK), Set-Shortcuts, Plan-OwnKey.
Scenario: `npm run dev:web -- --port 5189` then `http://localhost:5189/?scenario=settings&settings=<general|permissions|privacy|account|shortcuts>&size=1440x900&clean`, plus `&perm=accessibility-off`, `&record=hint` (Shortcuts), `&confirm=delete` (Privacy). Ctrl+, opens it too.

**What it is now.** The same sheet, born from the island and collapsing back into it (morph, hand-over and reduced-motion crossfade untouched), now 912x576 clamped to the screen (`sheetSize`: 24 px sides, 24 px under it, never past the screen) with a sidebar: General, Permissions, Privacy, Your key, Shortcuts. It stays black (decision 9). The section pane scrolls inside the sheet.
- **General:** Appearance (Match system / Dark / Light, caption `copy.appearanceCaption`), Launch at login, Voice (`voiceOnStart`), Works with (VS Code and Jupyter from the engine's `health` rows; "Watching" with the dashed gray ring during a lesson; nothing when the engine says nothing), and **Set up miyagi** (`openOnboarding()`).
- **Permissions:** Screen Recording and Accessibility from `permissions:get`, live through `permissions:watch` only while the section is on show; the VS Code extension row only when `health` has a `companion` item (hidden without a probe). On = white tick (never green), Not yet = white ring with Turn on (`permissions:open(kind)`, no prompt), unknown = gray dashed ring "Not sure yet" with the Terminal note for an external engine. One primary: the first row that needs turning on; others are quiet. Caption counts ("Two of three are on.").
- **Privacy (honest subset):** Screenshots and code/text "Sent to the AI provider" during lessons; keys "On this Mac" (memory-only wording without secure storage). Sync and usage switches HIDDEN, "See what was sent" hidden (log deferred). Delete my data: outline Delete → in-place confirm "Delete everything on this Mac?" (Cancel quiet, Delete the one primary; Esc backs out) → main `settings:delete` erases keys.bin and sends an all-empty `config.keys`, then the renderer resets prefs to defaults → "Deleted from this Mac". It says only what it can reach.
- **Your key (Plan-OwnKey):** the key flow moved, not rewritten, into `account.ts` (`useKeyFlow`): `settings:get/save/test`, `{set,last4}` only, full `config.keys` from main, drafts cleared after Save and dropped with the sheet. Fields are `type=password`, autocomplete/spellcheck/autocorrect off. Save key is the primary, Test quiet, "Where do I find my key?" via `open:external` (console.anthropic.com is allowlisted). Keychain line only when `secure`. Plan card and meter never show (`v2Cloud=false`).
- **Shortcuts:** keycaps from `bridge.platform.keys` via core `Keycap` (⌃⌥ on a Mac), pastel chips only on Explain / Hint / Show me / Diagram, Watch absent (decision 3), Dismiss fixed. Recorder in the browser stage only (`env.canRecord`): click a row, press keys; validated by `isAccelerator`, a bare key or Shift alone is refused, a clash names the other shortcut; stored in `prefs.shortcuts` (whole map) and shown as words with "Not active yet"; Restore defaults clears them. Esc cancels the recording without closing the sheet. Electron rows are read-only ("Changing shortcuts comes in a later update.").
- **Opening:** `settings:open {section}` (core `openSettings(section)` or this feature's `open.ts`, which ignores a click event passed as the section). Already open: `settings:section` switches. `settings:about` gives the version for the sidebar foot (empty in the stage).

**Files:** `Settings.tsx` (morph + clamp), `Shell.tsx`, `Sidebar.tsx`, `ui.tsx`, `env.ts`, `account.ts`, `permissions.ts`, `shortcuts.ts`, `sections/{General,Permissions,Privacy,Account,Shortcuts}.tsx` (General moved from the feature root), edits to `store.ts`, `open.ts`, `web.ts`, `keys.ts` (labels, `SHOWN`, `SECTIONS`, `AboutView`, `DeleteResult`), `index.tsx`; `src/main/features/settings.ts`; `mock/scenarios/settings.json` (segment renamed `settings_first_run`, adds a `health` reply; no `health.get` trigger so `full` keeps A3/core-v2's).

**Checked in the stage (headless Chromium over CDP, real time):** each section renders; recorder refuses a bare J ("Add Control, Option or Command."), stores `Control+Alt+J` for Hint and shows "Not active yet"; Control+Alt+E is refused ("Explain already uses that."); Esc in the recorder cancels it and the sheet stays open; sidebar click switches section; Esc on the sheet collapses it; Delete → "Deleted from this Mac"; Save key clears the field, shows `•••• 1234`, nothing in localStorage. Typecheck green. Brand lint (hex, typed keycaps, Cursor, innerHTML, console.log, openExternal) clean on the package files.
**Not verified:** Electron (`settings:delete` unlinking keys.bin, `settings:about`, section switch while open, permissions polling against real TCC), the reviewer agent round.

**Fix round 1 (review):** Esc in the delete confirm is now a window capture-phase listener while `step === 'confirm'` (focus stays on the sidebar because the first Delete never takes it, so the old wrapper `onKeyDown` never fired and the sheet closed). `settings:delete` restores the old keys and skips `config.keys` when unlinking keys.bin fails, so "Couldn’t delete. Nothing was removed." stays true. Your key note now reads "Kept in your Mac’s Keychain, never on our servers." (keys do go to the local miyagi engine). Main header no longer claims a first-run auto-open. Typecheck green; not re-run in the stage or Electron.

**Shots:** `shots/settings-v2-general.png`, `-permissions.png` (`perm=accessibility-off`), `-privacy-confirm.png`, `-account.png`, `-account-saved.png`, `-shortcuts-record.png`.

**Deviations from the mockups (brand rules or plan):**
- Sheet top is the pill's top (it grows out of the pill), not 48 px under a separate pill; one close dot instead of three traffic lights (the other two would be dead).
- Pastels are BRAND.md's (sky `#C5E4F9`, pink, lilac), not the mockup's; keycaps are the platform's (⌃⌥E, ⌥Space), not ⌥E / ⌘K; Watch has no row (decision 3).
- Nav reads "Your key", the section "Use your own key": no account or plan this push (`v2Cloud`). One row per key (Anthropic, Gemini, Tiger Data URL) instead of Plan-OwnKey's provider select, because the key flow is moved, not rewritten. Save key and Test sit under the rows; no Cancel button (Esc and the close dot close the sheet).
- Privacy copy changed for honesty (screenshots are sent to the provider during lessons, not "Used only..."), sync/usage switches and the log row hidden, Delete erases keys and settings on this Mac only.
- General: the "Works with" VS Code row shows the engine's version (no lesson file name in the app state); Voice caption describes `voiceOnStart`.

### Core requests (v2)
1. **core/surfaces.ts:** nothing needed; `openSettings(section)` already sends `{section}` and is handled.
2. **Live shortcut rebinding (wave 2, main/index.ts):** read `prefs.shortcuts` and re-register globalShortcut; then Settings can drop "Not active yet" and enable the recorder in Electron (`env.canRecord`). The display should then read the applied accelerators (a `platform.keys` built from them).
3. **Engine `data.delete` (deferred):** when it exists, Delete should also ask the engine to erase progress and history; until then the copy says "keys and settings on this Mac".
4. **Privacy log (deferred):** "See what was sent" needs an engine log of help requests; hidden until then.
5. **prefs reset from main:** Delete resets prefs from the renderer with `setPrefs(DEFAULT_PREFS)`; a main-side `prefs.reset()` would make it atomic with the keys erase.
6. Not sent: the coordination email to Adrian (the lane is claimed by draft PR #164 only).

### Pass 2 (Sat Nov 14, Adrian: "basic settings with the other stuff like light mode / dark mode")
The sheet is now **Settings**: a **General** section above **Keys** (keys unchanged, ElevenLabs still hidden). Shots: `shots/settings-general-*.png`.
- **Appearance:** System / Light / Dark segmented control → `setPrefs({appearance})`; ←/→ move it. Verified in the stage: `<html data-appearance>` and the `--glass-*` variables switch live; the sheet stays black (`01` system on a dark Mac, `03` light, `02`/`04` the whole stage).
- **Read lessons aloud** → `voiceOnStart`, **Open at login** → `launchAtLogin` (switches; saved, `05`).
- These apply at once (core prefs, `userData/prefs.json`); only the keys wait for Save. Neutral chrome: selected segment / on switch = white + ink, the rest `fill.*`. No pastel, no green.
- **Never past the screen:** the content is capped at `layout.height − pillTop − 24`; past that only the key rows scroll under the "Keys" label, the footer stays (`06`, forced to 400 px).

**Not visible yet, and not in this lane:** the glass panels (shortcut bar, player, drawer) still paint `color.glass`, so switching appearance changes nothing behind the sheet in `02`/`04`. They need to move to `theme.glass.*`. Also nothing reads `voiceOnStart` yet (the voice feature should turn voice on at `lesson.ready` when it's set).

### Pass 1 (Sat Nov 14)
**Works in the stage** (`http://localhost:5183/?scenario=settings`, headless Chrome frames in `shots/settings-*.png`):
- First run: the scenario answers Anthropic + Gemini `missing`, so the sheet grows out of the idle pill by itself, caret in Anthropic (`01`). Ctrl+, (⌘,) reopens it; anyone else calls `openSettings()` from `features/settings/open.ts`.
- Grows from the island's exact shape (pill or card) and settles in ~210 ms (`06`). Esc, ✕, click outside (and in Electron, losing focus) collapse it onto the island's current size, the island's content fades back in, then `island:return` (`07`). The island is hidden while the sheet is open.
- Paste a key → masked dots, Save turns white (`02`). Save (↵) → `•••• last4`, white dot, Clear (`03`). Clear → "Cleared" + Undo, applied on Save (`04`). Test → spinner until `config.status` (`05`); nothing back in 3 s → "No answer from Miyagi" (`08`). No safeStorage → "Not saved: no secure storage" (`09`, stage: `&nosecure`).
- Status per key: white dot = your key, gray dot + "From engine" = the engine's .env, ring = missing, "Invalid" in white. Optional rows say "Optional" unless a status line replaces it. No green, no amber, no glow.
- Checked in the page: `settings:get` / `settings:save` return `{set, last4}` only (never the key); unknown names and non-strings in a patch are ignored; `config.keys` always carries all five names; localStorage / sessionStorage stay empty.

**Written, not run (Electron, Michael's Mac):** `src/main/features/settings.ts`. keys.bin via safeStorage (write-then-rename, removed when empty, never logged, not even a parse error), full `config.keys` on `engine.onOpen` and on Save/Test, full-display focusable window (like the launcher) raised over the overlay, blur → collapse, `settings:hidden` → hide + `returnFocus`, opens once per run on a `missing` required key.

**Left:** Electron check on the Mac (list below). `invalid` only shows once the engine produces it. A way to open Settings in Electron before the overview's gear lands (see Core requests 3).

## Goal
Bring-your-own-keys. A small settings sheet **born from the notch island** (like the launcher): a focusable window whose panel starts at the island's exact rect and collapses back into it. Four keys: **Anthropic** and **Gemini** (required), **ElevenLabs** (optional: voice), **Tiger Data URL** (optional). One status per key, a Test button, Save.

## Owns
- `app/src/renderer/src/features/settings/`: window route `settings`, the sheet, status dots
- `app/src/main/features/settings.ts`: the focusable window, safeStorage, sending `config.keys`
- `app/mock/scenarios/settings.json`

## How the keys flow (the integration, read carefully)
1. **Storage (main only).** Keys live in `userData/keys.bin`: `safeStorage.encryptString(JSON.stringify(keys))` (Keychain on Mac, DPAPI on Windows). If `safeStorage.isEncryptionAvailable()` is false, keep them in memory for this run only and show "Not saved: no secure storage". Never plain text, never logged, never in the repo, never in localStorage.
2. **Renderer never gets a key back.** `bridge.invoke('settings:get')` returns `{ [name]: { set: boolean; last4?: string } }` only. `bridge.invoke('settings:save', partial)` sends new values to main; main merges, encrypts, writes, then sends `config.keys`. An empty field means "unchanged"; a Clear button per key removes it.
3. **Always send ALL stored keys.** The engine's `server/config.py set_app_keys` drops every key that's missing from the payload, so a partial `config.keys` would clear the others. Send the full set every time.
4. **On every (re)connect:** `ctx.engine.onOpen(() => ctx.engine.send(cmd('config.keys', all)))`. While offline nothing is queued; onOpen re-sends.
5. **Status:** the engine answers `config.status` per key: `ok` (your key) · `env` (the engine's own .env: how the demo Mac runs) · `missing` · `invalid` (not produced yet: the engine checks presence only today). Read it from `useLesson(s => s.keyStatus)`.
6. **Test** = re-send `config.keys` and show the new `config.status` (spinner on the Test button until it arrives, 3 s timeout → "No answer from Miyagi").
7. **Opening:** main handles `ctx.handle('settings:open', …)`; anyone calls `bridge.invoke('settings:open')` (the overview's gear does). In the browser stage, `registerWebHandler('settings:open' | 'settings:get' | 'settings:save', …)` with in-memory storage. First run: open it once if Anthropic or Gemini is `missing` (not `env`).

## Born from the island
Core has the hand-over: `ctx.islandSize()` + `ctx.yieldIsland(true|false)` in main, or `bridge.emit('island:yield' | 'island:return')` from the renderer. Copy the launcher's grow/collapse (`features/launcher/Launcher.tsx`): start at the island rect (top = `platform.pillTop`, centered, `shadows.pill`), spring to the sheet (`shadows.card`), reverse on close. Esc closes. The window is focusable (typing) and must not steal focus when hidden.

## Adrian's spec (pass 1, from his feedback on the other features)
- Brand: `app/brand/BRAND.md`. Black island, white text, system font. No blue, no gradients, no glow.
- **Status dots are not green and not amber** (green = passed, amber = off track only): `ok` = white dot, `env` = gray dot + "From engine", `missing` = hollow ring, `invalid` = white text "Invalid". No glow.
- Minimal copy: a title "Keys", one label per row, no paragraphs. Optional rows say "Optional" in `color.faint`. Masked fields show `•••• last4`.
- Save is the one `PrimaryButton`; Test and Clear are neutral (`fill.button`).
- Tokens only (`core/theme.ts`), the one spring.

## Done when
- Keys encrypted, never echoed, sent in full on every connect and on Save / Test
- Status per key from `config.status`; Test works; first run opens it when required keys are missing
- Grows out of the island and collapses back into it

## Test
`npm run dev:web -- --port 5183` → `http://localhost:5183/?scenario=settings` (add `mock/scenarios/settings.json` that answers `config.keys` with a `config.status`; restart the dev server after adding it).

## Core requests
1. **bridge.ts (web): let a renderer read the island size.** The web bridge keeps `islandSize` private, so in the stage `web.ts` measures the island off the DOM (the `[data-hit]` child of the centered wrapper at `top: pillTop`). Ask: fire `ui:island:size` from the web `emit('island:size')` (or expose `bridge.islandSize()`). Electron is fine: main has `ctx.islandSize()`.
2. **mock/engine.ts: let a scenario say what unset keys answer.** `handle()` answers every `config.keys` itself with `env` for unset keys, so a scenario can't show `missing → ok`: after the first Save the stage flips the other rows to "From engine". Workaround: `settings.json` sends one `config.status` 400 ms after connect (Anthropic/Gemini missing, ElevenLabs invalid). Ask: e.g. a scenario field `"keys": {"unset": "missing"}` or an `on["config.keys"]` segment.
3. **Opening Settings without the gear.** No global ⌘, on purpose (it would steal VS Code's Settings shortcut). Until the overview's gear lands, Electron opens it only on first run. Options: a "Keys" chip in the launcher, or ⌘, while the launcher window has focus (the launcher's call).
4. **platform.ts `returnFocus` on the Mac calls `app.hide()`,** which hides every window, the player included; only the overlay is re-shown. Settings reuses it like the launcher does, so both share whatever the fix is.

## Notes
The overlay window is not focusable, so Settings is its own window. Every `ctx.createWindow` window already follows Spaces / full-screen apps; call `ctx.raise(win)` so it floats on top.

- **Files:** `keys.ts` (names, `{set,last4}` view, patch merge, full payload; imported by main too), `Settings.tsx` (the sheet), `General.tsx` (the General rows, segmented control, switch), `store.ts` (open/close requests, `config.status` counter), `web.ts` (stage stand-in, in-memory), `open.ts` (`openSettings()`).
- **Channels:** `settings:open | get | save | test | island | hidden` (invoke) and `settings:open {from} | settings:close` (broadcast). `test` and `island` are additions to the brief: the renderer has no keys to re-send and needs the island's size at close time.
- **last4** only for values ≥ 12 characters, so a short secret never shows a third of itself. Values are trimmed; over 4096 characters is ignored as a paste accident.
- **Unsaved typing is dropped on close** (Esc, ✕, click outside, blur). The window covers the display, so it can't stay open while you're in another app.
- **Stage:** the sheet is a stage window at z 20 (above the launcher). In `full`, the engine's .env answers (`env` everywhere), so first run doesn't open.
- **Mac checklist:** first-run open takes focus (or at least a click into a field works); Keychain prompt on first save, if any; keys.bin survives a restart and the dots come back white; blur closes it; focus returns to the editor; the sheet sits on the pill's exact pixels (pillTop 40).
- **Shots script** (headless Chrome over CDP, screencast frame strips): `side-session-notes/…/settings-shots-cdp.mjs`.

## Round 3 (surfaces lane, michael/app-surfaces-feel)

**Landed**
- Chrome: the three window lights like every other miyagi window (close live, ✕ on hover/focus, minimize/zoom drawn inactive) and the app window surface (`surface.window` + hairline) fading in over the island's black as the sheet grows (and out as it lands back on the pill). Neutral focus rings (no browser blue).
- Sections: a vertical tablist. ↑ / ↓ / Home / End switch sections; the highlight slides on the house spring (`layoutId`); focus starts on the active section; Tab wraps inside the sheet (`aria-modal`). Section content crossfades (opacity only with reduced motion).
- Your own key: one name everywhere (`words.ts` `OWN_KEY`), copy that matches this build (no "our cloud covers it"), status in words under each provider ("Works", "Saved", "Using miyagi's key", "Not set", "Not yet. Check the key.") instead of bare dots, Test disabled until a key is stored, "Saved to Keychain" after Save, the key help is an underlined link with the external glyph.
- Privacy: values are plain secondary text. Delete confirm: Cancel is the focused white primary (Esc keycap), Delete is an outline.
- Permissions: names and captions from `words.ts` ("VS Code companion"); the footnote shows only while a row is off and its button is on screen.
- Shortcuts: read-only until live rebinding ships (`env.canRecord = false`): "Shortcuts work while miyagi is open, in any app."

**Stage:** `?scenario=settings&settings=<section>&size=1440x900&clean` (+ `&perm=accessibility-off`, `&confirm=delete`). Shots: `/Users/tripi/sand hacks/miyagi-v2/screens/round3/surfaces-settings-*.jpg`.

**Core requests (round 3)**
1. `core/ui/controls` SidebarNav: adopt the tablist + sliding highlight from `Sidebar.tsx` so every sidebar behaves the same.
2. Status rule for the onboarding lane: granted / running is a neutral check + white word everywhere (Settings already); green stays for passed steps and mastery. Onboarding's green "On / Running / Connected" should follow.
3. Glossary for every lane (`features/settings/words.ts`): "Your own key" (account menu, upgrade, pricing say "Use your own key", "Use my own key", "Bring your own key"), "VS Code companion".
4. `copy.appearanceCaption` (core) still says the sheet stays black; it now takes the window surface.

**Fix round 1 (surfaces)**
- Focus rings use the theme: `color.label` through a `--focus-ring` CSS variable on the sheet, which the sidebar tabs read too. No Tailwind `white/*`; the sheet's text is `color.text`, not `text-white` (same for the key field and the help link hover).
- Your own key: the caret lands in the key field again when the sheet opens on this section (`openSettings('account')` from the limit card's "Your own key") or on a click. The store records how a section was reached (`via: 'keys'` from ↑ / ↓ / Home / End); only then does focus stay on the sidebar.

**Decision for Michael: the sheet covers VS Code's Explorer and tabs**
At 1440x900 the 912x576 sheet sits at x 264-1175, y 40-615, over the Explorer and the editor tabs, which the UX bar otherwise forbids ("never cover Explorer/tabs/toolbar"). This lane keeps it as an explicit exception:
- Settings is a modal sheet the learner opened on purpose, with a scrim. Nothing in VS Code is needed while it is up, and Esc, the close light or a click outside collapses it into the island at once.
- "Every surface is born from the notch island" (Michael, Sat): it starts on the pill's exact pixels at the top center, and a sheet this big can't clear the Explorer and tabs from there without leaving the island.
- Clamping it to the editor's free area (right of the Explorer, under the tabs) would still cover code at 1440x900 and would detach it from the island.
If Michael wants it clear anyway, the cheapest option is a compact sheet (about 720x520) moved down under the tab bar, keeping the island neck. That needs Core request 5.

**Core requests (fix round 1)**
5. Only if Michael rejects the exception above: expose the editor's chrome rect (Explorer width, tab bar and toolbar bottom) from core/dock or the layout, so the sheet can be placed clear of it.

**Fix round 2 (surfaces)**
- One focus ring on the sidebar tabs: the tab's own `ring-1` is gone, so only the sheet's outline (`--focus-ring`) draws, and it waits for the first key press (a mouse open shows only the active row's fill). The active tab still takes focus on open, so ↑ / ↓ work at once. Shot: `surfaces-set-general-kbd.jpg`.
- Your own key: while Test is off the footer says why ("Save a key to test it.", beside "Where do I find my key?"); the tooltip moved to a wrapper, since a disabled button never shows its own. Shot: `surfaces-set-account-test.jpg`.
