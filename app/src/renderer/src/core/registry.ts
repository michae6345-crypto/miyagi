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
import type { NotchView } from './notchGeometry'
import type { PanelKind } from './islandTone'

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
  /**
   * In the notch (layout.notch.place 'notch'): what a pill-sized mode looks like. `useView` is a hook: 'rest' = just the
   * notch, 'ears' = the notch widened by an ear each side with `Left` (default the bonsai) and `Right` in them,
   * 'drop' = its Content under the notch row (also what a hover peek shows), 'ears+drop' = both. Default 'drop', so a
   * mode that says nothing keeps showing its content. Cards (width set) ignore it. Below the menu bar it is unused.
   */
  notch?: { useView: () => NotchView; Left?: ComponentType; Right?: ComponentType }
  /**
   * A React hook: what kind of panel this mode shows right now, when that changes while it is open (the notch home turns
   * 'warning' while a link it can't teach shows). Undefined = core/islandTone.ts MODE_PANEL decides. Only calm panels
   * get bon's gradient in the notch.
   */
  useTone?: () => PanelKind | undefined
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
  /**
   * v2 (W0-4). 'overlay' (default): a transparent, always-on-top window born from the island (launcher, settings,
   * player). 'app': a normal macOS window (Onboarding, Library, Progress, Account; decision 4) opened with
   * core/surfaces.ts and main/appWindows.ts (allowlisted routes). It shows a Dock icon while open, gets
   * <html data-kind="app">, and in the browser stage opens with ?window=<route>.
   */
  kind?: 'overlay' | 'app'
  /** v2: an app window's size in points (default theme.windowSize[route] when it has one). */
  size?: { w: number; h: number }
}

export type Feature = {
  id: string
  islandModes?: IslandMode[]
  overlayLayers?: OverlayLayer[]
  windows?: FeatureWindow[]
  /** v2 (W0-4): false = not mounted at all (a flag such as v2Cloud, or an old path wave 2 turns off). Default true. */
  enabled?: boolean
}

export function defineFeature(f: Feature): Feature {
  return f
}

const modules = import.meta.glob<{ default: Feature }>('../features/*/index.{ts,tsx}', { eager: true })

/*
 * Built on first use, NOT at import time: features import this file (defineFeature) and this file
 * imports every feature, so on a hot reload a feature can be mid-evaluation when we load. Reading
 * `.default` lazily avoids "Cannot access 'default' before initialization".
 */
type Built = { features: Feature[]; islandModes: IslandMode[]; overlayLayers: OverlayLayer[]; featureWindows: FeatureWindow[] }
let built: Built | undefined

function build(): Built {
  if (built) return built
  const features = Object.values(modules)
    .map((m) => m.default)
    .filter((f): f is Feature => !!f && typeof f.id === 'string' && f.enabled !== false)
  built = {
    features,
    islandModes: features.flatMap((f) => f.islandModes ?? []).sort((a, b) => b.priority - a.priority),
    overlayLayers: features.flatMap((f) => f.overlayLayers ?? []).sort((a, b) => a.z - b.z),
    featureWindows: features.flatMap((f) => f.windows ?? [])
  }
  if (import.meta.env.DEV) console.info(`[tut] features: ${features.map((f) => f.id).join(', ')}`)
  return built
}

export const getFeatures = (): Feature[] => build().features
/** Sorted by priority, highest first. Stable across renders (the island calls each mode's hook in order). */
export const getIslandModes = (): IslandMode[] => build().islandModes
export const getOverlayLayers = (): OverlayLayer[] => build().overlayLayers
export const getFeatureWindows = (): FeatureWindow[] => build().featureWindows
/** v2: the app-kind windows (Onboarding, Library, Progress, Account). */
export const getAppWindows = (): FeatureWindow[] => build().featureWindows.filter((w) => w.kind === 'app')
