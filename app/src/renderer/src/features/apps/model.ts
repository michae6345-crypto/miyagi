/**
 * Feature: apps. The apps miyagi teaches in (Adrian's MIC-87 note, docs/ui-next/apps/NOTE.md on adrian/ui-next), as
 * plain data and pure functions, so the sidebar, the picker, the app page and Home's "Learn in" read one model.
 *
 *   APPS               the apps supported today, in sidebar order: which catalog tools each one covers, its glyph, the
 *                      page "Get it" opens (only where main's setup list allows it), its name in full
 *   catalogApps()      every app the plans catalog names: the supported ones, then the rest as "soon" (greyed)
 *   appForTool(id)     the supported app a catalog tool belongs to (Jupyter and Terminal lessons count as VS Code)
 *   lessonApp(item)    which app a Library lesson works in, inferred from its own fields (tools, teaches, title)
 *   appContent(id, …)  everything miyagi has for an app: its plans, the learner's lessons, its skills, where to start
 *   installState(…)    installed / missing / unknown, from main's scan, the engine's health rows and "I have it"
 *   sidebarApps(…)     the apps the sidebar lists: the learner's pinned list, or the default
 *   togglePinned(…)    the pinned list after a tick in the picker
 *   libraryNavResets() whether picking Library goes back to the Library list (from an app's page, or from Library)
 *
 * Names come from the catalog (`tool.label`); nothing here names a lesson. Marks: names only (the note's trademark
 * section); each app gets a neutral glyph in the mark's slot.
 */
import type { CatalogPlan, LibraryItem, PlanState } from '../../../../../../shared/contracts/events'

export type AppGlyph = 'code' | 'box' | 'compass' | 'cuboid'

export type AppMeta = {
  id: string
  /** The catalog tool ids whose plans and lessons belong to this app (its own id first). */
  tools: readonly string[]
  glyph: AppGlyph
  /** "Get it": a download page on main's setup list (main/safeOpen.ts SETUP_PAGES). Absent: no Get button. */
  getUrl?: string
  /** The name in full, where the maker asks for it ("Autodesk Fusion"). The header uses it. */
  fullName?: string
}

/** Supported today (Michael, Nov 25: VS Code, Blender, Fusion, FreeCAD), in the order the sidebar lists them. */
export const APPS: readonly AppMeta[] = [
  { id: 'vscode', tools: ['vscode', 'jupyter', 'terminal'], glyph: 'code', getUrl: 'https://code.visualstudio.com/download' },
  { id: 'blender', tools: ['blender'], glyph: 'box', getUrl: 'https://www.blender.org/download/' },
  { id: 'freecad', tools: ['freecad'], glyph: 'compass' },
  { id: 'fusion', tools: ['fusion'], glyph: 'cuboid', fullName: 'Autodesk Fusion' }
]

const byTool = new Map(APPS.flatMap((a) => a.tools.map((t) => [t, a] as const)))
export const appMeta = (id: string | undefined): AppMeta | undefined => APPS.find((a) => a.id === id)
export const appForTool = (tool: string | undefined): AppMeta | undefined => (tool ? byTool.get(tool) : undefined)
export const isApp = (id: unknown): id is string => typeof id === 'string' && APPS.some((a) => a.id === id)

export type CatalogApp = { id: string; name: string; soon: boolean; plans: number }

/**
 * Every app the catalog names: the supported apps first (in APPS order, named by the catalog's own label), then the
 * other tools as "soon", by name. A tool that only feeds a supported app (Jupyter) is not listed apart.
 */
export function catalogApps(plans: readonly CatalogPlan[]): CatalogApp[] {
  const names = new Map<string, string>()
  const counts = new Map<string, number>()
  for (const p of plans) {
    if (!names.has(p.tool.id)) names.set(p.tool.id, p.tool.label)
    const owner = appForTool(p.tool.id)?.id ?? p.tool.id
    counts.set(owner, (counts.get(owner) ?? 0) + 1)
  }
  const supported = APPS.map((a) => ({ id: a.id, name: names.get(a.id) ?? a.fullName ?? a.id, soon: false, plans: counts.get(a.id) ?? 0 }))
  const soon = [...names.entries()]
    .filter(([id]) => !appForTool(id))
    .map(([id, name]) => ({ id, name, soon: true, plans: counts.get(id) ?? 0 }))
    .sort((a, b) => a.name.localeCompare(b.name))
  return [...supported, ...soon]
}

/** An app's short name (the catalog's label): "VS Code", "Fusion". */
export function appName(id: string, plans: readonly CatalogPlan[]): string {
  return plans.find((p) => p.tool.id === id)?.tool.label ?? appMeta(id)?.fullName ?? id
}

// ---- which app a lesson works in -------------------------------------------------------------------------------------

/** The bits of the catalog lessonApp reads (built once per catalog). */
export type ToolIndex = { skillTool: Map<string, string>; titleTool: Map<string, string> }

export function toolIndex(plans: readonly CatalogPlan[]): ToolIndex {
  const skillTool = new Map<string, string>()
  const titleTool = new Map<string, string>()
  for (const p of plans) {
    for (const s of p.skills) if (!skillTool.has(s.id)) skillTool.set(s.id, p.tool.id)
    for (const l of p.lessons) if (!titleTool.has(l.title.toLowerCase())) titleTool.set(l.title.toLowerCase(), p.tool.id)
  }
  return { skillTool, titleTool }
}

/**
 * The app a Library lesson works in, from what the lesson itself says, in this order: the plan that claims it (its
 * tool), the skills it teaches or uses (the catalog plan each skill belongs to), its title (a catalog lesson's), then
 * its `tools` (a notebook or terminal lesson is a VS Code lesson). Undefined when nothing points to a supported app.
 */
export function lessonApp(item: Pick<LibraryItem, 'title' | 'tools' | 'teaches' | 'uses'>, index: ToolIndex, planTool?: string): string | undefined {
  const fromPlan = appForTool(planTool)
  if (fromPlan) return fromPlan.id
  for (const id of [...(item.teaches ?? []), ...(item.uses ?? [])]) {
    const a = appForTool(index.skillTool.get(id))
    if (a) return a.id
  }
  const byTitle = appForTool(index.titleTool.get((item.title ?? '').toLowerCase()))
  if (byTitle) return byTitle.id
  for (const t of item.tools ?? []) {
    const a = appForTool(t)
    if (a) return a.id
  }
  return undefined
}

/** library item id → the tool of the learner's plan that holds it (PlanLesson.libraryId). */
export function planToolsByLesson(mine: readonly PlanState[]): Map<string, string> {
  const out = new Map<string, string>()
  for (const p of mine) {
    const tool = p.tool?.id
    if (!tool) continue
    for (const l of p.lessons) if (l.libraryId) out.set(l.libraryId, tool)
  }
  return out
}

// ---- what miyagi has for one app --------------------------------------------------------------------------------------

export type AppContent = {
  id: string
  name: string
  /** The catalog plans in this app: the start plan first, then the rest by catalog order. */
  plans: CatalogPlan[]
  /** Where to start: the learner's plan in progress here, else the first "start" plan, else the first plan. */
  start?: CatalogPlan
  /** The learner's own plans in this app (made from a playlist or a goal, or a catalog plan they added). */
  mine: PlanState[]
  /** The learner's Library lessons in this app. */
  lessons: LibraryItem[]
  /** The skills this app's plans grow (each once, in plan order). */
  skills: Array<{ id: string; label: string }>
  lessonCount: number
  minutes: number
}

/** `featured`: catalog plan ids to start with when the learner has none going here (plans/catalog.ts START_HERE). */
export function appContent(id: string, catalog: readonly CatalogPlan[], items: readonly LibraryItem[], mine: readonly PlanState[], featured: readonly string[] = []): AppContent {
  const meta = appMeta(id)
  const tools = new Set(meta?.tools ?? [id])
  const own = catalog.filter((p) => tools.has(p.tool.id))
  const myHere = mine.filter((m) => (m.tool && tools.has(m.tool.id)) || own.some((p) => p.id === m.catalogId))
  const going = myHere.find((m) => m.nextIndex !== null && m.done > 0 && own.some((p) => p.id === m.catalogId))
  const first =
    featured.map((f) => own.find((p) => p.id === f)).find(Boolean) ?? own.find((p) => p.tool.id === id && p.level === 'start') ?? own.find((p) => p.level === 'start') ?? own[0]
  const start = (going && own.find((p) => p.id === going.catalogId)) || first
  const plans = start ? [start, ...own.filter((p) => p !== start)] : own
  const index = toolIndex(catalog)
  const planTool = planToolsByLesson(mine)
  const lessons = items.filter((i) => lessonApp(i, index, planTool.get(i.id)) === id)
  const seen = new Set<string>()
  const skills: AppContent['skills'] = []
  for (const p of plans) for (const s of p.skills) if (!seen.has(s.id) && seen.add(s.id)) skills.push({ id: s.id, label: s.label })
  const lessonCount = plans.reduce((n, p) => n + p.lessons.length, 0)
  const minutes = plans.reduce((n, p) => n + p.lessons.reduce((m, l) => m + l.minutes, 0), 0)
  return { id, name: appName(id, catalog), plans, start, mine: myHere, lessons, skills, lessonCount, minutes }
}

/** Does the learner have anything in this app yet (a lesson in the Library, or a plan)? */
export const hasActivity = (c: Pick<AppContent, 'lessons' | 'mine'>): boolean => c.lessons.length > 0 || c.mine.length > 0

// ---- installed? --------------------------------------------------------------------------------------------------------

export type InstallState = 'installed' | 'missing' | 'unknown'

/** The engine's health rows that speak about VS Code (orchestrator/health.py): `vscode`, and the companion's fix. */
export type HealthLike = Record<string, { state?: string; fix?: string } | undefined>

/**
 * Is the app on this Mac? "I have it" wins (the learner knows), then main's scan of /Applications, then the engine's
 * health rows (VS Code only: a `vscode` row, or the companion row whose fix is get_vscode / install_companion).
 * Nothing said: unknown, and the UI claims neither.
 */
export function installState(id: string, scan: Record<string, boolean> | undefined, health: HealthLike, have: readonly string[]): InstallState {
  if (have.includes(id)) return 'installed'
  const s = scan?.[id]
  if (s === true) return 'installed'
  if (s === false) return 'missing'
  if (id === 'vscode') {
    const row = health.vscode
    if (row?.state === 'ok') return 'installed'
    if (row?.state === 'missing') return 'missing'
    const comp = health.companion
    if (comp?.fix === 'get_vscode') return 'missing'
    if (comp?.state === 'ok' || comp?.fix === 'install_companion') return 'installed'
  }
  return 'unknown'
}

// ---- the sidebar's list ------------------------------------------------------------------------------------------------

/**
 * The apps the sidebar lists, in APPS order. Pinned (the learner chose in the picker): exactly those that are still
 * supported. Default (null): the apps on this Mac, plus the ones the learner has lessons or plans in that nothing says
 * are missing; when that leaves none (a new learner, nothing scanned), every supported app.
 */
export function sidebarApps(pinned: readonly string[] | null, state: (id: string) => InstallState, active: (id: string) => boolean): string[] {
  if (pinned) return APPS.map((a) => a.id).filter((id) => pinned.includes(id))
  const picked = APPS.map((a) => a.id).filter((id) => state(id) === 'installed' || (state(id) === 'unknown' && active(id)))
  return picked.length ? picked : APPS.map((a) => a.id)
}

/** The pinned list after ticking `id` in the picker: starts from what the sidebar shows now, in APPS order. */
export function togglePinned(shown: readonly string[], id: string): string[] {
  if (!isApp(id)) return [...shown]
  const next = shown.includes(id) ? shown.filter((x) => x !== id) : [...shown, id]
  return APPS.map((a) => a.id).filter((x) => next.includes(x))
}

/**
 * Picking Library (its sidebar row, ⌘2) lands on the Library list when an app's page is up: that page lives on
 * Library, but it is not Library (the sidebar marks the app's row). Picking Library while on Library also goes back
 * to the list from any of its views. From another page, Library comes back as it was left, unless that was an app.
 */
export function libraryNavResets(target: string, page: string, view: { kind: string }): boolean {
  if (target !== 'lessons' || view.kind === 'library') return false
  return view.kind === 'app' || page === 'lessons'
}
