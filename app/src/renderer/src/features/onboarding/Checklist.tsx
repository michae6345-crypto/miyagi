/**
 * Feature: onboarding (A3). Onb-Checklist-Mixed: the compact setup sheet (the window when it isn't the two-pane first
 * run, e.g. "Set up miyagi" from Settings). One bar per row: green only for a row that is done, the track otherwise.
 */
import type { ReactNode } from 'react'
import { color, fill, status as tone, type2 } from '../../core/theme'
import { MiyagiMark } from '../../core/ui/Mark'
import { Row } from './Row'
import type { Row as RowData, Summary } from './rows'
import { Footer, ReadyCount } from './SetupList'

export function Bars({ rows }: { rows: RowData[] }): ReactNode {
  return (
    <div aria-hidden className="flex gap-[4px]">
      {rows.map((r) => (
        <span key={r.id} className="block h-[4px] w-[24px] rounded-[2px]" style={{ background: r.state === 'passed' ? tone.passed : fill.trackNext }} />
      ))}
    </div>
  )
}

export function SheetHeader({ title, rows, sum, brand }: { title: string; rows: RowData[]; sum: Summary; brand?: boolean }): ReactNode {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-[12px]">
        <MiyagiMark size={24} />
        <h2 id="onb-title" className="m-0" style={{ fontSize: brand ? type2.xl : type2.lg, lineHeight: brand ? '28px' : '24px', fontWeight: brand ? 500 : 600, color: color.text }}>
          {title}
        </h2>
      </div>
      <div className="flex items-center gap-[8px]">
        <Bars rows={rows} />
        <ReadyCount sum={sum} />
      </div>
    </div>
  )
}

export function Checklist({ rows, sum }: { rows: RowData[]; sum: Summary }): ReactNode {
  return (
    <div data-onb-view="checklist" className="mx-auto flex h-full w-full max-w-[656px] flex-col p-[32px] pt-[40px]">
      <SheetHeader title="Set up in one place" rows={rows} sum={sum} />
      <div role="list" className="mt-[24px] flex flex-col gap-[8px]">
        {rows.map((r) => (
          <Row key={r.id} row={r} variant="card" />
        ))}
      </div>
      <div className="flex-1" />
      <Footer sum={sum} border={false} />
    </div>
  )
}
