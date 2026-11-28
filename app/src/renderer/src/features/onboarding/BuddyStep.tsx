/**
 * Feature: onboarding. Pick your buddy's color: the last thing before "You're ready" (Adrian, Nov 23: the learner
 * chooses the color when they set miyagi up, like Clicky). v4 (Nov 24): the same top-anchored page as every setup
 * step (v4.tsx SetupPage), left-aligned: the buddy (features/buddy BuddyPreview, it watches the pointer and beams at a
 * pick) where the other steps have their title's room, the title and one line, the colors, and Continue (the ONE
 * primary). Ready.tsx shows it once, until the learner has picked or kept a color; after that the color lives in
 * Settings > General. What it is called is in features/buddy name.ts.
 */
import type { ReactNode } from 'react'
import { PrimaryButton } from '../../core/ui/buttons'
import { BuddyPreview, BuddySwatches, skinTitle } from '../buddy/ColorPicker'
import { words } from '../buddy/name'
import { confirmSkin, useSkinName } from '../buddy/skin'
import { color, v4type } from '../../core/theme'
import { Actions, Fine, FLOW_TOP, Rise, SetupPage, SetupTitle } from './v4'

export function BuddyStep({ chrome, onDone }: { chrome: 'window' | 'flow'; onDone: () => void }): ReactNode {
  const skin = useSkinName()
  const done = (): void => {
    confirmSkin()
    onDone()
  }
  return (
    <div data-onb-chrome={chrome} className="flex h-full w-full flex-col">
      {chrome === 'window' && <header data-drag className="mg-flow-head mg-lights-pad shrink-0" />}
      <div className="relative min-h-0 flex-1">
        <SetupPage view="buddy" top={chrome === 'flow' ? FLOW_TOP : undefined} enterDelay={0.05}>
          {/* The buddy stands over the title, on the page's center line (SetupPage 'center'). */}
          <Rise data={{ 'data-onb-stage': true }} className="flex justify-center" style={{ marginBottom: 14 }}>
            <BuddyPreview size={96} />
          </Rise>
          <SetupTitle title={words.stepTitle} lede={words.stepBody} />
          <Rise style={{ marginTop: 26 }}>
            {/* Centered under the title; the picked color's name sits at the row's end. */}
            <div className="flex items-center justify-center gap-[14px]">
              <BuddySwatches size={26} gap={10} name={false} />
              <span data-part="buddy-color-name" style={{ ...v4type.body, color: color.label }}>
                {skinTitle(skin)}
              </span>
            </div>
          </Rise>
          <Actions>
            <span data-onb-primary>
              <PrimaryButton label="Continue" onClick={done} />
            </span>
          </Actions>
          <Rise style={{ marginTop: 16 }}>
            <Fine>{words.stepLater}</Fine>
          </Rise>
        </SetupPage>
      </div>
    </div>
  )
}
