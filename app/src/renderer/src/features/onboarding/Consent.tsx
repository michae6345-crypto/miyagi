/**
 * Feature: onboarding. The consent screen (launch register R05 and R06): what miyagi sends and to whom, that it is AI,
 * and "By continuing you agree to the terms and privacy policy", before guided setup asks macOS for anything.
 *
 *   body     v4 (v4.tsx SetupPage, left-aligned, top-anchored): the bonsai (the shared element MARK_ID: it glides in
 *            from the login, then on to the strip), the title and one hairline group: each row one line and one line
 *            of detail under it (copy: consentCopy.ts)
 *   actions  the "I agree" line with the terms and privacy policy linked (common/consent.ts LEGAL_URL, through
 *            open:external), and right under it the ONE primary, Continue, which matches "By continuing"
 *
 * Continue calls the store's agree() (main stamps prefs.consent with this build's version and its own clock) and only
 * then onDone(): setup and its prompts come after. Nothing is captured while this is on screen. Enter presses Continue
 * unless focus is on a link. There is no Skip: without consent the gate stays closed. "Not now" (quiet, beside
 * Continue) quits miyagi cleanly, so leaving is never hard (age-delete lane, main agegate:quit).
 * Used by the home window's first-run flow (features/shell/flow, chrome 'flow') and the standalone setup window
 * (Onboarding.tsx, chrome 'window': a drag strip under the traffic lights instead of the flow's step strip).
 * Neutral chrome only (BRAND.md): no pastel, no hue, no icon tiles.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { color, spring } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { TextLink } from '../account/ui'
import { openLegal } from '../auth/store'
import { AGREE, AGREE_FAILED, CONSENT_ROWS, CONSENT_TITLE, CONTINUE } from './consentCopy'
import { bridge } from '../../bridge'
import { MARK_ID } from './Intro'
import { agree } from './store'
import { Actions, FLOW_TOP, Rise, SetupGroup, SetupPage, SetupRow, SetupTitle } from './v4'

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

  // v4 (Nov 24, v4.tsx): the same top-anchored page as the setup steps, left-aligned, one column (no rail: every line
  // here is the point). The tree (the shared MARK_ID), the title, one hairline group of what miyagi sends (no icon
  // tiles), then the "I agree" line right above the ONE primary it matches, Continue, and Not now beside it.
  return (
    <div data-onb-chrome={chrome} className="flex h-full w-full flex-col">
      {chrome === 'window' && <header data-drag className="mg-flow-head mg-lights-pad shrink-0" />}
      <div className="relative min-h-0 flex-1">
        <SetupPage view="consent" labelledBy="onb-consent-title" top={chrome === 'flow' ? FLOW_TOP : undefined} enterDelay={enterDelay}>
          <motion.div layoutId={MARK_ID} className="relative" style={{ width: 40, height: 40, marginBottom: 18 }} transition={{ layout: spring }}>
            <MiyagiMark size={40} />
          </motion.div>
          <SetupTitle id="onb-consent-title" title={CONSENT_TITLE} />
          <Rise style={{ marginTop: 22 }} data={{ 'data-consent-rows': true }}>
            <SetupGroup label={CONSENT_TITLE}>
              {CONSENT_ROWS.map((r) => (
                <SetupRow key={r.id} name={r.line} line={r.detail} data={{ 'data-consent-row': r.id }} />
              ))}
            </SetupGroup>
          </Rise>
          <Rise style={{ marginTop: 16 }}>
            <span className="flex flex-col gap-[2px]" style={{ fontSize: 12.5, lineHeight: '18px', color: color.label }}>
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
          </Rise>
          <Actions style={{ marginTop: 12 }}>
            <span data-onb-primary data-label={CONTINUE}>
              <PrimaryButton label={CONTINUE} busy={busy} disabled={busy} onClick={() => void go()} />
            </span>
            {/* age-delete lane: never a trap. Not now quits miyagi cleanly (agegate:quit); nothing was agreed or sent. */}
            <span data-consent-not-now>
              <QuietButton label="Not now" disabled={busy} onClick={() => void bridge.invoke('agegate:quit').catch(() => undefined)} />
            </span>
          </Actions>
        </SetupPage>
      </div>
    </div>
  )
}
