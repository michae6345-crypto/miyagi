/**
 * The "How it works" diagram (lesson.ready flow, 3-6 boxes, left to right). Shared by the "Before you start"
 * sheet (black island tokens) and the drawer's "What you're building" strip (glass tokens), so the colors come in
 * as a tone. The box the current step builds (FlowBox.stepIndex === the step's StepSummary.index) is outlined.
 * Wraps onto a second row in a narrow drawer instead of scrolling.
 */
import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import type { FlowBox } from '../../../../../../shared/contracts/events'
import { font } from '../../core/theme'

export type FlowTone = { text: string; faint: string; box: string; border: string; current: string }

export function FlowDiagram({ flow, currentIndex, tone }: { flow: FlowBox[]; currentIndex?: number; tone: FlowTone }): ReactNode {
  if (flow.length === 0) return null
  return (
    <div data-part="flow" className="flex flex-wrap items-center gap-x-[4px] gap-y-[6px]">
      {flow.map((b, i) => {
        const current = currentIndex !== undefined && b.stepIndex === currentIndex
        return (
          <div key={`${i}:${b.label}`} className="flex items-center gap-[4px]">
            {i > 0 && <ChevronRight size={12} strokeWidth={2} className="shrink-0" style={{ color: tone.faint }} />}
            <div
              data-flow-box={b.stepIndex ?? ''}
              data-current={current || undefined}
              className="min-w-0 max-w-[168px] rounded-[10px] border px-[9px] py-[5px]"
              style={{ background: tone.box, borderColor: current ? tone.current : tone.border }}
            >
              <div className="truncate text-[12.5px] font-semibold leading-[16px]" style={{ color: tone.text }}>
                {b.label}
              </div>
              {b.detail && (
                <div className="truncate text-[11px] leading-[15px]" style={{ color: tone.faint, fontFamily: font.mono }} title={b.detail}>
                  {b.detail}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
