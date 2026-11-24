/**
 * Feature: shell. The home window as an app (Michael, Nov 20: "a dashboard on the left; I should be able to click
 * different pages"). The Dock click, the tray's "Open miyagi" and setup's Start all open this window (route
 * `library`, features/library LibraryWindow.tsx), and it is now:
 *
 *   sidebar   Sidebar.tsx: the bonsai and wordmark, the six pages, status, the account chip
 *   content   the page on show, with its own header (title, and that page's actions)
 *
 * Pages switch instantly: the old page hides at once and the new one fades in and rises 6 px on the house spring
 * (opacity only with reduced motion). A page, once visited, stays mounted and hidden (visibility + inert), so it keeps
 * its scroll, its search, its open skill card and its drafts. A lesson's preview opens over the content area, the
 * sidebar stays; switching pages closes it.
 *
 * Keys: ⌘1..⌘6 (Ctrl on Windows) pick a page; the arrows walk the sidebar. Esc never closes this window: it closes a
 * preview, a skill card or clears the search, and otherwise does nothing.
 * Each page renders inside its own error boundary: a page that throws shows a calm card with Try again, and the
 * other pages keep working.
 *
 * Sign-in and the account open as a sheet over the content area (AccountSheet.tsx, sheet.ts), never a second window:
 * the content dims, the sidebar stays lit, and everything behind the sheet is inert until it closes. A click on the
 * sidebar while it is open closes it.
 *
 * The first run happens in this same window (flow/: one window from start to finish). Until setup is over, the flow
 * layer covers everything, sidebar included; nothing of home mounts under it. At the end the layer's screen fades
 * first (only its plain paper is left), then the paper fades while the sidebar slides in from the window's left edge,
 * the bonsai glides from the flow's step strip into the sidebar's logo (one LayoutGroup, layoutId MARK_ID; the
 * wordmark writes in once the tree has landed, flow/SidebarBrand.tsx) and Home rises in, its cards one after another.
 * Setup asked for again (Finish setup, the sidebar's status rows, Settings' Open setup: flow/store.ts requestSetup)
 * fades the flow in over home, which stays mounted and inert underneath, and out again. Asked for from another window
 * (the tray's Settings), it arrives here as this window's {setup} arg (core/surfaces.ts openOnboarding), read below.
 * Reduced motion: crossfades only.
 *
 * The sheet and the flow never show together: the sheet belongs to home, so it never opens while the flow covers,
 * and one that is open when setup is asked for closes (closeSheet) before the flow comes up.
 */
import { AnimatePresence, LayoutGroup, motion, useReducedMotion, type Variants } from 'motion/react'
import { RotateCcw } from 'lucide-react'
import { Component, useEffect, useLayoutEffect, useRef, useState, type ErrorInfo, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { useWindowArgs } from '../../core/surfaces'
import { color, duration, fill, highlight, layout, radius2, spring, stagger, surface, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { riseIn } from '../../core/ui/motion'
import { Detail } from '../library/Detail'
import { Home } from '../library/Home'
import { LessonSearch, Lessons, openLauncher } from '../library/Library'
import { Ring } from '../library/motion'
import { v2Cloud } from '../account/model'
import { itemFor, useLibrary } from '../library/store'
import { AccountSheetHost } from './AccountSheet'
import { AccountPage } from './pages/AccountPage'
import { ProgressPage } from './pages/ProgressPage'
import { SettingsPage } from './pages/SettingsPage'
import { SkillsHeaderTools, SkillsPage } from './pages/SkillsPage'
import { FlowLayer } from './flow/FlowLayer'
import { homeIn, sidebarIn } from './flow/motion'
import { flowCovers, initFlow, requestSetup, useFlow } from './flow/store'
import { closeSheet, useSheet } from './sheet'
import { useLocal } from '../settings/local'
import { pageLabel, Sidebar, SIDEBAR_COMPACT_W, SIDEBAR_NARROW_W, SIDEBAR_W } from './Sidebar'
import { COLUMN_W, LegacyPageHeader, PANEL, pageInset, TopBar, useCrumbs, WIDE_W } from './ui'
import { PAGES, setPage, useShell, type PageId } from './store'

/** Below this window width the sidebar shows icons only; below SHORT_H it drops the status block. */
const COMPACT_W = layout.sidebar.compactBelow
/** Below this window width the sidebar keeps its labels but narrows (SIDEBAR_NARROW_W). */
const NARROW_W = layout.sidebar.narrowBelow
const SHORT_H = 520 // the sidebar needs ~420 px; keep the Ready line at mid heights (round 3: it vanished at 1024x700)

// ---- page header ------------------------------------------------------------------------------------------------

/** Captions only where the page needs one to be understood; the redraft keeps them off (calm copy). */
const CAPTION: Partial<Record<PageId, string>> = {}

/**
 * The shell's own title for a page that has not moved to the v4 PageFrame yet (a v4 page owns its title: styles.css
 * hides this one as soon as the page renders a PageFrame). Home has no title (Michael's brief: no greeting).
 */
function Header({ page }: { page: PageId }): ReactNode {
  if (page === 'home') return null
  return <LegacyPageHeader title={pageLabel(page)} caption={CAPTION[page]} right={page === 'lessons' ? <LessonSearch /> : page === 'skills' ? <SkillsHeaderTools /> : undefined} />
}

/** The top bar's breadcrumb: the page's name, then the trail a page set for its deeper view (ui.tsx setCrumbs). */
function Crumbs({ page, detail }: { page: PageId; detail?: string }): ReactNode {
  const trail = useCrumbs((s) => (s.page === page ? s.trail : null))
  const parts = [pageLabel(page), ...(detail ? [detail] : (trail ?? []))]
  return <TopBar crumbs={parts} />
}

// ---- error boundary -----------------------------------------------------------------------------------------------

class PageBoundary extends Component<{ page: PageId; children: ReactNode }, { failed: boolean; tries: number }> {
  state = { failed: false, tries: 0 }
  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true }
  }
  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[miyagi] the ${this.props.page} page crashed:`, error, info.componentStack)
  }
  render(): ReactNode {
    if (!this.state.failed) return <PageKeyed key={this.state.tries}>{this.props.children}</PageKeyed>
    return (
      <div role="alert" data-shell-error={this.props.page} className="flex h-full items-center justify-center" style={{ padding: 32 }}>
        <div className="flex flex-col items-start gap-[12px]" style={{ maxWidth: 360, padding: 24, borderRadius: radius2.panel, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}` }}>
          <span className="font-semibold" style={{ fontSize: type2.body, color: color.text }}>
            This page didn’t load.
          </span>
          <span style={{ fontSize: type2.sm, color: color.label }}>The other pages still work. Try this one again.</span>
          <Ring>
            <QuietButton label="Try again" icon={RotateCcw} onClick={() => this.setState((s) => ({ failed: false, tries: s.tries + 1 }))} />
          </Ring>
        </div>
      </div>
    )
  }
}
/** Remounts its children when the boundary retries (a fresh first render). */
function PageKeyed({ children }: { children: ReactNode }): ReactNode {
  return children
}

// ---- pages --------------------------------------------------------------------------------------------------------

/** Home and Skills scroll inside themselves (Home's container queries, the constellation's own list). */
const SELF_SCROLL: ReadonlySet<PageId> = new Set(['home', 'skills', 'progress', 'settings'])

/**
 * The column each page's title sits on (content + gutters): 720 (ui.tsx COLUMN_W) or the wide 1040 (WIDE_W). The
 * header pads in by `--page-inset` for this width, so its left edge is the content's left edge.
 *
 * Who centers the content: every page, through its own column (ui.tsx PageColumn, the one column), centered in the full
 * pane. The shell never pads a page's body: a padded body shrank the box the columns measure (their gutter flips at a
 * 760 pane), which is how Lessons sat 20 px and Home 40 px off the title (review round 2, Nov 22). Whether a page
 * scrolls in the shell's body (Lessons, Settings, Account) or inside itself (SELF_SCROLL), its scrollbar is at the
 * pane's edge.
 *
 * Landing order: this frame expects the pages' own centered columns (the layout-pages lane: Settings, Account, Progress,
 * Skills; the layout-home lane: Home, Lessons, the preview). Land this lane with or after those two, never alone:
 * before them the pages still carry their old 40 px left padding and sit left of the centered title.
 */
function pageWidth(page: PageId): number {
  // Settings is a two-pane page (list + panel), so it takes the wide column too. Skills takes it always, its empty
  // state included (that state is a PageColumn wide), so its title starts where every v4 page's does (QA r1 Q01).
  return page === 'skills' || page === 'settings' || page === 'progress' || page === 'account' ? WIDE_W : COLUMN_W
}

function Body({ page, active }: { page: PageId; active: boolean }): ReactNode {
  switch (page) {
    case 'home':
      return <Home />
    case 'lessons':
      return <Lessons />
    case 'skills':
      return <SkillsPage />
    case 'progress':
      return <ProgressPage />
    case 'settings':
      return <SettingsPage active={active} />
    case 'account':
      return <AccountPage />
  }
}

/** The incoming page rises in on the spring; the outgoing one is gone at once (no crossfade, no waiting). */
const frame: Variants = {
  hidden: { opacity: 0, y: stagger.rise, transition: { duration: 0 } },
  shown: { opacity: 1, y: 0, transition: { ...spring, opacity: { duration: duration.base } } }
}

function PageSlot({ page, active, covered }: { page: PageId; active: boolean; covered: boolean }): ReactNode {
  const off = !active || covered
  // Reduced motion: a page is born in its final state (no hidden frame to wait on).
  const reduce = useReducedMotion() ?? false
  return (
    <motion.section
      data-shell-page={page}
      data-active={active || undefined}
      aria-hidden={off || undefined}
      inert={off}
      variants={frame}
      initial={reduce ? (active ? 'shown' : 'hidden') : 'hidden'}
      animate={active ? 'shown' : 'hidden'}
      // mg-page-frame: the size container the gutter follows (styles.css), the pane's width.
      className="mg-page-frame absolute inset-0 flex flex-col"
      // One centered column for every page (layout lane): the header pads in by --page-inset (pageWidth above); the
      // body is never padded, the page's own PageColumn centers in the full pane.
      style={{
        visibility: active ? 'visible' : 'hidden',
        color: color.text,
        ['--page-inset' as string]: pageInset(pageWidth(page))
      }}
    >
      <Header page={page} />
      <div
        data-shell-body={page}
        className={`min-h-0 flex-1 ${SELF_SCROLL.has(page) ? 'flex flex-col overflow-hidden' : 'overflow-y-auto'}`}
        style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}
      >
        <PageBoundary page={page}>
          <Body page={page} active={active && !covered} />
        </PageBoundary>
      </div>
    </motion.section>
  )
}

// ---- setup asked for from another window -------------------------------------------------------------------------

const ASK_KEY = 'miyagi.flow.setupAsk'
/** True once per {setup} value: remembered for this window's session, so a reload doesn't replay it. */
function freshAsk(v: string): boolean {
  try {
    if (sessionStorage.getItem(ASK_KEY) === v) return false
    sessionStorage.setItem(ASK_KEY, v)
  } catch {
    /* no storage: act on it; at worst a reload opens setup once more */
  }
  return true
}

// ---- the shell ------------------------------------------------------------------------------------------------------

function useSize<T extends HTMLElement>(): [React.RefObject<T | null>, { w: number; h: number }] {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ w: 1280, h: 820 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const read = (): void => setSize({ w: el.clientWidth, h: el.clientHeight })
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, size]
}

export function Shell(): ReactNode {
  const page = useShell((s) => s.page)
  const visited = useShell((s) => s.visited)
  const openId = useLibrary((s) => s.openId)
  const sheet = useSheet((s) => !!s.kind)
  const [ref, size] = useSize<HTMLDivElement>()
  const phase = useFlow((s) => s.phase)
  const reduce = useReducedMotion() ?? false
  /** Home arrives from the first-run flow (this session): the sidebar slides in and the content rises. */
  const arriving = useRef(false)
  if (phase === 'leaving') arriving.current = true
  useEffect(() => initFlow(), [])

  // The sheet never shows while the flow covers: setup asked for with the sheet open closes it first (zustand calls
  // these in the same tick as the change, before React renders the flow), and a sheet asked for under the flow (a
  // timer, another window's ask) closes at once.
  useEffect(() => {
    const offFlow = useFlow.subscribe((s) => {
      if (flowCovers(s.phase)) closeSheet()
    })
    const offSheet = useSheet.subscribe((s) => {
      if (s.kind && flowCovers(useFlow.getState().phase)) closeSheet()
    })
    return () => {
      offFlow()
      offSheet()
    }
  }, [])

  // Setup asked for from another window opens this one with {setup: <a fresh value>}: run it over home, once per ask
  // (a reload of this window re-reads the same args and must not open it again).
  const args = useWindowArgs('library')
  useEffect(() => {
    const ask = args?.setup
    if (ask === undefined || ask === false) return
    if (!freshAsk(String(ask))) return
    requestSetup()
  }, [args])

  // ⌘1..⌘6 (Ctrl+1..6 on Windows) pick a page. Typing in a field is left alone except for these chords.
  useEffect(() => {
    const mac = bridge.platform.os === 'mac'
    const onKey = (e: KeyboardEvent): void => {
      const mod = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey
      if (!mod || e.altKey || e.shiftKey || useFlow.getState().phase !== 'off') return
      const n = Number(e.key)
      if (!Number.isInteger(n) || n < 1 || n > PAGES.length) return
      e.preventDefault()
      setPage(PAGES[n - 1].id)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])

  const backLabel = pageLabel(page)
  const openTitle = useLibrary((s) => (s.openId ? itemFor(s, s.openId)?.title : undefined))
  const again = useFlow((s) => s.again)
  // Setup again (reopenFlow): home stays mounted under the flow, inert, the sidebar under the layer too.
  const home = phase === 'off' || phase === 'leaving' || again
  const covered = flowCovers(phase)
  // Settings > Appearance > Compact sidebar: icons only at any width.
  const forceCompact = useLocal((s) => s.sidebarCompact)
  const showStatus = useLocal((s) => s.sidebarStatus)
  const compact = forceCompact || size.w < COMPACT_W
  const sideW = compact ? SIDEBAR_COMPACT_W : size.w < NARROW_W ? SIDEBAR_NARROW_W : SIDEBAR_W
  const enter = arriving.current
  // The sidebar rides above the flow's fading paper on the way in (z 3) and under the flow during setup again (z 1).
  // With the flow gone it takes no z-index at all: the account chip lifts itself to z 45 while the avatar flies home
  // from the sheet (z 30 / 40 in <main>), which a stacking context here would trap under the sheet.
  const sideZ = phase === 'off' ? '' : again ? 'z-[1]' : 'z-[3]'
  return (
    <LayoutGroup id="shell">
      <div ref={ref} data-shell={page} data-flow-phase={phase} data-shell-sheet-open={sheet || undefined} className="relative flex h-full w-full overflow-hidden" style={{ color: color.text, background: color.window }}>
        {home && (
          <motion.div
            data-shell-sidebar-wrap
            aria-hidden={covered || undefined}
            inert={covered}
            className={`relative ${sideZ} flex h-full shrink-0`}
            // From the window's left edge, its own width (reduced motion: a fade, nothing slides).
            initial={enter && !reduce ? { x: -sideW } : false}
            animate={{ x: 0, opacity: 1 }}
            transition={sidebarIn}
          >
            <Sidebar compact={compact} short={size.h < SHORT_H || !showStatus} blocked={sheet} width={sideW} />
          </motion.div>
        )}
        {/* While the sheet is open the sidebar stays lit but inert; a click on it closes the sheet. */}
        {home && sheet && <div data-shell-sheet-catcher data-no-drag aria-hidden className="absolute inset-y-0 left-0 z-40" style={{ width: sideW }} onPointerDown={closeSheet} />}
        {home && (
          <motion.main
            aria-hidden={covered || undefined}
            inert={covered}
            data-shell-panel
            className="relative flex min-w-0 flex-1 flex-col overflow-hidden"
            // v4: the page is the window's own paper (no inset pane); the sidebar's hairline separates them.
            style={{ background: PANEL.backgroundColor }}
            initial={enter && !reduce ? { opacity: 0, y: 8 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={homeIn}
          >
            <Crumbs page={page} detail={openTitle} />
            <div data-shell-pages className="relative min-h-0 flex-1">
              {PAGES.filter((p) => visited.includes(p.id)).map((p) => (
                <PageSlot key={p.id} page={p.id} active={p.id === page} covered={!!openId || sheet || covered} />
              ))}
              <AnimatePresence>
                {openId && (
                  <motion.div key="detail" data-shell-detail={openId} {...riseIn} inert={sheet || covered} className="mg-page-frame absolute inset-0 z-20" style={{ backgroundColor: PANEL.backgroundColor }}>
                    <Detail id={openId} back={backLabel} />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <AccountSheetHost mainW={size.w - sideW} mainH={size.h} />
          </motion.main>
        )}
        <AnimatePresence>{covered && <FlowLayer key="flow" width={size.w} height={size.h} />}</AnimatePresence>
      </div>
    </LayoutGroup>
  )
}
