/**
 * Core: who the app says it is (lane realapp, app/agents/real-app.md). miyagi runs as its own app, never "Electron".
 *
 * The built app gets its name from the bundle (electron-builder.yml productName + CFBundleName/CFBundleDisplayName:
 * the menu bar, Dock, ⌘Tab, Activity Monitor and the macOS permission prompts all read those). This module covers
 * what the bundle can't:
 *   - app.name 'miyagi' before ready, so the app menu says "Hide miyagi" / "Quit miyagi" (package.json productName
 *     says the same; this is the backstop).
 *   - Its own settings folder per build (lane engine-isolation, app/agents/engine-isolation.md), set before ready:
 *     the installed app keeps ~/Library/Application Support/miyagi; `npm run dev` (not packaged) uses
 *     ~/Library/Application Support/miyagi-dev, so a dev app never reads or writes the installed app's prefs.json,
 *     onboarding.json, auth.bin, login.json, engine.json or crash marker (and the reverse). MIYAGI_USER_DATA, when
 *     set, wins in either build (a test or a second copy). Nothing on disk is moved or deleted here.
 *   - The About panel (tray / pill menu > About miyagi): name, app version, and which engine build is inside the app.
 *     The application menu (overlay-raise.ts) has only Hide / Quit, no About. The tray item lives in
 *     features/launch.ts (launch-ease lane) and is a Core request in app/agents/real-app.md until that lane adds it.
 *   - `npm run dev` only: the Dock shows the bonsai instead of Electron's atom while an app window is open (the name
 *     there stays "Electron": it comes from Electron.app's own bundle, which only a built app replaces).
 */
import { app } from 'electron'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

export const APP_NAME = 'miyagi'
/** The `npm run dev` settings folder, next to the installed app's under appData. */
export const DEV_USER_DATA = 'miyagi-dev'

/**
 * Pure: the userData folder this build should use, or undefined to keep Electron's default (appData/miyagi, from the
 * name). An explicit override wins; a built app keeps the default; `npm run dev` gets appData/miyagi-dev.
 */
export function userDataPath(o: { packaged: boolean; appData: string; override?: string }): string | undefined {
  const own = o.override?.trim()
  if (own) return own
  return o.packaged ? undefined : join(o.appData, DEV_USER_DATA)
}

/** Point userData at this build's own folder. Must run before ready (and before anything reads userData). → the path set */
export function isolateUserData(a: Pick<typeof app, 'isPackaged' | 'getPath' | 'setPath'> = app, env: NodeJS.ProcessEnv = process.env): string | undefined {
  const path = userDataPath({ packaged: a.isPackaged, appData: a.getPath('appData'), override: env.MIYAGI_USER_DATA })
  if (path) a.setPath('userData', path)
  return path
}

app.setName(APP_NAME)
// After setName: setName moves the default userData to appData/miyagi, this moves a dev build off it.
isolateUserData()

/** The engine commit inside a built app (Resources/engine/VERSION is `<ref>@<sha>`), as a short sha. */
function bundledEngine(): string | undefined {
  try {
    const v = readFileSync(join(process.resourcesPath, 'engine', 'VERSION'), 'utf8').trim()
    const sha = v.split('@').pop()?.trim()
    return sha ? sha.slice(0, 7) : undefined
  } catch {
    return undefined
  }
}

/** Call once app is ready (index.ts). Never throws: a missing icon or About option is no reason to stop the app. */
export function setupIdentity(): void {
  try {
    const engine = app.isPackaged ? bundledEngine() : undefined
    app.setAboutPanelOptions({
      applicationName: APP_NAME,
      applicationVersion: app.getVersion(),
      ...(engine ? { version: `engine ${engine}` } : {}),
      copyright: `© ${new Date().getFullYear()} miyagi`,
      credits: 'Learn anything, one step at a time.'
    })
  } catch {
    // About panel options are cosmetic.
  }
  if (process.platform === 'darwin' && !app.isPackaged) {
    const icon = join(app.getAppPath(), 'build', 'icon.png')
    try {
      if (existsSync(icon)) app.dock?.setIcon(icon)
    } catch {
      // Dev nicety only.
    }
  }
}
