/**
 * Feature: library. Home v4's local placeholder data (until "contract: ui-v4" lands with app/mock/scenarios/ui-v4.json).
 *
 *   FIRST_RUN   what a new learner can start: three catalog plans, four short lessons, four goals (Adrian's catalog,
 *               docs/ui-next/catalog). Shown on the first-run page with real data too: it is content, not progress.
 *   sampleHome  the mock's sample learner (README: "The learner in the mock is sample data"), for the browser stage
 *               only (?homeSample=full), so the page can be checked against the mock before the contract's scenario.
 */
import { addDays, dayKey, mondayOf } from '../../dashboard/model'
import type { DashData } from '../../dashboard/types'
import type { LibraryItem } from '../../../../../../../shared/contracts/events'
import type { V4Extra } from './data'

export const FIRST_RUN: Required<Pick<V4Extra, 'starters' | 'shortLessons' | 'goals'>> = {
  starters: [
    { id: 'intro-python', title: 'Intro to Python', tool: 'VS Code', lessons: 10, minutes: 180, ends: 'Ends with a number guessing game', cover: 'code' },
    { id: 'intro-blender', title: 'Intro to Blender', tool: 'Blender', lessons: 10, minutes: 150, ends: 'Ends with a desk lamp, modeled and rendered', cover: 'mug' },
    { id: 'intro-cad', title: 'Intro to CAD', tool: 'FreeCAD', lessons: 10, minutes: 150, ends: 'Ends with a phone stand you could print', cover: 'cad' }
  ],
  shortLessons: [
    { id: 'py-first', title: 'Run your first Python file', skill: 'Running a script', meta: 'VS Code · 4 steps · 10 min', cover: 'code', goal: 'Run your first Python file' },
    { id: 'sheets-first', title: 'Start a sign-up sheet', skill: 'Cells and ranges', meta: 'Google Sheets · 5 steps · 15 min', cover: 'table', goal: 'Start a sign-up sheet in Google Sheets' },
    { id: 'plot-first', title: 'Your first line plot', skill: 'Line plots', meta: 'Jupyter · 5 steps · 15 min', cover: 'plot', goal: 'Make your first line plot with matplotlib' },
    { id: 'blender-first', title: 'Move around the 3D viewport', skill: 'Viewport', meta: 'Blender · 5 steps · 10 min', cover: 'mug', goal: 'Move around the 3D viewport in Blender' }
  ],
  goals: [
    { title: 'Fit sin(x) with a network', skills: 13, minutes: 360 },
    { title: 'A sales report from a CSV', skills: 9, minutes: 240 },
    { title: 'A budget in Google Sheets', skills: 8, minutes: 180 },
    { title: 'A 3D-printable part', skills: 11, minutes: 300 }
  ]
}

/** ?homeSample=full|first in the browser stage; never in Electron. */
export function stageSample(): 'full' | 'first' | undefined {
  if (typeof location === 'undefined' || typeof window === 'undefined' || 'electron' in (window as unknown as Record<string, unknown>)) return undefined
  const v = new URLSearchParams(location.search).get('homeSample')
  return v === 'full' || v === 'first' ? v : undefined
}

const skill = (id: string, label: string, mastered: boolean, at?: number): DashData['tracks'][number]['skills'][number] => ({ id, label, state: mastered ? 'mastered' : 'not_started', lessons: [], masteredAt: mastered ? at : undefined })
const LABELS: Record<string, string[]> = {
  python: ['Variables', 'Loops', 'Functions', 'Lists'],
  numpy: ['Arrays', 'Indexing', 'Boolean masks'],
  math: ['Vectors', 'Dot product', 'Matrices'],
  pandas: ['DataFrames', 'Cleaning rows', 'groupby', 'Merge and join'],
  plotting: ['Line plots', 'Scatter plots', 'Subplots', 'Styling'],
  'neural networks': ['Single neuron', 'Layers', 'Training']
}
/** A track whose first `done` skills are mastered and the rest wait in a chain (so the next one is ready). */
const track = (name: string, done: number, total: number, at: number): DashData['tracks'][number] => {
  const ids = Array.from({ length: total }, (_, i) => `${name}-${i}`)
  return {
    track: name,
    mastered: done,
    total,
    skills: ids.map((id, i) => skill(id, LABELS[name]?.[i] ?? `${name} ${i + 1}`, i < done, i === 0 ? at : at - 20 * 86_400_000)),
    edges: ids.slice(1).map((id, i) => ({ from: ids[i], to: id })),
    cross: []
  }
}

/** The mock's learner, dated around `now` (today is the last bar). */
export function sampleHome(now: number): { data: DashData; items: LibraryItem[]; extra: V4Extra; cont: { title: string; line: string; done: number; total: number } } {
  const mon = mondayOf(now)
  const vals = [0, 22, 41, 0, 18, 12, 15]
  const minutes: Record<string, number> = {}
  vals.forEach((m, i) => {
    const t = addDays(mon, i)
    if (t <= now) minutes[dayKey(t)] = m
  })
  const at = (daysAgo: number, h = 12, m = 0): number => {
    const d = new Date(now - daysAgo * 86_400_000)
    d.setHours(h, m, 0, 0)
    return d.getTime()
  }
  const recentMaster = mon + 3600_000
  const data: DashData = {
    tracks: [track('python', 4, 4, recentMaster), track('numpy', 2, 3, recentMaster), track('math', 2, 3, 0), track('pandas', 2, 4, 0), track('plotting', 1, 4, 0), track('neural networks', 0, 3, 0)],
    completed: [],
    inProgress: [],
    next: [],
    activity: vals.map((m, i) => ({ date: dayKey(addDays(mon, i)), reps: m ? Math.max(1, Math.round(m / 7)) : 0, assisted: 0, hints: 0 })).filter((d) => d.date <= dayKey(now)),
    review: { items: [ { label: 'Functions', dueAt: now - 1, lastAt: now - 12 * 86_400_000 }, { label: 'DataFrames', dueAt: now - 1, lastAt: now - 9 * 86_400_000 } ] },
    settings: {}
  }
  const item = (id: string, title: string, tools: LibraryItem['tools'], steps: number, estMinutes: number, teaches: string): LibraryItem => ({ id, title, tools, steps, estMinutes, ready: true, teaches: [teaches] })
  data.tracks.push({ track: 'tags', mastered: 0, total: 0, skills: [skill('t-line', 'Line plots', false), skill('t-mat', 'Matrices', false), skill('t-gb', 'groupby', false), skill('t-mod', 'Modifiers', false)], edges: [], cross: [] })
  const items: LibraryItem[] = [
    item('plot', 'Plot your data with matplotlib', ['jupyter'], 6, 15, 't-line'),
    item('mat', 'Matrices as layers', ['jupyter'], 5, 25, 't-mat'),
    item('sales', 'Summarize sales with pandas', ['jupyter'], 6, 20, 't-gb'),
    { ...item('mod', 'Add a modifier', ['vscode'], 5, 15, 't-mod') }
  ]
  const extra: V4Extra = {
    minutes,
    plans: [
      { id: 'nn', title: 'Neural networks from scratch', done: 3, total: 8, next: 'Broadcasting' },
      { id: 'blender', title: 'Intro to Blender', done: 1, total: 10, next: 'Move, rotate and scale' }
    ],
    passes: [
      { key: 'p1', at: at(0, 16, 12), step: 'Add one row to every row', skill: 'Broadcasting' },
      { key: 'p2', at: at(0, 16, 3), step: 'Shapes and axes', skill: 'Broadcasting' },
      { key: 'p3', at: at(1), step: 'With numpy', skill: 'Dot product' },
      { key: 'p4', at: at(4), step: 'Slice rows and columns', skill: 'Indexing' },
      { key: 'p5', at: at(5), step: 'Scale the mug on one axis', skill: 'Transforms' }
    ],
    goal: { title: 'Fit sin(x) with a network', done: 8, total: 13, minutesLeft: 180 }
  }
  return { data, items, extra, cont: { title: 'Code your first neural network', line: 'Step 4 of 7 · Train it', done: 3, total: 7 } }
}
