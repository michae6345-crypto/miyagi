/**
 * Feature: library. Home v4's first-run "Start here": three catalog plans (Adrian's docs/ui-next/catalog/catalog.json,
 * the contract's `CatalogPlan`), as the cards draw them. Only the fields a card shows are kept here; the full catalog
 * ships with the plans lane (it replaces presets/packs.ts). Numbers are the catalog's own (lessons, minutes, project).
 */
import type { CatalogPlan } from '../../../../../../../shared/contracts/events'
import { coverForTool, endsWith, type CoverKind, type StarterPlan } from './data'

/**
 * The lesson a new learner is offered first (Home's first-run card, the first ask chip). Data, not UI code: the engine's
 * curated lesson (server/orchestrator/curated.py, lesson-nn-from-scratch) answers this goal with zero model calls.
 */
export type Featured = { title: string; goal: string; tool: string; steps: number; minutes: number; cover: CoverKind }
export const FEATURED: Featured = { title: 'A neural net from scratch', goal: 'build a neural network from scratch', tool: 'VS Code', steps: 6, minutes: 15, cover: 'net' }

/** The ask field's ideas: the featured lesson first, then the learner's own, topped up with these. */
export const IDEAS = ['Build a neural network from scratch', 'Clean a messy CSV with pandas', 'Build a tiny web server']

/** What a Start here card needs from a catalog plan (lessons: how many). */
export type CatalogCard = Pick<CatalogPlan, 'id' | 'title' | 'tool' | 'minutes'> & { lessons: number; project: string }

/** catalog.json, Nov 24: the three "start" plans the mock shows first. */
export const START_HERE: CatalogCard[] = [
  { id: 'intro-python', title: 'Intro to Python', tool: { id: 'vscode', label: 'VS Code' }, minutes: 170, lessons: 10, project: 'A number guessing game' },
  { id: 'intro-blender', title: 'Intro to Blender', tool: { id: 'blender', label: 'Blender' }, minutes: 155, lessons: 10, project: 'A desk lamp, modeled and rendered' },
  { id: 'intro-cad', title: 'Intro to CAD', tool: { id: 'freecad', label: 'FreeCAD' }, minutes: 150, lessons: 10, project: 'A phone stand you could print' }
]

/** A catalog plan (whole, or the card's fields) as a Start here card. */
export function starterFrom(p: CatalogCard | CatalogPlan): StarterPlan {
  const lessons = typeof p.lessons === 'number' ? p.lessons : p.lessons.length
  const project = typeof p.project === 'string' ? p.project : p.project.title
  const minutes = p.minutes ?? (typeof p.lessons === 'number' ? 0 : p.lessons.reduce((n, l) => n + l.minutes, 0))
  return { id: p.id, title: p.title, tool: p.tool.label, lessons, minutes, ends: endsWith(project), cover: coverForTool(p.tool.id) }
}

/** Start here, leaving out plans the learner already has (plans.list). */
export const starters = (have: ReadonlySet<string> = new Set()): StarterPlan[] => START_HERE.filter((p) => !have.has(p.id)).map(starterFrom)
