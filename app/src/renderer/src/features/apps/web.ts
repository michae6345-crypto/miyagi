/**
 * Feature: apps, browser stage only: stands in for main's apps:installed (main/features/apps.ts).
 *
 *   ?apps=mixed (default)  VS Code and Blender on this Mac, FreeCAD and Fusion not
 *   ?apps=all | none       every app installed, or none
 *   ?apps=unknown          main can't tell (Windows): the default list falls back to the learner's lessons
 */
import { isElectron, registerWebHandler } from '../../bridge'

const STAGE: Record<string, Record<string, boolean>> = {
  mixed: { vscode: true, blender: true, freecad: false, fusion: false },
  all: { vscode: true, blender: true, freecad: true, fusion: true },
  none: { vscode: false, blender: false, freecad: false, fusion: false },
  unknown: {}
}

if (!isElectron) {
  const pick = new URLSearchParams(location.search).get('apps') ?? 'mixed'
  registerWebHandler('apps:installed', () => STAGE[pick] ?? STAGE.mixed)
}
