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
  /** Handle bridge.invoke('<channel>', …args) from any window. */
  handle(channel: string, fn: (...args: unknown[]) => unknown): void
  /** Send to every window: bridge.onFeature('<channel>', cb). */
  broadcast(channel: string, payload?: unknown): void
  /** Listen to bridge.emit(signal, payload) from any window (core signals included). */
  onSignal(signal: string, fn: (payload?: unknown) => void): void
}

export type MainFeature = { id: string; setup(ctx: MainContext): void }

export function defineMainFeature(f: MainFeature): MainFeature {
  return f
}
