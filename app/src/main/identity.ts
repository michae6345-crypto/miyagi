/**
 * Core: who the app says it is (lane realapp, app/agents/real-app.md). miyagi runs as its own app, never "Electron".
 *
 * The built app gets its name from the bundle (electron-builder.yml productName + CFBundleName/CFBundleDisplayName:
 * the menu bar, Dock, ⌘Tab, Activity Monitor and the macOS permission prompts all read those). This module covers
 * what the bundle can't:
 *   - app.name 'miyagi' before ready, so the app menu says "Hide miyagi" / "Quit miyagi" and userData is
 *     ~/Library/Application Support/miyagi in dev too (package.json productName says the same; this is the backstop).
 *   - The About panel (app menu › About miyagi): name, app version, and which engine build is inside the app.
 *   - `npm run dev` only: the Dock shows the bonsai instead of Electron's atom while an app window is open (the name
 *     there stays "Electron": it comes from Electron.app's own bundle, which only a built app replaces).
 */
import { app } from 'electron'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

export const APP_NAME = 'miyagi'

app.setName(APP_NAME)

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
