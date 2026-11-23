/**
 * Feature: shell. The home window's persistent left sidebar:
 *
 *   top      room for the traffic lights (the window drags here), then the bonsai and the lowercase wordmark
 *            (flow/SidebarBrand.tsx: where the first run's bonsai lands, the wordmark writing in after it)
 *   nav      Home, Lessons, Skills, Progress, Settings, Account. The selection is one shape that slides between rows
 *            on the house spring (layoutId). Arrow keys move along the list (and switch the page, like the macOS
 *            sidebar), Home / End jump to the ends. ⌘1..⌘6 are handled by Shell.tsx.
 *   status   is miyagi ready (one calm line: getting ready, Ready, or couldn't start with Retry) and Setup at a glance
 *            (features/library Status.tsx), hidden when the window is short (the pill carries the status
 *            then, and the account chip stays fully in view down to the 420 px minimum height)
 *   account  a chip at the foot: who is signed in and the plan, or how miyagi runs without an account. Opens the
 *            account sheet over the content (signed in: the account; signed out: Sign in to sync), never a window.
 *            Its avatar is shared with the sheet: it flies into the sheet's header and back (AccountSheet.tsx).
 *
 * Compact (narrow window): icons only, 64 px, labels as tooltips. Navigation is chrome: neutral fills, never a hue.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ChevronRight, SquarePen } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { color, fill, focus, highlight, layout, radius2, spring, status, surface, type2, typeScale } from '../../core/theme'
import { fade, pressMotion } from '../../core/ui/motion'
import { openLauncher } from '../library/Library'
import { initialOf, planLabel, v2Cloud } from '../account/model'
import { loadAccount, useAccount } from '../account/store'
import { authOn } from '../auth/model'
import { loadAuth, useAuth } from '../auth/store'
import { StatusArea } from '../library/Status'
import { SharedAvatar } from './AccountSheet'
import { SidebarBrand } from './flow/SidebarBrand'
import { openSheet, useSheet } from './sheet'
import { PAGES, setPage, useShell, type PageId } from './store'

export const SIDEBAR_W = layout.sidebar.w
/** Between compact and full (Michael's audit at 1024x700: "the sidebar takes a large share"): labels stay, less width. */
export const SIDEBAR_NARROW_W = layout.sidebar.narrowW
export const SIDEBAR_COMPACT_W = layout.sidebar.compactW
/** A row: 30 tall, 10 px text inset (the row's highlight is itself inset 10 from the sidebar's edge). */
const ROW = layout.sidebar.row

/**
 * Redraft (Adrian, Nov 21): the main nav is the learner's pages (Home, Lessons, Skills, Progress). Settings sits at the
 * foot beside the account, as in macOS and Linear; Account is the chip itself (⌘6 still reaches its page).
 */
const FOOT: ReadonlySet<PageId> = new Set(['settings', 'account'])

/** New lesson: the launcher, one click from every page (a goal or a YouTube link). Chrome: neutral, never a hue. */
function NewLesson({ compact }: { compact: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      data-shell-new
      title={compact ? 'New lesson' : undefined}
      aria-label="New lesson"
      className="mg-press relative flex cursor-pointer items-center text-left font-medium outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{
        ...typeScale.nav,
        height: ROW,
        gap: 10,
        padding: compact ? 0 : '0 6px 0 10px',
        justifyContent: compact ? 'center' : undefined,
        borderRadius: radius2.control,
        color: color.text,
        outlineColor: focus.dark
      }}
      {...pressMotion()}
      onClick={openLauncher}
    >
      <SquarePen aria-hidden size={16} strokeWidth={1.8} className="relative shrink-0" />
      {!compact && <span className="relative flex-1 truncate">New lesson</span>}
    </motion.button>
  )
}

function NavRow({ id, label, Icon, on, compact, index }: { id: PageId; label: string; Icon: (typeof PAGES)[number]['icon']; on: boolean; compact: boolean; index: number }): ReactNode {
  return (
    <motion.button
      type="button"
      data-shell-nav={id}
      aria-current={on ? 'page' : undefined}
      // Roving focus: only the selected row is a tab stop; the arrows move between rows.
      tabIndex={on ? 0 : -1}
      title={compact ? label : undefined}
      aria-label={compact ? label : undefined}
      aria-keyshortcuts={`Meta+${index + 1} Control+${index + 1}`}
      className={`${on ? '' : 'mg-press'} relative flex cursor-pointer items-center text-left font-medium outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid`}
      style={{
        ...typeScale.nav,
        height: ROW,
        gap: 10,
        padding: compact ? 0 : '0 10px',
        justifyContent: compact ? 'center' : undefined,
        borderRadius: radius2.control,
        color: on ? color.text : color.label,
        fontWeight: on ? 600 : undefined,
        outlineColor: focus.dark
      }}
      {...pressMotion(on)}
      onClick={() => setPage(id)}
    >
      {on && (
        <motion.span
          layoutId="shell-nav-selection"
          aria-hidden
          className="absolute inset-0"
          // Selected: a quiet fill only (no hue, no edge, no left bar), so the content stays first.
          style={{ background: fill.trackSoft, borderRadius: radius2.control }}
          transition={spring}
        />
      )}
      <Icon aria-hidden size={16} strokeWidth={1.8} className="relative shrink-0" />
      {!compact && <span className="relative truncate">{label}</span>}
    </motion.button>
  )
}

/**
 * The nav's sections (Notion-style): a quiet label over its rows, collapsible with the chevron. The state is a
 * preference of this window only (localStorage, wrapped: it can be blocked), and a collapsed section still shows the
 * page you are on, so the selection never disappears. Compact (icons only) shows every row and no labels.
 */
const GROUPS: ReadonlyArray<{ id: string; label: string; pages: readonly PageId[] }> = [
  { id: 'learn', label: 'Learn', pages: ['home', 'lessons'] },
  { id: 'track', label: 'Track', pages: ['skills', 'progress'] }
]
const COLLAPSE_KEY = 'miyagi.sidebar.collapsed'

function readCollapsed(): string[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(COLLAPSE_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

function GroupLabel({ label, open, onToggle, id }: { label: string; open: boolean; onToggle: () => void; id: string }): ReactNode {
  return (
    <button
      type="button"
      data-shell-group={id}
      aria-expanded={open}
      onClick={onToggle}
      className="mg-press group relative flex cursor-pointer items-center text-left font-medium outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{ height: 24, gap: 4, padding: '0 10px', borderRadius: radius2.control, fontSize: type2.micro, letterSpacing: '0.02em', color: color.label, outlineColor: focus.dark }}
    >
      <span className="relative">{label}</span>
      <motion.span aria-hidden className="relative flex opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100" animate={{ rotate: open ? 90 : 0 }} transition={spring}>
        <ChevronRight size={12} strokeWidth={2} />
      </motion.span>
    </button>
  )
}

function Nav({ compact }: { compact: boolean }): ReactNode {
  const page = useShell((s) => s.page)
  const ref = useRef<HTMLElement>(null)
  const reduce = useReducedMotion()
  const [closed, setClosed] = useState<string[]>(readCollapsed)
  const toggle = (id: string): void =>
    setClosed((c) => {
      const next = c.includes(id) ? c.filter((x) => x !== id) : [...c, id]
      try {
        localStorage.setItem(COLLAPSE_KEY, JSON.stringify(next))
      } catch {
        /* storage blocked: the section still folds for this session */
      }
      return next
    })
  // A row is shown unless its section is folded and it is not the page on show.
  const shown = (g: (typeof GROUPS)[number], id: PageId): boolean => compact || !closed.includes(g.id) || id === page
  // The arrows walk the rows on show (Settings and the account live at the foot).
  const main = GROUPS.flatMap((g) => g.pages.filter((id) => shown(g, id)))
  const onKey = (e: KeyboardEvent<HTMLElement>): void => {
    if ((e.target as HTMLElement).closest('[data-shell-group]')) return
    const i = main.indexOf(page)
    const last = main.length - 1
    const to = e.key === 'ArrowDown' ? Math.min(last, i + 1) : e.key === 'ArrowUp' ? Math.max(0, i - 1) : e.key === 'Home' ? 0 : e.key === 'End' ? last : -1
    if (to < 0) return
    e.preventDefault()
    setPage(main[to])
  }
  // Keep keyboard focus on the selected row when the arrows (or the number shortcuts while the nav has focus) move it.
  useEffect(() => {
    const nav = ref.current
    if (!nav || !nav.contains(document.activeElement)) return
    nav.querySelector<HTMLButtonElement>(`[data-shell-nav="${page}"]`)?.focus()
  }, [page])
  return (
    <nav ref={ref} aria-label="Pages" className="flex flex-col" style={{ gap: compact ? layout.sidebar.rowGap : 8 }} onKeyDown={onKey}>
      {GROUPS.map((g) => {
        const open = compact || !closed.includes(g.id)
        const rows = g.pages.filter((id) => shown(g, id))
        return (
          <div key={g.id} role="group" aria-label={g.label} className="flex flex-col" style={{ gap: layout.sidebar.rowGap }}>
            {!compact && <GroupLabel id={g.id} label={g.label} open={open} onToggle={() => toggle(g.id)} />}
            <AnimatePresence initial={false}>
              {rows.map((id) => {
                const p = PAGES.find((x) => x.id === id)!
                return (
                  <motion.div key={id} layout={!reduce} initial={{ opacity: 0 }} animate={{ opacity: 1, transition: fade.in }} exit={{ opacity: 0, transition: fade.out }} transition={spring}>
                    <NavRow id={p.id} label={p.label} Icon={p.icon} on={p.id === page} compact={compact} index={PAGES.findIndex((x) => x.id === id)} />
                  </motion.div>
                )
              })}
            </AnimatePresence>
          </div>
        )
      })}
    </nav>
  )
}

/** The account chip's avatar. */
const CHIP_AVATAR = 20

/** Above the sheet's scrim (z 30) and the sheet itself (z 40) while the avatar flies back into the chip. */
const FLIGHT_Z = 45

/** Where the avatar sits while it is lent to the sheet: an empty recessed circle, so the chip never looks broken. */
function AvatarSocket(): ReactNode {
  return <span aria-hidden data-avatar="socket" className="block shrink-0" style={{ width: CHIP_AVATAR, height: CHIP_AVATAR, borderRadius: radius2.round, background: surface.well, boxShadow: `${highlight.well}, inset 0 0 0 1px ${fill.hairline}` }} />
}

/**
 * The account chip: the signed-in learner (the real login, features/auth: avatar initial, name, email), "Not signed
 * in / Sign in to sync" when signed out; the person and the plan under v2Cloud (mock); "This Mac" with login off.
 */
function AccountChip({ compact }: { compact: boolean }): ReactNode {
  const on = useShell((s) => s.page === 'account')
  // While a sheet shows the avatar, the chip keeps an empty slot (the avatar is in the sheet's header).
  const lent = useSheet((s) => s.kind !== null && s.kind !== 'plans')
  // Account → Plans: the avatar comes home without a flight (it would cross the paper sheet).
  const snap = useSheet((s) => s.kind === 'plans')
  // While the avatar flies home the chip rides above the scrim and the leaving sheet (they sit at z 30 and 40 in
  // <main>; the chip is in the sidebar, behind them). Set on the element, so it lands in the flight's first frame.
  const chip = useRef<HTMLButtonElement>(null)
  const onFlight = (on: boolean): void => {
    if (chip.current) chip.current.style.zIndex = on ? String(FLIGHT_Z) : ''
  }
  const account = useAccount((s) => s.account)
  const accountLoaded = useAccount((s) => s.loaded)
  const user = useAuth((s) => s.user)
  const authLoaded = useAuth((s) => s.loaded)
  const login = !v2Cloud && authOn
  useEffect(() => {
    if (v2Cloud) void loadAccount()
    else if (authOn) void loadAuth()
  }, [])
  let name: string
  let line: string
  let initial: string | undefined
  let signedIn = false
  if (v2Cloud) {
    signedIn = !!account?.signedIn
    name = signedIn ? (account?.name ?? account?.email ?? 'Signed in') : 'Not signed in'
    line = signedIn ? `${planLabel(account!.plan)} plan` : 'Sign in to sync'
    initial = signedIn ? initialOf(name) : undefined
  } else if (login) {
    signedIn = !!user
    name = user ? (user.name ?? user.email ?? 'Signed in') : 'Not signed in'
    line = user ? (user.name && user.email ? user.email : 'Signed in') : 'Sign in to sync'
    initial = user?.avatarInitial
  } else {
    name = 'This Mac'
    line = 'No account needed'
  }
  const pending = v2Cloud ? !accountLoaded : login ? !authLoaded : false
  return (
    <motion.button
      ref={chip}
      type="button"
      data-shell-account={signedIn ? 'in' : 'out'}
      aria-label={`Account: ${name}. ${line}.`}
      title={compact ? name : undefined}
      className="mg-press relative flex w-full cursor-pointer items-center text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{
        // 4/8 scale. With the 20 px avatar its center lines up with the nav icons' and the name with their labels (x 46 in a 232 sidebar).
        gap: 8,
        padding: compact ? 6 : '4px 8px',
        justifyContent: compact ? 'center' : undefined,
        borderRadius: radius2.control,
        background: on ? fill.navOn : 'transparent',
        outlineColor: focus.dark
      }}
      {...pressMotion()}
      aria-haspopup={login || v2Cloud ? 'dialog' : undefined}
      onClick={() => (login || v2Cloud ? openSheet(signedIn ? 'account' : 'signin') : setPage('account'))}
    >
      {lent ? <AvatarSocket /> : <SharedAvatar initial={initial} size={CHIP_AVATAR} snap={snap} onFlight={onFlight} />}
      {!compact && (
        <span className="relative flex min-w-0 flex-1 flex-col" style={{ gap: 2 }}>
          {pending ? (
            <>
              <span aria-hidden style={{ width: 96, height: 10, borderRadius: radius2.round, background: fill.skeleton }} />
              <span aria-hidden style={{ width: 64, height: 8, borderRadius: radius2.round, background: fill.skeleton }} />
            </>
          ) : (
            <>
              <span className="truncate font-medium" style={{ fontSize: type2.sm, lineHeight: '16px', color: color.text }}>
                {name}
              </span>
              <span className="truncate" style={{ fontSize: type2.micro, lineHeight: '14px', color: color.label }}>
                {line}
              </span>
            </>
          )}
        </span>
      )}
    </motion.button>
  )
}

export function Sidebar({ compact, short, blocked = false, width = SIDEBAR_W }: { compact: boolean; short: boolean; /** the account sheet is open: lit, but inert */ blocked?: boolean; /** full width, or SIDEBAR_NARROW_W in a mid-size window */ width?: number }): ReactNode {
  const page = useShell((s) => s.page)
  const settings = PAGES.findIndex((p) => p.id === 'settings')
  const S = PAGES[settings]
  return (
    <aside
      data-shell-sidebar={compact ? 'compact' : 'full'}
      inert={blocked}
      className="flex h-full shrink-0 flex-col"
      // The sidebar is the window itself (the lowest layer); the content panel beside it is the raised one.
      // 10 px each side, so every row's highlight is inset 10 from the edge; the foot sits 12 above the bottom.
      style={{ width: compact ? SIDEBAR_COMPACT_W : width, padding: `0 ${layout.sidebar.pad}px ${layout.sidebar.foot}px` }}
    >
      {/* The window's own traffic lights sit here (hiddenInset); this strip drags the window. */}
      <div data-drag className="mg-lights shrink-0" />
      <div data-drag className="flex shrink-0 items-center gap-[8px]" style={{ padding: compact ? '4px 0 18px' : '4px 10px 18px', justifyContent: compact ? 'center' : undefined }}>
        <SidebarBrand compact={compact} />
      </div>
      <div className="flex flex-col" style={{ gap: 12 }}>
        <NewLesson compact={compact} />
        <Nav compact={compact} />
      </div>
      <div className="mt-auto flex flex-col" style={{ gap: layout.sidebar.rowGap, paddingTop: layout.sidebar.groupGap }}>
        {!compact && !short && (
          // "Ready" here is the engine's state, not a passed check: styles.css swaps its green tick for the gray dot.
          <div data-sidebar-status style={{ ['--sidebar-ready-dot' as string]: status.watching }}>
            <StatusArea plan={false} />
          </div>
        )}
        <NavRow id={S.id} label={S.label} Icon={S.icon} on={page === 'settings'} compact={compact} index={settings} />
        <AccountChip compact={compact} />
      </div>
    </aside>
  )
}
