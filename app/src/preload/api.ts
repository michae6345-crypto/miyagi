/**
 * The bridge between renderer and main. Types only, shared by preload and renderer.
 *
 * UI signals (cross-window choreography):
 *   main -> launcher : 'launcher:open', 'launcher:close'
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
}

declare global {
  interface Window {
    tut?: TutBridge
  }
}
