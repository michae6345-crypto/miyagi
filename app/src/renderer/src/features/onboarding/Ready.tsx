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
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { startTour } from '../tips/tourStore'
import { thisDevice } from './device'
import { STAGE_MAX_H, STAGE_TOP } from './Guided'
import { LauncherHint, rise, stagger } from './parts'
import type { Row as RowData, Summary } from './rows'
import { startLearning } from './store'

/** Inside the block, the room above the tree, so it lands where the walk's picture was (the step centers in its main). */
const GROUP_TOP = 32

/**
 * `onStart`: home (the one-window flow hands over to it; the setup window opens the Library). `onTour`: the same, after
 * starting the walkthrough (the flow passes finishFlow). `rows`, `sum` are kept for the callers.
 * `chrome`: 'window' in the setup window (an empty drag strip where Guided has its header, then Guided's STAGE_TOP of
 * room), 'flow' inside the one-window flow (its strip is the header, and the walk's block starts right under it there,
 * because the flow caps the walk's height). Until the flow passes `chrome` (a shell request), `mark={false}`, which only
 * the flow passes, means 'flow'.
 */
export function Ready({
  onStart,
  onTour,
  again,
  mark,
  chrome = mark === false ? 'flow' : 'window'
}: {
  rows?: RowData[]
  sum?: Summary
  onStart?: () => void
  onTour?: () => void
  mark?: boolean
  again?: boolean
  chrome?: 'window' | 'flow'
}): ReactNode {
  const home = onStart ?? startLearning
  const reduce = useReducedMotion()
  const tour = (): void => {
    startTour()
    ;(onTour ?? home)()
  }
  // Top-anchored, as every onboarding step (fix round 2, Nov 22: the layout spec says never center vertically, even in
  // full screen; centering dropped the content ~300 px below where the last step's picture was). The same block as
  // Guided.tsx: STAGE_TOP of room that gives way first in a short window, then at most STAGE_MAX_H with the group at its
  // top, so the tree lands where the step's picture was. The actions sit right under the sample lesson and the launcher
  // hint 32 under them (no longer pinned to the window's foot). Skip and Show me around are both size md, so the row has
  // one text size: the quiet button's text stays 13 px at lg in core/ui/buttons.tsx (core request: lg text 15 for both
  // kinds; then both can go back to lg, like Guided's footer).
  return (
    <div data-onb-view="ready" data-onb-chrome={chrome} role="dialog" aria-labelledby="onb-title" className="flex h-full w-full flex-col">
      {chrome === 'window' && <header data-drag className="mg-flow-head mg-lights-pad shrink-0" />}
      <div className="flex min-h-0 flex-1 flex-col">
        <div aria-hidden className="min-h-0" style={{ flex: `0 1000 ${chrome === 'window' ? STAGE_TOP : 0}px` }} />
        <div className="flex min-h-0 w-full flex-col" style={{ flex: `0 1 ${STAGE_MAX_H}px` }}>
          <motion.div
            className="mx-auto flex w-full max-w-[560px] flex-col items-center px-[32px] text-center"
            style={{ paddingTop: GROUP_TOP }}
            variants={stagger(0.05)}
            initial={reduce ? false : 'hidden'}
            animate="shown"
          >
            <motion.div variants={rise} data-onb-stage className="grid w-full place-items-center" style={{ height: 120 }}>
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
                <PrimaryButton label="Done" onClick={home} />
              ) : (
                <>
                  <span data-onb-secondary>
                    <QuietButton label="Skip" onClick={home} />
                  </span>
                  <PrimaryButton label="Show me around" onClick={tour} />
                </>
              )}
            </motion.div>
            <motion.div variants={rise} data-onb-launcher-hint className="mt-[32px] flex justify-center">
              <LauncherHint lead="Open miyagi anytime" />
            </motion.div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
