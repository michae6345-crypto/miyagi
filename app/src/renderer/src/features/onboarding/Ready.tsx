/**
 * Feature: onboarding. The end of setup: "You're ready". One calm screen: the bonsai on a soft floor, one line, and a
 * sample lesson card that offers a short tour (features/tips TourLayer.tsx: five coach marks over a sample panel, nothing
 * real starts, no engine needed). The primary is "Show me around"; "Skip" goes straight to home. Either way setup is
 * finished and the learner lands on Home: no lesson is ever started from here.
 * `again`: setup opened again over home; the primary is Done (back to home, no tour offered).
 */
import { motion, useReducedMotion } from 'motion/react'
import { NotebookText } from 'lucide-react'
import type { ReactNode } from 'react'
import { color, elevation, fill, font, highlight, radius2, surface, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { startTour } from '../tips/tourStore'
import { thisDevice } from './device'
import { LauncherHint, rise, stagger } from './parts'
import type { Row as RowData, Summary } from './rows'
import { startLearning } from './store'

/**
 * `onStart`: home (the one-window flow hands over to it; the setup window opens the Library). `onTour`: the same, after
 * starting the walkthrough (the flow passes finishFlow). `rows`, `sum`, `mark` are kept for the callers.
 */
export function Ready({ onStart, onTour, again }: { rows?: RowData[]; sum?: Summary; onStart?: () => void; onTour?: () => void; mark?: boolean; again?: boolean }): ReactNode {
  const home = onStart ?? startLearning
  const reduce = useReducedMotion()
  const tour = (): void => {
    startTour()
    ;(onTour ?? home)()
  }
  // One centered group (Nov 22 layout pass): the tree, the line, the sample lesson and, right under it, the actions, so in
  // a full-screen window the buttons sit by the card they belong to (they used to be pinned to the bottom, 380 px away,
  // and overhung the card by 88 px). The launcher hint is a quiet caption at the foot, centered, like the sign-in's terms.
  return (
    <div data-onb-view="ready" role="dialog" aria-labelledby="onb-title" className="mx-auto flex h-full w-full max-w-[560px] flex-col px-[32px]">
      <motion.div className="flex min-h-0 flex-1 flex-col items-center justify-center text-center" variants={stagger(0.05)} initial={reduce ? false : 'hidden'} animate="shown">
        <motion.div
          variants={rise}
          data-onb-stage
          className="grid w-full place-items-center"
          style={{ height: 120 }}
        >
          <MiyagiMark size={88} />
        </motion.div>
        <motion.h1 id="onb-title" variants={rise} className="m-0 mt-[24px]" style={{ fontFamily: font.brand, fontSize: type2.xxl, lineHeight: '34px', fontWeight: 500, letterSpacing: '-0.4px', color: color.text }}>
          You’re ready
        </motion.h1>
        <motion.p variants={rise} className="m-0 mt-[8px]" style={{ fontSize: type2.body, lineHeight: '24px', color: color.label }}>
          miyagi is set up on {thisDevice()}.
        </motion.p>
        {!again && (
          <motion.button
            variants={rise}
            type="button"
            data-onb-lesson="sample"
            className="mg-press mt-[32px] flex w-full cursor-pointer items-center gap-[16px] p-[16px] text-left"
            style={{ borderRadius: radius2.group, background: surface.sheet, boxShadow: `${highlight.top}, inset 0 0 0 1px ${fill.hairline}, ${elevation.raised}` }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={tour}
          >
            <span className="grid h-[44px] w-[44px] shrink-0 place-items-center" style={{ borderRadius: radius2.card, background: fill.tile }}>
              <NotebookText size={22} strokeWidth={1.5} color={color.text} />
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
              <span className="truncate" style={{ fontSize: type2.body, fontWeight: 600, color: color.text }}>
                Sample lesson
              </span>
              <span className="truncate" style={{ fontSize: type2.sm, color: color.label }}>
                A one-minute tour. Nothing real starts.
              </span>
            </span>
          </motion.button>
        )}
        <motion.div variants={rise} data-onb-primary className="mt-[24px] flex w-full items-center justify-center gap-[8px]">
          {again ? (
            <PrimaryButton size="lg" label="Done" onClick={home} />
          ) : (
            <>
              <span data-onb-secondary>
                <QuietButton size="lg" label="Skip" onClick={home} />
              </span>
              <PrimaryButton size="lg" label="Show me around" onClick={tour} />
            </>
          )}
        </motion.div>
      </motion.div>
      <div className="flex h-[64px] shrink-0 items-center justify-center">
        <LauncherHint lead="Open miyagi anytime" />
      </div>
    </div>
  )
}
