/**
 * Feature: signincard. The two calm surfaces out of the island:
 *
 *   SignInCard  "Sign in to build new lessons" / "Lessons you've opened still work." Sign in (the ONE primary) starts
 *               the Google flow; Not now (quiet) and Esc close it. While the browser is out, Sign in spins.
 *   CapLine     one line: what ran out and when it comes back, in local time. Esc closes it; it leaves on its own.
 *   RegionLine  "miyagi isn't available in your region yet." (451 region_unavailable). No Sign in: it would not help.
 *               Not now and Esc close it.
 *
 * No hue for any of it (no red, no amber): this is information, the lesson still builds on this Mac.
 */
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { fade } from '../../core/ui/motion'
import { color, spring, type2 } from '../../core/theme'
import { useAuth } from '../auth/store'
import { REGION_LINE, SIGNIN } from './notice'
import { closeCap, closeRegion, notNow, setVisible, signIn, useSignInCard } from './store'

function useShown(which: 'signin' | 'cap' | 'region'): void {
  useEffect(() => {
    setVisible(which, true)
    return () => setVisible(which, false)
  }, [which])
}

/** Parts settle in one after another (40 ms apart); reduced motion keeps only the fade. */
function usePart(): (i: number) => Record<string, unknown> {
  const reduce = useReducedMotion()
  return (i) => {
    const delay = reduce ? 0 : 0.05 + i * 0.04
    return {
      initial: reduce ? { opacity: 0 } : { opacity: 0, y: 6 },
      animate: { opacity: 1, y: 0 },
      transition: { ...spring, delay, opacity: { ...fade.in, delay } }
    }
  }
}

export function SignInCard(): ReactNode {
  useShown('signin')
  const part = usePart()
  const busy = useAuth((s) => s.pending === 'google')
  const tried = useSignInCard((s) => s.tried)
  const note = useAuth((s) => s.note)
  return (
    <div data-hit data-signincard="signin" role="dialog" aria-labelledby="signincard-title" className="flex flex-col" style={{ padding: 20, gap: 16, color: color.text }}>
      <motion.div {...part(0)} className="flex min-h-[22px] items-center justify-between gap-3">
        <MiyagiMark size={18} />
        <Keycap k="dismiss" />
      </motion.div>
      <motion.div {...part(1)} className="flex flex-col" style={{ gap: 6 }}>
        <h2 id="signincard-title" className="m-0" style={{ fontSize: type2.lg, lineHeight: '22px', fontWeight: 600 }}>
          {SIGNIN.title}
        </h2>
        <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
          {SIGNIN.body}
        </p>
      </motion.div>
      <motion.div {...part(2)} className="grid grid-cols-2" style={{ gap: 8 }}>
        <QuietButton size="lg" block label={SIGNIN.notNow} onClick={notNow} />
        <PrimaryButton size="lg" block label={SIGNIN.signIn} busy={busy} onClick={signIn} />
      </motion.div>
      {tried && !busy && note && (
        <p role="status" className="m-0" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
          {note}
        </p>
      )}
    </div>
  )
}

export function RegionLine(): ReactNode {
  useShown('region')
  const part = usePart()
  return (
    <motion.div
      {...part(0)}
      data-hit
      data-signincard="region"
      role="status"
      aria-live="polite"
      className="flex items-center"
      style={{ padding: '8px 8px 8px 16px', gap: 10, color: color.text, fontSize: type2.sm, lineHeight: '18px', fontWeight: 500 }}
    >
      <MiyagiMark size={16} />
      <span className="min-w-0 flex-1">{REGION_LINE}</span>
      <QuietButton label={SIGNIN.notNow} onClick={closeRegion} />
      <Keycap k="dismiss" />
    </motion.div>
  )
}

/** The 56 slot: the region line when there is one (it outlasts a cap), else the cap line. */
export function NoticeLine(): ReactNode {
  return useSignInCard((s) => !!s.region) ? <RegionLine /> : <CapLine />
}

export function CapLine(): ReactNode {
  useShown('cap')
  const part = usePart()
  // Keep "4:00 PM" on one line when the line has to wrap.
  const line = useSignInCard((s) => s.cap?.line ?? '').replace(/(\d)[ \u202f](AM|PM)\b/g, '$1\u00a0$2')
  return (
    <motion.div
      {...part(0)}
      data-hit
      data-signincard="cap"
      role="status"
      aria-live="polite"
      className="flex items-center"
      style={{ padding: '12px 12px 12px 16px', gap: 10, color: color.text, fontSize: type2.sm, lineHeight: '18px', fontWeight: 500 }}
      onClick={closeCap}
    >
      <MiyagiMark size={16} />
      <span className="min-w-0 flex-1">{line}</span>
      <Keycap k="dismiss" />
    </motion.div>
  )
}
