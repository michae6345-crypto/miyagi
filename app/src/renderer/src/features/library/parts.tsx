/**
 * Feature: library. Small pieces shared by the list (Home-Library) and the preview (Home-LessonDetail). Neutral
 * fills only: nothing here is a status or an option, so no green and no pastel. Progress is white on the track.
 */
import type { ReactNode } from 'react'
import type { LessonTool, LibraryItem } from '../../../../../../shared/contracts/events'
import { color, fill, font, radius2, surface, type2 } from '../../core/theme'

/** Secondary text on the window (the mockups' white at 78%). */
export const soft = fill.keycapText

export const TOOL_NAME: Record<LessonTool, string> = { vscode: 'VS Code', jupyter: 'Jupyter', terminal: 'Terminal', excel: 'Excel' }
const TOOL_ABBR: Record<LessonTool, string> = { vscode: 'VS', jupyter: 'Jn', terminal: '>_', excel: 'Xl' }
/** The tools a lesson can be filtered by today; Excel shows as "soon". */
export const FILTER_TOOLS: LessonTool[] = ['vscode', 'jupyter', 'terminal']

/** A tool's two-letter tile (Home-Library .app). */
export function ToolTile({ tool, size = 32, muted }: { tool: LessonTool; size?: number; muted?: boolean }): ReactNode {
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center"
      style={{
        width: size,
        height: size,
        borderRadius: size <= 20 ? radius2.keycap : size >= 48 ? radius2.card : radius2.control,
        background: surface.row,
        boxShadow: `inset 0 0 0 1px ${surface.border}`,
        fontFamily: font.mono,
        fontSize: size >= 48 ? type2.sm : type2.micro,
        color: muted ? color.label : soft
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
