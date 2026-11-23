/**
 * Feature: buddy. The buddy's body: a character of its own, not the logo. (The bonsai stays the logo, in the notch.)
 *
 * Three were drawn to pick from (Adrian, Nov 22: "an actual personalized character... really cute") and on Nov 23
 * he picked the sprout. The other two stay for now, behind ?char=. All original, all drawn here as plain SVG so their parts can move, all in the buddy's skin
 * (palette.ts: its color, which is also still his to pick):
 *   sprout   a round creature with a two-leaf sprout on its head. The leaves are its ears and its wings.
 *   leaf     a leaf with a face. Its tip is its pointer.
 *   dot      a droplet of the island: black, a rim in its color, eyes only.
 * One face for all three, driven by:
 *   mood     calm, happy, curious, thinking, listening, sleepy: the eyes and the mouth
 *   look     where it is looking, -1..1 each way: the whole face slides that way
 *   talking  the mouth moves
 *   flying   the leaves beat (sprout), the body trembles a little
 *   point    -1 / 1: a little arm on that side (sprout)
 * And two ways it is the learner's own (sprout; proposals, nothing stores them yet):
 *   tint     its body color, one of the brand's pastels (palette.ts TINTS); without one it is the skin's
 *   grown    0 a seedling with one leaf, 1 two leaves, 2 two leaves and a bud: it grows as they learn
 * It blinks by itself. Transform and opacity only; with reduced motion nothing moves (buddy.css).
 * No glow, no gradient. A 48-unit box, like an icon: the body sits low so the sprout has room above it.
 */
import { useId, type CSSProperties, type ReactNode } from 'react'
import './buddy.css'
import { GLINT, INK, SKIN, TINTS, type Skin, type Tint } from './palette'

export type CharacterKind = 'sprout' | 'leaf' | 'dot'
export type Mood = 'calm' | 'happy' | 'curious' | 'thinking' | 'listening' | 'sleepy'

export type CharacterProps = {
  kind?: CharacterKind
  size?: number
  mood?: Mood
  look?: { x: number; y: number }
  talking?: boolean
  flying?: boolean
  point?: -1 | 0 | 1
  tint?: Tint
  grown?: 0 | 1 | 2
  /** Its colors, when not the skin in use: for the color sheet. */
  skin?: Skin
  className?: string
}

export const CHARACTERS: CharacterKind[] = ['sprout', 'leaf', 'dot']
/** The one in use: Adrian picked the sprout on Nov 23. In the browser stage ?char=<kind> shows another. */
export const DEFAULT_CHARACTER: CharacterKind = 'sprout'

const clamp = (v: number): number => Math.max(-1, Math.min(1, Number.isFinite(v) ? v : 0))
const OUTLINE = 1.7

/** Where each kind's face sits, and how far it slides when it looks. */
const FACE: Record<CharacterKind, { cx: number; cy: number; gap: number; slide: { x: number; y: number }; mouthY: number }> = {
  sprout: { cx: 24, cy: 27.2, gap: 5.6, slide: { x: 2.6, y: 1.7 }, mouthY: 6 },
  leaf: { cx: 24, cy: 27.5, gap: 4.6, slide: { x: 1.9, y: 1.4 }, mouthY: 5.4 },
  dot: { cx: 24, cy: 26.5, gap: 5.2, slide: { x: 2.4, y: 1.6 }, mouthY: 6.6 }
}

/** One eye, drawn around 0,0. `bar`: the dot's eyes are rounded bars, not ovals. */
function Eye({ mood, ink, bar }: { mood: Mood; ink: string; bar: boolean }): ReactNode {
  if (mood === 'happy') return <path d="M-2.7 1.2 Q0 -3.2 2.7 1.2" fill="none" stroke={ink} strokeWidth={1.8} strokeLinecap="round" />
  if (mood === 'sleepy') return <path d="M-2.5 0 Q0 1.9 2.5 0" fill="none" stroke={ink} strokeWidth={1.7} strokeLinecap="round" />
  const wide = mood === 'curious' || mood === 'listening'
  if (bar) {
    const h = wide ? 9 : mood === 'thinking' ? 5.4 : 7.4
    return <rect className="ch-eye" x={-2.3} y={-h / 2} width={4.6} height={h} rx={2.3} fill={ink} />
  }
  const rx = wide ? 2.7 : 2.3
  const ry = wide ? 3.6 : mood === 'thinking' ? 2.6 : 3.1
  return (
    <g className="ch-eye">
      <ellipse rx={rx} ry={ry} fill={ink} />
      <circle cx={0.9} cy={-1.2} r={wide ? 1 : 0.8} fill={GLINT} />
    </g>
  )
}

/** The mouth, drawn around 0,0. */
function Mouth({ mood, talking, ink }: { mood: Mood; talking: boolean; ink: string }): ReactNode {
  if (talking) return <ellipse className="ch-talk" rx={1.9} ry={2.1} fill={ink} />
  if (mood === 'happy') return <path d="M-3.1 -0.9 Q0 4.2 3.1 -0.9 Z" fill={ink} stroke={ink} strokeWidth={1} strokeLinejoin="round" />
  if (mood === 'curious' || mood === 'listening') return <ellipse rx={1.25} ry={1.5} fill={ink} />
  if (mood === 'thinking') return <path d="M-1.6 0.3 L1.9 -0.2" fill="none" stroke={ink} strokeWidth={1.6} strokeLinecap="round" />
  if (mood === 'sleepy') return <path d="M-1.4 0 Q0 0.9 1.4 0" fill="none" stroke={ink} strokeWidth={1.5} strokeLinecap="round" />
  return <path d="M-2.4 -0.4 Q0 2.2 2.4 -0.4" fill="none" stroke={ink} strokeWidth={1.6} strokeLinecap="round" />
}

/** The face: two eyes and a mouth, slid toward where it looks. */
function Face({ kind, mood, look, talking, blush, ink }: { kind: CharacterKind; mood: Mood; look: { x: number; y: number }; talking: boolean; blush: string; ink: string }): ReactNode {
  const f = FACE[kind]
  // Thinking looks up and away by itself.
  const lx = mood === 'thinking' ? -0.55 : clamp(look.x)
  const ly = mood === 'thinking' ? -0.85 : clamp(look.y)
  const bar = kind === 'dot'
  return (
    <g className="ch-face" style={{ transform: `translate(${(lx * f.slide.x).toFixed(2)}px, ${(ly * f.slide.y).toFixed(2)}px)` }}>
      {kind === 'sprout' && (
        <>
          <ellipse cx={f.cx - 9.4} cy={f.cy + 4.6} rx={2.5} ry={1.5} fill={blush} />
          <ellipse cx={f.cx + 9.4} cy={f.cy + 4.6} rx={2.5} ry={1.5} fill={blush} />
        </>
      )}
      <g transform={`translate(${f.cx - f.gap} ${f.cy})`}>
        <Eye mood={mood} ink={ink} bar={bar} />
      </g>
      <g transform={`translate(${f.cx + f.gap} ${f.cy})`}>
        <Eye mood={mood} ink={ink} bar={bar} />
      </g>
      {(kind !== 'dot' || talking) && (
        <g transform={`translate(${f.cx} ${f.cy + f.mouthY})`}>
          <Mouth mood={mood} talking={talking} ink={ink} />
        </g>
      )}
    </g>
  )
}

/** How far each of the sprout's leaves is turned from its rest, degrees (positive: outward and down). */
const LEAVES: Record<Mood, [number, number]> = { calm: [0, 0], happy: [14, 14], curious: [-14, 6], thinking: [22, -6], listening: [-24, -24], sleepy: [30, 30] }

/** The sprout's body. */
const ROUND = 'M24 12.6 C33.6 12.6 40.4 19.6 40.4 29.4 C40.4 37.8 33.8 43.2 24 43.2 C14.2 43.2 7.6 37.8 7.6 29.4 C7.6 19.6 14.4 12.6 24 12.6 Z'
/** A shaded skin: the lit part of the body is the body moved this far up and toward the light, so the shade is what is left under it. */
const LIT = { x: 1.5, y: -2.7 } as const

function Sprout({ mood, point, body, leaf, shade, grown, id }: { mood: Mood; point: -1 | 0 | 1; body: string; leaf: string; shade?: string; grown: 0 | 1 | 2; id: string }): ReactNode {
  const [l, r] = LEAVES[mood]
  return (
    <>
      {/* The arm it points with, behind the body. */}
      {point !== 0 && <ellipse cx={24 + point * 19} cy={29.5} rx={5.4} ry={3} fill={body} stroke={INK} strokeWidth={OUTLINE} transform={`rotate(${point * -20} ${24 + point * 15} 30)`} />}
      <g className="ch-sprout">
        {/* The stem: pale over ink, so it shows on a dark app (where the ink is lost) and on a light one. */}
        <path d="M24 13.6 L24 8.2" fill="none" stroke={INK} strokeWidth={OUTLINE * 2 + 1.5} strokeLinecap="round" />
        <path d="M24 14 L24 8.2" fill="none" stroke={leaf} strokeWidth={1.5} strokeLinecap="round" />
        {/* A seedling has one leaf; it gets its second as the learner gets going. */}
        {grown > 0 && (
          <g className="ch-leaf ch-leaf-l" style={{ '--turn': `${-l}deg` } as CSSProperties}>
            <path d="M24 8.6 C19.6 9.6 15.4 7.4 14.2 3.2 C18.8 1.6 23 3.8 24 8.6 Z" fill={leaf} stroke={INK} strokeWidth={OUTLINE} strokeLinejoin="round" />
          </g>
        )}
        <g className="ch-leaf ch-leaf-r" style={{ '--turn': `${r}deg` } as CSSProperties}>
          <path d="M24 8.6 C28.4 9.6 32.6 7.4 33.8 3.2 C29.2 1.6 25 3.8 24 8.6 Z" fill={leaf} stroke={INK} strokeWidth={OUTLINE} strokeLinejoin="round" />
        </g>
        {/* And a bud between them, later on. */}
        {grown > 1 && <circle cx={24} cy={6.4} r={3} fill={TINTS.pink.body} stroke={INK} strokeWidth={OUTLINE} />}
      </g>
      {shade ? (
        <>
          {/* Flat shading, no gradient: the body in its shade, the lit part over it (cut to the body), then the outline. */}
          <clipPath id={id}>
            <path d={ROUND} />
          </clipPath>
          <path d={ROUND} fill={shade} />
          <g clipPath={`url(#${id})`}>
            <path d={ROUND} fill={body} transform={`translate(${LIT.x} ${LIT.y})`} />
          </g>
          <path d={ROUND} fill="none" stroke={INK} strokeWidth={OUTLINE} strokeLinejoin="round" />
        </>
      ) : (
        <path d={ROUND} fill={body} stroke={INK} strokeWidth={OUTLINE} strokeLinejoin="round" />
      )}
    </>
  )
}

function Leaf({ body, leaf }: { body: string; leaf: string }): ReactNode {
  return (
    <>
      <path d="M24 43.4 L24 46.2" fill="none" stroke={INK} strokeWidth={OUTLINE} strokeLinecap="round" />
      <path d="M24 3.6 C34.6 10.2 40.6 21.2 37.4 32 C35.4 39 30.4 43.4 24 43.4 C17.6 43.4 12.6 39 10.6 32 C7.4 21.2 13.4 10.2 24 3.6 Z" fill={body} stroke={INK} strokeWidth={OUTLINE} strokeLinejoin="round" />
      <path d="M24 9.5 L24 19.5" fill="none" stroke={leaf} strokeWidth={1.4} strokeLinecap="round" />
    </>
  )
}

function Dot({ rim }: { rim: string }): ReactNode {
  return <rect x={7.6} y={12.4} width={32.8} height={30.8} rx={13.6} fill={INK} stroke={rim} strokeWidth={OUTLINE} />
}

export function Character({ kind = DEFAULT_CHARACTER, size = 44, mood = 'calm', look, talking = false, flying = false, point = 0, tint, grown = 1, skin = SKIN, className }: CharacterProps): ReactNode {
  // Each one blinks on its own clock.
  const id = useId().replace(/[^a-zA-Z0-9]/g, '')
  const beat = (parseInt(id.replace(/[^0-9]/g, '') || '0', 10) % 7) * 0.6
  // The learner's own color, where they picked one, else the skin's.
  const body = tint ? TINTS[tint].body : skin.body
  return (
    <span className={`ch shrink-0 select-none ${className ?? ''}`} data-kind={kind} data-mood={mood} data-flying={flying || undefined} data-talking={talking || undefined} style={{ width: size, height: size, '--ch-beat': `${-beat}s` } as CSSProperties} aria-hidden>
      <svg viewBox="0 0 48 48" width="100%" height="100%" style={{ overflow: 'visible', display: 'block' }}>
        <g className="ch-body">
          {kind === 'sprout' ? <Sprout mood={mood} point={point} body={body} leaf={skin.leaf} shade={tint ? undefined : skin.shade} grown={grown} id={`ch-${id}`} /> : kind === 'leaf' ? <Leaf body={body} leaf={skin.leaf} /> : <Dot rim={body} />}
          <Face kind={kind} mood={mood} look={look ?? { x: 0, y: 0 }} talking={talking} blush={tint ? TINTS[tint].blush : skin.blush} ink={kind === 'dot' ? body : INK} />
        </g>
      </svg>
    </span>
  )
}
