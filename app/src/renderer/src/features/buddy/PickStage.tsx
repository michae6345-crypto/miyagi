/**
 * Feature: buddy. A mock of the setup step where the learner picks their buddy's color, only in the browser stage
 * with ?buddy=pick (index.tsx). Not an app window: the real step belongs to setup (brief, Core requests), which would
 * mount the same BuddyColorPicker. Continue closes the mock and has the buddy point at something on the fake desktop,
 * so the pick can be seen in use; Pick again reopens it.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import { STAGE } from '../../bridge'
import { dispatch } from '../../core/bus'
import { color, fill, font, radius, radius2, shadows, text, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { fade } from '../../core/ui/motion'
import { BuddyColorPicker } from './ColorPicker'
import type { AnnotatePayload } from './marks'

/** Where the mock sits in the stage: the middle, like the setup window. */
export const PICK_STAGE = { x: Math.round(STAGE.width / 2 - 340), y: 170, w: 680, h: 520 }

const annotate = (payload: AnnotatePayload): void => dispatch({ type: 'annotate', payload } as never)

export function PickStage(): ReactNode {
  const [open, setOpen] = useState(true)
  const [shown, setShown] = useState(0)

  const done = (): void => {
    setOpen(false)
    const n = shown + 1
    setShown(n)
    // The same line the try-out's "One" points at (PointStage.tsx).
    setTimeout(() => annotate({ marks: [{ id: `pick-${n}`, x: Math.round(0.0625 * STAGE.width), y: Math.round(0.563 * STAGE.height), w: Math.round(0.2375 * STAGE.width), h: Math.round(0.018 * STAGE.height), why: 'point', label: 'The optimizer' }], holdMs: 9000 }), 420)
  }
  const again = (): void => {
    annotate({ clear: true })
    setOpen(true)
  }

  return (
    <div className="absolute inset-0" data-theme="dark">
      <AnimatePresence>
        {open ? (
          <motion.div
            key="step"
            data-hit
            data-buddy-pick
            role="dialog"
            aria-labelledby="buddy-pick-title"
            className="absolute inset-0 flex flex-col"
            style={{ background: color.window, borderRadius: radius2.card, boxShadow: shadows.card, padding: '36px 40px 28px' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: fade.in }}
            exit={{ opacity: 0, transition: fade.out }}
          >
            <h1 id="buddy-pick-title" className="m-0 text-center" style={{ fontFamily: font.brand, fontSize: type2.xxl, lineHeight: '34px', fontWeight: 500, letterSpacing: '-0.4px', color: color.text }}>
              Pick your buddy&apos;s color
            </h1>
            <p className="m-0 mt-[8px] text-center" style={{ fontSize: type2.body, lineHeight: '24px', color: color.label }}>
              It points things out and answers when you ask.
            </p>
            <div className="flex flex-1 items-center justify-center">
              <BuddyColorPicker />
            </div>
            <div className="flex items-center justify-between gap-[24px] pt-[24px]" style={{ borderTop: `1px solid ${fill.hairline}` }}>
              <span style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>You can change it later in Settings.</span>
              <span data-buddy-pick-done>
                <PrimaryButton size="lg" label="Continue" onClick={done} />
              </span>
            </div>
          </motion.div>
        ) : (
          <motion.button
            key="again"
            type="button"
            data-hit
            data-buddy-pick-again
            onClick={again}
            className="absolute bottom-0 left-0 cursor-pointer"
            style={{ background: color.island, border: `1px solid ${fill.chipBorder}`, borderRadius: radius.chip, color: fill.chipText, padding: '5px 12px', fontSize: text.xs, fontWeight: 500 }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: fade.in }}
            exit={{ opacity: 0, transition: fade.out }}
          >
            Pick again
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}
