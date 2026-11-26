/**
 * Feature: buddy. Brief: app/agents/buddy.md
 *
 * The living bonsai: the brand mark (core/ui/Mark.tsx MiyagiMark) with a little life, for the notch ears and anywhere
 * miyagi is present. Same brand SVG files, drawn inline so their parts can move:
 *   idle      still
 *   thinking  the canopy sways gently from the trunk base (the engine is working)
 *   lean      the canopy leans toward the pointer (hovering the notch), on the house curve
 *   bloom     the pads swell once, one after another, when a step passes
 * The pot never moves. Transform only. With reduced motion nothing moves (buddy.css).
 * No face, no glow, no recolor: the tree is the one from the brand kit, in color.
 */
import { useEffect, useId, useMemo, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import treeFull from '../../assets/brand/tree-full.svg?raw'
import treeFullDark from '../../assets/brand/tree-full-dark.svg?raw'
import treeIcon from '../../assets/brand/tree-icon.svg?raw'
import treeIconDark from '../../assets/brand/tree-icon-dark.svg?raw'
import treeSmall from '../../assets/brand/tree-small.svg?raw'
import treeSmallDark from '../../assets/brand/tree-small-dark.svg?raw'
import { markLevel } from '../../core/theme'
import './buddy.css'

export type BuddyState = 'idle' | 'thinking'
type Level = 'small' | 'icon' | 'full'
type Tone = 'light' | 'dark'

const RAW: Record<Level, Record<Tone, string>> = {
  full: { light: treeFull, dark: treeFullDark },
  icon: { light: treeIcon, dark: treeIconDark },
  small: { light: treeSmall, dark: treeSmallDark }
}

const SVG_NS = 'http://www.w3.org/2000/svg'
const built = new Map<string, string>()

/**
 * The SVG with its canopy wrapped as lean > sway > bloom (three nested groups, so the three motions never fight over
 * one transform) and its pads tagged .lm-pad with their order in --i. The pot stays outside, so it never moves.
 * Exported for the stage and tests; the component caches it per cut.
 */
export function livingSvg(raw: string): string {
  const doc = new DOMParser().parseFromString(raw, 'image/svg+xml')
  const svg = doc.documentElement
  svg.removeAttribute('width')
  svg.removeAttribute('height')
  // tree-icon / tree-full wrap everything in one bare <g>: work inside it.
  let host: Element = svg
  const only = svg.children.length === 1 ? svg.children[0] : undefined
  if (only && only.tagName === 'g' && only.attributes.length === 0) host = only
  const isPot = (e: Element): boolean =>
    e.getAttribute('data-part') === 'pot' ||
    (e.tagName === 'g' && e.firstElementChild?.tagName === 'rect' && Number(e.firstElementChild.getAttribute('y')) >= 70)
  const canopy = [...host.children].filter((e) => !isPot(e) && e.tagName !== 'clipPath' && e.tagName !== 'defs')
  if (canopy.length) {
    const group = (cls: string): Element => {
      const g = doc.createElementNS(SVG_NS, 'g')
      g.setAttribute('class', cls)
      return g
    }
    const lean = group('lm-lean'), sway = group('lm-sway'), bloom = group('lm-bloom')
    host.insertBefore(lean, canopy[0])
    lean.appendChild(sway)
    sway.appendChild(bloom)
    for (const e of canopy) bloom.appendChild(e)
    // The pads: tagged in the larger cuts; in the small cut, each pad is one clipped group.
    let pads = [...bloom.querySelectorAll('[data-part="pads"]')]
    if (!pads.length) pads = [...bloom.querySelectorAll('g[clip-path]')]
    pads.forEach((p, i) => {
      p.setAttribute('class', 'lm-pad')
      p.setAttribute('style', `--i:${i}`)
    })
  }
  return new XMLSerializer().serializeToString(svg)
}

function living(level: Level, tone: Tone): string {
  const key = `${level}-${tone}`
  let s = built.get(key)
  if (!s) built.set(key, (s = livingSvg(RAW[level][tone])))
  return s
}

/** Clip-path ids made unique per instance, so two marks on one page (or a hidden cut) never borrow each other's. */
function scoped(svg: string, suffix: string): string {
  return svg.replace(/id="([^"]+)"/g, `id="$1-${suffix}"`).replace(/url\(#([^)]+)\)/g, `url(#$1-${suffix})`)
}

export type LivingMarkProps = {
  size?: number
  state?: BuddyState
  /** -1 (lean left) to 1 (lean right); 0 stands straight. usePointerLean gives this from the pointer. */
  lean?: number
  /** Bump it to bloom once (a pass counter works: every new value plays it). 0 = never bloomed. */
  bloom?: number
  /** Omitted: both cuts, and the theme shows the one that fits (like MiyagiMark). */
  tone?: Tone
  level?: 'auto' | Level
  className?: string
}

/** The living bonsai. A drop-in for MiyagiMark where miyagi itself is present (the notch ears, the launcher). */
export function LivingMark({ size = 16, state = 'idle', lean = 0, bloom = 0, tone, level = 'auto', className }: LivingMarkProps): ReactNode {
  const lvl: Level = level === 'auto' ? markLevel(size) : level
  const uid = useId().replace(/[^A-Za-z0-9]/g, '')
  const cuts = useMemo(() => {
    const tones: Tone[] = tone ? [tone] : ['dark', 'light']
    return tones.map((t) => ({ t, html: scoped(living(lvl, t), `${uid}${t[0]}`) }))
  }, [lvl, tone, uid])
  const l = Math.max(-1, Math.min(1, Number.isFinite(lean) ? lean : 0))
  return (
    <span
      className={`lm shrink-0 select-none ${className ?? ''}`}
      data-state={state}
      style={{ width: size, height: size, '--lm-lean': l } as CSSProperties}
      aria-hidden
    >
      {cuts.map(({ t, html }) => (
        // A new key per bloom remounts the cut, which restarts its one-shot animation.
        <span
          key={`${t}-${bloom}`}
          className="lm-cut"
          data-bloom={bloom > 0 ? '' : undefined}
          style={tone ? undefined : { display: t === 'dark' ? 'var(--mk-dark)' : 'var(--mk-light)' }}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ))}
    </span>
  )
}

/**
 * Lean toward the pointer while `on` (for example while the notch is hovered): -1 when the pointer is `reach` px or
 * more to the left of the element's center, 1 to the right, 0 when off. Stepped to 0.05 so it re-renders rarely.
 * In the click-through overlay this needs mouse moves forwarded (setIgnoreMouseEvents with forward: true).
 */
export function usePointerLean(ref: RefObject<Element | null>, on: boolean, reach = 240): number {
  const [lean, setLean] = useState(0)
  useEffect(() => {
    if (!on) {
      setLean(0)
      return
    }
    let raf = 0
    const move = (e: PointerEvent): void => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const r = ref.current?.getBoundingClientRect()
        if (!r) return
        const dx = e.clientX - (r.left + r.width / 2)
        setLean(Math.round(Math.max(-1, Math.min(1, dx / reach)) * 20) / 20)
      })
    }
    window.addEventListener('pointermove', move)
    return () => {
      window.removeEventListener('pointermove', move)
      cancelAnimationFrame(raf)
    }
  }, [on, reach, ref])
  return lean
}
