/** Feature: diagrams. The latest diagram from the engine and whether it's open. */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { onMessage, onUi } from '../../core/bus'

type DiagramState = { diagram?: Payload<'diagram'>; open: boolean }

export const useDiagram = create<DiagramState>(() => ({ diagram: undefined, open: false }))
const set = useDiagram.setState

onUi('reset', () => set({ diagram: undefined, open: false }))
onUi('dismiss', () => set({ open: false }))
// ⌥D while a diagram is open just closes it (claim it, so no new request goes to the engine).
onUi('shortcut', (kind) => {
  if (kind !== 'diagram' || !useDiagram.getState().open) return
  set({ open: false })
  return true
})
onMessage('diagram', (p) => set({ diagram: p, open: true }))
onMessage('card', () => set({ open: false }))
onMessage('offtrack', () => set({ open: false }))
onMessage('step.started', () => set({ open: false }))
