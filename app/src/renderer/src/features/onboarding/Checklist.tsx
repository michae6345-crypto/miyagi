/**
 * Feature: onboarding. Review setup (Onb-Checklist-Mixed): every setup row on one sheet, each with its own button.
 * Settings ("Open setup") and any open after setup is done land here; guided setup is one click away ("Walk me
 * through it"). One bar per row: green only for a row that is done, the track otherwise. The rows rise in, 35 ms apart.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, fill, font, highlight, radius2, spring, status as tone, surface, type2 } from '../../core/theme'
import { QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { Footer, ReadyCount, rise, stagger } from './parts'
import { Row } from './Row'
import type { Row as RowData, Summary } from './rows'

export function Bars({ rows }: { rows: RowData[] }): ReactNode {
  return (
    <div aria-hidden className="flex gap-[4px]">
      {rows.map((r) => (
        <span key={r.id} className="relative block h-[4px] w-[24px] overflow-hidden rounded-[2px]" style={{ background: fill.trackNext }}>
          <motion.span className="absolute inset-0 block" style={{ background: tone.passed, originX: 0 }} initial={false} animate={{ scaleX: r.state === 'passed' ? 1 : 0 }} transition={spring} />
        </span>
      ))}
    </div>
  )
}

/** `mark={false}`: the one-window flow already shows the bonsai in its step strip. */
export function SheetHeader({ title, rows, sum, brand, mark = true }: { title: string; rows: RowData[]; sum: Summary; brand?: boolean; mark?: boolean }): ReactNode {
  return (
    <div data-drag className="flex items-center justify-between">
      <div className="flex items-center gap-[12px]">
        {mark && <MiyagiMark size={brand ? 32 : 24} />}
        <h2
          id="onb-title"
          className="m-0"
          style={{ fontFamily: brand ? font.brand : undefined, fontSize: brand ? type2.xxl : type2.lg, lineHeight: brand ? '34px' : '24px', fontWeight: brand ? 500 : 600, letterSpacing: brand ? '-0.4px' : undefined, color: color.text }}
        >
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

/** `again`: setup opened again over home (features/shell/flow); the primary is Done, which is always allowed (back to home). */
export function Checklist({ rows, sum, onGuide, onStart, mark, again }: { rows: RowData[]; sum: Summary; onGuide?: () => void; onStart?: () => void; mark?: boolean; again?: boolean }): ReactNode {
  return (
    <div data-onb-view="checklist" role="dialog" aria-labelledby="onb-title" className="mx-auto flex h-full w-full max-w-[656px] flex-col p-[32px] pt-[40px]">
      <SheetHeader title="Review setup" rows={rows} sum={sum} mark={mark} />
      <motion.div
        role="list"
        className="mt-[24px] flex flex-col overflow-hidden"
        style={{ borderRadius: radius2.chip, background: surface.row, boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${fill.hairline}` }}
        variants={stagger(0.04)}
        initial="hidden"
        animate="shown"
      >
        {rows.map((r, i) => (
          <motion.div key={r.id} role="none" variants={rise}>
            <Row row={r} variant="card" last={i === rows.length - 1} />
          </motion.div>
        ))}
      </motion.div>
      {/* The footer follows the list (32 under it, top-anchored), not the window's bottom edge: full screen, it used to sit
          600 px below the rows it acts on. */}
      <div className="shrink-0" style={{ height: 8 }} />
      <Footer
        sum={sum}
        border={false}
        onStart={onStart}
        {...(again ? { label: 'Done', always: true } : {})}
        left={
          <div className="flex min-w-0 items-center gap-[16px]">
            {onGuide && !sum.allOk && (
              <span data-onb-guide>
                <QuietButton size="lg" label="Walk me through it" onClick={onGuide} />
              </span>
            )}
            <span data-onb-hint style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
              {sum.hint}
            </span>
          </div>
        }
      />
    </div>
  )
}
