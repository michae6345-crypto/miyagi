/**
 * Feature: onboarding. Pick your buddy's color: the last thing before "You're ready" (Adrian, Nov 23: the learner
 * chooses the color when they set miyagi up, like Clicky). One calm screen in Ready's own layout, so the buddy lands
 * where the walk's picture was: the buddy (features/buddy BuddyPreview, it watches the pointer and beams at a pick),
 * one line, the colors, and Continue. Ready.tsx shows it once, until the learner has picked or kept a color; after
 * that the color lives in Settings > General. What it is called is in features/buddy name.ts (not picked yet).
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, font, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { BuddyPreview, BuddySwatches } from '../buddy/ColorPicker'
import { words } from '../buddy/name'
import { confirmSkin } from '../buddy/skin'
import { STAGE_MAX_H, STAGE_TOP } from './Guided'
import { rise, stagger } from './parts'

/** The same room above the picture as Ready's tree. */
const GROUP_TOP = 32

export function BuddyStep({ chrome, onDone }: { chrome: 'window' | 'flow'; onDone: () => void }): ReactNode {
  const reduce = useReducedMotion()
  const done = (): void => {
    confirmSkin()
    onDone()
  }
  return (
    <div data-onb-view="buddy" data-onb-chrome={chrome} role="dialog" aria-labelledby="onb-title" className="flex h-full w-full flex-col">
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
              <BuddyPreview size={104} />
            </motion.div>
            <motion.h1 id="onb-title" variants={rise} className="m-0 mt-[24px]" style={{ fontFamily: font.brand, fontSize: type2.xxl, lineHeight: '34px', fontWeight: 500, letterSpacing: '-0.4px', color: color.text }}>
              {words.stepTitle}
            </motion.h1>
            <motion.p variants={rise} className="m-0 mt-[8px]" style={{ fontSize: type2.body, lineHeight: '24px', color: color.label }}>
              {words.stepBody}
            </motion.p>
            <motion.div variants={rise} className="mt-[32px]">
              <BuddySwatches />
            </motion.div>
            <motion.div variants={rise} data-onb-primary className="mt-[32px] flex w-full items-center justify-center">
              <PrimaryButton label="Continue" onClick={done} />
            </motion.div>
            <motion.p variants={rise} className="m-0 mt-[24px]" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
              {words.stepLater}
            </motion.p>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
