/**
 * Feature: reminders. The one-time offer, grown out of the island after the first finished lesson (store.ts arms it):
 * "Want a nudge when a review is due?" Yes is the one primary; Not now (Esc) is quiet. Either answer is final, and
 * Settings can change it any time. Calm copy, no hue: nothing here is a status.
 */
import { BellRing } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { color, fill, radius2, type2 } from '../../core/theme'
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
    <section aria-labelledby="reminders-offer-title" data-reminders="offer" data-hit className="flex flex-col" style={{ width: OFFER_W, padding: '16px 20px 20px', gap: 14 }}>
      <div className="flex items-center gap-[8px]" style={{ height: 24, fontSize: type2.xs, color: color.label }}>
        <MiyagiMark size={16} />
        <MiyagiWordmark height={13} className="h-[13px] w-auto" />
        <span aria-hidden>·</span>
        <span>Reminders</span>
      </div>

      <div className="flex items-start gap-[12px]">
        <span aria-hidden className="grid h-[36px] w-[36px] shrink-0 place-items-center" style={{ borderRadius: radius2.row, background: fill.tile, color: color.text }}>
          <BellRing size={18} strokeWidth={1.6} />
        </span>
        <div className="flex min-w-0 flex-col gap-[4px]">
          <h1 id="reminders-offer-title" className="m-0 font-semibold" style={{ fontSize: type2.lg, lineHeight: '22px', letterSpacing: '-0.01em', color: color.text }}>
            Want a nudge when a review is due?
          </h1>
          <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
            One quiet reminder at {at}, only on days something is due.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-[8px]">
        <div className="min-w-0 flex-1">
          <PrimaryButton label="Yes" size="lg" block onClick={() => answerOffer(true)} />
        </div>
        <QuietButton label="Not now" size="lg" keyName="dismiss" onClick={() => answerOffer(false)} />
      </div>
      <p className="m-0" style={{ fontSize: type2.xs, color: color.faint }}>
        Change the time or turn it off in Settings.
      </p>
    </section>
  )
}
