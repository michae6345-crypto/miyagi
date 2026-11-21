/**
 * Feature: onboarding (A3). Onb-Setup-Full's right pane: "Set up in one place", the rows in one grouped list, and the
 * footer with what's left and the one primary, Start learning (on once nothing the learner can fix is left).
 */
import type { ReactNode } from 'react'
import { color, fill, radius2, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { Row } from './Row'
import type { Row as RowData, Summary } from './rows'
import { startLearning } from './store'

export function ReadyCount({ sum }: { sum: Summary }): ReactNode {
  return (
    <span data-onb-count style={{ fontSize: type2.sm, color: color.label }}>
      {sum.ready} of {sum.total} ready
    </span>
  )
}

export function Footer({ sum, left, border = true }: { sum: Summary; left?: ReactNode; border?: boolean }): ReactNode {
  return (
    <div className="flex items-center justify-between gap-[24px] pt-[24px]" style={{ borderTop: border ? `1px solid ${fill.hairline}` : undefined }}>
      {left ?? (
        <span data-onb-hint style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
          {sum.hint}
        </span>
      )}
      <PrimaryButton size="lg" label="Start learning" disabled={!sum.canStart} onClick={startLearning} />
    </div>
  )
}

export function SetupList({ rows, sum }: { rows: RowData[]; sum: Summary }): ReactNode {
  return (
    <div className="flex min-w-0 flex-1 flex-col px-[48px] pb-[40px] pt-[48px]">
      <div className="flex items-baseline justify-between">
        <h2 className="m-0" style={{ fontSize: type2.xl, lineHeight: '28px', fontWeight: 600, color: color.text }}>
          Set up in one place
        </h2>
        <ReadyCount sum={sum} />
      </div>
      <p className="m-0 mt-[8px]" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
        Each row updates on its own as you go.
      </p>
      <div role="list" className="mt-[24px] flex flex-col" style={{ borderRadius: radius2.group, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
        {rows.map((r, i) => (
          <Row key={r.id} row={r} variant="list" last={i === rows.length - 1} />
        ))}
      </div>
      <div className="flex-1" />
      <Footer sum={sum} />
    </div>
  )
}
