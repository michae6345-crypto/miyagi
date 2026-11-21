/**
 * Feature: tips. One coach mark: a small dark sheet beside the real element, with a caret pointing at it.
 *
 *   [title]                      13 semibold, text
 *   [body]                       13, label; keys as platform Keycaps, Hint / Show me as their pastel chips
 *   [...]              [Got it]  the "..." menu holds "Don't show tips"; Got it is the ONE primary here
 *
 * The sheet (surface.sheet, a step lighter than the island and the panel) reads as its own thing next to both. It
 * rises 6 px toward what it points at and fades in on the house spring; reduced motion: the fade only. data-hit, so
 * its buttons take clicks in the click-through overlay and the engine's screen reader ignores it.
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { MoreHorizontal } from 'lucide-react'
import { forwardRef, useId, type ReactNode } from 'react'
import { actionTone, color, duration, elevation, fill, highlight, radius2, spring, surface, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { pressMotion } from '../../core/ui/motion'
import type { CaretSide } from './place'
import type { BodyPart } from './tips'

export const MARK_W = 264
const CARET = 10
const LABEL: Record<'hint' | 'show_me', string> = { hint: 'Hint', show_me: 'Show me' }

type Props = {
  title: string
  body: BodyPart[]
  caret: CaretSide
  caretAt: number
  menu: boolean
  onMenu: (open: boolean) => void
  onGotIt: () => void
  onOff: () => void
}

/** Where the mark starts its rise: 6 px away from what it points at. */
const FROM: Record<CaretSide, { x: number; y: number }> = { top: { x: 0, y: 6 }, bottom: { x: 0, y: -6 }, left: { x: 6, y: 0 }, right: { x: -6, y: 0 } }

export const CoachMark = forwardRef<HTMLDivElement, Props>(function CoachMark({ title, body, caret, caretAt, menu, onMenu, onGotIt, onOff }, ref) {
  const reduced = useReducedMotion()
  const titleId = useId()
  const bodyId = useId()
  const from = reduced ? { x: 0, y: 0 } : FROM[caret]
  return (
    <motion.div
      ref={ref}
      data-hit
      data-part="tip"
      role="dialog"
      aria-modal={false}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      className="pointer-events-auto relative"
      style={{
        width: MARK_W,
        padding: '14px 14px 12px 16px',
        borderRadius: radius2.chip,
        background: surface.sheet,
        boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.overlay}`
      }}
      initial={{ opacity: 0, ...from }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      exit={{ opacity: 0, transition: { duration: duration.fast } }}
      transition={{ ...spring, opacity: { duration: duration.slow } }}
    >
      <Caret side={caret} at={caretAt} />
      <div id={titleId} className="font-semibold" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.text }}>
        {title}
      </div>
      <div id={bodyId} className="mt-[4px]" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label, textWrap: 'pretty' }}>
        {body.map((part, i) => (
          <Part key={i} part={part} />
        ))}
      </div>
      <div className="relative mt-[12px] flex items-center justify-between">
        <motion.button
          type="button"
          aria-label="Tip options"
          aria-haspopup="menu"
          aria-expanded={menu}
          title="Tip options"
          className="mg-press flex h-[28px] w-[28px] cursor-pointer items-center justify-center"
          style={{ borderRadius: radius2.control, color: fill.keyText, background: menu ? fill.chipHover : fill.clear }}
          {...pressMotion()}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onMenu(!menu)}
        >
          <MoreHorizontal size={16} strokeWidth={1.8} />
        </motion.button>
        <PrimaryButton label="Got it" onClick={onGotIt} />
        <AnimatePresence>{menu && <Menu onOff={onOff} />}</AnimatePresence>
      </div>
    </motion.div>
  )
})

function Part({ part }: { part: BodyPart }): ReactNode {
  if (typeof part === 'string') return part
  if ('key' in part) {
    return (
      <span className="inline-flex align-[-4px]">
        <Keycap k={part.key} size="sm" />
      </span>
    )
  }
  // An option named in the copy wears its own pastel (BRAND.md mapping), so the learner finds the same tile in the panel.
  return (
    <span
      className="inline-flex items-center whitespace-nowrap font-medium"
      style={{ height: 20, padding: '0 7px', borderRadius: radius2.keycap, background: actionTone[part.option], color: color.onAccent, fontSize: type2.xs, verticalAlign: 1 }}
    >
      {LABEL[part.option]}
    </span>
  )
}

/** The caret: a small square of the sheet, turned 45°, half outside the edge facing the target, its two outer edges lined. */
function Caret({ side, at }: { side: CaretSide; at: number }): ReactNode {
  const half = CARET / 2
  const pos =
    side === 'top'
      ? { left: at - half, top: -half }
      : side === 'bottom'
        ? { left: at - half, bottom: -half }
        : side === 'left'
          ? { top: at - half, left: -half }
          : { top: at - half, right: -half }
  // Turned 45° clockwise, the square's top-left corner points up, bottom-left points left, and so on: line the two
  // edges that meet at the pointing corner, and round that corner a touch.
  const edges: Record<CaretSide, string> = {
    top: `inset 1px 1px 0 ${surface.border}`,
    left: `inset 1px -1px 0 ${surface.border}`,
    bottom: `inset -1px -1px 0 ${surface.border}`,
    right: `inset -1px 1px 0 ${surface.border}`
  }
  const corner: Record<CaretSide, string> = { top: 'borderTopLeftRadius', left: 'borderBottomLeftRadius', bottom: 'borderBottomRightRadius', right: 'borderTopRightRadius' }
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute"
      style={{ width: CARET, height: CARET, background: surface.sheet, transform: 'rotate(45deg)', boxShadow: edges[side], [corner[side]]: 2, ...pos }}
    />
  )
}

function Menu({ onOff }: { onOff: () => void }): ReactNode {
  return (
    <motion.div
      role="menu"
      aria-label="Tips"
      // Its own data-hit: it hangs below the mark, outside the mark's rect that main's click poll reads.
      data-hit
      className="absolute left-0"
      style={{
        // Drops below the mark from the "..." button, so it never covers the tip's own words.
        top: 36,
        minWidth: 168,
        padding: 4,
        borderRadius: radius2.row,
        background: color.island,
        boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.overlay}`,
        transformOrigin: '0 0'
      }}
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, transition: { duration: duration.fast } }}
      transition={{ ...spring, opacity: { duration: duration.base } }}
    >
      <button
        type="button"
        role="menuitem"
        className="mg-press flex h-[30px] w-full cursor-pointer items-center whitespace-nowrap text-left"
        style={{ padding: '0 10px', borderRadius: radius2.control, color: color.text, fontSize: type2.sm }}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onOff}
      >
        Don&apos;t show tips
      </button>
    </motion.div>
  )
}
