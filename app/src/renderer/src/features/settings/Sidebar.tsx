/**
 * Feature: settings. The sidebar (Set-* mockups): the same three window lights as every other miyagi window (close
 * works and shows its ✕ on hover or focus; minimize and zoom are drawn but inactive, as on a macOS sheet), the five
 * sections, and the bonsai with the lowercase wordmark and the version at the foot.
 *
 * The section list is a vertical tablist: ↑ / ↓ (and Home / End) move between sections and switch at once, the active
 * row's highlight slides on the house spring (layoutId), and the active row takes focus when the sheet opens.
 */
import { motion, useReducedMotion } from 'motion/react'
import { KeyRound, Keyboard, Lock, ShieldCheck, SlidersHorizontal, X, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { MiyagiMark } from '../../core/ui/Mark'
import { color, copy, fill, radius2, spring, type2 } from '../../core/theme'
import type { SettingsSection } from './env'
import { OWN_KEY } from './words'

export const NAV: readonly { id: SettingsSection; label: string; icon: LucideIcon }[] = [
  { id: 'general', label: 'General', icon: SlidersHorizontal },
  { id: 'permissions', label: 'Permissions', icon: ShieldCheck },
  { id: 'privacy', label: 'Privacy', icon: Lock },
  { id: 'account', label: OWN_KEY, icon: KeyRound },
  { id: 'shortcuts', label: 'Shortcuts', icon: Keyboard }
]

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

function Nav({ section, onSelect, focusOnMount }: { section: SettingsSection; onSelect: (s: SettingsSection) => void; focusOnMount: boolean }): ReactNode {
  const reduce = useReducedMotion()
  const refs = useRef<Partial<Record<SettingsSection, HTMLButtonElement | null>>>({})

  useEffect(() => {
    if (focusOnMount) refs.current[section]?.focus({ preventScroll: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const go = (id: SettingsSection): void => {
    onSelect(id)
    refs.current[id]?.focus({ preventScroll: true })
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    const i = NAV.findIndex((n) => n.id === section)
    const to =
      e.key === 'ArrowDown' ? (i + 1) % NAV.length : e.key === 'ArrowUp' ? (i - 1 + NAV.length) % NAV.length : e.key === 'Home' ? 0 : e.key === 'End' ? NAV.length - 1 : -1
    if (to < 0) return
    e.preventDefault()
    go(NAV[to].id)
  }

  return (
    <div role="tablist" aria-orientation="vertical" aria-label="Settings sections" className="flex flex-col gap-[2px]" onKeyDown={onKey}>
      {NAV.map(({ id, label, icon: I }) => {
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
            className="relative flex cursor-pointer items-center gap-[9px] text-left font-medium outline-none focus-visible:ring-1 focus-visible:ring-white/60"
            style={{ height: 30, padding: '0 10px', borderRadius: radius2.control, fontSize: type2.sm, color: on ? color.text : color.label }}
            whileHover={on ? undefined : { color: color.text }}
            whileTap={{ scale: 0.98 }}
            transition={{ duration: 0.12 }}
            onClick={() => go(id)}
          >
            {on && (
              <motion.span
                layoutId="settings-nav-on"
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
  )
}

export function Sidebar({
  section,
  onSelect,
  onClose,
  version,
  focusOnMount = true
}: {
  section: SettingsSection
  onSelect: (s: string) => void
  onClose: () => void
  version?: string
  focusOnMount?: boolean
}): ReactNode {
  return (
    <div className="flex h-full w-[208px] shrink-0 flex-col gap-[16px] px-[12px] py-[16px]" style={{ background: fill.group, boxShadow: `inset -1px 0 0 ${fill.hairline}` }}>
      <Lights onClose={onClose} />
      <div className="mt-[8px]">
        <Nav section={section} onSelect={onSelect} focusOnMount={focusOnMount} />
      </div>
      <div className="mt-auto flex items-center gap-[8px] px-[8px]">
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
