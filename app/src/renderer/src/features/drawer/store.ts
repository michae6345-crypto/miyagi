/**
 * Feature: drawer. Is the lesson drawer open (the learner's choice)? The spotlight can make it yield
 * for a while (see index.tsx); that never changes `open`, so it slides back once the target moves on.
 */
import { create } from 'zustand'
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
// A new lesson starts closed (the stage's ?drawer=open keeps it open for review).
onMessage('lesson.ready', () => useDrawer.setState({ open: startOpen }))
