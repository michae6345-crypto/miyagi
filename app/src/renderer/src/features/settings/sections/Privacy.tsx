/**
 * Feature: settings. Privacy (Set-Privacy), the honest subset (BUILD-PLAN Section 6):
 *   - what leaves this Mac, said plainly: screenshots and code go to the AI provider during lessons;
 *   - the Lesson progress sync and Anonymous usage counts switches are HIDDEN (nothing syncs or counts this push);
 *   - "See what was sent" is hidden (the privacy log is deferred);
 *   - "Share crash reports and usage" (prefs.shareTelemetry, ROADMAP 1.6 / 1.7): off by default for everyone, applies at
 *     once. On: main/features/telemetry.ts sends scrubbed crash lines and lesson counts (the engine its own counts).
 *   - Delete my data is an in-place two-step confirm and erases what lives on this Mac: the keys (main, keys.bin) and
 *     the preferences. It says "on this Mac" because that is all it can reach.
 */
import { motion } from 'motion/react'
import { Activity, Camera, CodeXml, KeyRound } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { DEFAULT_PREFS } from '../../../../../common/prefs'
import { bridge } from '../../../bridge'
import { setPrefs, usePrefs } from '../../../core/prefs'
import { PrimaryButtonV2, QuietButton, Toggle } from '../../../core/ui/atoms'
import { color, type2 } from '../../../core/theme'
import { pressMotion } from '../../../core/ui/motion'
import { stage } from '../env'
import type { DeleteResult, KeysView } from '../keys'
import { Group, OnWord, PageHeader, Plain, Row } from '../ui'

type Step = 'idle' | 'confirm' | 'deleting' | 'done' | 'failed'

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
    try {
      const r = await bridge.invoke<DeleteResult>('settings:delete')
      if (!r?.ok) throw new Error('not deleted')
      onDeleted(r.keys)
      setPrefs({ ...DEFAULT_PREFS })
      setStep('done')
    } catch {
      setStep('failed')
    }
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
      <PageHeader title="Privacy" caption="What leaves your Mac, and when." />

      <Group label="What leaves your Mac" inset={64}>
        <Row minH={64} icon={Camera} label="Screenshots" caption="Sent to the AI provider during a lesson, to follow your step." right={<Plain>Lessons only</Plain>} />
        <Row minH={64} icon={CodeXml} label="Your code and text" caption="Sent to the AI provider when miyagi checks or helps." right={<Plain>Lessons only</Plain>} />
        <Row
          minH={64}
          icon={KeyRound}
          label="Your API keys"
          caption={secure === false ? 'Kept in memory for this run, sent only to their provider.' : 'Kept in your Mac’s Keychain, sent only to their provider.'}
          right={<Plain>On this Mac</Plain>}
        />
      </Group>

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
        {step === 'confirm' || step === 'deleting' ? (
          <Row
            minH={64}
            label="Delete everything on this Mac?"
            caption="Your keys and settings. Cannot be undone."
            right={
              // The safe choice is the default: Cancel is the white primary and takes focus; Delete is only an outline.
              <div className="flex shrink-0 items-center gap-[8px]">
                {step === 'deleting' ? (
                  <QuietButton label="Deleting" busy disabled onClick={() => undefined} />
                ) : (
                  <OutlineButton label="Delete" aria="Delete everything on this Mac" onClick={() => void erase()} />
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
              step === 'failed' ? (
                <span style={{ color: color.text }}>Couldn’t delete. Nothing was removed.</span>
              ) : (
                'Erases your keys and settings on this Mac. Cannot be undone.'
              )
            }
            right={step === 'done' ? <OnWord>Deleted from this Mac</OnWord> : <OutlineButton label="Delete" onClick={() => setStep('confirm')} />}
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
