/**
 * Feature: onboarding (A3). Onb-Setup-Full's left pane: the bonsai, "Welcome to miyagi", three lines on how it works,
 * and the launcher key at the bottom (its label from bridge.platform.keys, never typed).
 */
import type { ReactNode } from 'react'
import { Check, List, Play, type LucideIcon } from 'lucide-react'
import { color, copy, fill, font, radius2, surface, type2 } from '../../core/theme'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'

export const WELCOME_W = 352

const LINES: Array<{ icon: LucideIcon; text: string }> = [
  { icon: List, text: 'Paste a tutorial. miyagi turns it into steps.' },
  { icon: Play, text: 'It points at the real buttons in VS Code.' },
  { icon: Check, text: 'It checks your work before moving on.' }
]

export function LauncherHint(): ReactNode {
  return (
    <div className="flex items-center gap-[8px]">
      <Keycap k="launcher" />
      <span style={{ fontSize: type2.sm, color: color.label }}>{copy.launcherPlaceholder}</span>
    </div>
  )
}

export function Welcome(): ReactNode {
  return (
    <div
      data-onb-welcome
      className="flex shrink-0 flex-col justify-between px-[40px] pb-[48px] pt-[56px]"
      style={{ width: WELCOME_W, borderRight: `1px solid ${fill.hairline}` }}
    >
      <div className="flex flex-col gap-[24px]">
        <div className="grid h-[64px] w-[64px] place-items-center" style={{ borderRadius: radius2.group, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
          <MiyagiMark size={40} />
        </div>
        <div className="flex flex-col gap-[8px]">
          <h1 id="onb-title" className="m-0" style={{ fontFamily: font.brand, fontSize: 32, lineHeight: '40px', fontWeight: 500, letterSpacing: '-0.4px', color: color.text }}>
            Welcome to {copy.name}
          </h1>
          <p className="m-0" style={{ fontSize: type2.body, lineHeight: '24px', color: color.label }}>
            Learn by doing, in the apps you already use.
          </p>
        </div>
        <div className="flex flex-col gap-[16px] pt-[8px]">
          {LINES.map(({ icon: I, text }) => (
            <div key={text} className="flex items-start gap-[12px]">
              <I size={16} strokeWidth={1.5} color={color.label} className="mt-[2px] shrink-0" />
              <span style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>{text}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-[8px]">
        <span style={{ fontSize: type2.xs, color: color.label }}>After setup, open miyagi anytime</span>
        <LauncherHint />
      </div>
    </div>
  )
}
