/**
 * Feature: progress, v4 page state. The v4 fields of the engine's `progress` answer (model.ts readV4), next to the
 * dashboard store's reading of the same message (features/dashboard store.ts keeps tracks, completed, review).
 *
 * Browser stage only, `?v4sample`: until mock/scenarios/ui-v4.json (the UI-V4 contract's mock) lands, the payload is
 * topped up with a sample of the v4 fields (minutes, recent passes, goal, plans, bon), dated from today. Never in
 * Electron, never without the flag.
 */
import { create } from 'zustand'
import { engineMode } from '../../../bridge'
import { onMessage } from '../../../core/bus'
import { stageRebase } from '../../dashboard/stage'
import { EMPTY_V4, readV4, type V4 } from './model'

export const useV4 = create<{ v4: V4; seen: boolean }>(() => ({
  v4: EMPTY_V4,
  seen: false
}))

const params = typeof location === 'undefined' ? new URLSearchParams() : new URLSearchParams(location.search)
const SAMPLE = engineMode() === 'inline' && params.has('v4sample')

onMessage('progress', (raw) => {
  const base = stageRebase(raw)
  useV4.setState({ v4: readV4(SAMPLE ? withSample(base) : base), seen: true })
})

/** Stage sample of the v4 fields (Adrian's mock numbers), on top of whatever the scenario sent. */
function withSample(raw: unknown): unknown {
  const m = raw && typeof raw === 'object' ? { ...(raw as Record<string, unknown>) } : {}
  const now = new Date()
  const day = (back: number): string => {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - back)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }
  const at = (back: number, h = 12, min = 0): number => Math.floor(new Date(now.getFullYear(), now.getMonth(), now.getDate() - back, h, min).getTime() / 1000)
  // This week as in the mock (Mon 0 … Sun 15), ending today; earlier weeks rise toward now.
  const dow = (now.getDay() + 6) % 7
  const week = [0, 22, 41, 0, 18, 12, 15]
  const weekly = [0, 35, 62, 48, 90, 75, 110, 84, 96, 130, 121]
  const activity: Array<{ date: string; reps: number; minutes: number }> = []
  for (let i = 0; i <= dow; i++) {
    const min = week[(i + 7 - dow + 6) % 7]
    if (min)
      activity.push({
        date: day(dow - i),
        reps: Math.max(1, Math.round(min / 7)),
        minutes: min
      })
  }
  weekly.forEach((w, i) => {
    const back = dow + 1 + (10 - i) * 7
    if (w) {
      activity.push({
        date: day(back + 1),
        reps: Math.round(w / 14),
        minutes: Math.round(w * 0.6)
      })
      activity.push({
        date: day(back + 3),
        reps: Math.round(w / 18),
        minutes: w - Math.round(w * 0.6)
      })
    }
  })
  m.activity = activity
  m.recent = [
    {
      at: at(0, 16, 12),
      step: 'Add one row to every row',
      skill: 'Broadcasting',
      lesson: 'numpy for networks'
    },
    {
      at: at(0, 16, 3),
      step: 'Shapes and axes',
      skill: 'Broadcasting',
      lesson: 'numpy for networks'
    },
    {
      at: at(1),
      step: 'With numpy',
      skill: 'Dot product',
      lesson: 'The dot product'
    },
    {
      at: at(3),
      step: 'Slice rows and columns',
      skill: 'Indexing',
      lesson: 'numpy for networks'
    },
    {
      at: at(4),
      step: 'Scale the mug on one axis',
      skill: 'Transforms',
      lesson: 'Move, rotate and scale'
    },
    {
      at: at(4, 11),
      step: 'Move the mug with G',
      skill: 'Transforms',
      lesson: 'Move, rotate and scale'
    },
    {
      at: at(8),
      step: 'Label both axes',
      skill: 'Line plots',
      lesson: 'Plot your data with matplotlib'
    },
    {
      at: at(8, 11),
      step: 'Plot a line from two lists',
      skill: 'Line plots',
      lesson: 'Plot your data with matplotlib'
    }
  ]
  m.totals = { minutes: 999, steps: 58, lessons: 4 }
  m.bon = { passed: 58 }
  m.goal = {
    title: 'Fit sin(x) with a network',
    mastered: 8,
    total: 13,
    minutesLeft: 180,
    eta: at(-10)
  }
  m.plans = [
    { id: 'nn', title: 'Neural networks from scratch', done: 3, total: 8 },
    { id: 'intro-blender', title: 'Intro to Blender', done: 1, total: 10 }
  ]
  m.milestones = [
    { label: '10 skills mastered', at: at(3) },
    { label: 'First lesson finished', at: at(14) }
  ]
  // Steps to master on the practicing skills, so "Closest to mastered" has something to rank.
  const needs = [5, 4, 3, 4, 5]
  let k = 0
  m.skills = (Array.isArray(m.skills) ? m.skills : []).map((t) => {
    const tr = t as Record<string, unknown>
    const skills = (Array.isArray(tr.skills) ? tr.skills : []).map((s) => {
      const sk = s as Record<string, unknown>
      if (sk.state !== 'practicing') return sk
      const need = needs[k++ % needs.length]
      return {
        ...sk,
        need,
        reps: Math.min(typeof sk.reps === 'number' ? sk.reps : 1, need - 1)
      }
    })
    return { ...tr, skills }
  })
  // The mock's "Keep fresh · 4 min".
  m.review = { ...(m.review && typeof m.review === 'object' ? (m.review as Record<string, unknown>) : {}), minutes: 4 }
  return m
}
