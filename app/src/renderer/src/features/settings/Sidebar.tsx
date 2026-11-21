/**
 * Feature: settings. The sidebar (Set-* mockups): a close dot where the traffic lights sit, the five sections
 * (core SidebarNav), and the bonsai with the lowercase wordmark and the version at the foot.
 * The mockup's two other traffic-light dots are left out: they would be dead controls.
 */
import { KeyRound, Keyboard, Lock, ShieldCheck, SlidersHorizontal, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { MiyagiMark } from '../../core/ui/Mark'
import { SidebarNav, type NavItem } from '../../core/ui/atoms'
import { color, copy, fill, radius2, type2 } from '../../core/theme'
import type { SettingsSection } from './env'

export const NAV: readonly (NavItem & { id: SettingsSection })[] = [
  { id: 'general', label: 'General', icon: SlidersHorizontal },
  { id: 'permissions', label: 'Permissions', icon: ShieldCheck },
  { id: 'privacy', label: 'Privacy', icon: Lock },
  { id: 'account', label: 'Your key', icon: KeyRound },
  { id: 'shortcuts', label: 'Shortcuts', icon: Keyboard }
]

export function Sidebar({ section, onSelect, onClose, version }: { section: SettingsSection; onSelect: (s: string) => void; onClose: () => void; version?: string }): ReactNode {
  return (
    <div
      className="flex h-full w-[208px] shrink-0 flex-col gap-[16px] px-[12px] py-[16px]"
      style={{ background: fill.group, boxShadow: `inset -1px 0 0 ${fill.hairline}` }}
    >
      <div className="flex h-[16px] items-center px-[4px]">
        <button
          type="button"
          aria-label="Close settings"
          className="group grid h-[12px] w-[12px] cursor-pointer place-items-center"
          style={{ borderRadius: radius2.round, background: color.gray, color: color.onAccent }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={onClose}
        >
          <X size={8} strokeWidth={3} className="opacity-0 transition-opacity group-hover:opacity-100" />
        </button>
      </div>
      <div className="mt-[8px]">
        <SidebarNav title="Settings sections" items={NAV} active={section} onSelect={onSelect} />
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
