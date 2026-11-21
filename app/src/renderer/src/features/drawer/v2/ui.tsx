/**
 * Feature: drawer (v2, A1). The panel's small shared pieces: its text tones (all core/theme tokens), the hairline
 * divider, inline text where `backticks` mark code (React text only, never HTML), and the chrome tooltip.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { color, fill, font, radius2, surface, type2 } from '../../../core/theme'
import { fade } from '../../../core/ui/motion'
import { Keycap, type KeyName } from '../../../core/ui/Keycap'

/**
 * Les-*: titles in white, body copy at white .78, labels at .6. There is no .78 text token in core yet (Core request
 * 1 in agents/drawer.md); fill.keycapText has that exact value.
 */
export const tone = { text: color.text, body: fill.keycapText, label: color.label, hairline: fill.hairline } as const

/** A full-width 1 px rule between the panel's sections. */
export function Divider(): ReactNode {
  return <div aria-hidden className="h-px shrink-0" style={{ background: tone.hairline }} />
}

/** Text where `code` spans render in the mono font (Les-Checking caption, Les-NotYet lines, Les-Hint). */
export function Inline({ text, codeColor }: { text: string; codeColor?: string }): ReactNode {
  const parts = text.split('`')
  // An odd count of backticks: the last one is literal, not an opening.
  if (parts.length % 2 === 0) return text
  return parts.map((p, i) =>
    i % 2 ? (
      <span key={i} style={{ fontFamily: font.mono, fontSize: '0.95em', color: codeColor }}>
        {p}
      </span>
    ) : (
      p
    )
  )
}

/** The 12 px label above a block ("Type this in the new cell", "Need help"). */
export function Caption({ children }: { children: ReactNode }): ReactNode {
  return (
    <span className="block" style={{ fontSize: type2.xs, lineHeight: '16px', color: tone.label }}>
      {children}
    </span>
  )
}

/**
 * A small tooltip with the action's name and its keycap (persona QA: the panel's chrome glyphs were unlabeled). It
 * shows 350 ms after the pointer settles, or at once on keyboard focus; it never takes clicks. The keycap comes from
 * the platform (core Keycap), so a key the platform lacks just drops out.
 */
export function Tip({
  label,
  k,
  children,
  side = 'bottom',
  align = 'end'
}: {
  label: string
  k?: KeyName
  children: ReactNode
  side?: 'top' | 'bottom'
  align?: 'end' | 'center'
}): ReactNode {
  const [on, setOn] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const reduced = useReducedMotion()
  useEffect(() => () => clearTimeout(timer.current), [])
  const show = (now: boolean): void => {
    clearTimeout(timer.current)
    if (now) setOn(true)
    else timer.current = setTimeout(() => setOn(true), 350)
  }
  const hide = (): void => {
    clearTimeout(timer.current)
    setOn(false)
  }
  const y = side === 'bottom' ? -4 : 4
  return (
    <span
      className="relative inline-flex"
      onPointerEnter={() => show(false)}
      onPointerLeave={hide}
      onPointerDown={hide}
      onFocus={(e) => (e.target as HTMLElement).matches(':focus-visible') && show(true)}
      onBlur={hide}
    >
      {children}
      <AnimatePresence>
        {on && (
          <motion.span
            role="tooltip"
            data-part="panel-tip"
            className="pointer-events-none absolute z-10 flex items-center gap-[8px] whitespace-nowrap"
            style={{
              ...(side === 'bottom' ? { top: 'calc(100% + 6px)' } : { bottom: 'calc(100% + 6px)' }),
              ...(align === 'end' ? { right: 0 } : { left: '50%', x: '-50%' }),
              height: 28,
              padding: '0 8px 0 10px',
              borderRadius: radius2.control,
              background: color.glass,
              boxShadow: `inset 0 0 0 1px ${fill.hairline}, ${surface.shadowSmall}`,
              fontSize: type2.xs,
              color: color.text
            }}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: fade.instant }}
            transition={fade.tint}
          >
            <span>{label}</span>
            {k && <Keycap k={k} size="sm" />}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  )
}
