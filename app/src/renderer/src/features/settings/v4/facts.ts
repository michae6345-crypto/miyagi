/**
 * Feature: settings, v4 page (Nov 24). The pure half of data.ts (no bridge, so tests import it): the Apps list, the
 * words under each app, the cache size, and the Delete account ask.
 *
 * `APPS` is a LOCAL TYPED PLACEHOLDER until the ui-v4 contract (shared/contracts/UI-V4.md, plans catalog) lands: the
 * apps a plan can use, how miyagi reads each, and how many catalog plans use it (counted from docs/ui-next/catalog on
 * origin/adrian/ui-next, Nov 24). Engine health (vscode, jupyter, any other id it reports) overrides the placeholder
 * status in the panel; only an ok health item says Connected (no item: "Reads exactly" or "Screen only").
 */

import type { DataInventory, PlanToolId } from '../../../../../../../shared/contracts/events'

export type AppGroup = 'Code' | 'Sheets and design' | '3D and CAD' | 'Games' | 'Everything else'
/**
 * connected: read exactly through the editor or the terminal; screen: miyagi looks at the window.
 * No "connect" kind (Nov 25, app-ready-copy): the app has no way to set up an add-on yet, so a Connect button could
 * only ever say it wasn't ready. Blender, FreeCAD, Fusion and Onshape read as Screen only until the engine's health
 * reports their add-on ok, and then the row says Connected like any other.
 */
export type AppHow = 'connected' | 'screen'
export type AppRow = { id: PlanToolId | 'other'; name: string; group: AppGroup; reads?: string; how: AppHow; plans?: number }

export const APP_GROUPS: readonly AppGroup[] = ['Code', 'Sheets and design', '3D and CAD', 'Games', 'Everything else']

export const APPS: readonly AppRow[] = [
  { id: 'vscode', name: 'VS Code', group: 'Code', reads: 'Reads your files and the terminal.', how: 'connected', plans: 14 },
  { id: 'jupyter', name: 'Jupyter', group: 'Code', reads: 'Reads each cell and what it printed.', how: 'connected', plans: 7 },
  { id: 'terminal', name: 'Terminal', group: 'Code', reads: 'Reads commands and their output.', how: 'connected', plans: 2 },
  { id: 'xcode', name: 'Xcode', group: 'Code', how: 'screen', plans: 2 },
  { id: 'excel', name: 'Excel', group: 'Sheets and design', how: 'screen', plans: 1 },
  { id: 'sheets', name: 'Google Sheets', group: 'Sheets and design', how: 'screen', plans: 1 },
  { id: 'figma', name: 'Figma', group: 'Sheets and design', how: 'screen', plans: 1 },
  { id: 'blender', name: 'Blender', group: '3D and CAD', how: 'screen', plans: 3 },
  { id: 'freecad', name: 'FreeCAD', group: '3D and CAD', how: 'screen', plans: 2 },
  { id: 'fusion', name: 'Fusion', group: '3D and CAD', how: 'screen', plans: 1 },
  { id: 'onshape', name: 'Onshape', group: '3D and CAD', how: 'screen', plans: 1 },
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

/** What Your data shows, from the engine's `data` inventory (ui-v4 contract, data.get) when it answered. */
export type YourData = { cacheBytes?: number; folder: string; lessons?: number; canClearCache?: boolean; canClearHistory?: boolean; fromEngine?: boolean }

/** The contract's inventory to the panel's rows: the lesson folder's path and count, the cache's size and whether the
 * engine can really clear it (canDelete; the app offers Clear only then). */
export function fromInventory(inv: DataInventory): YourData {
  const folder = inv.items.find((i) => i.id === 'lesson_folder')
  const cache = inv.items.find((i) => i.id === 'lesson_cache')
  return {
    folder: folder?.path || '~/miyagi',
    lessons: folder?.count ?? undefined,
    cacheBytes: cache?.bytes ?? undefined,
    canClearCache: !!inv.canDelete?.includes('lesson_cache'),
    canClearHistory: !!inv.canDelete?.includes('progress'),
    fromEngine: true
  }
}

/** Your data's Delete account opens the Privacy panel straight on its two-step confirm. A moment, not a flag: React's
 * strict mode runs a state initializer twice, and a later visit must open plain. */
let deleteAskAt = 0
export const askDelete = (): void => {
  deleteAskAt = Date.now()
}
export const takeDeleteAsk = (): boolean => Date.now() - deleteAskAt < 1500

/** A chord split into its keys (⌥Space -> ⌥ and Space, Alt+Space -> Alt and Space), one cap each, as the mock draws it. */
export function splitKeys(label: string): string[] {
  return label.match(/[⌃⌥⇧⌘]|[^⌃⌥⇧⌘+\s]+/g) ?? []
}
