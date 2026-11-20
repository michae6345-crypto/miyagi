# miyagi in the Microsoft Store

Why: the direct download (`Miyagi-Windows-Setup.exe`) is unsigned, so Chrome and Edge hold it as possibly dangerous and Smart App Control can block it outright. A Store install has neither problem: the Store signs the package after certification. Registration is free for individual developers.

## What's ready (branch `adrian/windows-store`)

- `electron-builder.yml` → `appx:` builds `dist/Miyagi-Store.appx` (MSIX/AppX, x64, full-trust desktop app). It is unsigned on purpose; the Store signs it.
- `build/appx/`: Start menu, taskbar and Store tiles, made from the brand's tree by `scripts/make-store-tiles.py` (right cut per size, as in `brand/BRAND.md`). Re-run the script when the logo changes.
- "Open at login" is hidden in the Store build (`platform.ts` → `loginItem`), because Windows ignores a packaged app's Run-key entry. A Store version of it would need a `windows.startupTask` extension; not done yet.
- The direct download is unchanged: the sync agent builds `--win nsis` only.

## Build

```bash
cd app
npm ci && npm run build
npx electron-builder --win appx --x64 --publish never      # -> dist/Miyagi-Store.appx (~170 MB)
```

If makeappx fails with "side-by-side configuration is incorrect" (it did inside Claude's command sandbox, not in a normal shell), copy the folder it names to a folder you choose and set `ELECTRON_BUILDER_WINDOWS_KITS_PATH` to that folder. `-c.toolsets.winCodeSign=1.1.0` switches to the newer Windows Kits 10.0.26100 tools (electron-builder calls them beta).

## Partner Center, step by step (Adrian)

1. **Sign up** at developer.microsoft.com/microsoft-store/register as an **individual** (free; ID and selfie check).
2. **Apps and games → New product → MSIX or PWA app**, and reserve the name (`miyagi` if it's free).
3. **Product identity** page: copy the three values into the ★ lines of `electron-builder.yml`:
   `Package/Identity/Name` → `identityName`, `Package/Identity/Publisher` → `publisher`, `Package/Properties/PublisherDisplayName` → `publisherDisplayName`. Set `displayName` to the exact reserved name. Rebuild.
4. **Packages**: upload `dist/Miyagi-Store.appx`. The version must go up with every submission (`package.json` `version`, so 0.1.0 → 0.1.1).
5. **Properties**: category Education. A **privacy policy URL** is required (the app reads the screen and stores API keys): it needs a page, e.g. miyagi.study/privacy.
6. **Age ratings**: the questionnaire (a learning tool, no user-to-user content).
7. **Store listing**: short description, at least one screenshot (1366×768 or larger), the logos.
8. **Submission options**: it asks why the app needs `runFullTrust`: "Desktop (Electron) app packaged as MSIX; it needs full trust to show an always-on-top overlay, register global shortcuts and read the screen to check lesson steps."
9. **Pricing and availability**: Free. For the first submission choose a **private audience** (only listed Microsoft accounts can install it). That way you can test the Store-signed build before anyone else sees it, then switch to public.
10. Submit. Certification usually takes a few business days.

## Before it can pass review

- **The app needs an engine, and Windows has none.** The engine's screen reader is macOS-only (`server/`, Michael's), and the Windows build doesn't bundle or start one (`localEngine.ts` is Mac-only). Without an engine the pill says Offline and nothing can be checked, and Store review checks that the app works. One of these has to land first: a Windows engine (Michael), a hosted engine the app can reach, or a built-in demo lesson the app runs when no engine is found (`app/`, Adrian's call).
- Privacy policy page (step 5).

## Testing the package locally

Windows refuses to install it unsigned ("an unsigned package cannot include Executable activations", tried Nov 20). Use one of these:
- the Store's private audience (step 9): the real signed build, no local setup;
- Developer Mode on (Settings → System → For developers), unzip `dist/Miyagi-Store.appx` into a folder (it's a zip), then `Add-AppxPackage -Register <that folder>\AppxManifest.xml`;
- a self-signed test certificate in Trusted People, with `publisher` set to its subject.
