/**
 * Feature: shell. The home window's persistent left sidebar:
 *
 *   top      room for the traffic lights (the window drags here), then the bonsai and the lowercase wordmark
 *   nav      Home, Lessons, Skills, Progress, Settings, Account. The selection is one shape that slides between rows
 *            on the house spring (layoutId). Arrow keys move along the list (and switch the page, like the macOS
 *            sidebar), Home / End jump to the ends. ⌘1..⌘6 are handled by Shell.tsx.
 *   status   Setup, Engine and Cloud at a glance (features/library Status.tsx), hidden when the window is short
 *   account  a chip at the foot: who is signed in and the plan, or how miyagi runs without an account. Opens Account.
 *
 * Compact (narrow window): icons only, 64 px, labels as tooltips. Navigation is chrome: neutral fills, never a hue.
 */
import { motion } from 'motion/react'
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { color, fill, focus, highlight, radius2, spring, surface, type2 } from '../../core/theme'
import { pressMotion } from '../../core/ui/motion'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { planLabel, v2Cloud } from '../account/model'
import { loadAccount, useAccount } from '../account/store'
import { Avatar } from '../auth/Avatar'
import { authOn } from '../auth/model'
import { loadAuth, useAuth } from '../auth/store'
import { StatusArea } from '../library/Status'
import { PAGES, setPage, useShell, type PageId } from './store'

export const SIDEBAR_W = 224
export const SIDEBAR_COMPACT_W = 64

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
        height: 34,
        gap: 10,
        padding: compact ? 0 : '0 10px',
        justifyContent: compact ? 'center' : undefined,
        borderRadius: radius2.control,
        fontSize: type2.sm,
        color: on ? color.text : color.label,
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
          style={{ background: fill.navActive, borderRadius: radius2.control, boxShadow: highlight.topSoft }}
          transition={spring}
        />
      )}
      <Icon aria-hidden size={16} strokeWidth={1.8} className="relative shrink-0" />
      {!compact && <span className="relative truncate">{label}</span>}
    </motion.button>
  )
}

function Nav({ compact }: { compact: boolean }): ReactNode {
  const page = useShell((s) => s.page)
  const ref = useRef<HTMLElement>(null)
  const onKey = (e: KeyboardEvent<HTMLElement>): void => {
    const i = PAGES.findIndex((p) => p.id === page)
    const to = e.key === 'ArrowDown' ? Math.min(PAGES.length - 1, i + 1) : e.key === 'ArrowUp' ? Math.max(0, i - 1) : e.key === 'Home' ? 0 : e.key === 'End' ? PAGES.length - 1 : -1
    if (to < 0) return
    e.preventDefault()
    setPage(PAGES[to].id)
  }
  // Keep keyboard focus on the selected row when the arrows (or ⌘1..⌘6 while the nav has focus) move it.
  useEffect(() => {
    const nav = ref.current
    if (!nav || !nav.contains(document.activeElement)) return
    nav.querySelector<HTMLButtonElement>(`[data-shell-nav="${page}"]`)?.focus()
  }, [page])
  return (
    <nav ref={ref} aria-label="Pages" className="flex flex-col gap-[2px]" onKeyDown={onKey}>
      {PAGES.map((p, i) => (
        <NavRow key={p.id} id={p.id} label={p.label} Icon={p.icon} on={p.id === page} compact={compact} index={i} />
      ))}
    </nav>
  )
}

/**
 * The account chip: the signed-in learner (the real login, features/auth: avatar initial, name, email), "Not signed
 * in / Sign in to sync" when signed out; the person and the plan under v2Cloud (mock); "This Mac" with login off.
 */
function AccountChip({ compact }: { compact: boolean }): ReactNode {
  const on = useShell((s) => s.page === 'account')
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
      type="button"
      data-shell-account={signedIn ? 'in' : 'out'}
      aria-label={`Account: ${name}. ${line}.`}
      title={compact ? name : undefined}
      className="mg-press relative flex w-full cursor-pointer items-center text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{
        gap: 10,
        padding: compact ? 6 : '8px 10px',
        justifyContent: compact ? 'center' : undefined,
        borderRadius: radius2.card,
        background: on ? fill.navActive : fill.group,
        boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}`,
        outlineColor: focus.dark
      }}
      {...pressMotion()}
      onClick={() => setPage('account')}
    >
      <Avatar initial={initial} size={32} />
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

export function Sidebar({ compact, short }: { compact: boolean; short: boolean }): ReactNode {
  return (
    <aside
      data-shell-sidebar={compact ? 'compact' : 'full'}
      className="flex h-full shrink-0 flex-col"
      style={{ width: compact ? SIDEBAR_COMPACT_W : SIDEBAR_W, padding: compact ? '0 10px 12px' : '0 12px 12px', background: fill.group, boxShadow: `inset -1px 0 0 ${fill.hairline}` }}
    >
      {/* The window's own traffic lights sit here (hiddenInset); this strip drags the window. */}
      <div data-drag className="shrink-0" style={{ height: 40 }} />
      <div data-drag className="flex shrink-0 items-center gap-[8px]" style={{ padding: compact ? '4px 0 20px' : '4px 10px 20px', justifyContent: compact ? 'center' : undefined }}>
        <MiyagiMark size={compact ? 22 : 20} />
        {!compact && <MiyagiWordmark height={16} className="h-[16px] w-auto" />}
      </div>
      <Nav compact={compact} />
      <div className="mt-auto flex flex-col gap-[10px]" style={{ paddingTop: 16 }}>
        {!compact && !short && <StatusArea plan={false} />}
        <AccountChip compact={compact} />
      </div>
    </aside>
  )
}
