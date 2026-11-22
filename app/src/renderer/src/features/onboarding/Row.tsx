/**
 * Feature: onboarding (A3). One setup row, in the four shapes the mockups use:
 *   list     Onb-Setup-Full: icon tile, label + why, glyph + word and the row's button on the right (280 wide)
 *   card     Onb-Checklist-Mixed: a 72 px rounded card, glyph, label + the state in a sentence, the button
 *   compact  Onb-Setup-Ready: a 56 px tile, glyph and label (every row is done there)
 *   line     Onb-Permission-Recovery: a 40 px line, label left, glyph + word right
 * Buttons here are QuietButtons (chrome): each surface keeps its one white primary for Start learning / the fix.
 *
 * Polish: every row is a riseItem, so a list that wraps them in core staggerList arrives one row after another (and a
 * list that doesn't is unchanged). Card and tile rows carry the soft top highlight of a raised dark surface.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Code, Monitor, MousePointer2, Settings2, type LucideIcon } from 'lucide-react'
import { color, fill, highlight, radius2, status as tone, surface, type2 } from '../../core/theme'
import { riseItem } from '../../core/ui/motion'
import { QuietButton } from '../../core/ui/buttons'
import { StatusGlyph } from '../../core/ui/status'
import type { Row as RowData, RowId, RowState } from './rows'
import { runAction } from './store'

const ICON: Record<RowId, LucideIcon> = { screen: Monitor, accessibility: MousePointer2, companion: Code, engine: Settings2 }

export function wordColor(state: RowState): string {
  if (state === 'passed') return tone.passed
  if (state === 'notyet' || state === 'checking') return color.text
  return tone.watching
}

function Word({ row }: { row: RowData }): ReactNode {
  return (
    <span className="whitespace-nowrap" style={{ fontSize: type2.sm, fontWeight: row.state === 'passed' ? 500 : 400, color: wordColor(row.state) }}>
      {row.word}
    </span>
  )
}

function Action({ row, tall }: { row: RowData; tall?: boolean }): ReactNode {
  const a = row.action
  if (!a) return null
  const alt = row.alt
  return (
    <span data-onb-action={a.id} style={tall ? undefined : { height: 32 }} className="flex items-center gap-[8px]">
      {alt && (
        <span data-onb-alt={alt.id} className="flex items-center">
          <QuietButton size="md" label={alt.label} onClick={() => void runAction(alt.id)} />
        </span>
      )}
      <QuietButton size="md" label={a.label} busy={row.state === 'checking'} disabled={row.state === 'checking'} onClick={() => void runAction(a.id, a.item)} />
    </span>
  )
}

export function Row({ row, variant, last }: { row: RowData; variant: 'list' | 'card' | 'compact' | 'line'; last?: boolean }): ReactNode {
  const Icon = ICON[row.id]
  if (variant === 'line')
    return (
      <motion.div variants={riseItem} role="listitem" data-onb-row={row.id} data-state={row.state} className="flex h-[40px] items-center justify-between" style={{ fontSize: type2.sm, borderBottom: last ? undefined : `1px solid ${fill.hairline}` }}>
        <span style={{ color: color.text }}>{row.label}</span>
        <span className="flex items-center gap-[8px]">
          <StatusGlyph state={row.state} size={16} />
          <Word row={row} />
        </span>
      </motion.div>
    )
  if (variant === 'compact')
    return (
      <motion.div variants={riseItem} role="listitem" data-onb-row={row.id} data-state={row.state} className="flex h-[56px] items-center gap-[12px] px-[16px]" style={{ borderRadius: radius2.chip, background: surface.row, boxShadow: highlight.topSoft }}>
        <StatusGlyph state={row.state} size={24} />
        <span style={{ fontSize: type2.body, fontWeight: 500, color: color.text }}>{row.label}</span>
      </motion.div>
    )
  if (variant === 'card') {
    // The row miyagi is watching (the learner is in System Settings) is the one lit a step.
    const open = row.state === 'watching'
    return (
      <motion.div
        variants={riseItem}
        role="listitem"
        data-onb-row={row.id}
        data-state={row.state}
        className="flex h-[72px] items-center gap-[16px] px-[16px]"
        // One row of a grouped list (Checklist wraps them in one surface): a hairline between rows, no box per row.
        style={{ borderBottom: last ? undefined : `1px solid ${fill.hairline}`, background: open ? fill.highlight : undefined }}
      >
        <StatusGlyph state={row.state} size={24} />
        <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <span style={{ fontSize: type2.body, fontWeight: 600, color: color.text }}>{row.label}</span>
          <span className="truncate" style={{ fontSize: type2.sm, color: row.state === 'watching' || row.state === 'unknown' ? tone.watching : color.label }}>
            {row.detail}
          </span>
        </div>
        {row.action ? <Action row={row} tall /> : <Word row={row} />}
      </motion.div>
    )
  }
  // list (Onb-Setup-Full)
  return (
    <motion.div
      variants={riseItem}
      role="listitem"
      data-onb-row={row.id}
      data-state={row.state}
      className="flex min-h-[80px] items-center gap-[16px] px-[20px] py-[16px]"
      style={{ borderBottom: last ? undefined : `1px solid ${fill.hairline}` }}
    >
      <div className="grid h-[40px] w-[40px] shrink-0 place-items-center" style={{ borderRadius: radius2.row, background: surface.row }}>
        <Icon size={20} strokeWidth={1.5} color={color.text} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-[4px]">
        <span style={{ fontSize: type2.body, fontWeight: 600, color: color.text }}>{row.label}</span>
        <span style={{ fontSize: type2.sm, color: color.label }}>{row.state === 'unknown' || (row.id === 'engine' && row.state !== 'passed') ? row.detail : row.why}</span>
      </div>
      <div className="flex shrink-0 items-center justify-end gap-[12px]">
        <span className="flex items-center gap-[8px]">
          <StatusGlyph state={row.state} size={20} />
          <Word row={row} />
        </span>
        <Action row={row} />
      </div>
    </motion.div>
  )
}
