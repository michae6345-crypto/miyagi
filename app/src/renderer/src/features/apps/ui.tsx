/**
 * Feature: apps. Small shared parts: the app's glyph (a neutral line icon in the mark's slot: names only, no maker's
 * marks; MIC-87 note "Marks") and the install state in words.
 */
import { Box, Check, CodeXml, Cuboid, DraftingCompass, type LucideIcon } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { color } from '../../core/theme'
import { appMeta, type AppGlyph, type InstallState } from './model'

const GLYPH: Record<AppGlyph, LucideIcon> = { code: CodeXml, box: Box, compass: DraftingCompass, cuboid: Cuboid }

export function AppIcon({ id, size = 16, style }: { id: string; size?: number; style?: CSSProperties }): ReactNode {
  const I = GLYPH[appMeta(id)?.glyph ?? 'box']
  return <I aria-hidden size={size} strokeWidth={1.6} style={style} />
}

/** "Installed" / "Not installed"; nothing for unknown (miyagi never claims what it didn't see). */
export const stateWord = (s: InstallState | undefined): string => (s === 'installed' ? 'Installed' : s === 'missing' ? 'Not installed' : '')

/**
 * The state as the app page and the picker say it: an ink check before "Installed" (no green: green only means
 * passed), a hollow ring before "Not installed", nothing when unknown.
 */
export function StateLine({ state, version }: { state: InstallState | undefined; version?: string }): ReactNode {
  if (state === 'installed')
    return (
      <span className="inline-flex items-center gap-[6px]" data-app-state="installed">
        <Check aria-hidden size={14} strokeWidth={2.2} style={{ color: color.text }} />
        Installed{version ? ` · ${version}` : ''}
      </span>
    )
  if (state === 'missing')
    return (
      <span className="inline-flex items-center gap-[6px]" data-app-state="missing">
        <span aria-hidden className="inline-block" style={{ width: 12, height: 12, borderRadius: '50%', boxShadow: `inset 0 0 0 1.5px ${color.faint}` }} />
        Not installed
      </span>
    )
  return <span data-app-state="unknown">Checked when a lesson starts</span>
}
