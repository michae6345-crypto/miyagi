/**
 * Feature: errors. The small pieces every error surface shares: the pill line (one glyph, one line, an optional
 * mono count or chip), the glyphs (no hue: a white ring, a gray arc, the wifi marks), and the card frame that grows
 * out of the island (header with the Esc keycap, title, body).
 */
import { motion, useReducedMotion } from 'motion/react'
import { Children, isValidElement, useEffect, type ReactNode } from 'react'
import { Spinner } from '../../core/ui/atoms'
import { Keycap } from '../../core/ui/Keycap'
import { color, fill, font, radius2, spring, status, type2 } from '../../core/theme'
import { setVisible, type CardId } from './store'

export type Glyph = 'ring' | 'arc' | 'tick' | 'wifi-off' | 'wifi'

/** No status hue anywhere here: a stall is a white ring, a retry the gray arc, a recovery a white tick (never green). */
export function ErrGlyph({ g, size = 16 }: { g: Glyph; size?: number }): ReactNode {
  if (g === 'arc') return <Spinner size={size} c={status.watching} track={fill.track} />
  if (g === 'ring')
    return (
      <svg aria-hidden width={size} height={size} viewBox="0 0 16 16" className="shrink-0">
        <circle cx="8" cy="8" r="6.4" fill="none" stroke={status.notYet} strokeWidth="1.5" />
      </svg>
    )
  if (g === 'tick')
    return (
      <svg aria-hidden width={size} height={size} viewBox="0 0 16 16" className="shrink-0">
        <circle cx="8" cy="8" r="6.4" fill="none" stroke={color.text} strokeWidth="1.5" />
        <path d="M4.8 8.2 L7 10.3 L11.2 5.9" fill="none" stroke={color.text} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  const waves = 'M2 6 A9 9 0 0 1 14 6 M4.5 8.6 A5.5 5.5 0 0 1 11.5 8.6 M7 11.2 A2 2 0 0 1 9 11.2'
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 16 16" className="shrink-0">
      <path d={waves} fill="none" stroke={g === 'wifi' ? color.text : status.offline} strokeWidth="1.5" strokeLinecap="round" />
      {g === 'wifi-off' && <path d="M2.5 2.5 L13.5 13.5" stroke={color.text} strokeWidth="1.5" strokeLinecap="round" />}
    </svg>
  )
}

/**
 * The pill line: pill-sized (34 high, width hugs the text). `mono` = the step counter only ("Step 3 of 6"); `meta` = a
 * quiet count in the body font ("try 2 of 5", "18 s"); `chip` = the control to find; `action` = a small real button.
 */
export function PillLine({
  id,
  glyph,
  text,
  mono,
  meta,
  chip,
  action,
  live = 'polite',
  metaHidden
}: {
  id: string
  glyph: Glyph
  text: string
  mono?: string
  meta?: string
  chip?: string
  action?: { label: string; onClick: () => void }
  live?: 'polite' | 'off'
  /** A count that ticks every second (20 s, 19 s): kept out of the live region so it is not read out each tick. */
  metaHidden?: boolean
}): ReactNode {
  const reduce = useReducedMotion()
  return (
    <motion.div
      data-err-line={id}
      role="status"
      aria-live={live}
      className="flex h-[34px] items-center whitespace-nowrap"
      style={{ paddingLeft: 12, paddingRight: chip || action ? 5 : 16, gap: 10, fontSize: type2.sm, fontWeight: 500, color: color.text }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 3 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...spring, opacity: { duration: 0.18 } }}
    >
      <ErrGlyph g={glyph} />
      <span>{text}</span>
      {mono && (
        <span className="tabular-nums" style={{ fontFamily: font.mono, fontSize: type2.micro, color: color.label }}>
          {mono}
        </span>
      )}
      {meta && (
        <span aria-hidden={metaHidden || undefined} className="tabular-nums" style={{ fontSize: type2.xs, fontWeight: 400, color: color.label }}>
          {meta}
        </span>
      )}
      {chip && (
        <span className="flex h-[24px] items-center" style={{ padding: '0 10px', borderRadius: radius2.round, background: fill.navActive, fontSize: type2.xs, color: color.text }}>
          {chip}
        </span>
      )}
      {action && (
        <motion.button
          type="button"
          className="flex h-[24px] cursor-pointer items-center"
          style={{ padding: '0 10px', borderRadius: radius2.round, background: color.accent, color: color.onAccent, fontSize: type2.xs, fontWeight: 600, border: 'none' }}
          whileHover={{ filter: 'brightness(0.94)' }}
          whileTap={{ scale: 0.96 }}
          transition={{ duration: 0.12 }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={action.onClick}
        >
          {action.label}
        </motion.button>
      )}
    </motion.div>
  )
}

/** Marks a card as the one on the island while mounted (Esc closes it, store.ts). */
export function useVisible(id: CardId): void {
  useEffect(() => {
    setVisible(id, true)
    return () => setVisible(id, false)
  }, [id])
}

/** A card's frame: the island is the black background; this pads it and lays out header, title, body, the rest. */
export function CardFrame({
  id,
  head,
  title,
  body,
  sub,
  esc = true,
  children,
  role = 'dialog'
}: {
  id: CardId
  head?: ReactNode
  title: string
  /** A mono line under the title (Step 3 of 6), so the header row never has to cut its text. */
  sub?: string
  body?: ReactNode
  esc?: boolean
  children?: ReactNode
  role?: 'dialog' | 'alertdialog'
}): ReactNode {
  useVisible(id)
  const reduce = useReducedMotion()
  // Enter calmly: the card grows out of the island (core), then its parts settle in one after another, 40 ms apart.
  const part = (i: number): Record<string, unknown> => ({
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 6 },
    animate: { opacity: 1, y: 0 },
    transition: { ...spring, delay: reduce ? 0 : 0.05 + i * 0.04, opacity: { duration: 0.2, delay: reduce ? 0 : 0.05 + i * 0.04 } }
  })
  let n = 0
  return (
    <div data-err-card={id} role={role} aria-labelledby={`${id}-title`} className="flex flex-col" style={{ padding: 20, gap: 16, color: color.text }}>
      {(head || esc) && (
        <motion.div {...part(n++)} className="flex min-h-[22px] items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">{head}</div>
          {esc && <Keycap k="dismiss" />}
        </motion.div>
      )}
      <motion.div {...part(n++)} className="flex flex-col" style={{ gap: 6 }}>
        <h2 id={`${id}-title`} className="m-0" style={{ fontSize: type2.lg, lineHeight: '22px', fontWeight: 600 }}>
          {title}
        </h2>
        {sub && <span style={{ fontFamily: font.mono, fontSize: type2.micro, lineHeight: '16px', color: color.label }}>{sub}</span>}
        {body && (
          <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
            {body}
          </p>
        )}
      </motion.div>
      {/*
        Key each block by its child's own key. Children.toArray keys by original slot (".0", ".2", or the child's own
        key), so a block that appears or goes away (View report / Hide report) doesn't shift and remount the ones
        after it, which would replay their entrance.
      */}
      {Children.toArray(children).map((c, i) => (
        <motion.div key={isValidElement(c) && c.key != null ? c.key : i} {...part(n + i)} className="flex flex-col" style={{ gap: 16 }}>
          {c}
        </motion.div>
      ))}
    </div>
  )
}

/** A small caption under a button or at the card's foot. */
export function Caption({ children }: { children: ReactNode }): ReactNode {
  return (
    <p className="m-0" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
      {children}
    </p>
  )
}

/** The uppercase section label (Or start a library lesson, Includes, Never). */
export function Eyebrow({ children }: { children: ReactNode }): ReactNode {
  return (
    <span style={{ fontSize: type2.micro, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: color.label }}>{children}</span>
  )
}
