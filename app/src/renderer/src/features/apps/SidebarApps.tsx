/**
 * Feature: apps. The sidebar's Apps section, as drawn (Sidebar.tsx feeds it): the label, one row per app with its
 * glyph and name ("Not installed" on the right when main's scan says so), the open app's row marked, then "Add app".
 * Compact: the glyphs only, names as tooltips. No stores here, so it renders anywhere (tests included).
 */
import { Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import { v4 } from '../../core/theme'
import { SideLabel, SideRow } from '../shell/ui'
import type { InstallState } from './model'
import { AppIcon, stateWord } from './ui'

export type SidebarApp = { id: string; name: string; state: InstallState }

export function SidebarApps({ apps, openId, compact, picking = false, onOpen, onAdd }: { apps: readonly SidebarApp[]; openId?: string; compact: boolean; picking?: boolean; onOpen: (id: string) => void; onAdd: () => void }): ReactNode {
  return (
    <div data-shell-apps role="group" aria-label="Apps" className="flex flex-col">
      {compact ? <div style={{ height: v4.sidebar.labelTop }} /> : <SideLabel>Apps</SideLabel>}
      {apps.map((a) => (
        <SideRow
          key={a.id}
          icon={<AppIcon id={a.id} />}
          label={a.name}
          title={a.name}
          right={a.state === 'missing' ? stateWord(a.state) : undefined}
          on={openId === a.id}
          compact={compact}
          onClick={() => onOpen(a.id)}
          data={{ 'data-shell-app': a.id, 'data-app-state': a.state }}
        />
      ))}
      <SideRow icon={<Plus size={16} strokeWidth={1.6} />} label="Add app" compact={compact} onClick={onAdd} data={{ 'data-shell-add-app': '', 'aria-haspopup': 'dialog', 'aria-expanded': String(picking) }} />
    </div>
  )
}
