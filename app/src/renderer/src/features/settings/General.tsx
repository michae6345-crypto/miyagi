/**
 * Feature: settings. The General section: Appearance, Read lessons aloud, Open at login.
 * Each control applies at once through core prefs (setPrefs → main saves userData/prefs.json and tells every
 * window); only the keys wait for Save. Appearance switches the glass panels (theme.glass); the notch island,
 * the cards and this sheet stay black.
 *
 * Neutral chrome only (Adrian): no pastel, no green. The selected segment and an "on" switch are white with
 * ink, like the one primary button; everything else is fill.* on the black sheet.
 */
import { motion } from 'motion/react'
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react'
import { setPrefs, usePrefs, type Appearance } from '../../core/prefs'
import { color, fill, spring } from '../../core/theme'

const APPEARANCES: { value: Appearance; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' }
]
const SEGMENT_W = 62
/** Keyboard focus: a thin faint ring (outlineColor set inline from the theme), never the browser's default. */
const FOCUS = 'outline-none focus-visible:outline-solid focus-visible:outline-1 focus-visible:outline-offset-2'

export function General(): ReactNode {
  const appearance = usePrefs((s) => s.appearance)
  const voiceOnStart = usePrefs((s) => s.voiceOnStart)
  const launchAtLogin = usePrefs((s) => s.launchAtLogin)
  return (
    <>
      <Row label="Appearance">
        <Segmented value={appearance} onChange={(a) => setPrefs({ appearance: a })} />
      </Row>
      <Row label="Read lessons aloud">
        <Switch on={voiceOnStart} label="Read lessons aloud" onChange={(v) => setPrefs({ voiceOnStart: v })} />
      </Row>
      <Row label="Open at login">
        <Switch on={launchAtLogin} label="Open at login" onChange={(v) => setPrefs({ launchAtLogin: v })} />
      </Row>
    </>
  )
}

/** A section label ("General", "Keys"). */
export function SectionLabel({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="px-[24px] pb-[2px] text-[12px] font-medium leading-[16px]" style={{ color: color.faint }}>
      {children}
    </div>
  )
}

/** Label left (aligned with the key rows' labels), control right (aligned with their fields' right edge). */
function Row({ label, children }: { label: string; children: ReactNode }): ReactNode {
  return (
    <div className="flex h-[44px] items-center gap-[12px] pl-[48px] pr-[24px]">
      <span className="min-w-0 flex-1 truncate text-[14px] leading-[18px]" style={{ color: color.text }}>
        {label}
      </span>
      {children}
    </div>
  )
}

/** System / Light / Dark. The white segment slides on the spring; ←/→ move it. */
function Segmented({ value, onChange }: { value: Appearance; onChange: (a: Appearance) => void }): ReactNode {
  const i = Math.max(0, APPEARANCES.findIndex((a) => a.value === value))
  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const next = APPEARANCES[(i + step + APPEARANCES.length) % APPEARANCES.length]
    onChange(next.value)
    ;(e.currentTarget.querySelector(`[data-value="${next.value}"]`) as HTMLButtonElement | null)?.focus({ preventScroll: true })
  }
  return (
    <div role="radiogroup" aria-label="Appearance" className="relative flex h-[28px] shrink-0 rounded-full p-[2px]" style={{ background: fill.button }} onKeyDown={onKey}>
      <motion.span
        className="pointer-events-none absolute left-[2px] top-[2px] h-[24px] rounded-full"
        style={{ width: SEGMENT_W, background: color.accent }}
        initial={false}
        animate={{ x: i * SEGMENT_W }}
        transition={spring}
      />
      {APPEARANCES.map((a, k) => {
        const on = k === i
        // Plain CSS hover: motion's whileHover stuck "on" when it switched between defined and undefined.
        const vars = { '--c': on ? color.onAccent : color.label, '--h': on ? color.onAccent : color.text, width: SEGMENT_W, outlineColor: color.faint } as CSSProperties
        return (
          <button
            key={a.value}
            type="button"
            role="radio"
            aria-checked={on}
            data-value={a.value}
            tabIndex={on ? 0 : -1}
            className={`relative grid h-[24px] cursor-pointer place-items-center rounded-full text-[12.5px] font-medium text-(color:--c) transition-colors duration-150 hover:text-(color:--h) ${FOCUS}`}
            style={vars}
            onClick={() => onChange(a.value)}
          >
            {a.label}
          </button>
        )
      })}
    </div>
  )
}

/** On = white track, ink knob. Off = neutral track, gray knob. */
function Switch({ on, label, onChange }: { on: boolean; label: string; onChange: (v: boolean) => void }): ReactNode {
  return (
    <motion.button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`relative h-[22px] w-[38px] shrink-0 cursor-pointer rounded-full ${FOCUS}`}
      style={{ outlineColor: color.faint }}
      initial={false}
      animate={{ backgroundColor: on ? color.accent : fill.button }}
      transition={{ duration: 0.18 }}
      onClick={() => onChange(!on)}
    >
      <motion.span
        className="absolute left-[3px] top-[3px] h-[16px] w-[16px] rounded-full"
        initial={false}
        animate={{ x: on ? 16 : 0, backgroundColor: on ? color.onAccent : color.label }}
        transition={spring}
      />
    </motion.button>
  )
}
