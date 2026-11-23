/**
 * Feature: skills. One skill on the tree, and the small glyph the list and panel use.
 *
 * States (no legend: the words sit on the node):
 *   locked      a dashed faint ring on the pane, flat; the line under it says what it needs ("needs 3 skills")
 *   ready       a lifted disc with a solid ink ring
 *   practicing  the same with an inner ink arc for the evidence so far ("2 of 4 steps")
 *   mastered    a green disc with an ink check (the only green on the page)
 *   review      mastered but due: a hollow green ring and a green check. Never a demotion
 *   capstone    a rounded square with the bonsai, same rules; the goal is the hero, a bigger card
 * NEXT is a ring 3 px outside the node and the word "Next" leading the state line.
 *
 * The label rule: the name centered under the node (two lines at most), the state line under it (one line), both on a
 * plate in the pane's color. Edges never pass behind the words (layout.ts routes them around every label block).
 *
 * The unlock motion (one event, once): `anim.fill` grows the green disc from the center and draws the check (280 ms);
 * `anim.close` closes the dashed ring into a solid one. With reduced motion both arrive as a short fade.
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, ease, elevation, fill, highlight, radius2, type2 } from '../../core/theme'
import { MiyagiMark } from '../../core/ui/Mark'
import type { SkillGraphNode } from './model'

export type NodeAnim = { kind: 'fill' | 'close'; delay: number }

/** The page's own background, for the plates under labels and the locked node's face. */
export const PANE = 'var(--l-raised)'
export const CARD_BG = 'var(--l-overlay)'

type GlyphState = { state: SkillGraphNode['state']; review: boolean; evidence?: SkillGraphNode['evidence'] }

/** The check, drawn in a box of size s. */
const checkPath = (s: number): string => `M${s * 0.31},${s * 0.52} L${s * 0.44},${s * 0.65} L${s * 0.69},${s * 0.38}`

/** A round state glyph, size s (16 in the list, 44 on the tree). Pure SVG: no fill under it for the ring states. */
export function Glyph({ n, size, anim }: { n: GlyphState; size: number; anim?: NodeAnim }): ReactNode {
  const reduce = useReducedMotion() ?? false
  const s = size
  const c = s / 2
  const sw = s >= 30 ? 2 : 1.5
  const r = c - sw / 2
  const ink = color.text
  if (n.state === 'mastered' && !n.review) {
    const grow = anim?.kind === 'fill'
    return (
      <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden className="block">
        <motion.circle
          cx={c}
          cy={c}
          r={c}
          fill={color.green}
          initial={grow ? (reduce ? { opacity: 0 } : { scale: 0.2, opacity: 0 }) : false}
          animate={{ scale: 1, opacity: 1 }}
          style={{ transformOrigin: `${c}px ${c}px` }}
          transition={{ duration: reduce ? 0.12 : 0.28, ease: ease.out, delay: anim?.delay ?? 0 }}
        />
        <motion.path
          d={checkPath(s)}
          fill="none"
          stroke={color.onGreen}
          strokeWidth={s >= 30 ? 2.6 : 1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={grow ? (reduce ? { opacity: 0 } : { pathLength: 0, opacity: 0 }) : false}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: reduce ? 0.12 : 0.24, ease: ease.out, delay: (anim?.delay ?? 0) + (reduce ? 0 : 0.18) }}
        />
      </svg>
    )
  }
  if (n.state === 'mastered') {
    return (
      <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden className="block">
        <circle cx={c} cy={c} r={c - (s >= 30 ? 1.5 : 1)} fill="none" stroke={color.green} strokeWidth={s >= 30 ? 3 : 2} />
        <path d={checkPath(s)} fill="none" stroke={color.greenText} strokeWidth={s >= 30 ? 2.2 : 1.6} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (n.state === 'locked' || anim?.kind === 'close') {
    const closing = anim?.kind === 'close'
    return (
      <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden className="block">
        <motion.circle
          cx={c}
          cy={c}
          r={r}
          fill="none"
          stroke={fill.ring}
          strokeWidth={sw}
          strokeDasharray={s >= 30 ? '3.2 4' : '2 2.4'}
          initial={false}
          animate={{ opacity: closing ? 0 : 1 }}
          transition={{ duration: 0.2, delay: (anim?.delay ?? 0) + 0.3 }}
        />
        {closing && (
          <motion.circle
            cx={c}
            cy={c}
            r={r}
            fill="none"
            stroke={ink}
            strokeWidth={sw}
            transform={`rotate(-90 ${c} ${c})`}
            initial={reduce ? { opacity: 0 } : { pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: reduce ? 0.12 : 0.36, ease: ease.out, delay: anim!.delay, opacity: { duration: 0.08, delay: anim!.delay } }}
          />
        )}
      </svg>
    )
  }
  // ready / practicing
  const frac = n.state === 'practicing' ? Math.max(0.08, Math.min(1, n.evidence ? n.evidence.done / Math.max(1, n.evidence.total) : 0.5)) : 0
  const ri = s >= 30 ? c - 7.5 : c - 4
  const C = 2 * Math.PI * ri
  return (
    <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden className="block">
      <circle cx={c} cy={c} r={r} fill="none" stroke={ink} strokeWidth={sw} />
      {frac > 0 && (
        <>
          <circle cx={c} cy={c} r={ri} fill="none" stroke={fill.trackSoft} strokeWidth={s >= 30 ? 3 : 2} />
          <circle
            cx={c}
            cy={c}
            r={ri}
            fill="none"
            stroke={ink}
            strokeWidth={s >= 30 ? 3 : 2}
            strokeLinecap="round"
            strokeDasharray={`${frac * C} ${C}`}
            transform={`rotate(-90 ${c} ${c})`}
          />
        </>
      )}
    </svg>
  )
}

/** A project's square: the bonsai in a rounded card, the state as its edge. */
function Capstone({ n, size, hero }: { n: SkillGraphNode; size: number; hero: boolean }): ReactNode {
  const radius = hero ? 24 : radius2.chip
  const locked = n.state === 'locked'
  const done = n.state === 'mastered'
  const edge = done ? `inset 0 0 0 2.5px ${color.green}` : locked ? undefined : `inset 0 0 0 2px ${color.text}`
  return (
    <div
      className="relative flex items-center justify-center"
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        background: locked && !hero ? PANE : CARD_BG,
        boxShadow: [edge, locked && !hero ? undefined : highlight.card, locked && !hero ? undefined : hero ? elevation.overlay : elevation.raised].filter(Boolean).join(', ') || undefined
      }}
    >
      {locked && (
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="absolute inset-0">
          <rect x={1} y={1} width={size - 2} height={size - 2} rx={radius - 1} fill="none" stroke={fill.ring} strokeWidth={hero ? 2 : 1.5} strokeDasharray={hero ? '5 5' : '3.2 4'} />
        </svg>
      )}
      <span style={{ opacity: locked ? 0.62 : 1 }} className="flex">
        <MiyagiMark size={hero ? Math.round(size * 0.56) : Math.round(size * 0.56)} />
      </span>
      {done && (
        <span className="absolute" style={{ right: -6, top: -6 }}>
          <Glyph n={{ state: 'mastered', review: false }} size={hero ? 22 : 18} />
        </span>
      )}
    </div>
  )
}

export type SkillNodeProps = {
  n: SkillGraphNode
  x: number
  y: number
  /** The node's radius (half its size). */
  r: number
  hero: boolean
  labelW: number
  /** Node edge to the label's top (graphInput geom). */
  labelGap: number
  lines: number
  line: string
  /** The node's track, for its tooltip. */
  track?: string
  dim: boolean
  focused: boolean
  anim?: NodeAnim
  onOpen: (id: string) => void
  onHover: (id: string | undefined) => void
}

export function SkillNode({ n, x, y, r, hero, labelW, labelGap, lines, line, track, dim, focused, anim, onOpen, onHover }: SkillNodeProps): ReactNode {
  const reduce = useReducedMotion() ?? false
  const size = 2 * r
  const cap = n.kind === 'capstone'
  const locked = n.state === 'locked'
  const flat = locked && !cap
  const ring = n.isNext || focused
  const plate = { background: PANE, borderRadius: radius2.keycap, padding: '0 4px', boxDecorationBreak: 'clone' as const, WebkitBoxDecorationBreak: 'clone' as const }
  const w = Math.max(size, labelW)
  return (
    <motion.div
      data-skill-node={n.id}
      data-state={n.state}
      data-next={n.isNext || undefined}
      className="absolute flex flex-col items-center"
      style={{ left: x - w / 2, top: y - r, width: w, pointerEvents: 'none' }}
      initial={false}
      animate={{ opacity: dim ? 0.26 : 1 }}
      transition={{ duration: reduce ? 0 : 0.18 }}
    >
      <motion.button
        type="button"
        aria-label={`${n.label}, ${line}`}
        title={track ? `${track} · ${n.label}` : n.label}
        className="relative cursor-pointer outline-offset-4"
        style={{ width: size, height: size, borderRadius: cap ? (hero ? 24 : radius2.chip) : radius2.round, pointerEvents: 'auto' }}
        onClick={() => onOpen(n.id)}
        onPointerEnter={() => onHover(n.id)}
        onPointerLeave={() => onHover(undefined)}
        onFocus={() => onHover(n.id)}
        onBlur={() => onHover(undefined)}
        whileHover={reduce ? undefined : { y: -1.5 }}
        whileTap={reduce ? undefined : { scale: 0.96 }}
        transition={{ type: 'spring', stiffness: 420, damping: 34, mass: 0.9 }}
      >
        {cap ? (
          <Capstone n={n} size={size} hero={hero} />
        ) : (
          <span
            className="absolute inset-0 block"
            style={{
              borderRadius: radius2.round,
              background: flat ? PANE : CARD_BG,
              boxShadow: flat ? undefined : `${highlight.card}, ${elevation.raised}`
            }}
          />
        )}
        {!cap && (
          <span className="absolute inset-0 block">
            <Glyph n={n} size={size} anim={anim} />
          </span>
        )}
        {ring && (
          <span
            aria-hidden
            className="absolute block"
            style={{
              inset: -5,
              borderRadius: cap ? (hero ? 29 : radius2.chip + 5) : radius2.round,
              boxShadow: `0 0 0 2px ${n.isNext ? color.text : fill.ring}`
            }}
          />
        )}
      </motion.button>
      <div className="flex flex-col items-center text-center" style={{ marginTop: labelGap, maxWidth: labelW, gap: 1 }}>
        <span
          className="block"
          title={n.label}
          style={{
            fontSize: hero ? type2.md : type2.sm,
            lineHeight: hero ? '18px' : '16px',
            fontWeight: hero ? 600 : 500,
            color: locked ? color.label : color.text,
            display: '-webkit-box',
            WebkitLineClamp: lines,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            maxWidth: labelW
          }}
        >
          <span style={plate}>{n.label}</span>
        </span>
        <span className="block truncate" style={{ fontSize: type2.xs, lineHeight: '15px', color: locked ? color.faint : color.label, maxWidth: labelW, fontVariantNumeric: 'tabular-nums' }}>
          <span style={plate}>
            {n.isNext && <span style={{ color: color.text, fontWeight: 600 }}>Next · </span>}
            {line}
          </span>
        </span>
      </div>
    </motion.div>
  )
}

/** The trunk point that joins several roots into one tree (Map only). */
export function TrunkPoint({ x, y }: { x: number; y: number }): ReactNode {
  return <span aria-hidden className="absolute block" style={{ left: x - 5, top: y - 5, width: 10, height: 10, borderRadius: radius2.round, background: color.label }} />
}
