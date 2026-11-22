/**
 * Feature: reminders. The one-time offer, grown out of the island after the first finished lesson (store.ts arms it):
 * "Want a nudge when a review is due?" Yes is the one primary; Not now (Esc) is quiet. Either answer is final, and
 * Settings can change it any time. Calm copy, no hue: nothing here is a status.
 */
import { useEffect, type ReactNode } from 'react'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { color, type2 } from '../../core/theme'
import { fmtTime } from './logic'
import { answerOffer, setShowing, useReminders } from './store'

export const OFFER_W = 380

export function OfferCard(): ReactNode {
  const time = useReminders((r) => r.s?.time)
  useEffect(() => {
    setShowing(true)
    return () => setShowing(false)
  }, [])
  const at = time !== undefined ? fmtTime(time) : '6:00 PM'
  return (
    <section aria-labelledby="reminders-offer-title" data-reminders="offer" data-hit className="flex flex-col" style={{ width: OFFER_W, padding: 20, gap: 16 }}>
      <div className="flex min-h-[22px] items-center justify-between gap-3">
        <span className="flex items-center gap-[8px]" style={{ fontSize: type2.xs, color: color.label }}>
          <MiyagiMark size={14} />
          Reminders
        </span>
        <Keycap k="dismiss" />
      </div>

      <div className="flex">
        <div className="flex min-w-0 flex-col gap-[6px]">
          <h1 id="reminders-offer-title" className="m-0 font-semibold" style={{ fontSize: type2.lg, lineHeight: '22px', letterSpacing: '-0.01em', color: color.text }}>
            Want a nudge when a review is due?
          </h1>
          <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
            One quiet reminder at {at}, only on days something is due.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-[8px]">
        <QuietButton label="Not now" size="lg" block onClick={() => answerOffer(false)} />
        <PrimaryButton label="Remind me" size="lg" block onClick={() => answerOffer(true)} />
      </div>
      <p className="m-0" style={{ fontSize: type2.xs, color: color.faint }}>
        Change the time or turn it off in Settings.
      </p>
    </section>
  )
}
