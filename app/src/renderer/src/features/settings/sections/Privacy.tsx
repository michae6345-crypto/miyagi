/**
 * Feature: settings. Privacy (Set-Privacy), the honest subset (BUILD-PLAN Section 6, ROADMAP 5.4):
 *   - "What miyagi sees" (privacy/Sees.tsx): every source from privacy/facts.ts, the one list web/privacy.md quotes,
 *     each with "On this Mac" or where it goes;
 *   - Privacy policy opens https://miyagi.study/privacy through the existing external-link path (auth openLegal);
 *   - the Lesson progress sync and Anonymous usage counts switches are HIDDEN (nothing syncs or counts this push);
 *   - "See what was sent" is hidden (the privacy log is deferred);
 *   - "Share crash reports and usage" (prefs.shareTelemetry, ROADMAP 1.6 / 1.7): off by default for everyone, applies at
 *     once. On (and only once the login gate is open): main/features/telemetry.ts sends crash kinds and lesson counts
 *     (numbers and enums only, a crash is just {kind, app_version}) to miyagi-cloud POST /v1/events; the error text
 *     never leaves this Mac.
 *   - Delete my data is an in-place two-step confirm and erases what lives on this Mac: the keys (main, keys.bin), the
 *     sign-in (main removes auth.bin, login.json and cloud-link.json, then auth:sign-out, awaited, forgets the
 *     session and revokes it) and the preferences. privacy/erase.ts picks the step: a sign-out that fails is "partial", never "Deleted".
 *     It says "on this Mac" because that is all it can reach; lesson folders in ~/miyagi stay (the learner's own
 *     work, kept by the engine) and the confirm says so.
 */
import { motion } from 'motion/react'
import { Activity } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { DEFAULT_PREFS } from '../../../../../common/prefs'
import { bridge } from '../../../bridge'
import { setPrefs, usePrefs } from '../../../core/prefs'
import { PrimaryButtonV2, QuietButton, Toggle } from '../../../core/ui/atoms'
import { color, type2 } from '../../../core/theme'
import { pressMotion } from '../../../core/ui/motion'
import { openLegal, useAuth } from '../../auth/store'
import { stage } from '../env'
import type { KeysView } from '../keys'
import { eraseData } from '../privacy/erase'
import { DELETE, POLICY_LINE, onThisComputer } from '../privacy/facts'
import { Sees } from '../privacy/Sees'
import { Group, OnWord, PageHeader, Row, TextButton } from '../ui'

/** The Windows build says the same about its own machine: "this computer", never "this Mac" or the Keychain. */
const ON_MAC = bridge.platform.os === 'mac'
const HERE = ON_MAC ? 'this Mac' : 'this computer'


/** partial: keys and settings went, but a sign-in file could not be removed (main says signIn: false). */
type Step = 'idle' | 'confirm' | 'deleting' | 'done' | 'partial' | 'failed'

export function Privacy({ secure, onDeleted }: { secure?: boolean; onDeleted: (v: KeysView) => void }): ReactNode {
  const [step, setStep] = useState<Step>(stage.confirm === 'delete' ? 'confirm' : 'idle')
  const cancelBox = useRef<HTMLSpanElement>(null)
  const share = usePrefs((s) => s.shareTelemetry)
  // The confirm opens with focus on Cancel (the safe default): Enter or Space backs out, Esc too.
  useEffect(() => {
    if (step === 'confirm') cancelBox.current?.querySelector('button')?.focus({ preventScroll: true })
  }, [step])

  const erase = async (): Promise<void> => {
    if (step !== 'confirm') return
    setStep('deleting')
    // privacy/erase.ts: delete the files, then await auth:sign-out (main's auth feature owns the session in memory).
    // A sign-out that fails or doesn't answer true shows "partial": auth.ts would still hold the session.
    const r = await eraseData((channel) => bridge.invoke<unknown>(channel))
    if (r.deleted) {
      onDeleted(r.deleted.keys)
      setPrefs({ ...DEFAULT_PREFS })
    }
    if (r.signedOut) useAuth.setState({ user: null })
    setStep(r.step)
  }

  // Esc backs out of the confirm before it closes the sheet. Window capture phase, because focus is usually
  // outside this section (the first Delete never takes focus), so a local onKeyDown would never see it.
  useEffect(() => {
    if (step !== 'confirm') return
    const h = (e: globalThis.KeyboardEvent): void => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      e.stopPropagation()
      setStep('idle')
    }
    addEventListener('keydown', h, true)
    return () => removeEventListener('keydown', h, true)
  }, [step])

  return (
    <>
      <PageHeader title="Privacy" caption="What miyagi sees, and where it goes." />

      <Sees secure={secure} />

      <Group label="Help improve miyagi">
        <Row
          minH={64}
          icon={Activity}
          label="Share crash reports and usage"
          caption="Errors and lesson counts. Never your code or screen."
          right={<Toggle label="Share crash reports and usage" on={share === true} onChange={(v) => setPrefs({ shareTelemetry: v })} />}
        />
      </Group>

      <Group label="Your data">
        <Row minH={64} label="Privacy policy" caption={POLICY_LINE} right={<TextButton label="Open" onClick={() => openLegal('privacy')} />} />
        {step === 'confirm' || step === 'deleting' ? (
          <Row
            minH={64}
            label={DELETE.confirmLabel}
            caption={DELETE.confirm}
            right={
              // The safe choice is the default: Cancel is the white primary and takes focus; Delete is only an outline.
              <div className="flex shrink-0 items-center gap-[8px]">
                {step === 'deleting' ? (
                  <QuietButton label="Deleting" busy disabled onClick={() => undefined} />
                ) : (
                  <OutlineButton label="Delete" aria={DELETE.confirmLabel} onClick={() => void erase()} />
                )}
                <span ref={cancelBox} className="contents">
                  <PrimaryButtonV2 label="Cancel" onClick={() => setStep('idle')} disabled={step === 'deleting'} keyName="dismiss" />
                </span>
              </div>
            }
          />
        ) : (
          <Row
            minH={64}
            label="Delete my data"
            caption={
              step === 'failed' || step === 'partial' ? (
                <span style={{ color: color.text }}>{step === 'failed' ? DELETE.failed : DELETE.partial}</span>
              ) : (
                onThisComputer(DELETE.row, ON_MAC)
              )
            }
            right={step === 'done' ? <OnWord>{`Deleted from ${HERE}`}</OnWord> : <OutlineButton label="Delete" onClick={() => setStep('confirm')} />}
          />
        )}
      </Group>
    </>
  )
}

/** Delete is always an outline, never the white primary: the first one only asks, the second one is not the default. */
function OutlineButton({ label, onClick, aria = 'Delete my data' }: { label: string; onClick: () => void; aria?: string }): ReactNode {
  return (
    <motion.button
      type="button"
      aria-label={aria}
      className="mg-press h-[32px] shrink-0 cursor-pointer whitespace-nowrap rounded-[8px] px-[16px] font-medium"
      style={{ fontSize: type2.xs, color: color.text, boxShadow: `inset 0 0 0 1px ${color.faint}` }}
      {...pressMotion()}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
    </motion.button>
  )
}
