/**
 * Feature: onboarding. The consent screen (launch register R05 and R06): what miyagi sends and to whom, that it is AI,
 * and "By continuing you agree to the terms and privacy policy", before guided setup asks macOS for anything.
 *
 *   body     the bonsai (the shared element MARK_ID: it glides in from the login, then on to the strip), the title and
 *            one short list: each row one line and one line of detail under it (copy: consentCopy.ts)
 *   footer   the "I agree" line with the terms and privacy policy linked (common/consent.ts LEGAL_URL, through
 *            open:external), and the ONE primary, Continue, which matches "By continuing"
 *
 * Continue calls the store's agree() (main stamps prefs.consent with this build's version and its own clock) and only
 * then onDone(): setup and its prompts come after. Nothing is captured while this is on screen. Enter presses Continue
 * unless focus is on a link. There is no Skip: without consent the gate stays closed (quit miyagi to leave).
 * Used by the home window's first-run flow (features/shell/flow, chrome 'flow') and the standalone setup window
 * (Onboarding.tsx, chrome 'window': a drag strip under the traffic lights instead of the flow's step strip).
 * Neutral chrome only (BRAND.md): no pastel, no hue; the icons sit in neutral tiles.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { AppWindow, Info, Monitor, Video, type LucideIcon } from 'lucide-react'
import { color, fill, font, highlight, radius2, spring, surface, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { fade } from '../../core/ui/motion'
import { TextLink } from '../account/ui'
import { openLegal } from '../auth/store'
import { AGREE, AGREE_FAILED, CONSENT_ROWS, CONSENT_TITLE, CONTINUE, type ConsentRowId } from './consentCopy'
import { MARK_ID } from './Intro'
import { rise, stagger } from './parts'
import { agree } from './store'

const ICON: Record<ConsentRowId, LucideIcon> = { screen: Monitor, videos: Video, private: AppWindow, ai: Info }

export function Consent({ onDone, chrome = 'flow', enterDelay = 0 }: { onDone: () => void; chrome?: 'window' | 'flow'; enterDelay?: number }): ReactNode {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const go = useCallback(async () => {
    if (busy) return
    setBusy(true)
    setFailed(false)
    const ok = await agree()
    setBusy(false)
    if (ok) onDone()
    else setFailed(true)
  }, [busy, onDone])

  // Enter presses Continue, unless the learner is on a link or another control (Tab moves between them as usual).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Enter' || e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (t && t.closest('button, input, textarea, select, a')) return
      e.preventDefault()
      void go()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go])

  return (
    <div data-onb-view="consent" data-onb-chrome={chrome} role="dialog" aria-labelledby="onb-consent-title" className="flex h-full w-full flex-col">
      {chrome === 'window' && <header data-drag className="mg-flow-head mg-lights-pad shrink-0" />}

      <main className="relative min-h-0 flex-1 overflow-y-auto">
        <motion.div
          variants={stagger(enterDelay)}
          initial="hidden"
          animate="shown"
          className="mx-auto flex min-h-full w-full max-w-[580px] flex-col items-center justify-center px-[32px] py-[24px] text-center"
        >
          <motion.div layoutId={MARK_ID} className="relative" style={{ width: 40, height: 40 }} transition={{ layout: spring }}>
            <MiyagiMark size={40} />
          </motion.div>
          <motion.h1
            id="onb-consent-title"
            variants={rise}
            className="m-0 mt-[18px]"
            style={{ fontFamily: font.brand, fontSize: type2.xxl, lineHeight: '34px', fontWeight: 500, letterSpacing: '-0.4px', color: color.text }}
          >
            {CONSENT_TITLE}
          </motion.h1>
          <motion.ul
            variants={rise}
            data-consent-rows
            className="m-0 mt-[24px] w-full list-none p-0 text-left"
            style={{ borderRadius: radius2.group, background: surface.row, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}` }}
          >
            {CONSENT_ROWS.map((r, i) => {
              const Icon = ICON[r.id]
              return (
                <li key={r.id} data-consent-row={r.id} className="flex items-start gap-[14px] px-[16px] py-[14px]" style={{ borderTop: i > 0 ? `1px solid ${fill.hairline}` : undefined }}>
                  <span aria-hidden className="mt-[1px] grid h-[32px] w-[32px] shrink-0 place-items-center" style={{ borderRadius: radius2.control, background: surface.sheet, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
                    <Icon size={16} strokeWidth={1.75} color={color.text} />
                  </span>
                  <span className="flex min-w-0 flex-col gap-[2px]">
                    <span style={{ fontSize: type2.body, lineHeight: '22px', fontWeight: 500, color: color.text }}>{r.line}</span>
                    <span style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>{r.detail}</span>
                  </span>
                </li>
              )
            })}
          </motion.ul>
        </motion.div>
      </main>

      <motion.footer className="flex min-h-[84px] shrink-0 items-center justify-between gap-[24px] px-[40px] py-[12px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ...fade.in, delay: enterDelay }}>
        <span className="flex min-w-0 flex-col gap-[2px]" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
          <span data-consent-agree>
            {AGREE.lead}
            <TextLink onClick={() => openLegal('terms')}>{AGREE.terms}</TextLink>
            {AGREE.and}
            <TextLink onClick={() => openLegal('privacy')}>{AGREE.privacy}</TextLink>
            {AGREE.end}
          </span>
          <span data-consent-failed={failed || undefined} aria-live="polite" style={{ color: color.text }}>
            {failed ? AGREE_FAILED : null}
          </span>
        </span>
        <span data-onb-primary data-label={CONTINUE}>
          <PrimaryButton size="lg" label={CONTINUE} busy={busy} disabled={busy} onClick={() => void go()} />
        </span>
      </motion.footer>
    </div>
  )
}
