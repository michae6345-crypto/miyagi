/**
 * Feature: plans. The small parts the Library, Plans and plan pages share (Adrian's v4 mock): tabs with counts, the
 * neutral skill chip, a table head, section labels, the two "new plan" entry rows and the plan card. Neutral only:
 * green is for passed, pastels for option chips (the goal dialog's tool picker), nothing else gets a hue.
 */
import { ChevronRight, SquarePlay, Sprout } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { color, fill, radius2, surface, type2 } from '../../core/theme'
import { aboutHours, endsWith, planMinutes, type CatalogPlan } from './catalog'
import { showSkill, type SkillRef } from '../skills/go'
import { openDialog, showPlan } from './store'
import { Thumb, artFor } from './Thumb'

export const meta: CSSProperties = { fontSize: type2.sm, lineHeight: '18px', color: color.label, fontVariantNumeric: 'tabular-nums' }
export const strong: CSSProperties = { fontSize: type2.md, lineHeight: '20px', fontWeight: 600, color: color.text }
export const hair = `1px solid ${color.hairline}`

/** The width of a box, live (tables drop columns as the pane narrows). */
export function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(1040)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

/**
 * A skill the lesson grows: a neutral chip (never a status, never a pastel). With `skill` (its id, or just a label to
 * look up) it is a button that opens that skill on the Skills page (skills/go.ts showSkill). Inside a clickable row it
 * stops its click and its keys, so the chip goes to the skill and the row's own action doesn't fire too.
 */
export function SkillChip({ children, skill }: { children: ReactNode; skill?: SkillRef }): ReactNode {
  const look: CSSProperties = { height: 22, padding: '0 6px', borderRadius: radius2.keycap, background: fill.chip, color: color.text, fontSize: type2.sm }
  if (!skill) {
    return (
      <span className="inline-flex shrink-0 items-center whitespace-nowrap" style={look}>
        {children}
      </span>
    )
  }
  const label = typeof children === 'string' ? children : skill.label
  return (
    <button
      type="button"
      data-skill-chip={skill.id ?? skill.label ?? ''}
      aria-label={label ? `${label}. Open in Skills.` : 'Open in Skills'}
      title={label ? `Open ${label} in Skills` : undefined}
      onClick={(e) => {
        e.stopPropagation()
        showSkill({ id: skill.id, label: skill.label ?? label })
      }}
      onKeyDown={(e) => e.stopPropagation()}
      // The fill lives in classes (not the inline style) so the hover can change it on any page, not just the Library.
      className="mg-chip inline-flex shrink-0 cursor-pointer items-center whitespace-nowrap bg-(--f-chip) outline-offset-1 transition-colors hover:bg-(--f-chip-hover) focus-visible:outline-2"
      style={{ ...look, background: undefined, border: 0, outlineColor: color.text }}
    >
      {children}
    </button>
  )
}

/** "In progress 4": a section label with its count. */
export function SectionLabel({ children, count, right }: { children: ReactNode; count?: number; right?: ReactNode }): ReactNode {
  return (
    <div className="flex items-baseline justify-between gap-[12px]" style={{ marginBottom: 12 }}>
      <h2 className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', fontWeight: 500, color: color.label }}>
        {children}
        {count !== undefined && <span style={{ marginLeft: 6, color: color.faint, fontSize: type2.xs }}>{count}</span>}
      </h2>
      {right}
    </div>
  )
}

/** "Browse plans >": a quiet link at a section's right. */
export function MoreLink({ children, onClick }: { children: ReactNode; onClick: () => void }): ReactNode {
  return (
    <button type="button" onClick={onClick} className="inline-flex cursor-pointer items-center gap-[2px] whitespace-nowrap" style={{ ...meta, background: 'none', border: 0, padding: 0, minHeight: 24, marginBlock: -3 }}>
      {children}
      <ChevronRight size={14} strokeWidth={1.8} />
    </button>
  )
}

export type Tab<T extends string> = { id: T; label: string; count?: number }
/** Underlined tabs with counts (Library: All 13 · In progress 4 …; Plans: All 40 · Code 14 …). */
export function Tabs<T extends string>({ tabs, value, onChange, right, label }: { tabs: Tab<T>[]; value: T; onChange: (t: T) => void; right?: ReactNode; label: string }): ReactNode {
  return (
    <div className="flex items-end justify-between gap-[12px]" style={{ borderBottom: hair }}>
      <div role="tablist" aria-label={label} className="flex min-w-0 items-end gap-[4px] overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
        {tabs.map((t) => {
          const on = t.id === value
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={on}
              data-tab={t.id}
              onClick={() => onChange(t.id)}
              className="flex shrink-0 cursor-pointer items-baseline gap-[5px] whitespace-nowrap"
              style={{ height: 36, padding: '0 8px', background: 'none', border: 0, borderBottom: `2px solid ${on ? color.text : 'transparent'}`, marginBottom: -1, color: on ? color.text : color.label, fontSize: type2.md, fontWeight: on ? 600 : 500 }}
            >
              {t.label}
              {t.count !== undefined && <span style={{ fontSize: type2.xs, color: color.faint, fontWeight: 500 }}>{t.count}</span>}
            </button>
          )
        })}
      </div>
      {right && <div className="flex shrink-0 items-center gap-[4px]" style={{ paddingBottom: 4 }}>{right}</div>}
    </div>
  )
}

/** A table's head row: the column names in the label color, one hairline under it. */
export function TableHead({ cols, template, gap = 16 }: { cols: Array<{ label: string; align?: 'right' }>; template: string; gap?: number }): ReactNode {
  return (
    <div role="row" className="grid items-end" style={{ gridTemplateColumns: template, columnGap: gap, height: 32, paddingBottom: 8, borderBottom: hair, ...meta }}>
      {cols.map((c, i) => (
        <span key={i} role="columnheader" className="truncate" style={{ textAlign: c.align }}>
          {c.label}
        </span>
      ))}
    </div>
  )
}

/**
 * A table row: a hairline under it; with `onClick`, the whole row opens its thing (a soft fill on hover, the focus
 * ring, Enter and Space, the pointer). A row with nothing to open gets none of those, so it never looks clickable.
 * Keys pressed on a control inside the row (a skill chip, a button) are that control's, not the row's.
 */
export function TableRow({ template, children, onClick, label, gap = 16, height = 52, data, expanded, controls }: { template: string; children: ReactNode; onClick?: () => void; label?: string; gap?: number; height?: number; data?: Record<string, string>; expanded?: boolean; controls?: string }): ReactNode {
  return (
    <div
      role="row"
      tabIndex={onClick ? 0 : undefined}
      aria-label={label}
      aria-expanded={onClick && expanded !== undefined ? expanded : undefined}
      aria-controls={onClick && expanded ? controls : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (onClick && e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onClick()
        }
      }}
      className={`grid items-center ${onClick ? 'mg-v4-row cursor-pointer' : ''}`}
      style={{ gridTemplateColumns: template, columnGap: gap, minHeight: height, padding: '6px 0', borderBottom: expanded ? 0 : hair, color: color.text, fontSize: type2.md }}
      {...data}
    >
      {children}
    </div>
  )
}

/** The two ways to make a plan (Plans -29 and the first-run Library -27): a playlist link, or a goal. */
export function EntryCards(): ReactNode {
  const card = (icon: ReactNode, title: string, line: string, onClick: () => void, id: string): ReactNode => (
    <button
      type="button"
      data-entry={id}
      onClick={onClick}
      className="mg-lift flex min-w-0 flex-1 cursor-pointer items-center gap-[12px] text-left"
      style={{ height: 60, padding: '0 16px', borderRadius: radius2.card, background: surface.row, border: 0, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text }}
    >
      <span className="shrink-0" style={{ color: color.label }}>
        {icon}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate" style={{ fontSize: type2.md, fontWeight: 600 }}>
          {title}
        </span>
        <span className="truncate" style={meta}>
          {line}
        </span>
      </span>
      <ChevronRight size={15} strokeWidth={1.8} style={{ color: color.faint }} />
    </button>
  )
  return (
    <div className="flex flex-wrap gap-[12px]" data-entry-cards>
      {card(<SquarePlay size={17} strokeWidth={1.7} />, 'From a playlist', 'Paste a YouTube playlist link', () => openDialog('playlist'), 'playlist')}
      {card(<Sprout size={17} strokeWidth={1.7} />, 'From a goal', 'Say what you want to make', () => openDialog('goal'), 'goal')}
    </div>
  )
}

/** A plan as a card: its picture, its title, where it works, how long, and what it ends with. */
export function PlanCard({ plan }: { plan: CatalogPlan }): ReactNode {
  return (
    <button type="button" data-plan-card={plan.id} onClick={() => showPlan(plan.id)} className="group flex min-w-0 cursor-pointer flex-col text-left" style={{ background: 'none', border: 0, padding: 0, color: color.text }}>
      <span className="block w-full transition-transform duration-200 group-hover:-translate-y-[2px]">
        <Thumb art={artFor(plan)} w="100%" radius={radius2.card} />
      </span>
      <span className="truncate" style={{ marginTop: 10, fontSize: type2.md, lineHeight: '20px', fontWeight: 600 }}>
        {plan.title}
      </span>
      {/* Wraps between its parts rather than clipping, so a narrow card keeps the plan's length (QA R4-02). */}
      <span style={meta}>{[plan.tool.label, `${plan.lessons.length} lessons`, aboutHours(planMinutes(plan))].map((part) => part.replace(/ /g, ' ')).join(' · ')}</span>
      <span style={{ ...meta, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{endsWith(plan)}</span>
    </button>
  )
}

/** Cards in a row of `cols` (4 on a wide pane, 2 on a narrow one). */
export function CardGrid({ children, cols }: { children: ReactNode; cols: number }): ReactNode {
  return (
    <div className="grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, columnGap: 20, rowGap: 24 }}>
      {children}
    </div>
  )
}

/**
 * The page's own CSS (styles.css is core), rendered once by the Library page:
 *  - the rows' hover fill;
 *  - the shell's legacy title stays hidden under the Library's v4 frame. styles.css has that rule, but in @layer base,
 *    where Tailwind's `flex` utility on the header outranks it (so a second "Library" title was drawn). Unlayered here.
 *  - the top bar's earlier crumbs read as links while a deeper Library view is on show (Library.tsx useCrumbBack).
 */
export function RowStyle(): ReactNode {
  return (
    <style>{`.mg-v4-row{transition:background-color .12s}.mg-v4-row:hover{background:${surface.rowHover}}.mg-v4-row:focus-visible{outline:2px solid ${color.text};outline-offset:-2px}
.mg-page-frame:has([data-lessons][data-v4-frame])>[data-legacy-header]{display:none}
.mg-crumb-back [data-v4-top] nav>span:not([aria-current]){cursor:pointer}
.mg-crumb-back [data-v4-top] nav>span:not([aria-current]):hover{color:${color.text}}`}</style>
  )
}
