/**
 * Feature: buddy. The learner's color for their buddy (Adrian, Nov 23: "give users the option to choose the color,
 * like Clicky, when they are setting it up").
 *
 *   useSkin()          the skin in use (palette.ts Skin): the character, its loop and the bubble's bars all read it
 *   useSkinName()      its name
 *   pickSkin('peach')  the learner picks one (the picker, ColorPicker.tsx)
 *
 * Where it comes from, first match wins:
 *   1. the browser stage's ?skin=<name> (any skin in palette.ts, also the ones that are not offered to learners)
 *   2. localStorage `miyagi.buddy.skin`, in Electron only. Every miyagi window shares the origin, so a pick made in
 *      setup or Settings reaches the overlay through the `storage` event. This is the store until core Prefs has a
 *      field for it (brief, Core requests).
 *   3. DEFAULT_SKIN
 * A pick made in the browser stage stays in memory: it never writes localStorage, so a later stage load comes up in
 * the default again (the review pictures depend on that).
 */
import { create } from 'zustand'
import { DEFAULT_SKIN, SKINS, type Skin, type SkinName } from './palette'

const KEY = 'miyagi.buddy.skin'
const isName = (v: unknown): v is SkinName => typeof v === 'string' && Object.prototype.hasOwnProperty.call(SKINS, v)
/** The real app, not the browser stage (bridge.ts tells them apart the same way; not imported, so this file loads anywhere). */
const inApp = typeof window !== 'undefined' && 'tut' in window

function fromStage(): SkinName | undefined {
  if (inApp || typeof location === 'undefined') return undefined
  const q = new URLSearchParams(location.search).get('skin')
  return isName(q) ? q : undefined
}

function fromLocal(): SkinName | undefined {
  if (!inApp) return undefined
  try {
    const v = localStorage.getItem(KEY)
    return isName(v) ? v : undefined
  } catch {
    return undefined
  }
}

const store = create<{ name: SkinName }>(() => ({ name: fromStage() ?? fromLocal() ?? DEFAULT_SKIN }))

export function useSkinName(): SkinName {
  return store((s) => s.name)
}

export function useSkin(): Skin {
  return SKINS[store((s) => s.name)]
}

export function pickSkin(name: SkinName): void {
  if (!isName(name) || store.getState().name === name) return
  store.setState({ name })
  if (!inApp) return
  try {
    localStorage.setItem(KEY, name)
  } catch {
    // No storage: the pick holds for this window.
  }
}

// Another window picked (setup, Settings): follow it.
if (inApp) {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY && isName(e.newValue)) store.setState({ name: e.newValue })
  })
}
