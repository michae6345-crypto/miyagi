/**
 * Main-process side of the sidebar's Apps (renderer: src/renderer/src/features/apps/). Is an app miyagi teaches in on
 * this Mac?
 *
 * Handles (bridge.invoke from any window):
 *   apps:installed  → { [appId]: boolean } for the apps in APP_BUNDLES, or {} where it can't tell (not macOS)
 *
 * Read only: one existsSync per bundle path, in /Applications and ~/Applications. No subprocess, no Spotlight, no
 * network, nothing opened. The bundle names are a fixed list here; nothing from a renderer becomes a path.
 */
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { defineMainFeature } from '../context'

/** The app bundles that mean "installed", per app id (the plans catalog's tool ids). Any one of them counts. */
export const APP_BUNDLES: Readonly<Record<string, readonly string[]>> = {
  vscode: ['Visual Studio Code.app'],
  blender: ['Blender.app'],
  freecad: ['FreeCAD.app'],
  fusion: ['Autodesk Fusion.app', 'Autodesk Fusion 360.app']
}

export type InstalledDeps = { platform: string; home: string; exists: (p: string) => boolean }

/** Which apps are on this Mac (pure, for tests): {} off macOS, where the bundles mean nothing. */
export function installedApps(deps: InstalledDeps): Record<string, boolean> {
  if (deps.platform !== 'darwin') return {}
  const roots = ['/Applications', join(deps.home, 'Applications')]
  const out: Record<string, boolean> = {}
  for (const [id, bundles] of Object.entries(APP_BUNDLES)) out[id] = roots.some((r) => bundles.some((b) => deps.exists(join(r, b))))
  return out
}

export default defineMainFeature({
  id: 'apps',
  setup(ctx) {
    ctx.handle('apps:installed', () => installedApps({ platform: process.platform, home: homedir(), exists: existsSync }))
  }
})
