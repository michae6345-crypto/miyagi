/**
 * Feature: agegate. The under-13 screen: "miyagi is for people 13 and up" and one kind line. Final: no way past it.
 *
 * Signed in (a learner who signed in before the age step existed, or on another Mac): their account and data must be
 * deletable right here. One primary, Delete my account, then a two-step confirm (Delete is still not the default:
 * Cancel takes focus, Esc backs out). It runs Settings' Delete account flow (settings/privacy/erase.ts deleteAccount):
 * the server first, nothing deleted if it can't be reached or refuses, then the wipe, the sign-out and a restart.
 * main keeps the block itself through the wipe (accountDelete.ts), so deleting can't reopen the birthday screen.
 * The session is kept until then on purpose: signing out first would leave no access token to delete the account with.
 * While blocked the launch gate stays closed (auth.ts needsLogin): no overlay, no lessons, no sync.
 *
 * Always: a quiet "Quit miyagi" (agegate:quit), so the screen is never a trap. No red, no hue.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { color, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { fade } from '../../core/ui/motion'
import { TextLink } from '../account/ui'
import { useAuth } from '../auth/store'
import { deleteAccount, wiped, type EraseStep } from '../settings/privacy/erase'
import { DELETE } from '../settings/privacy/facts'
import { COPY, Frame } from './Steps'

type Step = 'offer' | 'confirm' | 'deleting' | EraseStep
const RESTART_MS = 2600

export const BLOCKED_COPY = {
  signedIn: 'You can delete your miyagi account and data now.',
  offer: 'Delete my account',
  confirm: 'Deletes your account and everything miyagi keeps. Cannot be undone.',
  done: 'Your account and data are deleted.',
  quit: 'Quit miyagi'
} as const

export function Blocked(): ReactNode {
  const user = useAuth((s) => s.user)
  const [step, setStep] = useState<Step>('offer')
  const cancelBox = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (step === 'confirm') cancelBox.current?.querySelector('button')?.focus({ preventScroll: true })
    if (step !== 'confirm') return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      e.stopPropagation()
      setStep('offer')
    }
    addEventListener('keydown', onKey, true)
    return () => removeEventListener('keydown', onKey, true)
  }, [step])

  useEffect(() => {
    if (!wiped(step)) return
    const t = setTimeout(() => void bridge.invoke('account:restart').catch(() => undefined), RESTART_MS)
    return () => clearTimeout(t)
  }, [step])

  const run = async (): Promise<void> => {
    setStep('deleting')
    const r = await deleteAccount((c, p) => bridge.invoke<unknown>(c, p), { lessons: false })
    if (r.signedOut) useAuth.setState({ user: null })
    setStep(r.step)
  }

  // Shown while signed in, and through the delete's own outcome (the sign-out clears the user mid-way).
  const deleting = step !== 'offer' || !!user
  const line = step === 'done' ? BLOCKED_COPY.done : step === 'pending' ? DELETE.pending : step === 'email' ? DELETE.email : step === 'offline' ? DELETE.offline : step === 'refused' ? DELETE.refused : undefined

  return (
    <Frame
      title={COPY.blockedTitle}
      line={COPY.blockedLine}
      footer={
        <span style={{ fontSize: type2.sm, color: color.label }}>
          <TextLink weight={500} onClick={() => void bridge.invoke('agegate:quit').catch(() => undefined)}>
            {BLOCKED_COPY.quit}
          </TextLink>
        </span>
      }
    >
      {deleting && (
        <div data-age-delete={step} className="mt-[28px] flex w-full flex-col items-center gap-[14px] text-center">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={line ?? step}
              role={line ? 'status' : undefined}
              style={{ fontSize: type2.sm, lineHeight: '20px', color: line ? color.text : color.label }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={fade.in}
            >
              {line ?? (step === 'confirm' || step === 'deleting' ? BLOCKED_COPY.confirm : BLOCKED_COPY.signedIn)}
            </motion.span>
          </AnimatePresence>
          {step === 'offer' && <PrimaryButton size="lg" block label={BLOCKED_COPY.offer} onClick={() => setStep('confirm')} />}
          {(step === 'offline' || step === 'refused') && <PrimaryButton size="lg" block label="Try again" onClick={() => void run()} />}
          {(step === 'confirm' || step === 'deleting') && (
            <div className="flex w-full gap-[8px]">
              <span className="flex flex-1">
                <QuietButton size="lg" block label={step === 'deleting' ? 'Deleting' : 'Delete'} busy={step === 'deleting'} disabled={step === 'deleting'} onClick={() => void run()} />
              </span>
              <span ref={cancelBox} className="flex flex-1">
                <PrimaryButton size="lg" block label="Cancel" keyName="dismiss" disabled={step === 'deleting'} onClick={() => setStep('offer')} />
              </span>
            </div>
          )}
        </div>
      )}
    </Frame>
  )
}
