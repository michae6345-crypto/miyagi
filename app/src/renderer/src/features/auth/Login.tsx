/**
 * Feature: auth. "miyagi login": the bonsai and the title up top, New user / Returning user, and three sign-on boxes
 * along the bottom (Google live; Apple and GitHub placeholders that send nothing). Signed in, the boxes give way to
 * "Signed in as …" and one Continue button that opens guided setup.
 *
 * Neutral only (BRAND.md): white on dark, no provider brand fills, no hue for status. Copy stays short.
 */
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, copy, fill, font, radius2, spring, surface, type2 } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { PrimaryButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { openLink } from '../account/store'
import { AppleGlyph, GoogleGlyph, Note, TextLink } from '../account/ui'
import { MARK_ID } from './Intro'
import { LIVE, PROVIDER_LABEL, type Mode, type Provider } from './model'
import { cancelSignIn, continueToSetup, setMode, signInWith, signOut, useAuth } from './store'

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

function ModeSwitch({ mode }: { mode: Mode }): ReactNode {
  return (
    <div role="radiogroup" aria-label="Account" className="relative flex" style={{ padding: 3, borderRadius: radius2.card, background: surface.well, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
      {MODES.map((m) => {
        const on = m.id === mode
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={on}
            data-auth-mode={m.id}
            className="relative cursor-pointer font-medium"
            style={{ height: 32, width: 140, borderRadius: radius2.row, fontSize: type2.sm, color: on ? color.text : color.label }}
            onClick={() => setMode(m.id)}
          >
            {on && <motion.span layoutId="auth-mode-pill" transition={spring} className="absolute inset-0" style={{ borderRadius: radius2.row, background: surface.rowHover, boxShadow: `inset 0 0 0 1px ${surface.border}` }} />}
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
  const verb = mode === 'new' ? 'Sign up' : 'Sign in'
  const sub = waiting ? 'Finish in your browser' : live ? 'Continue' : 'Soon'
  return (
    <motion.button
      type="button"
      data-auth-provider={p}
      aria-label={live ? `${verb} with ${PROVIDER_LABEL[p]}` : `${PROVIDER_LABEL[p]}, coming soon`}
      aria-busy={waiting || undefined}
      disabled={!!pending && !waiting}
      className="flex min-w-0 flex-1 cursor-pointer flex-col items-center justify-center gap-[10px] disabled:cursor-default"
      style={{
        height: 112,
        borderRadius: radius2.group,
        backgroundColor: surface.row,
        boxShadow: `inset 0 0 0 1px ${surface.border}`,
        color: color.text,
        opacity: (!!pending && !waiting) || !live ? 0.55 : 1
      }}
      whileHover={pending ? undefined : { backgroundColor: surface.rowHover }}
      whileTap={pending ? undefined : { scale: 0.98 }}
      transition={{ duration: 0.12 }}
      onClick={() => (waiting ? undefined : void signInWith(p))}
    >
      <span className="grid place-items-center" style={{ height: 24, transform: 'scale(1.4)' }}>
        {waiting ? <Spinner size={14} c={color.text} /> : <Glyph />}
      </span>
      <span className="flex flex-col items-center gap-[2px]">
        <span className="font-semibold" style={{ fontSize: type2.md, lineHeight: '18px' }}>
          {PROVIDER_LABEL[p]}
        </span>
        <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>{sub}</span>
      </span>
    </motion.button>
  )
}

function SignedIn({ name, email }: { name?: string; email?: string }): ReactNode {
  return (
    <motion.div key="signed-in" data-auth-signed-in initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={spring} className="flex w-full max-w-[360px] flex-col items-center gap-[16px]">
      <div className="flex w-full flex-col items-center gap-[4px] text-center" style={{ padding: '16px 20px', borderRadius: radius2.group, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
        <span style={{ fontSize: type2.xs, color: color.label }}>Signed in as</span>
        <span className="font-semibold" style={{ fontSize: type2.body, color: color.text }}>
          {name ?? email}
        </span>
        {name && email && <span style={{ fontSize: type2.sm, color: color.label }}>{email}</span>}
      </div>
      <PrimaryButton size="lg" block label="Continue" onClick={continueToSetup} />
      <span style={{ fontSize: type2.xs, color: color.label }}>
        Not you? <TextLink onClick={signOut}>Sign out</TextLink>
      </span>
    </motion.div>
  )
}

export function Login(): ReactNode {
  const mode = useAuth((s) => s.mode)
  const pending = useAuth((s) => s.pending)
  const user = useAuth((s) => s.user)
  const note = useAuth((s) => s.note)

  return (
    <motion.section
      data-auth-login
      aria-labelledby="auth-title"
      className="absolute inset-0 flex flex-col items-center"
      style={{ padding: '44px 40px 20px' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.24, delay: 0.08 }}
    >
      <div className="flex flex-col items-center gap-[14px] text-center">
        <motion.div layoutId={MARK_ID} transition={spring}>
          <MiyagiMark size={56} />
        </motion.div>
        <h1 id="auth-title" className="m-0" style={{ fontFamily: font.brand, fontSize: 28, lineHeight: '34px', fontWeight: 600, letterSpacing: '-0.02em', color: color.text }}>
          {`${copy.name} login`}
        </h1>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-[16px]">
        <AnimatePresence mode="wait" initial={false}>
          {user ? (
            <SignedIn name={user.name} email={user.email} />
          ) : (
            <motion.div key="choose" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={spring} className="flex flex-col items-center gap-[14px]">
              <ModeSwitch mode={mode} />
              <AnimatePresence mode="wait" initial={false}>
                <motion.p key={mode} className="m-0 text-center" style={{ fontSize: type2.md, lineHeight: '20px', color: color.label }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
                  {LEAD[mode]}
                </motion.p>
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {!user && (
        <div className="flex w-full max-w-[600px] flex-col items-center gap-[14px]">
          <div className="flex w-full items-center gap-[12px]" style={{ fontSize: type2.xs, color: color.label }} aria-hidden>
            <span className="h-px flex-1" style={{ background: fill.hairline }} />
            {mode === 'new' ? 'Sign up with' : 'Sign in with'}
            <span className="h-px flex-1" style={{ background: fill.hairline }} />
          </div>
          <div className="flex w-full gap-[12px]">
            {PROVIDERS.map((p) => (
              <ProviderBox key={p} p={p} mode={mode} pending={pending} />
            ))}
          </div>
          <div className="flex h-[20px] items-center gap-[16px]" style={{ fontSize: type2.xs, color: color.label }}>
            {pending ? (
              <TextLink onClick={cancelSignIn}>Cancel</TextLink>
            ) : (
              <>
                <TextLink onClick={continueToSetup}>Continue without an account</TextLink>
                <span aria-hidden>·</span>
                <span>
                  <TextLink onClick={() => openLink('terms')}>Terms</TextLink> and <TextLink onClick={() => openLink('privacy')}>Privacy</TextLink>
                </span>
              </>
            )}
          </div>
        </div>
      )}
      <div className="w-full" style={{ marginTop: 8 }}>
        <Note text={note} />
      </div>
    </motion.section>
  )
}
