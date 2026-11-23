/**
 * Feature: settings. The panels (the sidebar's sections) of the sheet and of the home window's Settings page.
 * core/surfaces SettingsSection stays the five ids that `openSettings(section)` and main know; PanelId is that set plus
 * the panels added here, so an old open request still lands on a valid panel.
 */
import { Bell, Code2, Database, Info, KeyRound, Keyboard, Lock, Palette, ShieldCheck, SlidersHorizontal, GraduationCap, type LucideIcon } from 'lucide-react'
import type { SettingsSection } from './env'
import { OWN_KEY } from './words'

export type PanelId = SettingsSection | 'appearance' | 'lessons' | 'editor' | 'notifications' | 'storage' | 'about'

export type PanelDef = { id: PanelId; label: string; icon: LucideIcon; caption: string }
export type PanelGroup = { label: string; panels: readonly PanelDef[] }

/** In sidebar order, grouped the way Notion groups its settings. */
export const GROUPS: readonly PanelGroup[] = [
  {
    label: 'App',
    panels: [
      { id: 'general', label: 'General', icon: SlidersHorizontal, caption: 'Startup, language and where miyagi lives.' },
      { id: 'appearance', label: 'Appearance', icon: Palette, caption: 'Theme, text size, density and motion.' },
      { id: 'notifications', label: 'Notifications', icon: Bell, caption: 'Reminders and sounds. Quiet unless you ask.' },
      { id: 'shortcuts', label: 'Shortcuts', icon: Keyboard, caption: 'The keys that reach miyagi from anywhere.' }
    ]
  },
  {
    label: 'Learning',
    panels: [
      { id: 'lessons', label: 'Lessons', icon: GraduationCap, caption: 'How a lesson hints, plays and moves on.' },
      { id: 'editor', label: 'Editor', icon: Code2, caption: 'Where you write code, and how samples look.' }
    ]
  },
  {
    label: 'Privacy and data',
    panels: [
      { id: 'permissions', label: 'Permissions', icon: ShieldCheck, caption: 'What macOS lets miyagi do.' },
      { id: 'privacy', label: 'Privacy', icon: Lock, caption: 'What miyagi sees, and what stays here.' },
      { id: 'storage', label: 'Storage and data', icon: Database, caption: 'Export your progress, reset tips.' },
      { id: 'account', label: OWN_KEY, icon: KeyRound, caption: 'Bring your own API key.' }
    ]
  },
  { label: 'miyagi', panels: [{ id: 'about', label: 'About', icon: Info, caption: 'Version, updates and feedback.' }] }
]

export const PANELS: readonly PanelDef[] = GROUPS.flatMap((g) => g.panels)
export const PANEL_IDS: readonly PanelId[] = PANELS.map((p) => p.id)
export const isPanel = (s: unknown): s is PanelId => typeof s === 'string' && (PANEL_IDS as readonly string[]).includes(s)
export const panelOf = (id: PanelId): PanelDef => PANELS.find((p) => p.id === id) ?? PANELS[0]
