/**
 * Feature: onboarding. The first run's one Back (onboarding redesign, Nov 28). A step that can go back registers its
 * handler with useBack; the host's top bar draws it (v4.tsx BackButton: the home window's flow strip, the login
 * window, the setup window), always in the same place, right of the traffic lights. Steps never draw a Back of their
 * own. Several steps can be mounted at once while one slides out and the next slides in, so each registration has its
 * own token and only clears itself: the newest live registration wins.
 */
import { useEffect, useRef } from 'react'
import { create } from 'zustand'

type Entry = { token: number; run: () => void }

export const useBackStore = create<{ stack: Entry[] }>(() => ({ stack: [] }))

let next = 1

/** Register (or clear, with undefined) a Back for as long as the calling step is mounted. */
export function useBack(run: (() => void) | undefined): void {
  // The latest handler, without re-registering on every render (a new closure each time).
  const ref = useRef(run)
  ref.current = run
  const on = !!run
  useEffect(() => {
    if (!on) return
    const token = next++
    useBackStore.setState((s) => ({ stack: [...s.stack, { token, run: () => ref.current?.() }] }))
    return () => useBackStore.setState((s) => ({ stack: s.stack.filter((e) => e.token !== token) }))
  }, [on])
}

/** The Back to draw now (the newest registration), or undefined. */
export function useBackAction(): (() => void) | undefined {
  return useBackStore((s) => s.stack[s.stack.length - 1]?.run)
}
