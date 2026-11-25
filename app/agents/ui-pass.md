# UI pass: "What changed tonight" and the Rules, checked against the merged code

Lane `michael/app-ui-pass`, base `michael/v2-integration` (d40431a8). Offline only, no live calls, no windows opened.
Method: every screen in Adrian's UI-PACKAGE.md rendered on the browser stage (`dev:web`, port 5424) in dark and light, at
1440x900 and 1024x700, on Mac and Windows where the screen differs, compared with his screenshots. On top of eyeballing,
a headless-Brave script (CDP) audited every screen for text contrast (WCAG, against the real composited background),
horizontal overflow, and Mac words on the Windows stage (this Mac, macOS, Keychain, Finder, Terminal). Static greps covered
hex outside `core/theme.ts`/`styles.css`, "Cursor", `dangerouslySetInnerHTML`, em dashes in copy, hand-typed keycaps,
capitalised "Miyagi", and every use of green.

Clean on the static greps: no stray hex in UI code (the only literals are the diagram weight-sign colors, documented as
diagram-only, the spotlight mask fills, and the dev stage backdrop), no "Cursor" in copy, no `dangerouslySetInnerHTML`,
no em dash in any rendered string, no hand-typed keycap (all from `bridge.platform.keys`), no "Miyagi" in copy. No
horizontal overflow on any audited screen at 1024x700 (sidebar, Settings, Lessons, Home, onboarding all fit).

## Fixes

| # | Mismatch | Fix | Before | After |
|---|---|---|---|---|
| 1 | Light mode: `faint` text (captions, "Due today" dates, the Skills legend, "Builds on ...") was ink at 42%, 2.7:1 on white. | `c-faint` light .42 to .60, `c-label` light .62 to .68 so the two still step (`core/theme.ts`). Dark unchanged. Test: `test/lightContrast.test.ts`. | `shots/app-ui-pass-before-skills-light-1024.png` | `shots/app-ui-pass-after-skills-light-1024.png` |
| 2 | Light mode: the "Best" label on search results was the raw pink pastel on a pale row, 1.45:1, almost invisible. | Uses `tone.pink.fg` (the pastel in dark, a deep pink in light), same hue (`launcher/Rows.tsx`). | `shots/app-ui-pass-before-best-light.png` | `shots/app-ui-pass-after-best-light.png` |
| 3 | Light mode: green words ("Running", "Passed", "Mastered") used the fill green `#22A24B`, 3.3:1 as text. | New `color.greenText` (`c-green-text`: pass green on dark, `#187A37` on light). Used by the onboarding row words, the Skills rail and node tooltip. Green still only means passed. | `shots/app-ui-pass-before-running-light.png` | `shots/app-ui-pass-after-running-light.png` |
| 4 | Windows copy: the crash consent card listed "App and macOS version". | Says "App and Windows version" on Windows (`errors/cards.tsx`). | n/a (copy) | n/a |
| 5 | Windows copy: the "install command copied" notice said "Paste it in Terminal". | Uses `shellName()` from `onboarding/device.ts`, so PowerShell on Windows (`pill/index.tsx`). | n/a (copy) | n/a |
| 6 | 1024x700, video lesson: the player's time ("6:12 / 24:20") and "Checks at 9:48 · Check now" wrapped to two lines. | `whitespace-nowrap`; the check label clips instead of wrapping (`player/Player.tsx`). | `shots/app-ui-pass-before-video-1024.png` | `shots/app-ui-pass-after-video-1024.png` |

Also tidied: an unused `status` import in `dashboard/Rail.tsx`.

Sweep shots after the fixes (Home, Lessons, Skills, Progress, Settings, launcher, panel; dark and light; 1440x900 and
1024x700): `shots/app-ui-pass-sweep-<screen>-<size>-<appearance>.png`.

## Needs Adrian's call (not changed)

1. **Windows open and back keycaps.** `main/platform.ts` gives `Ctrl⇧Space` and `Alt←`; UI-PACKAGE.md's table says
   Ctrl+Shift+Space and Alt+←. His own `ready-win.webp` shows `Ctrl⇧Space`, and `drawer/v2/KeysRow.tsx` says the short
   form is for room. Pick one form; the file is core, so one-line change once decided.
2. **Dark `faint` is 42% white, 3.8 to 4.0:1** on the island cards and window (tour "1 of 5", "Today", "In 4 days",
   onboarding captions, Skills legend). It is his token (`c-faint`), AA wants about 50%. Not changed because it moves every
   dark caption.
3. **Locked skill labels** are dimmed to 55% (2.2:1 light, 2.8:1 dark, e.g. "Vectorized math"). Reads as disabled on
   purpose; confirm that is the look.
4. **Green for "Ready" / "Running".** The sidebar "Ready" check and the onboarding engine row ("Running") are green, but
   they are engine status, not a passed step. The rule says green only means passed. Gray ring and check, or keep?
5. **1024x700 with everything open** (video lesson plus drawer plus a diagram plus the player): the shortcut bar sits over
   the steps drawer, the diagram card and the player (`shots/app-ui-pass-after-video-1024.png`). Fine at 1440x900. This is
   the layout engine, not a small fix; is 1024x700 a supported size for the overlay, or only for the home window?
6. **1024x700 "Not yet" panel.** The Explain/Hint/Show me/Diagram/Watch options sit below the fold of the panel's own
   scroller (the Not yet card pushes them down), so Diagram and Watch are hidden until you scroll. Pin the options, or
   shorten the Not yet card at short heights?
7. **UI-PACKAGE.md is behind the code on the progress dots**: it says five (Mac) and three (Windows); with Michael's
   consent screen the strip is six and four. Doc only.
8. **Settings > General on the stage has no Push to talk rows** that his `settings-general.webp` shows (they come from the
   push-to-talk feature, not touched here). Check they appear in the real app.

## Checks

- `npm run typecheck`: pass.
- Every `test/*.test.ts` one at a time: 32 of 32 pass (new: `lightContrast.test.ts`).
- Dim/disabled states (the paused panel in "engine offline", the disabled "Setting up" button) read as low contrast in the
  audit by design (opacity); not treated as bugs.

## Unverified

- Electron itself (stage only, as instructed). Real macOS vibrancy, the notch geometry and Windows Segoe metrics differ.
- Animated states are checked only at rest (reduced motion): the island growth/return and the pill flash were not seen.
- States that need a live engine or a real mic/permission: PTT rows, real sign-in, real updates.
- Light-mode `faint` change is checked on the white panel and warm window by script and by eye on a few screens, not on
  every light screen.
