/**
 * What a main-process feature gets. Put a file in src/main/features/<name>.ts:
 *
 *   import { defineMainFeature } from '../context'
 *   export default defineMainFeature({
 *     id: 'player',
 *     setup(ctx) {
 *       const win = ctx.createWindow('player', { ...bounds, frame: false })   // renderer: features/player windows[{route:'player'}]
 *       ctx.handle('player:save-bounds', (b) => …)                            // renderer: bridge.invoke('player:save-bounds', b)
 *       ctx.broadcast('player:visible', true)                                 // renderer: bridge.onFeature('player:visible', …)
 *       ctx.engine.onOpen(() => …)                                            // every (re)connect to the engine
 *     }
 *   })
 *
 * Files there are discovered automatically; no shared file to edit.
 */
import type { App, BrowserWindow, BrowserWindowConstructorOptions, Display } from 'electron'
import type { EngineLink } from './engine'
import type { PlatformInfo, Rect } from './platform'

export type MainContext = {
  app: App
  platform: PlatformInfo
  engine: EngineLink
  /** The core windows (always created first). */
  overlay: BrowserWindow
  launcher: BrowserWindow
  /** The display the overlay is on. */
  display(): Display
  /**
   * A window loading index.html#/<route> with the shared preload. It receives every engine event and
   * UI layout like the core windows. Pass full BrowserWindow options (bounds, frame, etc.).
   */
  createWindow(route: string, options: BrowserWindowConstructorOptions): BrowserWindow
  /** The flags every overlay-style window uses (frameless, transparent, always-on-top, no shadow…). */
  overlayOptions(bounds: Rect): BrowserWindowConstructorOptions
  /**
   * Handle bridge.invoke('<channel>', …args) from any window. v2 (W0-6): only our own windows' main frames get
   * through (sender check); anything else is rejected before `fn` runs.
   */
  handle(channel: string, fn: (...args: unknown[]) => unknown): void
  /** Send to every window: bridge.onFeature('<channel>', cb). */
  broadcast(channel: string, payload?: unknown): void
  /** Listen to bridge.emit(signal, payload) from any window (core signals included). */
  onSignal(signal: string, fn: (payload?: unknown) => void): void
  /**
   * Include this window's rect in `overlay.bounds` while it's visible, so the engine's screen reader
   * ignores it (e.g. the player: otherwise OCR reads the tutorial's code in the video as the learner's).
   * Re-sent automatically when the window moves, resizes, shows or hides.
   */
  reportBounds(win: BrowserWindow): void
  /**
   * Keep a window above everything, full-screen apps included (level 'screen-saver', every Space).
   * relativeLevel -1 = just under the overlay (the player: the spotlight dim must cover it).
   * Every ctx.createWindow window already follows Spaces; call this for windows that must float on top.
   */
  raise(win: BrowserWindow, relativeLevel?: number): void
  /**
   * The notch island hand-over, for a focusable surface that grows out of it (settings…), like the launcher:
   * read its current size, start your panel at exactly that rect (top = platform.pillTop, centered), then
   * yieldIsland(true) so it hides; collapse back into its rect and yieldIsland(false) when you close.
   * Renderer side: bridge.emit('island:yield') / bridge.emit('island:return') do the same.
   * dx/dy: how far an open card has moved from the notch spot to keep off the spotlight (core/islandPlace.ts).
   */
  islandSize(): {
    w: number
    h: number
    dx?: number
    dy?: number
    /** false = nothing drawn: no click target */
    shown?: boolean
    /** The notch island: its top (0) and corner radii, so the launcher / Settings start from the notch's exact shape. Absent below the menu bar. */
    top?: number
    place?: 'notch'
    radii?: { top: number; bottom: number }
  }
  yieldIsland(on: boolean): void
  /**
   * The overlay window's own visible UI (bar, cards, drawer, island…: every data-hit / data-ui element), in screen
   * points, as the renderer last reported it for overlay.bounds (sampled every 300 ms). Feature windows not included.
   */
  overlayRects(): { x: number; y: number; w: number; h: number }[]
  /**
   * v2 (W0-4): open or focus an app window (Onboarding, Library, Progress, Account; main/appWindows.ts). Only the
   * allowlisted routes open; anything else returns undefined. args: small view hints, delivered as window:args.
   */
  openWindow(route: string, args?: Record<string, string | number | boolean>): BrowserWindow | undefined
  /** v2: that app window if it's open. */
  appWindow(route: string): BrowserWindow | undefined
}

export type MainFeature = { id: string; setup(ctx: MainContext): void }

export function defineMainFeature(f: MainFeature): MainFeature {
  return f
}
