/**
 * Feature registry. Every folder in src/renderer/src/features/<name>/ with an index.ts(x) whose
 * default export is defineFeature({...}) is discovered automatically. Adding a feature never
 * requires editing a shared file: create the folder, export the feature, done.
 *
 * A feature can contribute:
 *   islandModes   : states of the Dynamic-Island pill (pill-sized or cards that grow out of it)
 *   overlayLayers : full-screen layers in the overlay window (spotlight, shortcut bar, toasts…)
 *   windows       : its own Electron window route (launcher, player, settings…); also shown in the browser stage
 */
import type { ComponentType } from 'react'
import type { Layout } from '../../../preload/api'

export type IslandMode = {
  id: string
  /**
   * Higher wins when several modes are active at once.
   * Convention: 0–9 pill-sized (idle/building/compact) · 20 hover overview · 40–79 cards · 80+ diagram/modal.
   */
  priority: number
  /** Card width in px. Omit for a pill-sized mode: 34px tall, width hugs the content. */
  width?: number
  /** A React hook: is this mode wanted right now? `hover` = the pointer is over the island. */
  useActive: (hover: boolean) => boolean
  Content: ComponentType
}

export type OverlayLayer = {
  id: string
  /** Stacking order inside the overlay. The island itself sits at z = 50. */
  z: number
  Component: ComponentType<{ layout: Layout }>
}

export type FeatureWindow = {
  /** Electron loads index.html#/<route>. The main-process side creates the window (see src/main/features/). */
  route: string
  Component: ComponentType<{ layout: Layout }>
  /** Where it sits in the browser stage: 'fill' (full-screen layer) or a rect in stage points. Omit to hide it there. */
  stage?: 'fill' | { x: number; y: number; w: number; h: number }
  /** Stage stacking order (overlay = 0). */
  z?: number
}

export type Feature = {
  id: string
  islandModes?: IslandMode[]
  overlayLayers?: OverlayLayer[]
  windows?: FeatureWindow[]
}

export function defineFeature(f: Feature): Feature {
  return f
}

const modules = import.meta.glob<{ default: Feature }>('../features/*/index.{ts,tsx}', { eager: true })

export const features: Feature[] = Object.values(modules)
  .map((m) => m.default)
  .filter((f): f is Feature => !!f && typeof f.id === 'string')

export const islandModes: IslandMode[] = features.flatMap((f) => f.islandModes ?? []).sort((a, b) => b.priority - a.priority)

export const overlayLayers: OverlayLayer[] = features.flatMap((f) => f.overlayLayers ?? []).sort((a, b) => a.z - b.z)

export const featureWindows: FeatureWindow[] = features.flatMap((f) => f.windows ?? [])

if (import.meta.env.DEV) console.info(`[tut] features: ${features.map((f) => f.id).join(', ')}`)
