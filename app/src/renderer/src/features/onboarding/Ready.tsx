/**
 * Feature: onboarding. The end of setup: "You're ready". One calm v4 page (v4.tsx): the bonsai, one line, and a
 * sample lesson row that offers a short tour (features/tips TourLayer.tsx: five coach marks over a sample panel, nothing
 * real starts, no engine needed). The primary is "Show me around"; "Skip" goes straight to home. Either way setup is
 * finished and the learner lands on Home: no lesson is ever started from here.
 * `again`: setup opened again over home; the primary is Done (back to home, no tour offered).
 * Before it, once: Pick your buddy's color (BuddyStep.tsx).
 */
import { NotebookText } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { color, v4, v4c } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { RowChev } from '../shell/ui'
import { isSkinChosen } from '../buddy/skin'
import { startTour } from '../tips/tourStore'
import { BuddyStep } from './BuddyStep'
import { thisDevice } from './device'
import { LauncherHint } from './parts'
import type { Row as RowData, Summary } from './rows'
import { startLearning } from './store'
import { Actions, FLOW_TOP, LiveState, RailRow, RailSection, Rise, SetupGroup, SetupPage, SetupRow, SetupTitle } from './v4'

/**
 * `onStart`: home (the one-window flow hands over to it; the setup window opens the Library). `onTour`: the same, after
 * starting the walkthrough (the flow passes finishFlow). `rows`, `sum` are kept for the callers.
 * `chrome`: 'window' in the setup window (an empty drag strip where Guided has its header, then Guided's STAGE_TOP of
 * room), 'flow' inside the one-window flow (its strip is the header, and the walk's block starts right under it there,
 * because the flow caps the walk's height). Until the flow passes `chrome` (a shell request), `mark={false}`, which only
 * the flow passes, means 'flow'.
 */
type ReadyProps = {
  rows?: RowData[]
  sum?: Summary
  onStart?: () => void
  onTour?: () => void
  mark?: boolean
  again?: boolean
  chrome?: 'window' | 'flow'
}

/**
 * The first time through, the learner picks their buddy's color first (BuddyStep.tsx), then this screen. Decided when
 * it opens: a pick inside the step must not close it, only its Continue does. Not when setup is opened again: by then
 * the color lives in Settings.
 */
export function Ready(props: ReadyProps): ReactNode {
  const [picking, setPicking] = useState(() => !props.again && !isSkinChosen())
  if (picking) return <BuddyStep chrome={props.chrome ?? (props.mark === false ? 'flow' : 'window')} onDone={() => setPicking(false)} />
  return <ReadyScreen {...props} />
}

function ReadyScreen({ rows, onStart, onTour, again, mark, chrome = mark === false ? 'flow' : 'window' }: ReadyProps): ReactNode {
  const home = onStart ?? startLearning
  const tour = (): void => {
    startTour()
    ;(onTour ?? home)()
  }
  // v4 (Nov 24): the same top-anchored page as every setup step, left-aligned. The tree, the title and one line, the
  // sample lesson as the one row to open, then the ONE primary (Show me around; Done when setup is opened again) with
  // Skip beside it, and the launcher's key. The rail lists what was set up, each with its live check (said once, here).
  const done = rows?.filter((r) => r.state === 'passed') ?? []
  return (
    <div data-onb-chrome={chrome} className="flex h-full w-full flex-col">
      {chrome === 'window' && <header data-drag className="mg-flow-head mg-lights-pad shrink-0" />}
      <div className="relative min-h-0 flex-1">
        <SetupPage
          view="ready"
          top={chrome === 'flow' ? FLOW_TOP : undefined}
          enterDelay={0.05}
          rail={
            rows && rows.length > 0 ? (
              <RailSection first title="Set up" right={`${done.length} of ${rows.length}`}>
                {rows.map((r) => (
                  <RailRow key={r.id} title={r.label} right={<LiveState state={r.state} word={r.word} still />} />
                ))}
              </RailSection>
            ) : undefined
          }
        >
          <Rise data={{ 'data-onb-stage': true }} style={{ marginBottom: 18 }}>
            <MiyagiMark size={48} />
          </Rise>
          <SetupTitle title="You’re ready" lede={`miyagi is set up on ${thisDevice()}.`} />
          {!again && (
            <Rise style={{ marginTop: 26 }}>
              <SetupGroup label="Try it">
                <SetupRow
                  name="Sample lesson"
                  line="A one-minute tour. Nothing real starts."
                  lead={
                    <span aria-hidden className="grid h-[36px] w-[36px] shrink-0 place-items-center" style={{ borderRadius: v4.radius.control, background: v4c.fill }}>
                      <NotebookText size={18} strokeWidth={1.6} color={color.text} />
                    </span>
                  }
                  right={<RowChev />}
                  onClick={tour}
                  data={{ 'data-onb-lesson': 'sample' }}
                />
              </SetupGroup>
            </Rise>
          )}
          <Actions>
            {again ? (
              <span data-onb-primary>
                <PrimaryButton label="Done" onClick={home} />
              </span>
            ) : (
              <>
                <span data-onb-primary>
                  <PrimaryButton label="Show me around" onClick={tour} />
                </span>
                <span data-onb-secondary>
                  <QuietButton label="Skip" onClick={home} />
                </span>
              </>
            )}
          </Actions>
          <Rise data={{ 'data-onb-launcher-hint': true }} style={{ marginTop: 28 }}>
            <LauncherHint lead="Open miyagi anytime" />
          </Rise>
        </SetupPage>
      </div>
    </div>
  )
}
