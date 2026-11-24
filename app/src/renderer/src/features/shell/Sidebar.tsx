/**
 * Feature: shell. The home window's persistent left sidebar, v4 (Adrian's ui-next mock, Nov 23: Notion's sidebar):
 *
 *   top      room for the traffic lights (the window drags here), then the bonsai and the lowercase wordmark
 *            (flow/SidebarBrand.tsx: where the first run's bonsai lands) with New lesson (the compose icon) on the right
 *   nav      Search (the launcher, its keycap on the right), Home, Library, Skills, Progress. Arrow keys move along the
 *            pages (and switch the page, like the macOS sidebar), Home / End jump to the ends. ⌘1..⌘6 are Shell.tsx's.
 *   Plans    the learner's plans with "3 of 8" on the right (ui.tsx useSidebarFeed; hidden until there are plans)
 *   Recent   the last three lessons opened: the ink ring while in progress, the green tick once passed (green = passed)
 *   foot     Settings, then the account row: who is signed in and the plan, or how miyagi runs without an account. Opens
 *            the account sheet over the content, never a window. Its avatar flies into the sheet's header and back.
 *   status   only while miyagi is not ready (getting ready, reconnecting, couldn't start with Retry): one calm line
 *            above Settings (features/library Status.tsx). When all is well the sidebar says nothing about it.
 *
 * A page with its own list (Settings) swaps the whole list for its own (ui.tsx setSidebarList): a back row, then its
 * sections. One sidebar on screen.
 *
 * Compact (narrow window): icons only, 64 px, labels as tooltips. Navigation is chrome: neutral fills, never a hue.
 */
import { motion } from 'motion/react'
import { ChevronLeft, GitBranch, Library, List, PenLine, Search, type LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { color, fill, focus, highlight, radius2, status, surface, v4, v4c, v4type } from '../../core/theme'
import { pressMotion } from '../../core/ui/motion'
import { openLauncher } from '../library/Library'
import { openDetail, useLibrary } from '../library/store'
import { initialOf, planLabel, v2Cloud } from '../account/model'
import { loadAccount, useAccount } from '../account/store'
import { authOn } from '../auth/model'
import { loadAuth, useAuth } from '../auth/store'
import { useBoot } from '../errors/startup'
import { StatusArea } from '../library/Status'
import { SharedAvatar } from './AccountSheet'
import { SidebarBrand } from './flow/SidebarBrand'
import { openSheet, useSheet } from './sheet'
import { PAGES, setPage, useShell, type PageId } from './store'
import { PassedMark, ProgressRing, useSidebarFeed, useSidebarList, type SidebarList, type SidebarRecent } from './ui'

export const SIDEBAR_W = v4.sidebar.w
/** Between compact and full (a 1024 window): labels stay, a little less width. */
export const SIDEBAR_NARROW_W = v4.sidebar.narrowW
export const SIDEBAR_COMPACT_W = v4.sidebar.compactW
const ROW = v4.sidebar.row
const PAD = v4.sidebar.padX

/** The sidebar's names for the pages (v4: "Library" for the lessons page). The page ids stay. */
export const NAV_LABEL: Partial<Record<PageId, string>> = { lessons: 'Library' }
/** The mock's glyphs where they differ from the page's own icon (store.ts): Library's shelf, Skills' branch. */
const NAV_ICON: Partial<Record<PageId, LucideIcon>> = { lessons: Library, skills: GitBranch }
export const pageLabel = (id: PageId): string => NAV_LABEL[id] ?? PAGES.find((p) => p.id === id)?.label ?? ''
/** The learner's pages, in order (Settings and the account live at the foot). */
const MAIN: readonly PageId[] = ['home', 'lessons', 'skills', 'progress']

/**
 * One sidebar row (Notion's): 30 tall, 8 px in, the icon then the label, a quiet value on the right. Selected: the
 * active wash, ink text and icon, a touch heavier.
 */
function SideRow({ icon, label, right, on = false, compact, onClick, data, title, keys }: { icon: ReactNode; label: string; right?: ReactNode; on?: boolean; compact: boolean; onClick: () => void; data?: Record<string, string>; title?: string; keys?: string }): ReactNode {
  return (
    <button
      type="button"
      aria-current={on ? 'page' : undefined}
      title={compact ? label : title}
      aria-label={compact ? label : undefined}
      aria-keyshortcuts={keys}
      className={`mg-v4-side-row relative flex w-full shrink-0 cursor-pointer items-center text-left outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid`}
      style={{
        ...v4type.nav,
        height: ROW,
        gap: 9,
        padding: compact ? 0 : `0 ${PAD}px`,
        justifyContent: compact ? 'center' : undefined,
        borderRadius: v4.radius.row,
        background: on ? v4c.active : undefined,
        color: on ? color.text : color.label,
        fontWeight: on ? 560 : 500,
        outlineColor: focus.dark
      }}
      onClick={onClick}
      {...data}
    >
      <span aria-hidden className="flex shrink-0 items-center justify-center" style={{ width: 16, height: 16, color: on ? color.text : color.faint }}>
        {icon}
      </span>
      {!compact && <span className="min-w-0 flex-1 truncate">{label}</span>}
      {!compact && right != null && (
        <span className="shrink-0 whitespace-nowrap" style={{ fontSize: 12, lineHeight: '16px', fontWeight: 450, color: color.label, fontVariantNumeric: 'tabular-nums' }}>
          {right}
        </span>
      )}
    </button>
  )
}

/** A quiet section label (Plans, Recent): 12 / 550 faint, 18 above, 4 under. */
function SideLabel({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="truncate" style={{ ...v4type.navLabel, color: color.faint, padding: `0 ${PAD}px`, margin: `${v4.sidebar.labelTop}px 0 ${v4.sidebar.labelBottom}px` }}>
      {children}
    </div>
  )
}

const icon = (I: LucideIcon): ReactNode => <I size={16} strokeWidth={1.6} />

function Nav({ compact }: { compact: boolean }): ReactNode {
  const page = useShell((s) => s.page)
  const ref = useRef<HTMLElement>(null)
  const onKey = (e: KeyboardEvent<HTMLElement>): void => {
    if (!(e.target as HTMLElement).closest('[data-shell-nav]')) return
    const i = MAIN.indexOf(page)
    const last = MAIN.length - 1
    const to = e.key === 'ArrowDown' ? Math.min(last, i + 1) : e.key === 'ArrowUp' ? Math.max(0, i - 1) : e.key === 'Home' ? 0 : e.key === 'End' ? last : -1
    if (to < 0) return
    e.preventDefault()
    setPage(MAIN[to])
  }
  // Keep keyboard focus on the selected row when the arrows (or the number shortcuts while the nav has focus) move it.
  useEffect(() => {
    const nav = ref.current
    if (!nav || !nav.contains(document.activeElement)) return
    nav.querySelector<HTMLButtonElement>(`[data-shell-nav="${page}"]`)?.focus()
  }, [page])
  return (
    <nav ref={ref} aria-label="Pages" className="flex flex-col" onKeyDown={onKey}>
      <SideRow icon={icon(Search)} label="Search" right={bridge.platform.keys.launcher} compact={compact} onClick={openLauncher} data={{ 'data-shell-search': '' }} />
      {MAIN.map((id) => {
        const p = PAGES.find((x) => x.id === id)!
        const index = PAGES.findIndex((x) => x.id === id)
        return <SideRow key={id} icon={icon(NAV_ICON[id] ?? p.icon)} label={pageLabel(id)} on={page === id} compact={compact} onClick={() => setPage(id)} data={{ 'data-shell-nav': id }} keys={`Meta+${index + 1} Control+${index + 1}`} />
      })}
    </nav>
  )
}

/** Recent: the feed's, or until the ui-v4 contract is wired, the library's last three lessons with progress. */
function useRecent(): SidebarRecent[] {
  const fed = useSidebarFeed((s) => s.recent)
  const items = useLibrary((s) => s.items)
  return useMemo(() => {
    if (fed) return fed.slice(0, 3)
    return items
      .filter((i) => i.progress)
      .sort((a, b) => (b.updatedAt ?? '').localeCompare(a.updatedAt ?? ''))
      .slice(0, 3)
      .map((i) => ({ id: i.id, title: i.title, passed: !!i.progress && i.progress.total > 0 && i.progress.stepIndex >= i.progress.total }))
  }, [fed, items])
}

function openRecent(r: SidebarRecent): void {
  if (r.onOpen) return r.onOpen()
  setPage('lessons')
  openDetail(r.id)
}

function Lists({ compact }: { compact: boolean }): ReactNode {
  const plans = useSidebarFeed((s) => s.plans)
  const recent = useRecent()
  if (compact) return null
  return (
    <>
      {plans && plans.length > 0 && (
        <div data-shell-plans className="flex flex-col">
          <SideLabel>Plans</SideLabel>
          {plans.map((p) => (
            <SideRow key={p.id} icon={icon(List)} label={p.title} title={p.title} right={`${p.done} of ${p.total}`} compact={false} onClick={() => (p.onOpen ? p.onOpen() : setPage('lessons'))} data={{ 'data-shell-plan': p.id }} />
          ))}
        </div>
      )}
      {recent.length > 0 && (
        <div data-shell-recent className="flex flex-col">
          <SideLabel>Recent</SideLabel>
          {recent.map((r) => (
            <SideRow key={r.id} icon={r.passed ? <PassedMark size={16} /> : <ProgressRing size={16} />} label={r.title} title={r.title} compact={false} onClick={() => openRecent(r)} data={{ 'data-shell-recent-item': r.id }} />
          ))}
        </div>
      )}
    </>
  )
}

/** The account row's avatar: a 22 px rounded square (the mock's), shared with the sheet. */
const CHIP_AVATAR = 22

/** Above the sheet's scrim (z 30) and the sheet itself (z 40) while the avatar flies back into the chip. */
const FLIGHT_Z = 45

/** Where the avatar sits while it is lent to the sheet: an empty recessed circle, so the chip never looks broken. */
function AvatarSocket(): ReactNode {
  return <span aria-hidden data-avatar="socket" className="block shrink-0" style={{ width: CHIP_AVATAR, height: CHIP_AVATAR, borderRadius: radius2.round, background: surface.well, boxShadow: `${highlight.well}, inset 0 0 0 1px ${fill.hairline}` }} />
}

/**
 * The account row: the signed-in learner (the real login, features/auth: avatar initial, name) and the plan on the
 * right; "Not signed in" / "Sign in" when signed out; the person and the plan under v2Cloud (mock); "This Mac" with
 * login off.
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
  let right: string
  let line: string
  let initial: string | undefined
  let signedIn = false
  if (v2Cloud) {
    signedIn = !!account?.signedIn
    name = signedIn ? (account?.name ?? account?.email ?? 'Signed in') : 'Not signed in'
    right = signedIn ? planLabel(account!.plan) : 'Sign in'
    line = signedIn ? `${planLabel(account!.plan)} plan` : 'Sign in to sync'
    initial = signedIn ? initialOf(name) : undefined
  } else if (login) {
    signedIn = !!user
    name = user ? (user.name ?? user.email ?? 'Signed in') : 'Not signed in'
    right = user ? '' : 'Sign in'
    line = user ? (user.email ?? 'Signed in') : 'Sign in to sync'
    initial = user?.avatarInitial
  } else {
    name = 'This Mac'
    right = ''
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
      className="mg-v4-side-row relative flex w-full shrink-0 cursor-pointer items-center text-left outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
      style={{
        gap: 9,
        height: v4.sidebar.account,
        marginTop: 2,
        padding: compact ? 0 : `0 ${PAD}px`,
        justifyContent: compact ? 'center' : undefined,
        borderRadius: v4.radius.row,
        background: on ? v4c.active : undefined,
        outlineColor: focus.dark
      }}
      {...pressMotion()}
      aria-haspopup={login || v2Cloud ? 'dialog' : undefined}
      onClick={() => (login || v2Cloud ? openSheet(signedIn ? 'account' : 'signin') : setPage('account'))}
    >
      {lent ? <AvatarSocket /> : <SharedAvatar initial={initial} size={CHIP_AVATAR} snap={snap} onFlight={onFlight} />}
      {!compact &&
        (pending ? (
          <span aria-hidden style={{ width: 96, height: 10, borderRadius: radius2.round, background: fill.skeleton }} />
        ) : (
          <>
            <span className="min-w-0 flex-1 truncate" style={{ fontSize: 13.5, lineHeight: '18px', fontWeight: 550, color: color.text }}>
              {name}
            </span>
            {right && (
              <span className="shrink-0" style={{ fontSize: 12, lineHeight: '16px', color: color.label }}>
                {right}
              </span>
            )}
          </>
        ))}
    </motion.button>
  )
}

/** A page's own list (Settings): its back row, its sections, its foot. */
function OwnList({ list, compact }: { list: SidebarList; compact: boolean }): ReactNode {
  return (
    <>
      <nav aria-label={list.back.label} className="flex flex-col">
        <SideRow icon={icon(ChevronLeft)} label={list.back.label} compact={compact} onClick={list.back.onClick} data={{ 'data-shell-back': '' }} />
        {list.groups.map((g, gi) => (
          <div key={gi} role="group" aria-label={g.label} className="flex flex-col">
            {g.label && !compact ? <SideLabel>{g.label}</SideLabel> : gi > 0 ? <div style={{ height: v4.sidebar.labelTop }} /> : null}
            {g.items.map((it) => (
              <SideRow key={it.id} icon={icon(it.icon)} label={it.label} on={list.active === it.id} compact={compact} onClick={() => list.onPick(it.id)} data={{ 'data-shell-own': it.id }} />
            ))}
          </div>
        ))}
      </nav>
      <div className="mt-auto flex flex-col" style={{ paddingTop: v4.sidebar.labelTop }}>
        {list.foot?.map((it) => (
          <SideRow key={it.id} icon={icon(it.icon)} label={it.label} on={list.active === it.id} compact={compact} onClick={() => list.onPick(it.id)} data={{ 'data-shell-own': it.id }} />
        ))}
      </div>
    </>
  )
}

/** miyagi's own start-up, only while it is not ready (the sidebar is quiet when all is well). */
function Boot(): ReactNode {
  const phase = useBoot().phase
  if (phase !== 'failed' && phase !== 'starting' && phase !== 'reconnecting') return null
  // "Ready" is the engine's state, not a passed check: styles.css swaps its green tick for the gray dot.
  return (
    <div data-sidebar-status style={{ ['--sidebar-ready-dot' as string]: status.watching, marginBottom: 4 }}>
      <StatusArea plan={false} setup={false} />
    </div>
  )
}

export function Sidebar({ compact, short, blocked = false, width = SIDEBAR_W }: { compact: boolean; short: boolean; /** the account sheet is open: lit, but inert */ blocked?: boolean; /** full width, or SIDEBAR_NARROW_W in a mid-size window */ width?: number }): ReactNode {
  const page = useShell((s) => s.page)
  const own = useSidebarList((s) => s.list)
  const settings = PAGES.findIndex((p) => p.id === 'settings')
  const S = PAGES[settings]
  return (
    <aside
      data-shell-sidebar={compact ? 'compact' : 'full'}
      inert={blocked}
      className="flex h-full shrink-0 flex-col overflow-hidden"
      // The sidebar shares the page's paper; one hairline on its right edge separates them (the mock's paper-cream).
      style={{ width: compact ? SIDEBAR_COMPACT_W : width, padding: `0 ${PAD}px ${v4.sidebar.padY}px`, background: v4c.side, boxShadow: `inset -1px 0 0 ${v4c.hair}` }}
    >
      {/* The window's own traffic lights sit here (hiddenInset); this strip drags the window. */}
      <div data-drag className="mg-lights shrink-0" />
      <div data-drag className="flex shrink-0 items-center gap-[8px]" style={{ height: v4.sidebar.brand, padding: compact ? 0 : `0 ${PAD}px`, marginBottom: 6, justifyContent: compact ? 'center' : undefined }}>
        <SidebarBrand compact={compact} />
        {!compact && (
          <button
            type="button"
            data-shell-new
            aria-label="New lesson"
            title="New lesson"
            onClick={openLauncher}
            className="mg-v4-side-row ml-auto grid cursor-pointer place-items-center outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
            style={{ width: 26, height: 26, borderRadius: v4.radius.row, color: color.label, outlineColor: focus.dark }}
          >
            <PenLine aria-hidden size={16} strokeWidth={1.6} />
          </button>
        )}
      </div>
      {own ? (
        <OwnList list={own} compact={compact} />
      ) : (
        <>
          <div className="flex min-h-0 flex-col overflow-y-auto" style={{ scrollbarWidth: 'none' }}>
            <Nav compact={compact} />
            {!short && <Lists compact={compact} />}
          </div>
          <div className="mt-auto flex shrink-0 flex-col" style={{ paddingTop: v4.sidebar.labelTop }}>
            {!compact && !short && <Boot />}
            {compact && <SideRow icon={icon(PenLine)} label="New lesson" compact onClick={openLauncher} data={{ 'data-shell-new': '' }} />}
            <SideRow icon={icon(S.icon)} label={S.label} on={page === 'settings'} compact={compact} onClick={() => setPage('settings')} data={{ 'data-shell-nav': 'settings' }} keys={`Meta+${settings + 1} Control+${settings + 1}`} />
            <AccountChip compact={compact} />
          </div>
        </>
      )}
    </aside>
  )
}
