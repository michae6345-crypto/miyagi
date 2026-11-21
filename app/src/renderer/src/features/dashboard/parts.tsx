/**
 * Feature: dashboard. Small shared pieces. Colors are theme tokens only:
 *   green (status.passed)  a mastered skill, an edge between two mastered skills, a closed daily ring / day. Nothing else.
 *   white                  practicing (a ring), activity, a due review's dot, the ring filling up.
 *   gray                   available (solid outline), locked (dashed, 40%), empty days.
 * No pastels here: none of these is an option (Explain / Hint / Show me ...).
 */
import type { CSSProperties, ReactNode } from 'react'
import { color, fill, radius2, status, surface, type2 } from '../../core/theme'
import type { NodeState } from './model'

export const caption: CSSProperties = { fontSize: type2.xs, lineHeight: '16px', color: color.label }
export const h2: CSSProperties = { fontSize: type2.body, lineHeight: '20px', color: color.text, fontWeight: 600, margin: 0 }

export const STATE_WORD: Record<NodeState, string> = { mastered: 'Mastered', practicing: 'Practicing', available: 'Ready to learn', locked: 'Locked' }

/** A skill node: 28 px box, the circle in the middle; `due` adds the review dot, `selected` a thin outer ring. */
export function NodeGlyph({ state, due, selected, size = 28 }: { state: NodeState; due?: boolean; selected?: boolean; size?: number }): ReactNode {
  return (
    <svg data-node-glyph={state} width={size} height={size} viewBox="0 0 28 28" className="shrink-0" aria-hidden>
      {selected && <circle cx="14" cy="14" r="13.2" fill="none" stroke={fill.keycapText} strokeWidth="1" />}
      {state === 'mastered' ? (
        <>
          <circle cx="14" cy="14" r="10.5" fill={status.passed} />
          <path d="M9.6 14.3 L12.6 17.2 L18.6 10.9" fill="none" stroke={color.onGreen} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : state === 'practicing' ? (
        <circle cx="14" cy="14" r="9.6" fill="none" stroke={status.notYet} strokeWidth="2" />
      ) : (
        <circle cx="14" cy="14" r="9.6" fill={surface.window} stroke={status.watching} strokeWidth="1.5" strokeDasharray={state === 'locked' ? '3 2.4' : undefined} />
      )}
      {due && <circle data-review-dot cx="22.4" cy="5.6" r="3.6" fill={color.text} stroke={surface.window} strokeWidth="1.6" />}
    </svg>
  )
}

/** The daily ring: white fills toward the goal; closed, it turns green (the day's goal passed). */
export function TodayRing({ fraction, closed, size = 64, children }: { fraction: number; closed: boolean; size?: number; children?: ReactNode }): ReactNode {
  const stroke = 6
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const f = Math.max(0, Math.min(1, fraction))
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={fill.trackNext} strokeWidth={stroke} />
        {f > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={closed ? status.passed : color.text}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${c * f} ${c}`}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">{children}</div>
    </div>
  )
}

/** A day square: empty (a faint well), active (white), closed (green: the ring closed that day), future (an outline). */
export function DayCellBox({ state, size, today, title }: { state: 'future' | 'empty' | 'active' | 'closed'; size: number; today?: boolean; title?: string }): ReactNode {
  const bg = state === 'closed' ? status.passed : state === 'active' ? color.text : state === 'empty' ? fill.trackSoft : 'transparent'
  return (
    <span
      data-day={state}
      title={title}
      className="block shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: size >= 20 ? radius2.keycap : 2,
        background: bg,
        boxShadow: state === 'future' ? `inset 0 0 0 1px ${fill.hairline}` : today ? `0 0 0 1.5px ${surface.window}, 0 0 0 2.5px ${fill.keycapText}` : undefined
      }}
    />
  )
}

/** A rest token: filled white when held, an empty ring when not. */
export function TokenDot({ held }: { held: boolean }): ReactNode {
  return <span className="block shrink-0" style={{ width: 10, height: 10, borderRadius: radius2.round, background: held ? color.text : 'transparent', boxShadow: held ? undefined : `inset 0 0 0 1.5px ${fill.ring}` }} />
}

export function Empty({ title, body }: { title: string; body?: string }): ReactNode {
  return (
    <div data-empty className="flex flex-col gap-[4px]">
      <span className="font-semibold" style={{ fontSize: type2.sm, color: color.text }}>
        {title}
      </span>
      {body && <span style={caption}>{body}</span>}
    </div>
  )
}

/** A small neutral text button (chrome: "12 weeks", "Pause", the goal stepper). Never a hue. */
export function TextButton({ label, onClick, disabled, title, pressed }: { label: ReactNode; onClick: () => void; disabled?: boolean; title?: string; pressed?: boolean }): ReactNode {
  return (
    <button
      type="button"
      title={title}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex shrink-0 cursor-pointer items-center justify-center whitespace-nowrap hover:brightness-125 disabled:cursor-default"
      style={{
        height: 24,
        minWidth: 24,
        padding: '0 8px',
        borderRadius: radius2.control,
        fontSize: type2.xs,
        color: pressed ? color.text : fill.keycapText,
        background: pressed ? fill.navActive : surface.row,
        boxShadow: `inset 0 0 0 1px ${fill.hairline}`,
        opacity: disabled ? 0.4 : 1
      }}
    >
      {label}
    </button>
  )
}

export function Tile({ children, label, right, className = '' }: { children: ReactNode; label: string; right?: ReactNode; className?: string }): ReactNode {
  return (
    <section
      aria-label={label}
      className={`flex min-w-0 flex-col gap-[10px] ${className}`}
      style={{ padding: 16, borderRadius: radius2.chip, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}
    >
      <div className="flex min-h-[24px] items-center justify-between gap-[8px]">
        <h2 style={{ ...h2, fontSize: type2.sm }}>{label}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}
