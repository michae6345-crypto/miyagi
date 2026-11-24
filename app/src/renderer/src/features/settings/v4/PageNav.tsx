/**
 * Feature: settings, v4 page. The Settings page's own list (Adrian's ui-next mock): Account on top, then App, Learning
 * and Privacy, About at the foot. Panels the v4 page folded into another (Appearance into General, Editor into
 * Lessons, Storage and Privacy into Your data) light the row they now live in, so an old openSettings(section) still
 * shows where it landed. A vertical tablist: ↑ / ↓, Home / End move and switch at once.
 */
import { motion, useReducedMotion } from 'motion/react'
import { Bell, CircleUser, Eye, GraduationCap, Info, KeyRound, Keyboard, Plug, ShieldCheck, SlidersHorizontal, type LucideIcon } from 'lucide-react'
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { color, fill, radius2, spring } from '../../../core/theme'
import { openPage } from '../../shell/store'
import type { PanelId } from '../panels'
import { OWN_KEY } from '../words'

type Item = { id: PanelId | 'account-page'; label: string; icon: LucideIcon }
type Group = { label?: string; items: readonly Item[] }

export const NAV4: readonly Group[] = [
  { items: [{ id: 'account-page', label: 'Account', icon: CircleUser }] },
  {
    label: 'App',
    items: [
      { id: 'general', label: 'General', icon: SlidersHorizontal },
      { id: 'shortcuts', label: 'Shortcuts', icon: Keyboard },
      { id: 'notifications', label: 'Notifications', icon: Bell }
    ]
  },
  {
    label: 'Learning',
    items: [
      { id: 'lessons', label: 'Lessons', icon: GraduationCap },
      { id: 'apps', label: 'Apps', icon: Plug }
    ]
  },
  {
    label: 'Privacy',
    items: [
      { id: 'permissions', label: 'Permissions', icon: ShieldCheck },
      { id: 'data', label: 'Your data', icon: Eye },
      { id: 'account', label: OWN_KEY, icon: KeyRound }
    ]
  }
]
export const FOOT4: Item = { id: 'about', label: 'About', icon: Info }

/** The row a panel lights: the folded panels light the one that holds them now. */
export function navRowOf(p: PanelId): PanelId {
  if (p === 'appearance') return 'general'
  if (p === 'editor') return 'lessons'
  if (p === 'storage' || p === 'privacy') return 'data'
  return p
}

const ORDER: readonly Item[] = [...NAV4.flatMap((g) => g.items), FOOT4]

export function PageNav({ panel, onSelect }: { panel: PanelId; onSelect: (p: PanelId) => void }): ReactNode {
  const reduce = useReducedMotion()
  const uid = useId()
  const refs = useRef<Partial<Record<string, HTMLButtonElement | null>>>({})
  const on = navRowOf(panel)
  const go = (it: Item): void => {
    if (it.id === 'account-page') return void openPage('account')
    onSelect(it.id)
    refs.current[it.id]?.focus({ preventScroll: true })
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    const tabs = ORDER.filter((i) => i.id !== 'account-page')
    const i = tabs.findIndex((t) => t.id === on)
    const to = e.key === 'ArrowDown' ? (i + 1) % tabs.length : e.key === 'ArrowUp' ? (i - 1 + tabs.length) % tabs.length : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : -1
    if (to < 0) return
    e.preventDefault()
    go(tabs[to])
  }
  const row = (it: Item): ReactNode => {
    const active = it.id === on
    const I = it.icon
    return (
      <motion.button
        key={it.id}
        ref={(el) => {
          refs.current[it.id] = el
        }}
        type="button"
        role={it.id === 'account-page' ? undefined : 'tab'}
        id={`settings-tab-${it.id}`}
        aria-selected={it.id === 'account-page' ? undefined : active}
        aria-controls={it.id === 'account-page' ? undefined : 'settings-panel'}
        tabIndex={active ? 0 : -1}
        data-nav={it.id}
        className="relative flex cursor-pointer items-center gap-[10px] text-left"
        style={{ height: 30, padding: '0 10px', borderRadius: radius2.control, fontSize: 14, fontWeight: active ? 560 : 480, color: active ? color.text : color.label }}
        whileHover={active ? undefined : { color: color.text }}
        onClick={() => go(it)}
      >
        {active && (
          <motion.span
            layoutId={`settings4-on-${uid}`}
            aria-hidden
            className="absolute inset-0"
            style={{ borderRadius: radius2.control, background: fill.navActive }}
            transition={reduce ? { duration: 0 } : spring}
          />
        )}
        <I size={15} strokeWidth={1.7} className="relative shrink-0" aria-hidden />
        <span className="relative truncate">{it.label}</span>
      </motion.button>
    )
  }
  return (
    <nav aria-label="Settings" className="flex h-full min-h-0 flex-col">
      <div role="tablist" aria-orientation="vertical" aria-label="Settings sections" className="flex min-h-0 flex-1 flex-col gap-[14px] overflow-y-auto" style={{ scrollbarWidth: 'none' }} onKeyDown={onKey}>
        {NAV4.map((g, gi) => (
          <div key={g.label ?? gi} role="presentation" className="flex flex-col gap-[2px]">
            {g.label && (
              <span className="px-[10px]" style={{ fontSize: 12.5, color: color.faint, height: 22, lineHeight: '22px', fontWeight: 500 }}>
                {g.label}
              </span>
            )}
            {g.items.map(row)}
          </div>
        ))}
        <div className="mt-auto flex flex-col pt-[14px]">{row(FOOT4)}</div>
      </div>
    </nav>
  )
}
