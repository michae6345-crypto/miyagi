/**
 * Feature: auth. "Sign in to miyagi", lighter (Michael, Nov 21): one big primary, Continue with Google; a quiet line
 * "Apple · GitHub · coming soon"; "Continue without an account" under it. No New / Returning toggle (it only changed
 * the copy; the Google call is the same).
 *
 *   waiting   the button morphs into "Waiting for Google…" (spinner for the glyph, one faint band crossing it on a
 *             slow loop: transform only, no gradient), with "Finish in your browser · Cancel" under it. Esc cancels.
 *             The wait ends at once (store.ts, R20) on Cancel here, on Cancel in Google's page (main's auth:attempt),
 *             or when the learner comes back to miyagi from the browser without finishing.
 *   failed    main's plain-words reason (the sign-in fix, model.ts reasonLine) fades in under the button, with
 *             Try again. A cancel gets a calm line too ("Sign-in cancelled."). No shake, no hue.
 *   signed in "Signed in as …" and one Continue.
 *
 * Used twice: inside the home window's first-run flow (features/shell/flow: `onContinue` moves the flow on to setup)
 * and in the standalone login window (AuthView: the Account page's Sign in, a fallback). The bonsai at the top is the
 * shared element (MARK_ID): it glides in from the intro and on to the next screen.
 * Neutral only (BRAND.md): white on dark, no provider brand colors, no hue for status. Copy stays short.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { color, copy, duration, elevation, fill, font, highlight, radius2, spring, surface, tint, type2 } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { StatusGlyph } from '../../core/ui/status'
import { ease, pressMotion } from '../../core/ui/motion'
import { AppleGlyph, GoogleGlyph, TextLink } from '../account/ui'
import { MARK_ID } from '../onboarding/Intro'
import { AgeFirst } from '../agegate/AgeFirst'
import { Avatar } from './Avatar'
import { cancelSignIn, continueToSetup, leaveSignIn, openLegal, signInWith, signOut, useAuth } from './store'

const fade = { duration: duration.base, ease: ease.out }

function GitHubGlyph({ size = 16 }: { size?: number }): ReactNode {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"
      />
    </svg>
  )
}

/** The waiting shimmer: one faint ink band crossing the white button (opacity breath with reduced motion). */
function Shimmer(): ReactNode {
  const reduce = useReducedMotion() ?? false
  return (
    <motion.span
      aria-hidden
      data-auth-shimmer
      className="pointer-events-none absolute bottom-0 top-0 block w-[34%]"
      style={{ left: 0, background: tint.hoverOnLight, borderRadius: radius2.card }}
      initial={reduce ? { opacity: 0, x: '97%' } : { x: '-110%' }}
      animate={reduce ? { opacity: [0, 1, 0] } : { x: '310%' }}
      transition={reduce ? { duration: 2.2, ease: ease.inOut, repeat: Infinity } : { duration: 1.8, ease: ease.inOut, repeat: Infinity, repeatDelay: 0.4 }}
    />
  )
}

/** The one primary: Continue with Google, morphing into Waiting for Google… while the browser is open. */
function GoogleButton({ waiting }: { waiting: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      data-auth-provider="google"
      data-button="primary"
      aria-busy={waiting || undefined}
      aria-label={waiting ? 'Waiting for Google. Finish signing in in your browser.' : 'Continue with Google'}
      // Waiting keeps the white slab (no held press tint: the shimmer says it is working, not that it is off).
      className={`${waiting ? '' : 'mg-press mg-press-light cursor-pointer'} relative flex h-[48px] w-full items-center justify-center gap-[10px] overflow-hidden`}
      style={{
        borderRadius: radius2.card,
        backgroundColor: color.accent,
        color: color.onAccent,
        fontSize: type2.body,
        fontWeight: 600,
        boxShadow: waiting ? `${highlight.onLight}, ${highlight.base}` : `${highlight.onLight}, ${highlight.base}, ${elevation.raised}`
      }}
      {...pressMotion(waiting)}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => (waiting ? undefined : void signInWith('google'))}
    >
      {waiting && <Shimmer />}
      <span className="relative grid h-[18px] w-[18px] place-items-center">
        <AnimatePresence initial={false} mode="popLayout">
          <motion.span key={waiting ? 'spin' : 'g'} className="flex" initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.7 }} transition={spring}>
            {waiting ? <Spinner size={15} c={color.onAccent} track={fill.onAccentKey} /> : <GoogleGlyph />}
          </motion.span>
        </AnimatePresence>
      </span>
      <span className="relative grid">
        <AnimatePresence initial={false} mode="popLayout">
          <motion.span key={waiting ? 'w' : 'c'} className="whitespace-nowrap" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ y: spring, opacity: fade }}>
            {waiting ? 'Waiting for Google…' : 'Continue with Google'}
          </motion.span>
        </AnimatePresence>
      </span>
    </motion.button>
  )
}

function SignedIn({ name, email, initial, onContinue }: { name?: string; email?: string; initial: string; onContinue: () => void }): ReactNode {
  return (
    <motion.div key="signed-in" data-auth-signed-in initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ y: spring, opacity: fade }} className="flex w-full flex-col items-center gap-[16px]">
      <div className="flex w-full items-center gap-[14px] text-left" style={{ padding: '14px 16px', borderRadius: radius2.group, background: surface.row, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}` }}>
        <Avatar initial={initial} size={40} />
        <span className="flex min-w-0 flex-col gap-[2px]">
          <span style={{ fontSize: type2.xs, color: color.label }}>Signed in as</span>
          <span className="truncate font-semibold" style={{ fontSize: type2.body, color: color.text }}>
            {name ?? email}
          </span>
          {name && email && (
            <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
              {email}
            </span>
          )}
        </span>
      </div>
      <PrimaryButton size="lg" block label="Continue" onClick={onContinue} />
      <span style={{ fontSize: type2.xs, color: color.label }}>
        Not you? <TextLink onClick={signOut}>Sign out</TextLink>
      </span>
    </motion.div>
  )
}

/**
 * The failure line: main's reason in plain words, and the one thing that can help. Fades in; never shakes. Redraft
 * (Michael's audit: "a failed login looks like the normal login"): the hollow Not yet ring and full-contrast words, so
 * it reads as a state, never red. When trying again can't help (Google sign-in not set up), the action is Continue
 * without an account, not Try again.
 */
function Failure({ text, onWithout }: { text: string; onWithout: () => void }): ReactNode {
  const retry = /try again/i.test(text) || !/continue without an account/i.test(text)
  // The action below says it: don't say it twice.
  const line = text.replace(/\s*Try again\.?$/, '').replace(/\s*Continue without an account( for now)?\.?$/, '')
  return (
    <motion.div
      key="fail"
      role="alert"
      data-auth-failure={retry ? 'retry' : 'without'}
      className="flex flex-col items-center gap-[8px] text-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: duration.fast } }}
      transition={{ duration: duration.slow, ease: ease.out }}
    >
      <span className="flex items-center gap-[8px]" style={{ fontSize: type2.md, lineHeight: '20px', color: color.text, maxWidth: 380 }}>
        <StatusGlyph state="notyet" size={16} still />
        <span>{line}</span>
      </span>
      <span style={{ fontSize: type2.sm }}>
        <TextLink weight={500} onClick={retry ? () => void signInWith('google') : onWithout}>
          {retry ? 'Try again' : 'Continue without an account'}
        </TextLink>
      </span>
    </motion.div>
  )
}

/**
 * Esc while the browser sign-in runs cancels it (main closes its loopback listener) instead of leaving a sign-in that
 * keeps waiting; leaving this screen mid-wait (the flow moving on, the window closing) cancels it too. Here, in the
 * login itself, so both hosts (the home window's flow and the standalone login window) behave the same.
 */
function useCancelOnEsc(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape' || !useAuth.getState().pending) return
      e.preventDefault()
      e.stopPropagation()
      cancelSignIn()
    }
    addEventListener('keydown', onKey, true)
    return () => {
      removeEventListener('keydown', onKey, true)
      // Quietly: no "Sign-in cancelled." left behind for the next visit. Also ends a listener main kept up after the
      // wait ended (Cancel on Google's page, coming back to miyagi).
      leaveSignIn()
    }
  }, [])
}

/** The age step (features/agegate) comes first in every host, before Google and before the guest path. */
export function Login(props: { onContinue?: () => void } = {}): ReactNode {
  return (
    <AgeFirst>
      <SignIn {...props} />
    </AgeFirst>
  )
}

function SignIn({ onContinue }: { onContinue?: () => void }): ReactNode {
  useCancelOnEsc()
  const pending = useAuth((s) => s.pending)
  const user = useAuth((s) => s.user)
  const note = useAuth((s) => s.note)
  const waiting = pending === 'google'
  const done = (): void => {
    continueToSetup()
    onContinue?.()
  }

  return (
    <motion.section
      data-auth-login
      data-auth-state={user ? 'signed-in' : waiting ? 'waiting' : note ? 'failed' : 'idle'}
      aria-labelledby="auth-title"
      className="absolute inset-0 flex flex-col items-center justify-center"
      style={{ padding: '40px 40px 28px' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: duration.slow, delay: 0.08, ease: ease.out }}
    >
      <div className="flex w-full max-w-[360px] flex-col items-center">
        <motion.div layoutId={MARK_ID} transition={spring}>
          <MiyagiMark size={56} />
        </motion.div>
        <h1 id="auth-title" className="m-0 mt-[20px] text-center" style={{ fontFamily: font.brand, fontSize: type2.xxl, lineHeight: '34px', fontWeight: 500, letterSpacing: '-0.4px', color: color.text }}>
          {user ? "You're signed in" : `Sign in to ${copy.name}`}
        </h1>
        <p className="m-0 mt-[8px] text-center" style={{ fontSize: type2.body, lineHeight: '22px', color: color.label }}>
          Your lessons and progress follow you to any computer.
        </p>

        <div className="mt-[32px] flex w-full flex-col items-center">
          <AnimatePresence mode="wait" initial={false}>
            {user ? (
              <SignedIn key="in" name={user.name} email={user.email} initial={user.avatarInitial} onContinue={done} />
            ) : (
              <motion.div key="out" className="flex w-full flex-col items-center gap-[14px]" exit={{ opacity: 0, y: -6, transition: { duration: duration.fast } }}>
                <GoogleButton waiting={waiting} />
                <div className="flex min-h-[44px] w-full flex-col items-center justify-start">
                  <AnimatePresence mode="wait" initial={false}>
                    {waiting ? (
                      <motion.span key="wait" data-auth-waiting className="flex items-center gap-[8px]" style={{ fontSize: type2.sm, color: color.label }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={fade}>
                        Finish in your browser
                        <span aria-hidden>·</span>
                        <TextLink onClick={cancelSignIn}>Cancel</TextLink>
                      </motion.span>
                    ) : note ? (
                      <Failure key="fail" text={note} onWithout={done} />
                    ) : (
                      // What signing in shares, plainly (age-delete lane).
                      <motion.span key="shares" data-auth-shares style={{ fontSize: type2.sm, color: color.label }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={fade}>
                        Google shares your name, email and photo with miyagi.
                      </motion.span>
                    )}
                  </AnimatePresence>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <div className="absolute bottom-[28px] left-0 right-0 flex flex-col items-center gap-[10px]">
        {!user && (
          <motion.span initial={false} animate={{ opacity: waiting ? 0.4 : 1 }} transition={fade} style={{ fontSize: type2.sm, color: color.label }}>
            <TextLink weight={500} onClick={waiting ? () => undefined : done}>
              Continue without an account
            </TextLink>
          </motion.span>
        )}
        <span style={{ fontSize: type2.xs, color: color.faint }}>
          <TextLink onClick={() => openLegal('terms')}>Terms</TextLink> and <TextLink onClick={() => openLegal('privacy')}>Privacy</TextLink>
        </span>
      </div>
    </motion.section>
  )
}
