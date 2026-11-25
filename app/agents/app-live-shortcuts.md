# app-live-shortcuts (Nov 24)

Custom shortcuts are live. Branch `michael/app-live-shortcuts`, from `michael/app-ui-v4`.

## What changed
- **One source of truth.** The key in effect per shortcut is `prefs.shortcuts[kind] ?? platform.accelerators[kind]` (`src/common/shortcuts.ts` `effectiveAccelerators`).
- **Main applies it.** `src/main/shortcutKeys.ts` holds a pure `rebind(current, want, ops, press)`: it unregisters the keys that changed, registers the new ones, and puts the old key back for any that fail. `createShortcutKeys` wraps it:
  - `sync()` runs at startup (after prefs load), on lesson start and end, on gate changes and on every prefs change.
  - `accept(next, prev)` checks a shortcuts patch before it is saved, through `main/prefs.ts setShortcutCheck`. A clash (another shortcut, or the quit key) or a taken key (`globalShortcut.register` returns false, for example ⌘Space) is refused. The previous key stays registered, and the saved prefs keep the old override.
  - Keys that are not live right now are tried once and released, so a taken key is caught at once.
- **Rules kept.** In `index.ts`, `shortcutLive(kind)` decides what may register: nothing while the login gate is shut, the launcher only between the gate's on and off, lesson keys only from lesson.ready to lesson.ended, and voice never while `VOICE_ENABLED` is false. The quit key uses `quitAccelerator`.
- **Gate check.** `main/loginFirst.check.ts` now requires these:
  - `globalShortcut.register` is called only from the `createShortcutKeys({...})` ops, or for the quit key.
  - The controller takes `live: shortcutLive`.
  - `shortcutLive` starts with `if (!gateIsOpen()) return false`.
  - `launcherWanted` is set only inside `gateCore({...})`.

  The check was already failing on `hideLauncher`'s `overlay.showInactive()`. That call is now gated too.
- **Labels follow the key.**
  - `acceleratorLabel` builds a keycap in the platform's glyph style: `Control+Alt+J` shows as ⌃⌥J on a Mac and Alt+J on Windows.
  - `core/keys.ts` adds `useKey(kind)`, `useKeys()`, `liveKeyLabel()` and `useAccelerators()`. `bridge.platform.keys` stays the default. Settings, dismiss and ptt keep their fixed labels.
  - `Keycap` and `keyLabel` read the live label, so every `<Keycap k=…>` follows it.
  - Call sites that read `bridge.platform.keys` directly now use the hooks: pill, overview, notch-home, shell sidebar, stage menu, cards, drawer VideoHelp, KeysRow, Help, tour layer, settings v4 KeyCaps and the dev HUD.
  - The tray menu shows the rebound launcher key.
- **Settings > Shortcuts.**
  - The recorder is on (`env.canRecord = true`) and "Not active yet" is gone.
  - A rebound row has a per-row **Reset**. A **Reset all** text button shows while any override exists.
  - The clash check covers defaults, overrides and quit. Voice's unused key stays free while voice is off.
  - Main's refusal shows as "Another app uses that key." `core/prefs savePrefs` waits for main's answer.
  - Esc cancels recording.

## Files
- New: `src/common/shortcuts.ts`, `src/main/shortcutKeys.ts`, `src/renderer/src/core/keys.ts`, `test/liveShortcuts.test.ts`.
- Changed in main and common: `src/main/index.ts`, `src/main/prefs.ts`, `src/main/loginFirst.check.ts`, `src/main/features/launch.ts`, `src/common/prefs.ts`.
- Changed in the renderer: `core/prefs.ts`, `core/ui/Keycap.tsx`, `features/settings/{env.ts,shortcuts.ts,sections/Shortcuts.tsx}` and the label call sites listed above.

## Verified
- `npm run typecheck`: green.
- Full node suite plus `test/liveShortcuts.test.ts`: 1135 tests pass, 0 fail (after the fix pass below, merged with `michael/app-ui-v4`; the first pass ran 1113, not 1123). The new file tests:
  - accelerator to label, the effective map and the clash check
  - rebind: a taken key restores the old one, two shortcuts can trade keys
  - the controller: gate, lesson and voice rules; a live swap; a refused key not saved; probing a key that is not live; reset
  - `sanitizePrefs` and the prefs check hook
  - that `loginFirst.check.ts` passes
- Headless stage shots, light and dark, taken with Playwright (`~/miyagi/tools/playwright/live-shortcuts-shots.mjs`):
  - `shots/shortcuts-override-{light,dark}.png`: Explain rebound to ⌃⌥J, with Reset and Reset all.
  - `shots/shortcuts-recording-{light,dark}.png`: recording Hint, ⌃⌥D pressed, "Diagram already uses that."
- Not checked in Electron on the Mac. The auto-install loop picks this up once it is merged. To try it there:
  1. Rebind a key, start a lesson and press the new key.
  2. Try ⌘Space for the launcher. Expect "Another app uses that key." and ⌥Space still working.

## Fix pass (fix-live-shortcuts-1)
- **Reset can't put two shortcuts on one key.** `accept()` clash-checks every changed kind's key in effect, so a reset is checked on its default. Example: Explain to ⌃⌥J, Hint to ⌃⌥E, then Reset on Explain. Main now refuses it, with or without a lesson.
- **Settings Reset checks first.** `Shortcuts.tsx reset()` runs `conflictWith` on the default and reads main's answer. A refusal shows on that row ("Hint already uses that." or "Another app uses that key.").
- **Shift alone is refused.** `isAccelerator('Shift+E')` is false, so a hand-edited prefs.json or a `prefs:set` patch can't take capital E from every app.
- **The option pill keeps its size** while the problem line shows (`items-start` on the label column). The four `shots/shortcuts-*.png` were retaken headless.
- Gap 5 (startup fallback) is closed. See the next section.

## Startup fallback (app-shortcut-fallback, Nov 24)
Branch `michael/app-shortcut-fallback`, from `michael/app-ui-v4`. Closes gap 5: a saved override that another app owns when main registers it used to stay unbound while its keycap still showed the override.
- **Fallback in main.** `rebind(current, want, ops, press, fallback)` takes a fallback key per kind. A key that fails gets its old key back first (a live swap), else the fallback.
  - `createShortcutKeys` passes the platform default as the fallback for each live override.
  - The default is skipped when another shortcut (or quit) uses it, so two shortcuts never share a key.
  - This covers every registration: startup, a lesson starting (action keys) and the gate opening (launcher).
- **The learner's choice stays.** The override is never removed from prefs. Every later `sync()` tries it again, so it works once the other app frees it, on this run or a later start.
- **Main state and broadcast.** The controller records each kind whose override would not register: `'default'` (the default is bound) or `'none'` (no key).
  - `.taken()` reads it, and `onTaken` fires on every change.
  - `index.ts` broadcasts it as `feat:shortcuts:taken` and answers `bridge.invoke('shortcuts:taken')` for windows that open later.
  - A kind not registered now (lesson over) keeps what was last learned until its override changes.
- **Labels show the key really bound.** `effectiveLabel(k, platform, overrides, fallbacks)` gives the default's label, or none for `'none'`. `core/keys.ts` adds the `useTaken` store, and `useKey`, `useKeys` and `liveKeyLabel` follow it. In the browser stage, `?taken=explain` or `?taken=explain:none` fakes it.
- **Settings row.** A taken row reads "Another app uses that key. Using ⌃⌥E." or "Another app uses that key." when no key is bound. Reset stays, and a Reset clears the state.
- **Tests:** `test/shortcutFallback.test.ts` (16 tests):
  - rebind with a fallback: startup falls back, both taken, the old key comes first, never steals a held key
  - the controller: startup launcher, a lesson starting and ending, both taken, a default another shortcut uses, the override coming back when freed, a free later start, Reset, a new key on a taken row, a new key on a row not live
  - the label: `effectiveLabel`, `sanitizeFallbacks`, and `core/keys` following main's broadcast with a fake bridge, plus `takenLine`
- **Verified.** `npm run typecheck` is green. The full node suite passes: 1151 tests, 0 fail.
- **Headless stage shots** (`shots/shortcuts-taken-{light,dark}.png`): the launcher has no key and Explain falls back to ⌃⌥E, both with Reset.
- Not checked in Electron on the Mac. To try it there: save a launcher key, have another app take it, then restart miyagi. Expect ⌥Space to work and the row to say so.
