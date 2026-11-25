/**
 * Feature: buddy. Pick your buddy's color, in two pieces so setup and Settings can lay them out their own way:
 *
 *   BuddyPreview    the buddy itself. It watches the pointer, and beams and hops when a color is picked.
 *   BuddySwatches   the colors to pick from (palette.ts PICKS), as a radio group, with the picked one's name under it.
 *   BuddyColorPicker  both, stacked (the stage's ?buddy=pick mock).
 *
 * A pick shows at once and everything the buddy does from then on (its loop, the bars in its bubble) is in that
 * color (skin.ts). Used by features/onboarding BuddyStep.tsx and SettingsRows.tsx here.
 */
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { color, type2 } from '../../core/theme'
import { spring } from '../../core/ui/motion'
import { Character } from './Character'
import { words } from './name'
import { PICKS, SKINS, type SkinName } from './palette'
import { pickSkin, useSkinName, useSkinPicks } from './skin'

/** How long it beams after a pick (ms). */
const BEAM_MS = 900
/** The smallest a swatch's hit area may be (WCAG 2.5.8): a smaller dot keeps this much button around it. */
const MIN_TARGET = 24

export const skinTitle = (name: SkinName): string => name.charAt(0).toUpperCase() + name.slice(1)

export function BuddyPreview({ size = 132 }: { size?: number }): ReactNode {
  const name = useSkinName()
  const picks = useSkinPicks()
  const reduced = useReducedMotion() ?? false
  const [beam, setBeam] = useState(false)
  const [look, setLook] = useState({ x: 0, y: 0 })
  const body = useRef<HTMLDivElement>(null)
  const seen = useRef(picks)

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

  // A pick: it beams for a moment.
  useEffect(() => {
    if (picks === seen.current) return
    seen.current = picks
    setBeam(true)
    const t = setTimeout(() => setBeam(false), BEAM_MS)
    return () => clearTimeout(t)
  }, [picks])

  return (
    <div ref={body} data-part="buddy-preview" style={{ width: size, height: size }}>
      {/* A new color lands with a small hop. */}
      <motion.div key={name} initial={reduced || picks === 0 ? false : { y: size * 0.08, scale: 0.9 }} animate={{ y: 0, scale: 1 }} transition={spring}>
        <Character size={size} mood={beam ? 'happy' : 'calm'} look={beam ? undefined : look} />
      </motion.div>
    </div>
  )
}

export function BuddySwatches({ size = 30, gap = 14, name: showName = true }: { size?: number; gap?: number; name?: boolean }): ReactNode {
  const name = useSkinName()
  const group = useRef<HTMLDivElement>(null)
  // Arrow keys move the pick, like any radio group.
  const onKey = (e: KeyboardEvent): void => {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const i = PICKS.indexOf(name)
    const next = PICKS[(Math.max(0, i) + step + PICKS.length) % PICKS.length]
    pickSkin(next)
    group.current?.querySelector<HTMLElement>(`[data-swatch="${next}"]`)?.focus()
  }
  return (
    <div data-part="buddy-colors" className="flex flex-col items-center">
      <div ref={group} role="radiogroup" aria-label={words.colors} className="flex items-center" style={{ gap }} onKeyDown={onKey}>
        {PICKS.map((p) => {
          const on = p === name
          return (
            <button
              key={p}
              type="button"
              role="radio"
              aria-checked={on}
              aria-label={skinTitle(p)}
              title={skinTitle(p)}
              tabIndex={on || (!PICKS.includes(name) && p === PICKS[0]) ? 0 : -1}
              data-no-drag
              data-swatch={p}
              data-on={on || undefined}
              onClick={() => pickSkin(p)}
              className="flex shrink-0 cursor-pointer items-center justify-center p-0"
              style={{
                // The button is the hit area (at least MIN_TARGET); the dot inside is drawn at `size`.
                width: Math.max(size, MIN_TARGET),
                height: Math.max(size, MIN_TARGET),
                borderRadius: '50%',
                background: 'transparent',
                border: 'none',
                // The picked one wears a ring in the text color, a gap out from the dot (an outline, so the gap is
                // whatever it sits on: a window, a settings card).
                outline: on ? `2px solid ${color.text}` : '2px solid transparent',
                outlineOffset: (size > 24 ? 3 : 2) - (Math.max(size, MIN_TARGET) - size) / 2,
                transition: 'outline-color 140ms ease-out'
              }}
            >
              <span
                aria-hidden
                className="block shrink-0"
                // A hairline, so a pale one shows on a light window.
                style={{ width: size, height: size, borderRadius: size / 2, background: SKINS[p].body, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.18)' }}
              />
            </button>
          )
        })}
      </div>
      {showName && (
        <div data-part="buddy-color-name" className="mt-[16px]" style={{ fontSize: type2.sm, color: color.label }}>
          {skinTitle(name)}
        </div>
      )}
    </div>
  )
}

export function BuddyColorPicker({ size = 132 }: { size?: number }): ReactNode {
  return (
    <div className="flex flex-col items-center">
      <BuddyPreview size={size} />
      <div className="mt-[28px]">
        <BuddySwatches />
      </div>
    </div>
  )
}
