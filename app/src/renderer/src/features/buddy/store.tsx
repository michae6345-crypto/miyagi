/**
 * Feature: buddy. What the living bonsai shows, from the engine:
 *   thinking  core/lesson's useThinking (engine status "thinking")
 *   bloom     a counter bumped on every real step.passed (a Skip is not a pass and never blooms)
 *   pointing  while a branch is out (pointing.ts), the tree leans toward what it points at
 * <Buddy /> is LivingMark wired to all three; pass lean from usePointerLean where the pointer matters (the notch hover).
 */
import type { ReactNode } from 'react'
import { create } from 'zustand'
import { onMessage } from '../../core/bus'
import { useThinking } from '../../core/lesson'
import { LivingMark, type BuddyState } from './LivingMark'
import { usePointing } from './pointing'

const useBloom = create<{ n: number }>(() => ({ n: 0 }))

onMessage('step.passed', (p) => {
  if (!p.skipped) useBloom.setState((s) => ({ n: s.n + 1 }))
})

/** The buddy's state and bloom counter, for anything that draws a LivingMark itself. */
export function useBuddy(): { state: BuddyState; bloom: number } {
  const thinking = useThinking()
  const bloom = useBloom((s) => s.n)
  return { state: thinking ? 'thinking' : 'idle', bloom }
}

/** The living bonsai, wired to the engine. Where MiyagiMark stands for miyagi itself (the notch ears), use this. */
export function Buddy({ size = 16, lean = 0, className }: { size?: number; lean?: number; className?: string }): ReactNode {
  const { state, bloom } = useBuddy()
  // Pointing wins over the pointer: the tree leans toward what is pointed at.
  const toward = usePointing((s) => s.lean)
  return <LivingMark size={size} state={state} lean={toward || lean} bloom={bloom} className={className} />
}
