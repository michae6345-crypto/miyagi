# Miyagi on Windows

Same app as on the Mac: one codebase, every OS difference in `src/main/platform.ts` (keys, pill position, window flags). Branch `adrian/windows` = `adrian/shell` + the Windows packaging; a sync agent merges `adrian/shell` in every ~20 minutes, fixes anything that would break on Windows, rebuilds the installer and republishes it.

## Build the installer

```bash
npm ci
npm run build && npx electron-builder --win nsis --x64 --publish never
# -> dist/Miyagi-Windows-Setup.exe (one-click, per-user, no admin prompt)
```

## Where it's published

- Release `windows` in the public repo `adrian-erlikhman/miyagi`, asset `Miyagi-Windows-Setup.exe`.
- miyagi.study links straight to it: `https://github.com/adrian-erlikhman/miyagi/releases/download/windows/Miyagi-Windows-Setup.exe`.
- The Mac zip comes from CI (`mac-zip` artifact from the nightly `ci` run, or a manual one) and goes to release `mac` the same way.

## Differences from the Mac, on purpose

| | Mac | Windows |
|---|---|---|
| Launcher | ⌥Space | Ctrl+Shift+Space (Alt+Space is the system menu) |
| Actions | ⌥E ⌥D ⌥S ⌥H ⌥V ⌥← | Alt+E Alt+D Alt+S Alt+H Alt+V Alt+← |
| Quit | ⌥Q | Alt+Q |
| Pill | under the notch (top 40) | top center (top 8) |
| Window | `panel`, every Space | always on top (`screen-saver` level) |
| Second launch | macOS focuses the running app | the installed app keeps one instance (`src/main/features/windows.ts`) |

## Known limits

- Unsigned: SmartScreen asks once (More info > Run anyway). PCs with Smart App Control on can block it outright; only code signing fixes that.
- Checked on Adrian's laptop (Sat Nov 14, packaged build, `DEMO=1`): the pill shows Ctrl⇧Space, Ctrl+Shift+Space opens the launcher, Esc closes it, a second launch exits. Smart App Control let the first two builds run and blocked the third (Code Integrity event 3118), so the sync agent's smoke test skips a blocked build instead of failing it.
- The app talks to the engine at `ENGINE_URL` (default `ws://localhost:8787`), same as the Mac. Without an engine the pill says Offline. The engine's screen reader is macOS-only for now (Michael's `server/`).
