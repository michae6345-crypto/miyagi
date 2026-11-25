/**
 * Feature: settings. The sidebar (Set-* mockups), Notion-style: search on top, the panels in labeled groups, and (in the
 * sheet) the same three window lights as every other miyagi window (close works; minimize and zoom are drawn but
 * inactive, as on a macOS sheet) and the bonsai with the lowercase wordmark and the version at the foot.
 *
 * The panel list is a vertical tablist: ↑ / ↓ (and Home / End) move between panels and switch at once, the active
 * row's highlight slides on the house spring (layoutId), and the active row takes focus when the sheet opens.
 * `Nav` is also the home window's Settings page list (Sidebar's lights and foot are the sheet's only).
 */
import { motion, useReducedMotion } from 'motion/react'
import { X } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { MiyagiMark } from '../../core/ui/Mark'
import { color, copy, fill, radius2, spring, type2 } from '../../core/theme'
import { fade, press } from '../../core/ui/motion'
import { SearchField } from './Search'
import { GROUPS, PANELS, type PanelId } from './panels'

/** The window's three lights: neutral dots (OS chrome, never a hue), close is the only live one. */
function Lights({ onClose }: { onClose: () => void }): ReactNode {
  return (
    <div className="flex h-[16px] items-center gap-[8px] px-[4px]">
      <button
        type="button"
        aria-label="Close settings"
        title="Close"
        data-light="close"
        className="group grid h-[12px] w-[12px] cursor-pointer place-items-center outline-none"
        style={{ borderRadius: radius2.round, background: fill.toggleOff, color: color.text }}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onClose}
      >
        <X size={8} strokeWidth={3} className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden />
      </button>
      {['minimize', 'zoom'].map((l) => (
        <span key={l} aria-hidden data-light={l} className="block h-[12px] w-[12px]" style={{ borderRadius: radius2.round, background: fill.toggleOff, opacity: 0.5 }} />
      ))}
    </div>
  )
}

export function Nav({ section, onSelect, focusOnMount, tight }: { section: PanelId; onSelect: (s: PanelId, via?: 'keys') => void; focusOnMount: boolean; tight?: boolean }): ReactNode {
  const reduce = useReducedMotion()
  const uid = useId()
  const refs = useRef<Partial<Record<PanelId, HTMLButtonElement | null>>>({})

  useEffect(() => {
    if (focusOnMount) refs.current[section]?.focus({ preventScroll: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // The tab is focused on open so the arrow keys work at once, but its ring waits for the first key press: a mouse
  // open shows only the active row's fill, never fill plus ring (round 3 review). One ring, the sheet's own outline.
  const [kbd, setKbd] = useState(false)
  useEffect(() => {
    if (kbd) return
    const on = (): void => setKbd(true)
    window.addEventListener('keydown', on, true)
    return () => window.removeEventListener('keydown', on, true)
  }, [kbd])

  const go = (id: PanelId, via?: 'keys'): void => {
    onSelect(id, via)
    refs.current[id]?.focus({ preventScroll: true })
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    const i = PANELS.findIndex((n) => n.id === section)
    const to =
      e.key === 'ArrowDown' ? (i + 1) % PANELS.length : e.key === 'ArrowUp' ? (i - 1 + PANELS.length) % PANELS.length : e.key === 'Home' ? 0 : e.key === 'End' ? PANELS.length - 1 : -1
    if (to < 0) return
    e.preventDefault()
    go(PANELS[to].id, 'keys')
  }

  return (
    <div role="tablist" aria-orientation="vertical" aria-label="Settings sections" className="flex flex-col" style={{ gap: tight ? 10 : 14 }} onKeyDown={onKey}>
      {GROUPS.map((g) => (
        <div key={g.label} role="presentation" className="flex flex-col gap-[2px]">
          <span className="px-[10px] font-medium" style={{ fontSize: type2.micro, color: color.faint, height: 20, lineHeight: '20px' }}>
            {g.label}
          </span>
          {g.panels.map(({ id, label, icon: I }) => {
            const on = id === section
            return (
              <motion.button
                key={id}
                ref={(el) => {
                  refs.current[id] = el
                }}
                type="button"
                role="tab"
                id={`settings-tab-${id}`}
                aria-selected={on}
                aria-controls="settings-panel"
                tabIndex={on ? 0 : -1}
                data-nav={id}
                className="relative flex cursor-pointer items-center gap-[9px] text-left font-medium"
                data-kbd={kbd || undefined}
                style={{ height: 30, padding: '0 10px', borderRadius: radius2.control, fontSize: type2.sm, color: on ? color.text : color.label, ...(kbd ? {} : { outlineStyle: 'none' }) }}
                whileHover={on ? undefined : { color: color.text }}
                whileTap={{ scale: press.scale }}
                transition={{ ...fade.tint, scale: spring }}
                onClick={() => go(id)}
              >
                {on && (
                  <motion.span
                    layoutId={`settings-nav-on-${uid}`}
                    aria-hidden
                    className="absolute inset-0"
                    style={{ borderRadius: radius2.control, background: fill.navActive }}
                    transition={reduce ? { duration: 0 } : spring}
                  />
                )}
                <I size={15} strokeWidth={1.8} className="relative shrink-0" aria-hidden />
                <span className="relative truncate">{label}</span>
              </motion.button>
            )
          })}
        </div>
      ))}
    </div>
  )
}

export function Sidebar({
  section,
  onSelect,
  onClose,
  version,
  focusOnMount = true
}: {
  section: PanelId
  onSelect: (s: PanelId, via?: 'keys') => void
  onClose: () => void
  version?: string
  focusOnMount?: boolean
}): ReactNode {
  return (
    <div className="flex h-full w-[208px] shrink-0 flex-col gap-[12px] px-[12px] py-[16px]" style={{ background: fill.group, boxShadow: `inset -1px 0 0 ${fill.hairline}` }}>
      <Lights onClose={onClose} />
      <SearchField />
      <div className="min-h-0 flex-1 overflow-y-auto" style={{ scrollbarWidth: 'none' }}>
        <Nav section={section} onSelect={onSelect} focusOnMount={focusOnMount} tight />
      </div>
      <div className="flex items-center gap-[8px] px-[8px]">
        <MiyagiMark size={20} />
        <span className="font-medium" style={{ fontFamily: 'var(--font-brand)', fontSize: type2.md, color: color.text }}>
          {copy.name}
        </span>
        {version && (
          <span className="ml-auto tabular-nums" style={{ fontSize: type2.micro, color: color.label }}>
            {version}
          </span>
        )}
      </div>
    </div>
  )
}
