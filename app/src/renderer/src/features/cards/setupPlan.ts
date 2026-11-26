/**
 * The calm setup card (Michael, Nov 22, the AutoCAD lesson: "this whole UI looks very bad, very inefficient"). Pure, so
 * tests can check it without React.
 *
 * One surface says what to do, with one white primary per card, picked by the kind of tool still missing:
 *   install    a package or a free app the engine installs (pip / brew / brew_cask): "Install NumPy", or "Install all"
 *   licensed   a paid app miyagi never installs (AutoCAD): "Get AutoCAD", or "I have it" when the scan saw it on this
 *              Mac; the free alternative ("Try FreeCAD") is the quiet second button; Skip stays a quiet link
 *   web        a web app: "Open <app>"
 *   download   an older engine's download page: "Get <app>"
 * A paid app's buttons are engine actions (have_it / get_it / alternative), read from the card's actions or the row's
 * own, whichever the engine sent. Only a row with no actions at all (an older engine) falls back to a link.
 * The rest of the card (Download tutorial files, Open VS Code) keeps its own quiet buttons.
 *
 * Older engines: rows without setupKind / actions still work (a download row is "Get it", a pip row is "Install").
 */
import type { Payload } from '../../../../common/wire'
import { dockRect } from '../../core/geometry'
import { rowSettled, rowWaiting } from './setupHold'

type Card = Payload<'card'>
type Row = NonNullable<Card['items']>[number]
type InstallState = { running?: boolean; ok?: boolean; error?: string }

/** A button the setup card draws itself (never one of card.actions' generic buttons). */
export type SetupBtn =
  | { do: 'install'; tool: string; label: string }
  | { do: 'install_all'; label: string }
  /** A download page or a web app: main's setup list opens it (drawer/store linkRowAct), never the engine. */
  | { do: 'link'; tool: string; url?: string; label: string }
  /** have_it / get_it / alternative: the engine re-checks the Mac, opens the vendor page or switches to the alternative. */
  | { do: 'card'; action: 'have_it' | 'get_it' | 'alternative'; tool: string; label: string }

export type SetupPlan = {
  /** The card's one white primary. Undefined: the card's own actions decide (Open VS Code on a ready card...). */
  primary?: SetupBtn
  /** Quiet buttons beside it (the free alternative, "I have it" when Get is the primary). */
  secondary: SetupBtn[]
  /** Rows whose button the plan draws: those rows carry no button of their own. */
  owns: string[]
}

export type ToolKind = 'install' | 'licensed' | 'web' | 'download' | 'none'

const PACKAGE = new Set<Row['install']['method']>(['pip', 'brew', 'brew_cask'])

/** What kind of thing is missing: decides the primary. */
export function toolKind(x: Row): ToolKind {
  if (x.setupKind === 'licensed_app') return 'licensed'
  if (x.setupKind === 'web_app' || x.kind === 'web_app' || x.install.method === 'open') return 'web'
  if (PACKAGE.has(x.install.method)) return 'install'
  if (x.install.method === 'download' && x.install.url) return 'download'
  return 'none'
}

/** Card actions the plan draws itself: CardActions leaves them out of a setup card. */
export const PLAN_ACTIONS = new Set<string>(['have_it', 'get_it', 'alternative', 'install', 'install_all'])

const rows = (c: Card): Row[] => (c.setup?.items ?? c.items ?? []).filter((x) => x.needed)

/** Needed rows still waiting on the learner (not ok, not settled, not just installed). */
export function waitingRows(c: Card | undefined, installs: Record<string, InstallState> = {}): Row[] {
  if (c?.kind !== 'setup') return []
  return rows(c).filter((x) => rowWaiting(x) && !installs[x.tool]?.ok)
}

export function planSetup(c: Card, installs: Record<string, InstallState> = {}, queued = false): SetupPlan {
  const none: SetupPlan = { secondary: [], owns: [] }
  if (c.kind !== 'setup') return none
  const waiting = waitingRows(c, installs)
  const actions = (c.actions ?? []) as string[]
  const labels = c.setup?.actionLabels ?? {}
  const lic = waiting.find((x) => toolKind(x) === 'licensed')
  // The licensed app's free alternative, when it has its own row to install (today's engine: FreeCAD's Install).
  const altTool = lic?.alternative?.tool
  const isAlt = (x: Row): boolean => !!altTool && x.tool === altTool
  const installable = waiting.filter((x) => toolKind(x) === 'install')
  const free = installable.filter((x) => !isAlt(x) && !installs[x.tool]?.running)

  // 1. Packages first: they are what Install can get right now.
  const unfinished = installable.filter((x) => !isAlt(x))
  if (unfinished.length >= 2 || queued) return { primary: { do: 'install_all', label: 'Install all' }, secondary: [], owns: unfinished.map((x) => x.tool) }
  if (free.length === 1) return { primary: { do: 'install', tool: free[0].tool, label: `Install ${free[0].label}` }, secondary: [], owns: [free[0].tool] }

  // 2. A paid app: Get it (or I have it, when the scan saw it), the free alternative beside it.
  // The engine handles have_it / get_it / alternative from either place: the card's actions (an engine with
  // APP_RENDERS_APP_ACTIONS) or the row's own actions (today's engine: card.actions is only [install, skip_setup], the
  // AutoCAD row still offers [have_it, get_it, alternative, skip]). get_it opens the vendor page on the engine's own
  // allowlist; main's setup list has no vendor pages, so a link button there would open nothing.
  if (lic) {
    const owns = [lic.tool]
    const can = (a: 'have_it' | 'get_it' | 'alternative'): boolean => actions.includes(a) || !!lic.actions?.includes(a)
    // An older engine (no actions on the row or the card): the row's download page through main's list.
    const oldRow = lic.actions === undefined && !actions.includes('get_it') && !actions.includes('have_it')
    const pageUrl = lic.install.url ?? lic.vendorUrl
    const get: SetupBtn | undefined = can('get_it')
      ? { do: 'card', action: 'get_it', tool: lic.tool, label: labels.get_it ?? `Get ${lic.label}` }
      : oldRow && pageUrl
        ? { do: 'link', tool: lic.tool, url: pageUrl, label: `Get ${lic.label}` }
        : undefined
    const have: SetupBtn | undefined = can('have_it') ? { do: 'card', action: 'have_it', tool: lic.tool, label: labels.have_it ?? 'I have it' } : undefined
    const altRow = installable.find(isAlt)
    let alt: SetupBtn | undefined
    if (lic.alternative && can('alternative')) {
      // The engine switches the lesson to the alternative; its offered row (today's engine) then gets Install.
      alt = { do: 'card', action: 'alternative', tool: lic.tool, label: labels.alternative ?? `Try ${lic.alternative.name}` }
      if (altRow) owns.push(altRow.tool)
    } else if (altRow && !installs[altRow.tool]?.running) {
      alt = { do: 'install', tool: altRow.tool, label: `Install ${altRow.label}` }
      owns.push(altRow.tool)
    }
    // No Mac version: getting it is no use here, the alternative leads.
    if (lic.noMac && alt) return { primary: alt, secondary: [], owns }
    // "I have it" leads only when the scan saw the app (installed, not yet confirmed); otherwise Get leads.
    const primary = (lic.installed && have) || get || have || alt
    const secondary = [alt, have, get].filter((b): b is SetupBtn => !!b && b !== primary)
    return { primary, secondary, owns }
  }

  // 3. A web app: Open it. 4. An older engine's download page: Get it.
  const web = waiting.find((x) => toolKind(x) === 'web')
  if (web) return { primary: { do: 'link', tool: web.tool, url: web.install.url, label: `Open ${web.label}` }, secondary: [], owns: [web.tool] }
  const page = waiting.find((x) => toolKind(x) === 'download')
  if (page) return { primary: { do: 'link', tool: page.tool, url: page.install.url, label: `Get ${page.label}` }, secondary: [], owns: [page.tool] }
  return none
}

/**
 * The quiet line elsewhere (drawer step, folded chip): what the step still needs, or undefined when nothing waits.
 * "Needs AutoCAD", "Needs NumPy, pandas", "Needs NumPy, pandas +1".
 */
export function needsLine(c: Card | undefined, name: (x: Row) => string = (x) => x.label): string | undefined {
  const all = waitingRows(c)
  // A paid app's free alternative (FreeCAD for AutoCAD) is a choice, not a second thing the step needs.
  const alts = new Set(all.map((x) => x.alternative?.tool).filter((t): t is string => !!t))
  const w = all.filter((x) => !alts.has(x.tool))
  if (!w.length) return undefined
  const shown = w.slice(0, 2).map(name).join(', ')
  return `Needs ${shown}${w.length > 2 ? ` +${w.length - 2}` : ''}`
}

/**
 * The card's body, minus what an older engine said that the card can't back up: no "editor" talk on a lesson that needs
 * no editor, and no "Install now?" when nothing on it can be installed (AutoCAD).
 */
export function setupBody(c: Card): string {
  let b = c.body ?? ''
  if (c.kind !== 'setup' || !c.setup) return b
  if (c.setup.editorNeeded === false) b = b.replace(/\s*No editor needed\b[^.]*(\.|$)/gi, '')
  const canInstall = waitingRows(c).some((x) => toolKind(x) === 'install')
  if (!canInstall) b = b.replace(/\s*Install now\?/g, '')
  return b.trim()
}

/** The narrowest the setup card gets between the drawer and the player (title, two body lines, one row each). */
export const SETUP_MIN_W = 260
/** Air between the setup card and the drawer or the player (core islandPlace keeps 16 from the dock and the edge). */
const SIDE_GAP = 16
/** The drawer panel's inset from the screen edge (features/drawer/geometry.ts INSET). */
const DRAWER_INSET = 8

/**
 * The setup card's width (Michael, Nov 22: it covered the player's edge). In a video lesson it fits the room between
 * the open drawer and the docked player:
 *   centre given  the island is attached to the notch and never steps aside (core Island.tsx), so the card grows evenly
 *                 from that centre: half its width has to fit on each side.
 *   no centre     a pill below the menu bar: core slides an open card clear of the player (islandPlace offDock), so the
 *                 whole room between the drawer and the player counts.
 * Elsewhere it's the usual card width. `drawer.w`: the drawer panel's width (drawer/geometry PANEL_W).
 */
export function setupCardWidth(overlayW: number, videoLesson: boolean, drawer: { open: boolean; at: 'left' | 'right'; w: number }, cardW: number, centre?: number): number {
  if (!videoLesson) return cardW
  const dockX = dockRect({ x: 0, y: 0, width: overlayW, height: 900 }).x
  const left = (drawer.open && drawer.at === 'left' ? DRAWER_INSET + drawer.w : 0) + SIDE_GAP
  // A right-hand drawer lives in the player's column (common/screenLayout.ts, Nov 25), never left of the player.
  const right = dockX - SIDE_GAP
  const room = centre === undefined ? right - left : 2 * Math.min(centre - left, right - centre)
  return Math.round(Math.max(SETUP_MIN_W, Math.min(cardW, room)))
}

/** Rows the learner settled show what they chose, never a button. */
export const settledLine = (x: Row): string | undefined => (x.using ? `Using ${x.using}` : x.haveIt ? 'You have it' : undefined)
export { rowSettled }
