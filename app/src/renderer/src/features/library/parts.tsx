/**
 * Feature: library. Small pieces shared by the list (Home-Library) and the preview (Home-LessonDetail). Neutral
 * fills only: nothing here is a status or an option, so no green and no pastel. Progress is white on the track.
 */
import type { ReactNode } from 'react'
import type { LessonTool, LibraryItem } from '../../../../../../shared/contracts/events'
import { brand, color, fill, radius2, surface, type2 } from '../../core/theme'

/** Secondary text on the window (the mockups' white at 78%). */
export const soft = fill.keycapText

export const TOOL_NAME: Record<LessonTool, string> = { vscode: 'VS Code', jupyter: 'Jupyter', terminal: 'Terminal', excel: 'Excel' }
const TOOL_ABBR: Record<LessonTool, string> = { vscode: 'VS', jupyter: 'Jn', terminal: 'Sh', excel: 'Xl' }
/** The tools a lesson can be filtered by today; Excel shows as "soon". */
export const FILTER_TOOLS: LessonTool[] = ['vscode', 'jupyter', 'terminal']

/** Soft pastel per tool. A tag, never status: ink on the pastel reads in light and dark. */
export const TOOL_TONE: Record<LessonTool, string> = { vscode: brand.pastel.sky, jupyter: brand.pastel.lilac, terminal: brand.pastel.pink, excel: brand.pastel.apricot }

/** A tool's soft tag: "VS Code" in its pastel. */
export function ToolTag({ tool }: { tool: LessonTool }): ReactNode {
  return (
    <span className="inline-flex shrink-0 items-center whitespace-nowrap font-medium" style={{ height: 20, padding: '0 8px', borderRadius: radius2.round, background: TOOL_TONE[tool], color: brand.ink, fontSize: type2.micro }}>
      {TOOL_NAME[tool]}
    </span>
  )
}

/** A tool's tile (Lessons cards): the pastel square with its two letters in ink. */
export function ToolTile({ tool, size = 32, muted }: { tool: LessonTool; size?: number; muted?: boolean }): ReactNode {
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center font-medium"
      style={{
        width: size,
        height: size,
        borderRadius: size <= 20 ? radius2.keycap : size >= 48 ? radius2.card : radius2.control,
        background: TOOL_TONE[tool],
        opacity: muted ? 0.6 : 1,
        fontSize: size >= 48 ? type2.sm : type2.micro,
        color: brand.ink
      }}
    >
      {TOOL_ABBR[tool]}
    </span>
  )
}

/** "7 steps", "About 25 min". */
export const stepsLabel = (n: number): string => `${n} ${n === 1 ? 'step' : 'steps'}`
export const minutesLabel = (m: number | undefined): string | undefined => (m ? `About ${m} min` : undefined)

/** Where the learner left a lesson: "Step 4 of 7. Train it". */
export function progressLabel(p: NonNullable<LibraryItem['progress']>): string {
  return `Step ${p.stepIndex + 1} of ${p.total}${p.stepTitle ? `. ${p.stepTitle}` : ''}`
}

/** A 4 px meter: white on the track. Never green (green only means a passed check). */
export function Meter({ fraction, label }: { fraction: number; label: string }): ReactNode {
  const f = Math.max(0, Math.min(1, fraction))
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(f * 100)} style={{ height: 4, borderRadius: radius2.round, background: fill.hairline }}>
      <div style={{ width: `${f * 100}%`, height: 4, borderRadius: radius2.round, background: color.text }} />
    </div>
  )
}

/** A filter chip (All, VS Code, …). Selected = a brighter neutral, never a hue. */
export function Chip({ label, on, onClick, disabled }: { label: string; on?: boolean; onClick?: () => void; disabled?: boolean }): ReactNode {
  return (
    <button
      type="button"
      aria-pressed={disabled ? undefined : !!on}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex shrink-0 cursor-pointer items-center whitespace-nowrap disabled:cursor-default"
      style={{
        height: 32,
        padding: '0 12px',
        borderRadius: radius2.group,
        fontSize: type2.sm,
        background: on ? fill.trackSoft : 'transparent',
        color: on ? color.text : disabled ? color.label : soft,
        border: `1px ${disabled ? 'dashed' : 'solid'} ${on ? fill.trackNextMini : surface.border}`
      }}
    >
      {label}
    </button>
  )
}

/** A gray placeholder block while the first answer is on its way. */
export function Skeleton({ h }: { h: number }): ReactNode {
  return <div aria-hidden style={{ height: h, borderRadius: radius2.group, background: fill.skeleton }} />
}
