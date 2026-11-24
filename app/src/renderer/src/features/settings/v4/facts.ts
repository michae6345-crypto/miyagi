/**
 * Feature: settings, v4 page (Nov 24). The pure half of data.ts (no bridge, so tests import it): the Apps list, the
 * words under each app, the cache size, and the Delete account ask.
 *
 * `APPS` is a LOCAL TYPED PLACEHOLDER until the ui-v4 contract (shared/contracts/UI-V4.md, plans catalog) lands: the
 * apps a plan can use, how miyagi reads each, and how many catalog plans use it (counted from docs/ui-next/catalog on
 * origin/adrian/ui-next, Nov 24). Engine health (vscode, jupyter, any other id it reports) overrides the placeholder
 * status in the panel; only an ok health item says Connected (no item: "Reads exactly" or "Screen only").
 */

export type AppGroup = 'Code' | 'Sheets and design' | '3D and CAD' | 'Games' | 'Everything else'
/** connected: read exactly through an add-on or the editor; connect: an add-on exists but is not set up; screen: miyagi looks at the window. */
export type AppHow = 'connected' | 'connect' | 'screen'
export type AppRow = { id: string; name: string; group: AppGroup; reads?: string; how: AppHow; plans?: number }

export const APP_GROUPS: readonly AppGroup[] = ['Code', 'Sheets and design', '3D and CAD', 'Games', 'Everything else']

export const APPS: readonly AppRow[] = [
  { id: 'vscode', name: 'VS Code', group: 'Code', reads: 'Reads your files and the terminal.', how: 'connected', plans: 14 },
  { id: 'jupyter', name: 'Jupyter', group: 'Code', reads: 'Reads each cell and what it printed.', how: 'connected', plans: 7 },
  { id: 'terminal', name: 'Terminal', group: 'Code', reads: 'Reads commands and their output.', how: 'connected', plans: 2 },
  { id: 'xcode', name: 'Xcode', group: 'Code', how: 'screen', plans: 2 },
  { id: 'excel', name: 'Excel', group: 'Sheets and design', how: 'screen', plans: 1 },
  { id: 'sheets', name: 'Google Sheets', group: 'Sheets and design', how: 'screen', plans: 1 },
  { id: 'figma', name: 'Figma', group: 'Sheets and design', how: 'screen', plans: 1 },
  { id: 'blender', name: 'Blender', group: '3D and CAD', reads: 'Reads your scene. Objects, modifiers, materials, lights.', how: 'connect', plans: 3 },
  { id: 'freecad', name: 'FreeCAD', group: '3D and CAD', reads: 'Reads your model. Sketches, constraints, features.', how: 'connect', plans: 2 },
  { id: 'fusion', name: 'Fusion', group: '3D and CAD', reads: 'Reads your timeline and bodies.', how: 'connect', plans: 1 },
  { id: 'onshape', name: 'Onshape', group: '3D and CAD', reads: 'Reads your Part Studio after you sign in.', how: 'connect', plans: 1 },
  { id: 'unity', name: 'Unity', group: 'Games', how: 'screen', plans: 1 },
  { id: 'godot', name: 'Godot', group: 'Games', how: 'screen', plans: 1 },
  { id: 'other', name: 'Any other app', group: 'Everything else', reads: 'Lessons still work.', how: 'screen' }
]

/** "Used by 14 plans." */
export const usedBy = (n?: number): string => (n ? `Used by ${n} ${n === 1 ? 'plan' : 'plans'}.` : '')

/** The caption under an app: what it reads, then what uses it. */
export const appCaption = (a: AppRow): string => [a.reads, usedBy(a.plans)].filter(Boolean).join(' ')

/** "212 MB". */
export function size(bytes?: number): string | undefined {
  if (bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return undefined
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 ** 2)} MB`
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`
}

/** Your data's Delete account opens the Privacy panel straight on its two-step confirm. A moment, not a flag: React's
 * strict mode runs a state initializer twice, and a later visit must open plain. */
let deleteAskAt = 0
export const askDelete = (): void => {
  deleteAskAt = Date.now()
}
export const takeDeleteAsk = (): boolean => Date.now() - deleteAskAt < 1500
