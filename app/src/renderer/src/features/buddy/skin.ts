/**
 * Feature: buddy. The learner's color for their buddy (Adrian, Nov 23: "give users the option to choose the color,
 * like Clicky, when they are setting it up").
 *
 *   useSkin()          the skin in use (palette.ts Skin): the character, its loop and the bubble's bars all read it
 *   useSkinName()      its name
 *   pickSkin('peach')  the learner picks one (setup's color step, Settings' Buddy color row; ColorPicker.tsx)
 *   isSkinChosen()     they have picked, or kept, one: setup shows its color step only until then
 *   confirmSkin()      setup's Continue: the one showing is theirs, also when they kept the one it came in
 *
 * Where it comes from, first match wins:
 *   1. the browser stage's ?skin=<name>: any skin in palette.ts, also the ones not offered to learners. It counts as
 *      chosen, so stage shots of setup with ?skin= skip the color step.
 *   2. localStorage `miyagi.buddy.skin`, in the app only, and only a name from PICKS. Every miyagi window shares the
 *      origin, so a pick made in setup or Settings reaches the overlay through the `storage` event, and it is still
 *      there after a restart. This is the store until core Prefs has a field for it (brief, Core requests), the way
 *      features/sound kept its setting before Prefs had one.
 *   3. DEFAULT_SKIN, not chosen yet.
 * A pick made in the browser stage stays in memory: it never writes localStorage, so a later stage load comes up in
 * the default again (the review pictures depend on that).
 *
 * createSkins() is the whole of it without the browser, so test/buddySkin.test.ts can run it.
 */
import { create, type StoreApi, type UseBoundStore } from 'zustand'
import { DEFAULT_SKIN, PICKS, SKINS, type Skin, type SkinName } from './palette'

export const SKIN_KEY = 'miyagi.buddy.skin'

type SkinState = {
  name: SkinName
  /** The learner picked or kept a color. */
  chosen: boolean
  /** How many picks were made in this window: the picker's buddy beams at each one. */
  picks: number
}

type Env = {
  /** The real app (Electron), not the browser stage. */
  app: boolean
  /** location.search */
  search?: string
  /** localStorage, where there is one. */
  storage?: Pick<Storage, 'getItem' | 'setItem'>
}

const isSkin = (v: unknown): v is SkinName => typeof v === 'string' && Object.prototype.hasOwnProperty.call(SKINS, v)
const isPick = (v: unknown): v is SkinName => isSkin(v) && PICKS.includes(v)

export type Skins = {
  store: UseBoundStore<StoreApi<SkinState>>
  pick: (name: SkinName) => void
  confirm: () => void
  chosen: () => boolean
  /** Another window wrote the key (the `storage` event). */
  onStorage: (key: string | null, value: string | null) => void
}

export function createSkins(env: Env): Skins {
  const fromStage = (): SkinName | undefined => {
    if (env.app) return undefined
    const q = new URLSearchParams(env.search ?? '').get('skin')
    return isSkin(q) ? q : undefined
  }
  const fromLocal = (): SkinName | undefined => {
    if (!env.app) return undefined
    try {
      const v = env.storage?.getItem(SKIN_KEY)
      return isPick(v) ? v : undefined
    } catch {
      return undefined
    }
  }
  const save = (name: SkinName): void => {
    if (!env.app) return
    try {
      env.storage?.setItem(SKIN_KEY, name)
    } catch {
      // No storage: the pick holds for this window.
    }
  }
  const first = fromStage() ?? fromLocal()
  const store = create<SkinState>(() => ({ name: first ?? DEFAULT_SKIN, chosen: !!first, picks: 0 }))
  return {
    store,
    pick: (name) => {
      if (!isPick(name)) return
      const s = store.getState()
      store.setState({ name, chosen: true, picks: s.picks + 1 })
      save(name)
    },
    confirm: () => {
      store.setState({ chosen: true })
      save(store.getState().name)
    },
    chosen: () => store.getState().chosen,
    onStorage: (key, value) => {
      if (env.app && key === SKIN_KEY && isPick(value)) store.setState({ name: value, chosen: true })
    }
  }
}

const here = typeof window !== 'undefined'
/** bridge.ts tells the app from the stage the same way; not imported, so this file loads anywhere. */
const app = here && 'tut' in window
const storage = ((): Env['storage'] => {
  try {
    return here ? window.localStorage : undefined
  } catch {
    return undefined
  }
})()
const skins = createSkins({ app, search: here ? window.location.search : '', storage })

// Another window picked (setup, Settings): follow it.
if (here && app) window.addEventListener('storage', (e) => skins.onStorage(e.key, e.newValue))

export function useSkinName(): SkinName {
  return skins.store((s) => s.name)
}

export function useSkin(): Skin {
  return SKINS[skins.store((s) => s.name)]
}

/** Counts up at each pick in this window. */
export function useSkinPicks(): number {
  return skins.store((s) => s.picks)
}

export const pickSkin = skins.pick
export const confirmSkin = skins.confirm
export const isSkinChosen = skins.chosen
