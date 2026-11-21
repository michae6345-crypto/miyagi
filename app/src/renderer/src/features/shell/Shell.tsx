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
 */
import { AnimatePresence, motion, type Variants } from 'motion/react'
import { RotateCcw } from 'lucide-react'
import { Component, useEffect, useLayoutEffect, useRef, useState, type ErrorInfo, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { color, duration, fill, highlight, radius2, spring, stagger, surface, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { riseIn } from '../../core/ui/motion'
import { Detail } from '../library/Detail'
import { Home } from '../library/Home'
import { LessonSearch, Lessons, greeting, openLauncher } from '../library/Library'
import { Ring } from '../library/motion'
import { useLibrary } from '../library/store'
import { AccountPage } from './pages/AccountPage'
import { ProgressPage } from './pages/ProgressPage'
import { SettingsPage } from './pages/SettingsPage'
import { SkillsPage } from './pages/SkillsPage'
import { Sidebar } from './Sidebar'
import { PAGES, setPage, useShell, type PageId } from './store'

/** Below this window width the sidebar shows icons only; below SHORT_H it drops the status block. */
const COMPACT_W = 880
const SHORT_H = 700

// ---- page header ------------------------------------------------------------------------------------------------

const CAPTION: Partial<Record<PageId, string>> = {
  skills: 'Pick a skill to see the lessons that teach it.',
  progress: 'Every number is a step you passed yourself.',
  account: 'Your plan and how miyagi runs here.'
}

function Header({ page }: { page: PageId }): ReactNode {
  const label = PAGES.find((p) => p.id === page)?.label ?? ''
  const title = page === 'home' ? greeting() : label
  const caption = page === 'home' ? new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }) : CAPTION[page]
  return (
    <header data-drag className="flex shrink-0 items-center gap-[16px]" style={{ height: 68, padding: '0 32px', borderBottom: `1px solid ${fill.hairline}` }}>
      <div className="flex min-w-0 items-baseline gap-[12px]">
        <h1 className="m-0 shrink-0 font-semibold" style={{ fontSize: type2.xl, letterSpacing: '-0.01em', color: color.text }}>
          {title}
        </h1>
        {caption && (
          <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
            {caption}
          </span>
        )}
      </div>
      {page === 'home' && (
        // Home's own hero holds the one white primary; New lesson stays quiet here.
        <div data-no-drag className="ml-auto shrink-0">
          <Ring>
            <QuietButton label="New lesson" keyName="launcher" onClick={openLauncher} />
          </Ring>
        </div>
      )}
      {page === 'lessons' && (
        <div data-no-drag className="ml-auto flex min-w-0 items-center gap-[12px]">
          <LessonSearch />
          <Ring>
            <PrimaryButton label="New lesson" keyName="launcher" onClick={openLauncher} />
          </Ring>
        </div>
      )}
    </header>
  )
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
const SELF_SCROLL: ReadonlySet<PageId> = new Set(['home', 'skills'])

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

function PageFrame({ page, active, covered }: { page: PageId; active: boolean; covered: boolean }): ReactNode {
  const off = !active || covered
  return (
    <motion.section
      data-shell-page={page}
      data-active={active || undefined}
      aria-hidden={off || undefined}
      inert={off}
      variants={frame}
      initial="hidden"
      animate={active ? 'shown' : 'hidden'}
      className="absolute inset-0 flex flex-col"
      style={{ visibility: active ? 'visible' : 'hidden', color: color.text }}
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
  const [ref, size] = useSize<HTMLDivElement>()

  // ⌘1..⌘6 (Ctrl+1..6 on Windows) pick a page. Typing in a field is left alone except for these chords.
  useEffect(() => {
    const mac = bridge.platform.os === 'mac'
    const onKey = (e: KeyboardEvent): void => {
      const mod = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey
      if (!mod || e.altKey || e.shiftKey) return
      const n = Number(e.key)
      if (!Number.isInteger(n) || n < 1 || n > PAGES.length) return
      e.preventDefault()
      setPage(PAGES[n - 1].id)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])

  const backLabel = PAGES.find((p) => p.id === page)?.label
  return (
    <div ref={ref} data-shell={page} className="flex h-full w-full" style={{ color: color.text }}>
      <Sidebar compact={size.w < COMPACT_W} short={size.h < SHORT_H} />
      <main className="relative min-w-0 flex-1 overflow-hidden">
        {PAGES.filter((p) => visited.includes(p.id)).map((p) => (
          <PageFrame key={p.id} page={p.id} active={p.id === page} covered={!!openId} />
        ))}
        <AnimatePresence>
          {openId && (
            <motion.div key="detail" data-shell-detail={openId} {...riseIn} className="absolute inset-0 z-20" style={{ background: color.window }}>
              <Detail id={openId} back={backLabel} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  )
}
