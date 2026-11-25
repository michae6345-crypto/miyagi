/**
 * Feature: library. Small pieces shared by the list (Home-Library) and the preview (Home-LessonDetail). Neutral
 * fills only: nothing here is a status or an option, so no green and no pastel. Progress is white on the track.
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import type { LessonTool, LibraryItem } from '../../../../../../shared/contracts/events'
import { color, fill, radius2, surface, tone, type Tone, type2 } from '../../core/theme'

/** Secondary text on the window (the mockups' white at 78%). */
export const soft = fill.keycapText

export const TOOL_NAME: Record<LessonTool, string> = { vscode: 'VS Code', jupyter: 'Jupyter', terminal: 'Terminal', excel: 'Excel' }
const TOOL_ABBR: Record<LessonTool, string> = { vscode: 'VS', jupyter: 'Jn', terminal: 'Sh', excel: 'Xl' }
/** The tools a lesson can be filtered by today; Excel shows as "soon". */
export const FILTER_TOOLS: LessonTool[] = ['vscode', 'jupyter', 'terminal']

/** Soft pastel per tool (the theme's tone tokens, so a tag reads in light and dark). A tag, never status. */
export const TOOL_TONE: Record<LessonTool, Tone> = { vscode: 'sky', jupyter: 'lilac', terminal: 'pink', excel: 'peach' }

/** A tool's soft tag: "VS Code" in its pastel. */
export function ToolTag({ tool }: { tool: LessonTool }): ReactNode {
  return (
    <span className="inline-flex shrink-0 items-center whitespace-nowrap font-medium" style={{ height: 20, padding: '0 8px', borderRadius: radius2.round, background: tone[TOOL_TONE[tool]].bg, color: tone[TOOL_TONE[tool]].fg, fontSize: type2.micro }}>
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
        background: tone[TOOL_TONE[tool]].bg,
        opacity: muted ? 0.6 : 1,
        fontSize: size >= 48 ? type2.sm : type2.micro,
        color: tone[TOOL_TONE[tool]].fg
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
export function Skeleton({ h, w }: { h: number; w?: number | string }): ReactNode {
  // .mg-skeleton is an opacity pulse (no gradient sweep); styles.css drops it with reduced motion.
  return <div aria-hidden className="mg-skeleton" style={{ height: h, width: w, borderRadius: radius2.group, background: fill.skeleton }} />
}

/**
 * A progress ring: a hairline track and an ink arc that draws in on first paint (an opacity-free path draw: a plain
 * snap with reduced motion). Ink, never green: green only means a passed check. `children` sits in the middle.
 */
export function ProgressRing({ fraction, size = 56, stroke = 4, label, children }: { fraction: number; size?: number; stroke?: number; label: string; children?: ReactNode }): ReactNode {
  const reduce = useReducedMotion()
  const f = Math.max(0, Math.min(1, fraction))
  const r = (size - stroke) / 2
  return (
    <div role="img" aria-label={label} className="relative flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg aria-hidden width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={fill.hairline} strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color.text}
          strokeWidth={stroke}
          strokeLinecap="round"
          initial={{ pathLength: reduce ? f : 0 }}
          animate={{ pathLength: f }}
          transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 120, damping: 24 }}
        />
      </svg>
      {children && <div className="absolute inset-0 flex items-center justify-center">{children}</div>}
    </div>
  )
}
