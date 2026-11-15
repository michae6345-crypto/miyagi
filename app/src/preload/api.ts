/**
 * The bridge between renderer and main. Types only, shared by preload and renderer.
 *
 * UI signals (cross-window choreography):
 *   main -> launcher : 'launcher:open' {from:{w,h}} (the island's current size: the launcher grows out of it), 'launcher:close'
 *   main -> overlay  : 'launcher:open' (the island hides: the launcher has it), 'launcher:closed' (the island is back)
 *   overlay -> main  : 'island:size' {w,h,dx,dy} (the island's current size, so the launcher can start from it; dx/dy:
 *                      a card's offset from the notch spot, core/islandPlace.ts)
 *   any <-> any      : 'video:intent' (core seekVideo: main relays it to every OTHER window)
 *   any -> overlay   : 'island:yield' / 'island:return' (a focusable surface like settings grows out of the
 *                      island: the island hides until it's handed back). Main relays them to the overlay.
 *   launcher -> main : 'launcher:hidden' (closed normally), 'launcher:built' (shrank into the pill)
 *   main -> overlay  : 'pill:receive' (launcher just landed on the pill), 'shortcut' (kind)
 *   any -> main      : 'launcher:toggle' (e.g. clicking the idle pill or "Ask anything")
 *   overlay -> main  : 'overlay:interactive' (boolean: stop click-through while over a control)
 *   main -> any      : 'layout' (Layout)
 */
import type { Incoming, Outgoing } from '../common/wire'
import type { PlatformInfo, Rect } from '../main/platform'

export type UiSignal =
  | 'launcher:open'
  | 'launcher:close'
  | 'launcher:hidden'
  | 'launcher:built'
  | 'launcher:toggle'
  | 'pill:receive'
  | 'launcher:closed'
  | 'island:size'
  | 'video:intent'
  | 'island:yield'
  | 'island:return'
  | 'shortcut'
  | 'overlay:interactive'
  | 'layout'

/** Geometry of the display the overlay covers, in the window's own coordinates. */
export type Layout = {
  /** Where this window sits in screen points (primary display top-left = 0,0). */
  origin: { x: number; y: number }
  width: number
  height: number
  /** Usable area (excludes menu bar / dock / taskbar). */
  workArea: Rect
}

export type Unsub = () => void

export type TutBridge = {
  platform: PlatformInfo
  /** Engine messages (already parsed, {type, payload}). */
  onEvent(cb: (m: Incoming) => void): Unsub
  onStatus(cb: (connected: boolean) => void): Unsub
  send(cmd: Outgoing): void
  /** Ask main to replay the events so far (after a reload) and send the layout. */
  ready(): void
  on(signal: UiSignal, cb: (payload?: unknown) => void): Unsub
  emit(signal: UiSignal, payload?: unknown): void
  /**
   * Feature channels. Call a main-process handler a feature registered with ctx.handle('<channel>')
   * in src/main/features/<name>.ts (browser stage: registerWebHandler in the renderer).
   */
  invoke<T = unknown>(channel: string, ...args: unknown[]): Promise<T>
  /** Messages main sends to windows with ctx.broadcast('<channel>', payload). */
  onFeature(channel: string, cb: (payload?: unknown) => void): Unsub
}

declare global {
  interface Window {
    tut?: TutBridge
  }
}
