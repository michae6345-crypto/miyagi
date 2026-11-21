/**
 * Feature: shell. The account sheet: sign-in and the account live INSIDE the home window (sheet.ts has the kinds).
 *
 * Motion (UI-POLISH-SPEC 5, the house spring, transform and opacity only):
 *   open     the content area dims (a scrim fades in, the sidebar stays lit), the sheet slides down 16 px from the top
 *            of the content area while its surface fades in, then its rows rise 6 px one after another (35 ms apart).
 *            The learner's avatar is a shared element: it flies from the sidebar's account chip into the sheet's
 *            header (layoutId), and back into the chip on close.
 *   switch   Account → Sign out, Cancel back, or a sign-in that just finished: the two bodies crossfade at the same
 *            time (popLayout: the old one is lifted out of the flow and fades in 80 ms while the new one's rows rise in
 *            from 20 ms), and the surface springs to the new height (layout, a scale transform with corrected radius;
 *            DarkSheet re-renders in the same commit, so Motion has its before snapshot). Done in under 300 ms.
 *   close    Esc, the backdrop, the sidebar, the close button or ⌘1..⌘6: the sheet lifts 8 px and fades in 120 ms,
 *            faster than it came. Only the chip's avatar flies home (the sheet's copy hides at once, no crossfade), and
 *            the chip rides above the scrim while it flies. To Plans the avatar snaps into the chip: no flight across
 *            the paper sheet. Reduced motion (MotionConfig): fades only.
 * Focus: the sheet takes focus on open, Tab and Shift+Tab stay inside it (everything behind is inert), and focus goes
 * back to whatever opened it on close. A switch moves focus into the new body: Cancel on the sign-out confirm (the
 * safe default), Done on "You're signed in", the Sign out row when Cancel comes back to the account; otherwise the
 * sheet itself. The leaving body is inert.
 *
 * Sign in: the real login's own pieces from features/auth (store: signInWith → auth:google, cancelSignIn → auth:cancel,
 * signOut → auth:sign-out; model: LIVE, PROVIDER_LABEL; Avatar). Login.tsx exports only the whole window view (its
 * ModeSwitch and ProviderBox are private), so the two are re-drawn here faithfully: same copy, same states, same calls.
 * auth:continue is NOT called: main records the learner's choice when the sign-in succeeds (auth.ts decide()), and
 * from the home window continue could open guided setup as a second window (agents/shell.md, Core requests).
 */
import { AnimatePresence, LayoutGroup, motion, useIsPresent, type Variants } from 'motion/react'
import { ChevronRight, KeyRound, LogOut, X } from 'lucide-react'
import { useEffect, useRef, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type ReactNode, type Ref } from 'react'
import { bridge, isElectron } from '../../bridge'
import { color, copy, duration, elevation, fill, focus, highlight, paper, radius2, scrim, spring, stagger, surface, type2 } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { pressMotion, riseItem } from '../../core/ui/motion'
import { planLabel, v2Cloud } from '../account/model'
import { Pricing } from '../account/Pricing'
import { loadAccount, signOut as signOutMock, useAccount } from '../account/store'
import { AppleGlyph, Chip, GoogleGlyph, MeterGroup, Note, TextLink } from '../account/ui'
import { Avatar } from '../auth/Avatar'
import { LIVE, PROVIDER_LABEL, type Mode, type Provider } from '../auth/model'
import { cancelSignIn, loadAuth, openLegal, setMode, signInWith, signOut as signOutAuth, useAuth } from '../auth/store'
import { Ring } from '../library/motion'
import { backFromSheet, closeSheet, isSheetKind, openSheet, registerSheetHost, useSheet, type SheetKind } from './sheet'
import { PAGES, setPage, setSettingsSection } from './store'

/** The sidebar chip's avatar and the sheet's are one element (Sidebar.tsx renders it too). */
export const AVATAR_ID = 'shell-account-avatar'
const SHEET_W = 480
const SHEET_TOP = 20
/** The content area dims to about 45% black: the spotlight scrim at two thirds (opacity, so no new color). */
const DIM = 0.66

/** "across Macs" on a Mac, "across computers" elsewhere. */
const acrossMachines = (): string => (bridge.platform.os === 'mac' ? 'across Macs' : 'across computers')

// ---- the shared avatar ------------------------------------------------------------------------------------------------

/**
 * The learner's avatar as a shared element (layoutId): wherever it renders last, it flies there on the house spring.
 * Its face (person glyph, or the initial once signed in) crossfades with a small scale, so a sign-in that lands while
 * the sheet is open turns the glyph into the initial in place.
 *
 * One avatar at a time: no crossfade between the two copies (layoutCrossfade false hides the one left behind), and a
 * copy inside a leaving sheet hides at once, so nothing trails the real one home.
 *   snap     land without a flight (the chip, when the Plans sheet takes over from the account sheet)
 *   onFlight called with true when a flight starts and false when it ends (the chip lifts itself above the scrim)
 */
export function SharedAvatar({ initial, size, snap, onFlight }: { initial?: string; size: number; snap?: boolean; onFlight?: (on: boolean) => void }): ReactNode {
  const present = useIsPresent()
  const flight = useRef(onFlight)
  flight.current = onFlight
  useEffect(() => () => flight.current?.(false), [])
  return (
    <motion.span
      layoutId={AVATAR_ID}
      layoutCrossfade={false}
      transition={snap ? { duration: 0 } : spring}
      onLayoutAnimationStart={() => flight.current?.(true)}
      onLayoutAnimationComplete={() => flight.current?.(false)}
      className="relative block shrink-0"
      style={{ width: size, height: size, borderRadius: radius2.round, visibility: present ? undefined : 'hidden' }}
    >
      <AnimatePresence initial={false} mode="popLayout">
        <motion.span
          key={initial ?? 'person'}
          className="absolute inset-0 block"
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.85, transition: { duration: duration.fast } }}
          transition={{ ...spring, opacity: { duration: duration.base } }}
        >
          <Avatar initial={initial} size={size} />
        </motion.span>
      </AnimatePresence>
    </motion.span>
  )
}

// ---- motion -----------------------------------------------------------------------------------------------------------

/** The sheet: slides down 16 px on the spring (no fade, so the flying avatar stays solid); leaves up 8 px, fading. */
const sheetV: Variants = {
  hidden: { y: -16 },
  shown: { y: 0, opacity: 1, transition: { ...spring, delayChildren: (i: number) => 0.04 + Math.min(i, stagger.cap - 1) * stagger.each } },
  gone: { y: -8, opacity: 0, transition: { duration: duration.fast } }
}
/** Its surface fades in fast, ahead of the content, so text never sits on a half-clear sheet. */
const surfaceV: Variants = {
  hidden: { opacity: 0 },
  shown: { opacity: 1, transition: { duration: duration.instant, delay: 0 } }
}
/**
 * A body: its rows rise in one after another (riseItem). On open they wait for the header (100 ms); on a switch they
 * start almost at once (20 ms) while the old body, lifted out of the flow (popLayout), fades out in 80 ms.
 */
const bodyV: Variants = {
  hidden: {},
  shown: (swap: boolean) => ({ opacity: 1, transition: { delayChildren: (i: number) => (swap ? 0.02 : 0.1) + Math.min(i, stagger.cap - 1) * stagger.each } }),
  gone: { opacity: 0, transition: { duration: duration.instant } }
}

// ---- small pieces -----------------------------------------------------------------------------------------------------

function CloseButton({ onPaper }: { onPaper?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      aria-label="Close"
      data-shell-sheet-close
      className={`mg-press ${onPaper ? 'mg-press-light' : ''} grid shrink-0 cursor-pointer place-items-center`}
      style={{ width: 28, height: 28, borderRadius: radius2.round, background: onPaper ? paper.field : fill.button, color: onPaper ? paper.ink : color.label, boxShadow: onPaper ? `inset 0 0 0 1px ${paper.border}` : highlight.topSoft }}
      {...pressMotion()}
      onClick={closeSheet}
    >
      <X aria-hidden size={14} strokeWidth={2} />
    </motion.button>
  )
}

/** One row of the account sheet: icon, label, an optional word on the right, a chevron. Neutral chrome. */
function SheetRow({ icon: I, label, right, onClick, chevron = true }: { icon: typeof KeyRound; label: string; right?: string; onClick: () => void; chevron?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      variants={riseItem}
      data-shell-sheet-row={label}
      className="mg-press flex w-full cursor-pointer items-center gap-[12px] text-left"
      style={{ height: 44, padding: '0 12px', borderRadius: radius2.row, color: color.text, fontSize: type2.md }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
    >
      <I aria-hidden size={16} strokeWidth={1.7} className="shrink-0" style={{ color: fill.chipText }} />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {right && <span style={{ fontSize: type2.xs, color: color.label }}>{right}</span>}
      {chevron && <ChevronRight aria-hidden size={14} strokeWidth={1.8} className="shrink-0" style={{ color: color.faint }} />}
    </motion.button>
  )
}

const group: CSSProperties = { padding: 4, borderRadius: radius2.card, background: fill.group, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}` }
const caption: CSSProperties = { fontSize: type2.sm, lineHeight: '20px', color: color.label }

// ---- sign in (features/auth, faithful) --------------------------------------------------------------------------------

const MODES: Array<{ id: Mode; label: string }> = [
  { id: 'new', label: 'New user' },
  { id: 'returning', label: 'Returning user' }
]
const LEAD: Record<Mode, string> = {
  new: 'Make an account. Your lessons and progress follow you.',
  returning: 'Welcome back. Pick up where you left off.'
}
const PROVIDERS: Provider[] = ['google', 'apple', 'github']

function GitHubGlyph(): ReactNode {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"
      />
    </svg>
  )
}
const GLYPH: Record<Provider, () => ReactNode> = { google: GoogleGlyph, apple: AppleGlyph, github: GitHubGlyph }

/** New user / Returning user: a radio group (one tab stop, the arrows move and select); the thumb slides (layoutId). */
function ModeSwitch({ mode }: { mode: Mode }): ReactNode {
  const onKey = (e: ReactKeyboardEvent<HTMLDivElement>): void => {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const i = MODES.findIndex((m) => m.id === mode)
    const next = MODES[(i + step + MODES.length) % MODES.length].id
    setMode(next)
    e.currentTarget.querySelector<HTMLButtonElement>(`[data-shell-mode="${next}"]`)?.focus()
  }
  return (
    <div role="radiogroup" aria-label="Account" onKeyDown={onKey} className="relative flex w-full" style={{ padding: 3, borderRadius: radius2.card, background: surface.well, boxShadow: `${highlight.well}, inset 0 0 0 1px ${surface.border}` }}>
      {MODES.map((m) => {
        const on = m.id === mode
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            data-shell-mode={m.id}
            className="relative flex-1 cursor-pointer font-medium"
            style={{ height: 30, borderRadius: radius2.row - 2, fontSize: type2.sm, color: on ? color.text : color.label }}
            onClick={() => setMode(m.id)}
          >
            {on && <motion.span layoutId="shell-sheet-mode" transition={spring} className="absolute inset-0" style={{ borderRadius: radius2.row - 2, background: fill.segmentOn, boxShadow: `${highlight.top}, ${elevation.raised}` }} />}
            <span className="relative">{m.label}</span>
          </button>
        )
      })}
    </div>
  )
}

function ProviderBox({ p, mode, pending }: { p: Provider; mode: Mode; pending?: Provider }): ReactNode {
  const Glyph = GLYPH[p]
  const live = LIVE[p]
  const waiting = pending === p
  const off = !!pending && !waiting
  const verb = mode === 'new' ? 'Sign up' : 'Sign in'
  const sub = waiting ? 'Finish in your browser' : live ? 'Continue' : 'Soon'
  return (
    <motion.button
      type="button"
      data-shell-provider={p}
      aria-label={live ? `${verb} with ${PROVIDER_LABEL[p]}` : `${PROVIDER_LABEL[p]}, coming soon`}
      aria-busy={waiting || undefined}
      disabled={off}
      className="mg-press flex min-w-0 flex-1 cursor-pointer flex-col items-center justify-center gap-[8px] disabled:cursor-default"
      style={{ height: 96, borderRadius: radius2.chip, backgroundColor: surface.row, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}`, color: color.text, opacity: off || !live ? 0.55 : 1 }}
      {...pressMotion(off || waiting, true)}
      animate={{ opacity: off || !live ? 0.55 : 1 }}
      onClick={() => (waiting ? undefined : void signInWith(p))}
    >
      <span className="grid place-items-center" style={{ height: 22, transform: 'scale(1.3)' }}>
        {waiting ? <Spinner size={13} c={color.text} /> : <Glyph />}
      </span>
      <span className="flex flex-col items-center gap-[1px]">
        <span className="font-semibold" style={{ fontSize: type2.md, lineHeight: '18px' }}>
          {PROVIDER_LABEL[p]}
        </span>
        <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>{sub}</span>
      </span>
    </motion.button>
  )
}

function SignInBody(): ReactNode {
  const mode = useAuth((s) => s.mode)
  const pending = useAuth((s) => s.pending)
  const note = useAuth((s) => s.note)
  return (
    <>
      <motion.div variants={riseItem}>
        <ModeSwitch mode={mode} />
      </motion.div>
      <motion.div variants={riseItem} style={{ minHeight: 20 }}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.p key={mode} className="m-0" style={caption} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: duration.fast }}>
            {LEAD[mode]}
          </motion.p>
        </AnimatePresence>
      </motion.div>
      <motion.div variants={riseItem} className="flex flex-col gap-[10px]">
        <div aria-hidden className="flex items-center gap-[12px]" style={{ fontSize: type2.xs, color: color.label }}>
          {mode === 'new' ? 'Sign up with' : 'Sign in with'}
          <span className="h-px flex-1" style={{ background: fill.hairline }} />
        </div>
        <div className="flex w-full gap-[10px]">
          {PROVIDERS.map((p) => (
            <ProviderBox key={p} p={p} mode={mode} pending={pending} />
          ))}
        </div>
      </motion.div>
      <motion.div variants={riseItem} className="flex h-[20px] items-center gap-[14px]" style={{ fontSize: type2.xs, color: color.label }}>
        {pending ? (
          <>
            <span>Finish signing in in your browser.</span>
            <TextLink onClick={cancelSignIn}>Cancel</TextLink>
          </>
        ) : (
          <>
            <TextLink onClick={closeSheet}>Not now</TextLink>
            <span aria-hidden>·</span>
            <span>
              <TextLink onClick={() => openLegal('terms')}>Terms</TextLink> and <TextLink onClick={() => openLegal('privacy')}>Privacy</TextLink>
            </span>
          </>
        )}
      </motion.div>
      {note && (
        <motion.div variants={riseItem}>
          <Note text={note} />
        </motion.div>
      )}
    </>
  )
}

/** A sign-in that just finished inside the sheet: the avatar has turned into the initial; one Done. */
function SignedInBody(): ReactNode {
  return (
    <>
      <motion.p variants={riseItem} className="m-0" style={caption}>
        {`Your lessons and progress now sync ${acrossMachines()}.`}
      </motion.p>
      <motion.div variants={riseItem}>
        <span data-sheet-focus className="contents">
          <Ring>
            <PrimaryButton size="lg" block label="Done" onClick={closeSheet} />
          </Ring>
        </span>
      </motion.div>
      <motion.span variants={riseItem} style={{ fontSize: type2.xs, color: color.label }}>
        Not you? <TextLink onClick={() => openSheet('signout')}>Sign out</TextLink>
      </motion.span>
    </>
  )
}

// ---- account, sign out ------------------------------------------------------------------------------------------------

const toYourKey = (): void => {
  closeSheet()
  setSettingsSection('account')
  setPage('settings')
}

function AccountBody(): ReactNode {
  const ownKey = useAccount((s) => s.ownKey)
  const account = useAccount((s) => s.account)
  const keyWord = ownKey === undefined ? undefined : ownKey ? 'On' : 'Off'
  const help = v2Cloud ? account?.help : undefined
  return (
    <>
      {v2Cloud && account?.signedIn && (
        <motion.div variants={riseItem}>{help ? <MeterGroup help={help} title="Help this month" count={`${help.used} of ${help.limit}`} label="Help requests used this month" /> : <span style={caption}>Checks never count. Only live help does.</span>}</motion.div>
      )}
      <motion.div variants={riseItem} role="group" aria-label="Account actions" className="flex flex-col" style={group}>
        <SheetRow icon={KeyRound} label="Use your own key" right={keyWord} onClick={toYourKey} />
        <span aria-hidden className="block" style={{ height: 1, margin: '0 12px', background: fill.rule }} />
        <SheetRow icon={LogOut} label="Sign out" onClick={() => openSheet('signout', 'account')} />
      </motion.div>
      {v2Cloud && account?.signedIn && (
        <motion.div variants={riseItem}>
          <Ring>{account.plan === 'free' ? <PrimaryButton size="lg" block label="Upgrade to Pro" onClick={() => openSheet('plans')} /> : <QuietButton size="lg" block label="See plans" onClick={() => openSheet('plans')} />}</Ring>
        </motion.div>
      )}
    </>
  )
}

function SignOutBody(): ReactNode {
  const confirm = (): void => {
    if (v2Cloud && useAccount.getState().account?.signedIn) signOutMock()
    else signOutAuth()
    closeSheet()
  }
  return (
    <motion.div variants={riseItem} className="grid grid-cols-2 gap-[10px]">
      <span data-sheet-focus className="contents">
        <Ring>
          <QuietButton size="lg" block label="Cancel" onClick={backFromSheet} />
        </Ring>
      </span>
      <Ring>
        <PrimaryButton size="lg" block icon={LogOut} label="Sign out" onClick={confirm} />
      </Ring>
    </motion.div>
  )
}

// ---- the panel --------------------------------------------------------------------------------------------------------

type Who = { signedIn: boolean; name?: string; email?: string; initial?: string; plan?: string }

function useWho(): Who {
  const user = useAuth((s) => s.user)
  const account = useAccount((s) => s.account)
  // v2Cloud (mock): the mock account when it has one; otherwise the real login below, like the shipped build.
  if (v2Cloud && account?.signedIn) {
    return { signedIn: true, name: account.name ?? account.email ?? 'Signed in', email: account.name ? account.email : undefined, plan: planLabel(account.plan) }
  }
  if (!user) return { signedIn: false }
  return { signedIn: true, name: user.name ?? user.email, email: user.name ? user.email : undefined, initial: user.avatarInitial }
}

function headerFor(kind: SheetKind, who: Who, signedInHere: boolean): { title: string; sub: string } {
  if (kind === 'signout') return { title: `Sign out of ${copy.name}?`, sub: 'Your lessons and progress stay on this Mac.' }
  if (kind === 'signin' && !who.signedIn) return { title: 'Sign in to sync', sub: `Your lessons and progress, ${acrossMachines()}.` }
  if (kind === 'signin' && signedInHere) return { title: 'You’re signed in', sub: who.email ?? who.name ?? '' }
  return { title: who.name ?? 'Signed in', sub: who.email ?? (who.plan ? `${who.plan} plan` : 'Signed in') }
}

/** A line of header text that crossfades (and rises 4 px) when it changes, e.g. Account → Sign out. */
function Swap({ id, children, style, className }: { id: string; children: ReactNode; style: CSSProperties; className?: string }): ReactNode {
  return (
    <span className="relative block" style={{ minHeight: style.lineHeight }}>
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={id}
          className={`block truncate ${className ?? ''}`}
          style={style}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4, transition: { duration: duration.instant } }}
          transition={{ ...spring, opacity: { duration: duration.base } }}
        >
          {children}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}

type BodyKind = 'signin' | 'signed-in' | 'account' | 'signout'

/**
 * Where focus lands when the body switches: the safe choice on the sign-out confirm (Cancel), Done once signed in,
 * and the Sign out row when Cancel comes back to the account (the row that opened the confirm).
 */
const FOCUS: Partial<Record<BodyKind, string>> = {
  signout: '[data-sheet-focus] button',
  'signed-in': '[data-sheet-focus] button',
  account: '[data-shell-sheet-row="Sign out"]'
}

/** One body. Leaving, it is lifted out of the flow (popLayout) and inert, so focus and clicks only reach the new one. */
function Body({ id, swap, ref, children }: { id: BodyKind; swap: boolean; ref?: Ref<HTMLDivElement>; children: ReactNode }): ReactNode {
  const present = useIsPresent()
  return (
    <motion.div ref={ref} data-shell-sheet-body={id} inert={!present} custom={swap} variants={bodyV} initial="hidden" animate="shown" exit="gone" className="flex flex-col gap-[14px]" style={{ width: '100%' }}>
      {children}
    </motion.div>
  )
}

function DarkSheet({ kind }: { kind: SheetKind }): ReactNode {
  const who = useWho()
  // Subscribed here, not only in SignInBody, so a note that appears or goes re-renders the sheet and the surface's
  // layout spring gets its before snapshot (otherwise the height would jump).
  useAuth((s) => s.note)
  const content = useRef<HTMLDivElement>(null)
  // A sign-in that finished while this sheet was open shows "You're signed in"; open on a signed-in learner, it is the
  // account sheet (a stale "Sign in" button).
  const signedInHere = useRef(false)
  const wasSignedIn = useRef(who.signedIn)
  if (kind === 'signin' && who.signedIn && !wasSignedIn.current) signedInHere.current = true
  wasSignedIn.current = who.signedIn
  const shown: SheetKind = kind === 'account' && !who.signedIn ? 'signin' : kind === 'signin' && who.signedIn && !signedInHere.current ? 'account' : kind
  const body: BodyKind = shown === 'signin' ? (who.signedIn ? 'signed-in' : 'signin') : shown === 'plans' ? 'account' : shown
  const head = headerFor(shown, who, signedInHere.current)

  // A switch (not the first body) starts its rows at once and takes focus into the new body.
  const first = useRef<BodyKind>(body)
  const swapped = useRef(false)
  if (body !== first.current) swapped.current = true
  useEffect(() => {
    if (!swapped.current) return
    const root = content.current
    const at = root?.querySelector<HTMLElement>(`[data-shell-sheet-body="${body}"]`)
    const sel = FOCUS[body]
    const target = (sel && at?.querySelector<HTMLElement>(sel)) || root?.closest<HTMLElement>('[data-shell-sheet]')
    target?.focus({ preventScroll: true })
  }, [body])

  return (
    <LayoutGroup>
      {/* The surface: springs to each body's height (layout: a scale transform, radius and shadow corrected). */}
      <motion.div
        layout
        aria-hidden
        variants={surfaceV}
        transition={{ layout: spring }}
        className="mg-grain absolute inset-0"
        style={{ background: surface.sheet, borderRadius: radius2.sheet, boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.panel}` }}
      />
      <div ref={content} className="relative flex flex-col" style={{ padding: 24, gap: 20 }}>
        <div className="flex items-center gap-[14px]">
          <SharedAvatar initial={who.initial} size={48} />
          <motion.div variants={riseItem} className="flex min-w-0 flex-1 flex-col gap-[2px]">
            <span className="flex min-w-0 items-center gap-[8px]">
              <h2 id="shell-sheet-title" className="m-0 min-w-0 flex-1 font-semibold">
                <Swap id={head.title} style={{ fontSize: type2.lg, lineHeight: '22px', letterSpacing: '-0.01em', color: color.text }}>
                  {head.title}
                </Swap>
              </h2>
              {who.plan && shown === 'account' && <Chip>{who.plan}</Chip>}
            </span>
            <Swap id={head.sub} style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
              {head.sub}
            </Swap>
          </motion.div>
          <motion.div variants={riseItem} className="self-start">
            <CloseButton />
          </motion.div>
        </div>
        <AnimatePresence mode="popLayout" initial={false}>
          <Body key={body} id={body} swap={swapped.current}>
            {body === 'signin' ? <SignInBody /> : body === 'signed-in' ? <SignedInBody /> : body === 'signout' ? <SignOutBody /> : <AccountBody />}
          </Body>
        </AnimatePresence>
      </div>
    </LayoutGroup>
  )
}

function PaperSheet({ width, maxH }: { width: number; maxH: number }): ReactNode {
  const account = useAccount((s) => s.account)
  return (
    <>
      <motion.div aria-hidden variants={surfaceV} className="absolute inset-0" style={{ background: paper.bg, borderRadius: radius2.sheet, boxShadow: `inset 0 0 0 1px ${paper.hairline}, ${elevation.panel}` }} />
      <h2 id="shell-sheet-title" className="sr-only">
        Plans
      </h2>
      <motion.div variants={riseItem} className="relative overflow-y-auto" style={{ maxHeight: maxH, paddingTop: 28, borderRadius: radius2.sheet, color: paper.ink, '--mg-focus': focus.paper } as CSSProperties}>
        <Pricing account={account} width={width} />
      </motion.div>
      <motion.div variants={riseItem} className="absolute" style={{ top: 14, right: 14 }}>
        <CloseButton onPaper />
      </motion.div>
    </>
  )
}

/** Tab and Shift+Tab stay inside the sheet. */
function trapTab(e: ReactKeyboardEvent<HTMLElement>): void {
  if (e.key !== 'Tab') return
  const all = [...e.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter((el) => el.offsetParent !== null)
  if (!all.length) return
  const first = all[0]
  const last = all[all.length - 1]
  const at = document.activeElement
  if (e.shiftKey && (at === first || at === e.currentTarget)) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && at === last) {
    e.preventDefault()
    first.focus()
  }
}

function Sheet({ kind, mainW, mainH }: { kind: SheetKind; mainW: number; mainH: number }): ReactNode {
  const ref = useRef<HTMLDivElement>(null)
  // Leaving, the sheet is only a picture: it stops taking clicks and stops being a dialog at once (the shared avatar's
  // flight back to the chip can keep it in the tree a few hundred ms after it has faded).
  const present = useIsPresent()
  useEffect(() => {
    ref.current?.focus({ preventScroll: true })
  }, [])
  const plans = kind === 'plans'
  const width = plans ? Math.max(320, Math.min(1100, mainW - 48)) : Math.max(300, Math.min(SHEET_W, mainW - 32))
  return (
    <div className="pointer-events-none absolute inset-x-0 z-40 flex justify-center" style={{ top: SHEET_TOP }}>
      <motion.div
        ref={ref}
        role={present ? 'dialog' : undefined}
        aria-modal={present ? 'true' : undefined}
        aria-hidden={present ? undefined : true}
        aria-labelledby="shell-sheet-title"
        data-shell-sheet={kind}
        data-closing={present ? undefined : true}
        data-no-drag
        tabIndex={-1}
        variants={sheetV}
        initial="hidden"
        animate="shown"
        exit="gone"
        onKeyDown={trapTab}
        className="relative"
        style={{ width, outline: 'none', color: color.text, pointerEvents: present ? 'auto' : 'none' }}
      >
        {plans ? <PaperSheet width={width} maxH={mainH - SHEET_TOP * 2} /> : <DarkSheet kind={kind} />}
      </motion.div>
    </div>
  )
}

// ---- the host ---------------------------------------------------------------------------------------------------------

/** Stage only: ?sheet=<kind> opens the window with the sheet showing, for the screenshots. */
const stageSheet: SheetKind | undefined = (() => {
  if (isElectron) return undefined
  const v = new URLSearchParams(location.search).get('sheet')
  return isSheetKind(v) ? v : undefined
})()

/** The dim over the content area. A click on it closes the sheet; leaving, it lets clicks through at once. */
function Scrim(): ReactNode {
  const present = useIsPresent()
  return (
    <motion.div
      data-shell-sheet-scrim
      data-no-drag
      aria-hidden
      className="absolute inset-0 z-30"
      style={{ background: scrim.spotlight, pointerEvents: present ? 'auto' : 'none' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: DIM, transition: { duration: duration.slow } }}
      exit={{ opacity: 0, transition: { duration: duration.base } }}
      onPointerDown={closeSheet}
    />
  )
}

let opener: HTMLElement | null = null
useSheet.subscribe((s, prev) => {
  // Remember what opened the sheet (before the content behind it goes inert and drops focus), and give focus back to it.
  if (s.kind && !prev.kind) opener = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null
  if (!s.kind && prev.kind) {
    const el = opener
    opener = null
    requestAnimationFrame(() => {
      if (el?.isConnected && !el.closest('[inert]')) el.focus({ preventScroll: true })
    })
  }
})

/**
 * Lives inside the content area (<main>): the scrim over the content and the sheet. Shell.tsx makes the sidebar and the
 * pages inert while it is open and closes it on a sidebar click.
 */
export function AccountSheetHost({ mainW, mainH }: { mainW: number; mainH: number }): ReactNode {
  const kind = useSheet((s) => s.kind)

  useEffect(() => {
    const off = registerSheetHost()
    if (stageSheet) setTimeout(() => openSheet(stageSheet), 300)
    // Fresh account data for the chip, the rows and the On / Off of "Use your own key".
    void loadAuth()
    void loadAccount()
    return off
  }, [])
  useEffect(() => {
    if (kind) void loadAccount()
  }, [kind])

  // Esc closes the sheet before anything behind it sees the key (a preview, a skill card, the search). ⌘1..⌘6 close it
  // and still switch the page.
  useEffect(() => {
    if (!kind) return
    const mac = bridge.platform.os === 'mac'
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopImmediatePropagation()
        closeSheet()
        return
      }
      // The same chords Shell.tsx takes for the pages: ⌘1..⌘<pages>, no Alt, no Shift.
      const mod = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey
      const n = Number(e.key)
      if (mod && !e.altKey && !e.shiftKey && Number.isInteger(n) && n >= 1 && n <= PAGES.length) closeSheet()
    }
    addEventListener('keydown', onKey, true)
    return () => removeEventListener('keydown', onKey, true)
  }, [kind])

  return (
    <>
      <AnimatePresence>
        {kind && <Scrim key="scrim" />}
      </AnimatePresence>
      <AnimatePresence>{kind && <Sheet key={kind === 'plans' ? 'paper' : 'dark'} kind={kind} mainW={mainW} mainH={mainH} />}</AnimatePresence>
    </>
  )
}

