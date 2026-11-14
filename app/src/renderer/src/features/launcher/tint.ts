/**
 * Feature: launcher. Launcher-only helpers on top of the core tokens (core/theme.ts: fill, scrim, shadows,
 * brand.pastel). No colors are defined here any more.
 */
import { brand } from '../../core/theme'

/** Suggestion chips cycle through the options pastels, in order. */
export const chipTones = [brand.pastel.pink, brand.pastel.sky, brand.pastel.lilac] as const

/** Result tile tone by source kind (videos keep their thumbnail). */
export const kindTone: Partial<Record<string, string>> = {
  notebook: brand.pastel.skyDeep,
  repo: brand.pastel.skyDeep,
  paper: brand.pastel.pinkDeep,
  blog: brand.pastel.lilac
}

/** A #RRGGBB color at an alpha, as rgba(). */
export function alpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1, 7), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}
