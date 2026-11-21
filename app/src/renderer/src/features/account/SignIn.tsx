/**
 * Plan-SignIn. UI only in this push (v2Cloud): no OAuth, no magic link, no network. Every button says so in one calm
 * line and sends nothing; the email lives in this component's state only and is cleared on submit (never stored,
 * never logged, never put in a URL). Terms and Privacy open through main's fixed links.
 */
import { useState, type FormEvent, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { PrimaryButton } from '../../core/ui/buttons'
import { GlassCard } from '../../core/ui/GlassCard'
import { MiyagiMark } from '../../core/ui/Mark'
import { color, copy, fill, radius2, surface, type2 } from '../../core/theme'
import { looksLikeEmail } from './model'
import { openLink, say } from './store'
import { AppleGlyph, GlyphButton, GoogleGlyph, TextLink } from './ui'

const NOT_LIVE = 'Sign in is not live yet. Nothing was sent.'

export function SignIn(): ReactNode {
  const [email, setEmail] = useState('')
  const ok = looksLikeEmail(email)
  const submit = (e?: FormEvent): void => {
    e?.preventDefault()
    if (!ok) return
    setEmail('')
    say(NOT_LIVE)
  }
  const where = bridge.platform.os === 'mac' ? 'on every Mac' : 'on every computer'
  return (
    <GlassCard surface="panel" width={400} padding={32} style={{ display: 'flex', borderRadius: radius2.launcher }}>
      <section aria-labelledby="account-si-title" className="flex w-full flex-col gap-[20px]">
        <div className="flex flex-col items-center gap-[8px] text-center">
          <span style={{ marginBottom: 8 }}>
            <MiyagiMark size={40} />
          </span>
          <h1 id="account-si-title" className="m-0 font-semibold" style={{ fontSize: 22, lineHeight: '28px', letterSpacing: '-0.015em', color: color.text }}>
            {`Sign in to ${copy.name}`}
          </h1>
          <p className="m-0" style={{ fontSize: type2.md, lineHeight: '20px', color: color.label }}>
            {`Your lessons and progress, ${where}.`}
          </p>
        </div>

        <div className="flex flex-col gap-[8px]">
          <GlyphButton glyph={<AppleGlyph />} label="Continue with Apple" onClick={() => say(NOT_LIVE)} />
          <GlyphButton glyph={<GoogleGlyph />} label="Continue with Google" onClick={() => say(NOT_LIVE)} />
        </div>

        <div aria-hidden className="flex items-center gap-[12px]" style={{ fontSize: type2.xs, color: color.label }}>
          <span className="h-px flex-1" style={{ background: fill.hairline }} />
          or
          <span className="h-px flex-1" style={{ background: fill.hairline }} />
        </div>

        <form className="m-0 flex flex-col gap-[12px]" onSubmit={submit} noValidate>
          <div className="flex flex-col gap-[8px]">
            <label htmlFor="account-si-email" className="font-medium" style={{ fontSize: type2.sm, lineHeight: '16px', color: color.label }}>
              Email
            </label>
            <input
              id="account-si-email"
              type="email"
              autoComplete="email"
              spellCheck={false}
              autoCapitalize="off"
              maxLength={254}
              placeholder="name@school.edu"
              value={email}
              className="w-full outline-none"
              style={{ height: 44, padding: '0 14px', borderRadius: radius2.card, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text, fontSize: type2.md }}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <PrimaryButton size="lg" block label="Email me a sign-in link" disabled={!ok} onClick={() => submit()} />
        </form>

        <p className="m-0 text-center" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
          No password needed. By continuing you accept the <TextLink onClick={() => openLink('terms')}>Terms</TextLink> and{' '}
          <TextLink onClick={() => openLink('privacy')}>Privacy Policy</TextLink>.
        </p>
      </section>
    </GlassCard>
  )
}
