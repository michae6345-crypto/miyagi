/**
 * Feature: agegate. The age step in front of the sign-in. features/auth/Login.tsx wraps its screen in this, so every
 * host of the login gets it: the home window's first-run flow (features/shell/flow) and the standalone login window
 * (AuthView, the Account page's Sign in). "Continue without an account" lives on the login screen, so the signed-out
 * path is gated too; main refuses auth:google and auth:continue before the step as well (main/features/agegate.ts).
 *
 *   birthday → under 13   Blocked, final. Only {blockedUntil} is saved (main keeps it against a re-entry).
 *            → 13 to 17   Guardian (the box starts unchecked) → saves {band '13-17'} → the sign-in
 *            → 18 and up  saves {band '18+'} → the sign-in
 *   On record already (an earlier run): straight to the sign-in, or straight to Blocked while the block holds.
 *
 * Back and Esc: Guardian → birthday; the sign-in → birthday (only when the step ran in this visit, and not while a
 * Google sign-in waits: Login's own Esc cancels that); on the birthday screen Esc clears the pickers. Blocked has none.
 *
 * Motion (house tokens, core/ui/motion; the spec's numbers in agents/age-delete.md): each screen is absolutely placed,
 * so the old one leaves while the new one arrives. Forward: the old screen slides 16 px left and fades (fade.out,
 * 120 ms), the new one comes in from 24 px right on the spring with a 180 ms fade, three beats late (the bonsai,
 * the shared MARK_ID, stays put between them). Back runs the other way. Blocked arrives as a slower rise (8 px, fade
 * slow). Reduced motion (MotionConfig reducedMotion="user", main.tsx) drops the travel and keeps the fades.
 */
import { AnimatePresence, motion, useReducedMotion, type Variants } from 'motion/react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { color, type2 } from '../../core/theme'
import { beat, enter, fade } from '../../core/ui/motion'
import { TextLink } from '../account/ui'
import { loadAuth, useAuth } from '../auth/store'
import { ageCleared, bandRecord, blockActive, decide, todayOf, type Birth } from './age'
import { Blocked } from './Blocked'
import { Birthday, COPY, Guardian } from './Steps'
import { loadAge, saveAge, useAge } from './store'

export type AgeView = 'birthday' | 'guardian' | 'blocked' | 'through'

/** Travel (px) and timing, from the house tokens. */
export const AGE_MOTION = { inX: 24, outX: 16, delay: 3 * beat, blockedRise: 8 } as const

const views: Variants = {
  from: (dir: number) => (dir === 0 ? { opacity: 0 } : { opacity: 0, x: AGE_MOTION.inX * dir }),
  shown: { opacity: 1, x: 0, y: 0, transition: enter(AGE_MOTION.delay) },
  gone: (dir: number) => ({ opacity: 0, x: -AGE_MOTION.outX * dir, transition: fade.out })
}
const blocked: Variants = {
  from: (dir: number) => (dir === 0 ? { opacity: 0 } : { opacity: 0, y: AGE_MOTION.blockedRise }),
  shown: { opacity: 1, x: 0, y: 0, transition: enter(AGE_MOTION.delay, fade.slow) },
  gone: { opacity: 0, transition: fade.out }
}

export function AgeFirst({ children }: { children: ReactNode }): ReactNode {
  const loaded = useAge((s) => s.loaded)
  const record = useAge((s) => s.record ?? undefined)
  const today = useMemo(() => todayOf(), [])
  /** The view this visit is on; undefined until main answered (then it follows the record). */
  const [view, setView] = useState<AgeView | undefined>(undefined)
  /** 1 forward, -1 back, 0 the first screen (a fade only). */
  const [dir, setDir] = useState(0)
  /** The step ran in this visit (so the sign-in offers Back). */
  const [ran, setRan] = useState(false)
  /** Bumped by Esc on the birthday screen: the pickers start empty again. */
  const [round, setRound] = useState(0)
  const user = useAuth((s) => s.user)
  // Reduced motion: MotionConfig would snap an exit's x to its end in one frame; here nothing travels at all (0).
  const reduce = useReducedMotion() ?? false
  const travel = reduce ? 0 : dir

  useEffect(() => {
    void loadAge()
    void loadAuth() // the blocked screen offers Delete my account to a signed-in learner
  }, [])

  // What the record says, whenever it changes (main's answer, Delete account's wipe): a block always wins.
  const fromRecord: AgeView | undefined = !loaded ? undefined : blockActive(record, today) ? 'blocked' : ageCleared(record, today) ? 'through' : 'birthday'
  useEffect(() => {
    if (!fromRecord) return
    setView((v) => {
      if (fromRecord === 'blocked') return 'blocked'
      if (v === undefined || fromRecord === 'birthday') return fromRecord
      return v
    })
  }, [fromRecord])

  const go = (next: AgeView, d: number): void => {
    setDir(d)
    setView(next)
  }

  const onBirthday = (b: Birth): void => {
    const r = decide(b, today) // the date goes no further than this line
    setRan(true)
    if (r.kind === 'blocked') {
      go('blocked', 1)
      void saveAge(r.record)
    } else if (r.kind === 'teen') go('guardian', 1)
    else void saveAge(bandRecord('18+', today)).then((s) => go(blockActive(s ?? undefined, today) ? 'blocked' : 'through', 1))
  }
  const onGuardian = (): void => void saveAge(bandRecord('13-17', today)).then((s) => go(blockActive(s ?? undefined, today) ? 'blocked' : 'through', 1))
  const back = (): void => go('birthday', -1)

  // Esc: one step back (see the header). Capture phase, before the flow's own keys; never while Google is pending.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape' || e.defaultPrevented || e.isComposing) return
      if (view === 'birthday') return setRound((r) => r + 1)
      if (view === 'guardian' || (view === 'through' && ran && !useAuth.getState().pending && !useAuth.getState().user)) {
        e.preventDefault()
        e.stopPropagation()
        back()
      }
    }
    addEventListener('keydown', onKey, true)
    return () => removeEventListener('keydown', onKey, true)
  }, [view, ran])

  return (
    <div data-age-step={view ?? 'loading'} className="absolute inset-0">
      <AnimatePresence custom={travel} initial={false}>
        {view && (
          <motion.div
            key={view}
            data-age-view={view}
            className="absolute inset-0"
            custom={travel}
            variants={view === 'blocked' ? blocked : views}
            initial="from"
            animate="shown"
            exit="gone"
          >
            {view === 'birthday' && <Birthday key={round} today={today} onDone={onBirthday} />}
            {view === 'guardian' && <Guardian onDone={onGuardian} onBack={back} />}
            {view === 'blocked' && <Blocked />}
            {view === 'through' && children}
            {view === 'through' && ran && !user && (
              // Below the standalone login window's traffic lights; in the flow, under the step strip.
              <span data-age-back className="absolute left-[24px] top-[44px]" style={{ fontSize: type2.sm, color: color.label }}>
                <TextLink onClick={back}>{COPY.back}</TextLink>
              </span>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
