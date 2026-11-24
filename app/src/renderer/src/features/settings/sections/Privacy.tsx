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
 *   - Delete account and data (age-delete lane; it replaced Delete my data, which only reached this Mac): an in-place
 *     two-step confirm, no red. The confirm holds "Also delete my lesson folders in ~/miyagi", UNCHECKED (the learner's
 *     own work). privacy/erase.ts runs it: main asks miyagi-cloud to delete the account and this install first; if the
 *     server can't be reached nothing is deleted anywhere and the row offers Try again. Then main wipes everything miyagi
 *     keeps on this Mac (main/features/accountDelete/wipe.ts), the keys leave settings.ts's memory, the session signs
 *     out, and a moment later a built app starts again from the first-run screen (account:restart).
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
import { deleteAccount } from '../privacy/erase'
import { DELETE, POLICY_LINE } from '../privacy/facts'
import '../privacy/deleteWeb'
import { Sees } from '../privacy/Sees'
import { here } from '../here'
import { Group, OnWord, PageHeader, Row, TextButton } from '../ui'
import { takeDeleteAsk } from '../v4/facts'

/** offline: the server couldn't be reached, nothing was deleted. done / pending: deleted; a restart follows. */
type Step = 'idle' | 'confirm' | 'deleting' | 'done' | 'pending' | 'offline' | 'refused'
/** How long the deleted line shows before the app starts again (account:restart). */
const RESTART_MS = 2600

export function Privacy({ secure, onDeleted }: { secure?: boolean; onDeleted: (v: KeysView) => void }): ReactNode {
  const share = usePrefs((s) => s.shareTelemetry)
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
        <DeleteAccount onDeleted={onDeleted} />
      </Group>
    </>
  )
}

/**
 * The Delete account row and its in-place two-step confirm (header above). Privacy and the v4 Your data panel both
 * draw it inside their own group, so Delete account opens its confirm right where it was clicked. `label`, `row` and
 * `button` name the idle row the way the panel around it does.
 */
export function DeleteAccount({
  onDeleted,
  label = DELETE.label,
  row = DELETE.row,
  button = 'Delete'
}: {
  onDeleted?: (v: KeysView) => void
  label?: string
  row?: string
  button?: string
}): ReactNode {
  // The stage's ?confirm=delete opens straight on the confirm.
  const [step, setStep] = useState<Step>(() => (takeDeleteAsk() || stage.confirm === 'delete' ? 'confirm' : 'idle'))
  // Unchecked by default, and again every time the confirm opens: lesson folders are the learner's own work.
  const [lessons, setLessons] = useState(false)
  const [leftovers, setLeftovers] = useState(false)
  const cancelBox = useRef<HTMLSpanElement>(null)
  const box = useRef<HTMLDivElement>(null)
  // The confirm opens with focus on Cancel (the safe default): Enter or Space backs out, Esc too. It is scrolled into
  // view, so the click visibly did something wherever the row sat.
  useEffect(() => {
    if (step !== 'confirm') return
    cancelBox.current?.querySelector('button')?.focus({ preventScroll: true })
    box.current?.scrollIntoView?.({ block: 'nearest' })
  }, [step])

  const open = (): void => {
    setLessons(false)
    setStep('confirm')
  }

  // From the confirm, or Try again after the server couldn't be reached (the learner confirmed already; same choice).
  const erase = async (): Promise<void> => {
    if (step !== 'confirm' && step !== 'offline' && step !== 'refused') return
    setStep('deleting')
    const r = await deleteAccount((channel, payload) => bridge.invoke<unknown>(channel, payload), { lessons })
    if (r.deleted) {
      onDeleted?.(r.deleted.keys)
      setPrefs({ ...DEFAULT_PREFS })
    }
    if (r.signedOut) useAuth.setState({ user: null })
    setLeftovers(!r.local)
    setStep(r.step)
  }

  // Deleted: the line shows for a moment, then a built app starts again from the first-run screen.
  useEffect(() => {
    if (step !== 'done' && step !== 'pending') return
    const t = setTimeout(() => void bridge.invoke('account:restart').catch(() => undefined), RESTART_MS)
    return () => clearTimeout(t)
  }, [step])

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

  /** The server couldn't be reached, or couldn't delete the account: nothing was deleted, Try again runs it again. */
  const retry = step === 'offline' || step === 'refused'
  const deletedLine = step === 'pending' ? DELETE.pending : leftovers ? DELETE.partial : DELETE.done

  return (
    <>
        {step === 'confirm' || step === 'deleting' ? (
          <div ref={box} data-delete-step={step}>
            <Row
              minH={64}
              label={DELETE.confirmLabel}
              caption={
                <span className="flex flex-col gap-[10px]">
                  <span>
                    {here(DELETE.confirm)} {DELETE.undo}
                  </span>
                  <label data-delete-lessons className="flex min-h-[28px] cursor-pointer items-center gap-[10px]" style={{ fontSize: type2.sm, color: color.text }}>
                    <input
                      type="checkbox"
                      checked={lessons}
                      disabled={step === 'deleting'}
                      onChange={(e) => setLessons(e.target.checked)}
                      style={{ width: 16, height: 16, margin: 0, accentColor: color.accent }}
                    />
                    {DELETE.lessons}
                  </label>
                </span>
              }
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
          </div>
        ) : (
          <div data-delete-step={step}>
            <Row
              minH={64}
              label={label}
              caption={
                step === 'offline' || step === 'refused' ? (
                  <span role="alert" style={{ color: color.text }}>
                    {step === 'offline' ? DELETE.offline : DELETE.refused}
                  </span>
                ) : step === 'done' || step === 'pending' ? (
                  <span role="status" style={{ color: color.text }}>
                    {here(deletedLine)} {DELETE.restart}
                  </span>
                ) : (
                  row
                )
              }
              right={
                step === 'done' || step === 'pending' ? (
                  <OnWord>Deleted</OnWord>
                ) : (
                  <OutlineButton label={retry ? 'Try again' : button} aria={retry ? 'Try deleting again' : label} onClick={retry ? () => void erase() : open} />
                )
              }
            />
          </div>
        )}
    </>
  )
}

/** Delete is always an outline, never the white primary: the first one only asks, the second one is not the default. */
function OutlineButton({ label, onClick, aria = DELETE.label }: { label: string; onClick: () => void; aria?: string }): ReactNode {
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
