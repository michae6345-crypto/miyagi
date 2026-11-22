/**
 * Feature: shell. The redraft's small shared pieces (Adrian, Nov 21: Michael's brief "fewer boxes, more depth, more
 * pastel, calm copy"). Every page of the home window builds from these, so the pages read as one app:
 *
 *   PANEL       the content surface: one raised layer inset from the window, the sidebar sits on the window itself
 *   PageTitle   a page's title row (no hairline under it; spacing does the grouping)
 *   SectionHead a quiet section header with an optional right-hand action
 *   LessonTile  a lesson's pastel tile: the tone of its first tool (or a stable tone from its id) with the tool's icon
 *   StepBar     "Step 4 of 7" as seven short segments: done in ink/white, the current one outlined, never green
 *   Row         a list row that lifts one level on hover (Linear / Notion rows, no border box)
 *
 * Colors come from core/theme tokens only. Pastel tones here are tags, never status: green still only means passed.
 * Peach (the apricot Adrian found too orange) and sand (earth) are left out of the lesson tones.
 */
import { motion } from 'motion/react'
import { BookOpen, Code2, NotebookText, SquareTerminal, Table2, type LucideIcon } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import type { LessonTool } from '../../../../../../shared/contracts/events'
import { color, elevation, fill, highlight, radius2, surface, tone, type Tone, type2 } from '../../core/theme'
import { fade, press, spring } from '../../core/ui/motion'

// ---- the content panel ------------------------------------------------------------------------------------------

/** The gap between the window edge and the raised content panel (the sidebar fills the rest of the window). */
export const PANEL_INSET = 8

/**
 * The content panel's surface: the raised layer, its top highlight, a hairline and the soft wide shadow. Inside it,
 * `--f-group` is re-pointed at a quiet wash so grouped rows (Settings) still read as a group on the white light panel.
 */
export const PANEL: CSSProperties = {
  background: 'var(--l-raised)',
  borderRadius: radius2.group,
  boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}, ${elevation.raised}`,
  ['--f-group' as string]: 'var(--s-row)'
}

/** A card lifted one more level off the panel (the Continue card, gallery tiles). */
export const CARD: CSSProperties = {
  background: 'var(--l-overlay)',
  borderRadius: radius2.group,
  boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.raised}`
}

/** The page column: roomy, capped so a full-screen window stays calm. */
export const COLUMN: CSSProperties = { maxWidth: 760, padding: '0 40px' }

export const caption: CSSProperties = { fontSize: type2.xs, lineHeight: '16px', color: color.label }

// ---- headers ----------------------------------------------------------------------------------------------------

export function PageTitle({ children, right, sub }: { children: ReactNode; right?: ReactNode; sub?: ReactNode }): ReactNode {
  return (
    <div className="flex min-h-[36px] items-center gap-[16px]">
      <div className="flex min-w-0 flex-col" style={{ gap: 2 }}>
        <h1 className="m-0 truncate font-semibold" style={{ fontSize: type2.xxl - 4, lineHeight: '30px', letterSpacing: '-0.015em', color: color.text }}>
          {children}
        </h1>
        {sub && <span style={{ fontSize: type2.sm, color: color.label }}>{sub}</span>}
      </div>
      {right && <div className="ml-auto flex shrink-0 items-center gap-[10px]">{right}</div>}
    </div>
  )
}

export function SectionHead({ id, children, right, icon }: { id?: string; children: ReactNode; right?: ReactNode; icon?: ReactNode }): ReactNode {
  return (
    <div className="flex min-h-[28px] items-center gap-[8px]" style={{ marginBottom: 8 }}>
      {icon}
      <h2 id={id} className="m-0 font-semibold" style={{ fontSize: type2.sm, color: color.text }}>
        {children}
      </h2>
      {right && <div className="ml-auto flex items-center">{right}</div>}
    </div>
  )
}

// ---- lesson tones and tiles -----------------------------------------------------------------------------------------

const LESSON_TONES: readonly Tone[] = ['sky', 'lilac', 'pink', 'mint']
const TOOL_TONE: Record<LessonTool, Tone> = { vscode: 'sky', jupyter: 'lilac', terminal: 'pink', excel: 'mint' }
const TOOL_ICON: Record<LessonTool, LucideIcon> = { vscode: Code2, jupyter: NotebookText, terminal: SquareTerminal, excel: Table2 }

function hashTone(key: string): Tone {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0
  return LESSON_TONES[h % LESSON_TONES.length]
}

/** A lesson's tone: its first tool's pastel, else a stable one from its id or title. */
export function lessonTone(tools: readonly LessonTool[] | undefined, key: string): Tone {
  const t = tools?.[0]
  return t ? TOOL_TONE[t] : hashTone(key)
}

export function lessonIcon(tools: readonly LessonTool[] | undefined): LucideIcon {
  const t = tools?.[0]
  return t ? TOOL_ICON[t] : BookOpen
}

/** The lesson's pastel tile with its tool icon. size 28 in lists, 44 on Continue, 'cover' fills its box. */
export function LessonTile({ tools, id, size = 28, style }: { tools?: readonly LessonTool[]; id: string; size?: number; style?: CSSProperties }): ReactNode {
  const t = tone[lessonTone(tools, id)]
  const Icon = lessonIcon(tools)
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center"
      style={{ width: size, height: size, borderRadius: size >= 40 ? radius2.card : radius2.control, background: size >= 40 ? t.cover : t.bg, color: size >= 40 ? t.coverFg : t.fg, ...style }}
    >
      <Icon size={Math.round(size * 0.5)} strokeWidth={1.7} />
    </span>
  )
}

// ---- step bar -------------------------------------------------------------------------------------------------------

/**
 * Where a lesson stands, as its steps: one short bar per step. Passed steps are solid text color, the current one
 * outlined, the rest a faint track. Ink and white only (green stays for a passed check on the island and panel).
 */
export function StepBar({ done, total, width = 160, label }: { done: number; total: number; width?: number; label?: string }): ReactNode {
  const n = Math.max(1, Math.min(total, 24))
  const d = Math.max(0, Math.min(done, n))
  return (
    <div role="img" aria-label={label ?? `Step ${Math.min(d + 1, n)} of ${n}`} className="flex items-center" style={{ width, gap: 3 }}>
      {Array.from({ length: n }, (_, i) => (
        <span
          key={i}
          className="block flex-1"
          style={{
            height: 4,
            borderRadius: radius2.round,
            background: i < d ? color.text : i === d ? 'transparent' : fill.hairline,
            boxShadow: i === d ? `inset 0 0 0 1px ${fill.ring}` : undefined
          }}
        />
      ))}
    </div>
  )
}

// ---- rows ---------------------------------------------------------------------------------------------------------

/** A list row with no box: hover lays a soft wash under it and the press dips it on the house spring. */
export function Row({ children, onClick, label, style, data }: { children: ReactNode; onClick?: () => void; label?: string; style?: CSSProperties; data?: Record<string, string> }): ReactNode {
  if (!onClick)
    return (
      <div className="flex items-center gap-[12px]" style={{ padding: '8px 10px', ...style }} {...data}>
        {children}
      </div>
    )
  return (
    <motion.button
      type="button"
      aria-label={label}
      onClick={onClick}
      initial="rest"
      animate="rest"
      whileHover="hover"
      whileTap="press"
      variants={{ rest: { scale: 1, transition: spring }, hover: { scale: 1 }, press: { scale: press.scale, transition: spring } }}
      className="relative flex w-full cursor-pointer items-center gap-[12px] text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{ padding: '8px 10px', borderRadius: radius2.row, outlineColor: color.text, ...style }}
      {...data}
    >
      <motion.span
        aria-hidden
        variants={{ rest: { opacity: 0, transition: fade.tint }, hover: { opacity: 1, transition: fade.tint }, press: { opacity: 1, transition: fade.press } }}
        className="pointer-events-none absolute inset-0"
        style={{ background: surface.rowHover, borderRadius: 'inherit' }}
      />
      {children}
    </motion.button>
  )
}

/** A quiet text action ("See all"), chrome: neutral, never a hue. */
export function TextAction({ children, onClick }: { children: ReactNode; onClick: () => void }): ReactNode {
  return (
    <button type="button" onClick={onClick} className="mg-press relative flex cursor-pointer items-center gap-[2px] outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid" style={{ height: 26, padding: '0 8px', borderRadius: radius2.control, fontSize: type2.xs, color: color.label, outlineColor: color.text }}>
      {children}
    </button>
  )
}

/** A calm empty state: the bonsai's place, one line, one action. */
export function Empty({ mark, title, line, action }: { mark?: ReactNode; title: string; line?: string; action?: ReactNode }): ReactNode {
  return (
    <div className="flex flex-col items-center text-center" style={{ padding: '72px 24px', gap: 10 }}>
      {mark}
      <span className="font-semibold" style={{ fontSize: type2.lg, color: color.text, marginTop: mark ? 6 : 0 }}>
        {title}
      </span>
      {line && <span style={{ fontSize: type2.sm, color: color.label, maxWidth: 360 }}>{line}</span>}
      {action && <div style={{ marginTop: 10 }}>{action}</div>}
    </div>
  )
}
