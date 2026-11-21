/**
 * The renderer's two buses. Features subscribe here instead of editing a shared reducer.
 *
 *   onMessage('offtrack', (p) => …)   every engine message, already parsed ({type, payload})
 *   onUi('dismiss', () => …)          window-local UI events (Esc / close button, dev reset, shortcuts)
 *
 * Subscribe at module top level in your feature's store file: features are imported at startup,
 * before the engine feed starts, so nothing is missed.
 */
import type { Incoming } from '../../../common/wire'

export type MessageType = Incoming['type']
export type PayloadOf<T extends MessageType> = Extract<Incoming, { type: T }>['payload']

type AnyHandler = (payload: unknown, msg: Incoming) => void
const messageHandlers = new Map<string, Set<AnyHandler>>()

export function onMessage<T extends MessageType>(type: T, fn: (payload: PayloadOf<T>, msg: Incoming) => void): () => void {
  if (!messageHandlers.has(type)) messageHandlers.set(type, new Set())
  messageHandlers.get(type)!.add(fn as AnyHandler)
  return () => messageHandlers.get(type)!.delete(fn as AnyHandler)
}

/** One gate (core/lesson's): returns false to drop a message before any feature sees it (a replayed lesson.ready). */
let gate: ((msg: Incoming) => boolean) | undefined
export function setGate(fn: (msg: Incoming) => boolean): void {
  gate = fn
}

/** Called once per engine message by the feed in main.tsx. */
export function dispatch(msg: Incoming): void {
  if (gate && !gate(msg)) return
  messageHandlers.get(msg.type)?.forEach((fn) => {
    try {
      fn(msg.payload, msg)
    } catch (err) {
      console.error(`[tut] handler for ${msg.type} threw`, err)
    }
  })
}

// ---------------------------------------------------------------------------

/**
 * UI events, local to one window.
 *   dismiss  : Esc or a card's close button; every card/diagram closes itself
 *   reset    : dev reset / new lesson; feature stores go back to blank
 *   shortcut : a shortcut fired (global key, bar button, stage key). Payload = kind.
 *              A handler returns true to "claim" it, which stops the action going to the engine
 *              (e.g. ⌥D while a diagram is open just closes it).
 */
export type UiEvent =
  | 'dismiss'
  | 'reset'
  | 'shortcut'
  /**
   * v2 (W0-5). panel: open / collapse / toggle the lesson panel (payload PanelRequest). The drawer feature (A1) owns
   * the panel and answers it; the Mini pill (A2), the recovery card (A3) and the keys ask through this, so no feature
   * imports another's opener inside the overlay.
   */
  | 'panel'
  /**
   * v2. surface: an overlay surface opened or closed (payload SurfaceSignal: {id, open}), for surfaces that must
   * yield to each other (the shortcut bar hides while the panel is open; a card stays off the recovery card).
   */
  | 'surface'

export type PanelRequest = 'open' | 'collapse' | 'toggle'
export type SurfaceSignal = { id: string; open: boolean }

type UiHandler = (payload?: unknown) => boolean | void
const uiHandlers = new Map<UiEvent, Set<UiHandler>>()

export function onUi(name: UiEvent, fn: UiHandler): () => void {
  if (!uiHandlers.has(name)) uiHandlers.set(name, new Set())
  uiHandlers.get(name)!.add(fn)
  return () => uiHandlers.get(name)!.delete(fn)
}

/** Returns true if any handler claimed the event. */
export function emitUi(name: UiEvent, payload?: unknown): boolean {
  let claimed = false
  uiHandlers.get(name)?.forEach((fn) => {
    if (fn(payload) === true) claimed = true
  })
  return claimed
}
