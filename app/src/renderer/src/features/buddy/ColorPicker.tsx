/**
 * Feature: buddy. Pick your buddy's color: the buddy, big, and a row of swatches under it. A pick shows at once: it
 * beams and hops, and everything it does from then on (its loop, the bars in its bubble) is in that color (skin.ts).
 * No window of its own: setup and Settings mount it (brief, Core requests); ?buddy=pick shows it in a mock setup step.
 * The buddy looks at the pointer, so it feels alive before the learner has done anything.
 */
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { color, type2 } from '../../core/theme'
import { spring } from '../../core/ui/motion'
import { Character } from './Character'
import { PICKS, SKINS, type SkinName } from './palette'
import { pickSkin, useSkinName } from './skin'

/** How long it beams after a pick (ms). */
const BEAM_MS = 900
const SWATCH = 30

const title = (name: SkinName): string => name.charAt(0).toUpperCase() + name.slice(1)

export function BuddyColorPicker({ size = 132 }: { size?: number }): ReactNode {
  const name = useSkinName()
  const reduced = useReducedMotion() ?? false
  const [beam, setBeam] = useState(false)
  const [look, setLook] = useState({ x: 0, y: 0 })
  const body = useRef<HTMLDivElement>(null)

  // It watches the pointer.
  useEffect(() => {
    const move = (e: MouseEvent): void => {
      const box = body.current?.getBoundingClientRect()
      if (!box || !box.width) return
      const dx = (e.clientX - (box.left + box.width / 2)) / 260
      const dy = (e.clientY - (box.top + box.height / 2)) / 260
      setLook({ x: Math.max(-1, Math.min(1, dx)), y: Math.max(-1, Math.min(1, dy)) })
    }
    window.addEventListener('mousemove', move)
    return () => window.removeEventListener('mousemove', move)
  }, [])

  useEffect(() => {
    if (!beam) return
    const t = setTimeout(() => setBeam(false), BEAM_MS)
    return () => clearTimeout(t)
  }, [beam, name])

  const pick = (next: SkinName): void => {
    pickSkin(next)
    setBeam(true)
  }

  return (
    <div data-part="buddy-colors" className="flex flex-col items-center">
      <div ref={body} style={{ height: size }}>
        {/* A new color lands with a small hop. */}
        <motion.div key={name} initial={reduced ? false : { y: 10, scale: 0.9 }} animate={{ y: 0, scale: 1 }} transition={spring}>
          <Character size={size} mood={beam ? 'happy' : 'calm'} look={beam ? undefined : look} />
        </motion.div>
      </div>
      <div role="radiogroup" aria-label="Buddy color" className="mt-[28px] flex items-center gap-[14px]">
        {PICKS.map((p) => {
          const on = p === name
          return (
            <button
              key={p}
              type="button"
              role="radio"
              aria-checked={on}
              aria-label={title(p)}
              data-swatch={p}
              data-on={on || undefined}
              onClick={() => pick(p)}
              className="cursor-pointer p-0"
              style={{
                width: SWATCH,
                height: SWATCH,
                borderRadius: SWATCH / 2,
                background: SKINS[p].body,
                border: 'none',
                // The ring of the one that is picked: a gap in the window's color, then the text color.
                boxShadow: on ? `0 0 0 3px ${color.window}, 0 0 0 5px ${color.text}` : `inset 0 0 0 1px rgba(0,0,0,.18)`,
                transition: 'box-shadow 140ms ease-out'
              }}
            />
          )
        })}
      </div>
      <div data-part="buddy-color-name" className="mt-[16px]" style={{ fontSize: type2.sm, color: color.label }}>
        {title(name)}
      </div>
    </div>
  )
}
