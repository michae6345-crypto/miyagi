/**
 * Feature: drawer. Is the lesson drawer open (the learner's choice)? The spotlight can make it yield
 * for a while (see index.tsx); that never changes `open`, so it slides back once the target moves on.
 */
import { create } from 'zustand'
import { bridge, registerWebHandler } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'

type DrawerState = { open: boolean }

/** Stage only: `?drawer=open` starts with the drawer open (review and screenshots). */
const startOpen = typeof location !== 'undefined' && new URLSearchParams(location.search).get('drawer') === 'open'

export const useDrawer = create<DrawerState>(() => ({ open: startOpen }))

export const toggleDrawer = (): void => useDrawer.setState((s) => ({ open: !s.open }))
export const closeDrawer = (): void => useDrawer.setState({ open: false })

// Esc / a card's close button closes every surface, the drawer included.
onUi('dismiss', closeDrawer)
onUi('reset', closeDrawer)
// A new lesson starts closed (the stage's ?drawer=open keeps it open for review). A "Just teach me" lesson
// (lesson.mode "lesson") opens it: there's no player and no chapter list, so the drawer is where
// "Step N of M" and the step's instructions live (Michael, Sat 3:56 PM).
onMessage('lesson.ready', (p) => useDrawer.setState({ open: startOpen || p.lesson.mode === 'lesson' }))

/** http(s) links only; anything else (file:, javascript:, a bare path) is ignored. */
export function isWebLink(url: string): boolean {
  try {
    const u = new URL(url)
    return u.protocol === 'https:' || u.protocol === 'http:'
  } catch {
    return false
  }
}

/**
 * A source row was clicked. Electron: main opens it in the default browser (src/main/features/drawer.ts).
 * Browser stage: a new tab.
 */
export function openSource(url: string): void {
  if (!isWebLink(url)) return
  bridge.invoke('drawer:open-url', url).catch((err) => console.warn('[drawer] open-url failed', err))
}
registerWebHandler('drawer:open-url', (url) => {
  if (typeof url === 'string' && isWebLink(url)) window.open(url, '_blank', 'noopener,noreferrer')
  return true
})
