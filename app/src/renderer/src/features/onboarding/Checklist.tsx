/**
 * Feature: onboarding. Review setup (Onb-Checklist-Mixed): every setup row on one page, each with its live check once
 * it is on or, while it is not, its own quiet button (the row miyagi is watching is washed). Settings ("Open setup") and any open after setup is done land here; guided
 * setup is one click away ("Walk me through it"). v4 (Nov 24, v4.tsx): the title with what is left as its one line,
 * one hairline group of rows, then the ONE primary (Start learning, or Done when opened again over home). The rows
 * rise in, 35 ms apart.
 */
import type { ReactNode } from 'react'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import type { Row as RowData, Summary } from './rows'
import { statusLine } from './steps'
import { startLearning, runAction } from './store'
import { Actions, FLOW_TOP, LiveState, Rise, SetupGroup, SetupPage, SetupRow, SetupTitle } from './v4'

/** A row's own fix: its quiet button (and the engine's Copy details beside Retry). */
function RowFix({ row }: { row: RowData }): ReactNode {
  const a = row.action
  if (!a || row.state === 'passed') return null
  const alt = row.alt
  return (
    <span data-onb-action={a.id} className="flex items-center gap-[6px]">
      {alt && (
        <span data-onb-alt={alt.id}>
          <QuietButton label={alt.label} onClick={() => void runAction(alt.id)} />
        </span>
      )}
      <QuietButton label={a.label} busy={row.state === 'checking'} disabled={row.state === 'checking'} onClick={() => void runAction(a.id, a.item)} />
    </span>
  )
}

/** `again`: setup opened again over home (features/shell/flow); the primary is Done, which is always allowed (back to home). */
export function Checklist({ rows, sum, onGuide, onStart, mark = true, again }: { rows: RowData[]; sum: Summary; onGuide?: () => void; onStart?: () => void; mark?: boolean; again?: boolean }): ReactNode {
  const start = onStart ?? startLearning
  const can = again || sum.canStart
  return (
    <div className="relative h-full w-full">
      <SetupPage view="checklist" top={mark ? 'clamp(24px, 6vh, 64px)' : FLOW_TOP}>
        {mark && (
          <Rise data={{ 'data-drag': true }} style={{ marginBottom: 18 }}>
            <MiyagiMark size={32} />
          </Rise>
        )}
        <SetupTitle title="Review setup" lede={<span data-onb-hint>{sum.hint}</span>} />
        <Rise style={{ marginTop: 26 }}>
          <SetupGroup label="Setup">
            {rows.map((r) => (
              <SetupRow
                key={r.id}
                current={r.state === 'watching'}
                name={r.label}
                line={r.state === 'passed' ? r.why : statusLine(r)}
                // Like the mock's setup rows: the live check once it is on (or nothing to press), else the row's own fix.
                right={r.action && r.state !== 'passed' ? <RowFix row={r} /> : <LiveState state={r.state} word={r.word} />}
                data={{ 'data-onb-row': r.id, 'data-state': r.state }}
              />
            ))}
          </SetupGroup>
        </Rise>
        <Actions>
          <span data-onb-primary>
            <PrimaryButton label={again ? 'Done' : 'Start learning'} disabled={!can} onClick={start} />
          </span>
          {onGuide && !sum.allOk && (
            <span data-onb-guide>
              <QuietButton label="Walk me through it" onClick={onGuide} />
            </span>
          )}
        </Actions>
      </SetupPage>
    </div>
  )
}
