/**
 * Feature: settings, v4 page. The Settings page's own list (Adrian's ui-next mock): Account on top, then App, Learning
 * and Privacy, About at the foot. The shell's sidebar draws it in place of the app's pages while Settings is on show
 * (shell ui.tsx setSidebarList, "one sidebar on screen"). Panels the v4 page folded into another (Appearance into
 * General, Editor into Lessons, Storage and Privacy into Your data) light the row they now live in, so an old
 * openSettings(section) still shows where it landed.
 */
import { Bell, CircleUser, Eye, GraduationCap, Info, KeyRound, Keyboard, Plug, ShieldCheck, SlidersHorizontal, type LucideIcon } from 'lucide-react'
import type { PanelId } from '../panels'
import { OWN_KEY } from '../words'

export type Item = { id: PanelId | 'account-page'; label: string; icon: LucideIcon }
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

/** The list row's word for a panel ("General" for Appearance): the top bar's crumb and the panel's region label. */
export const navLabel = (p: PanelId): string => ORDER.find((i) => i.id === navRowOf(p))?.label ?? ''
