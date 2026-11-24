/**
 * Feature: skills. The one place the flat page reads the per-skill fields that `contract: ui-v4` adds to
 * `progress.graph` (shared/contracts/UI-V4.md section 4: SkillInfo.steps, the passing check, minutes, the project's
 * artifact). The page's view model (../model.ts) does not carry them yet, so these are typed placeholders built from
 * what it does carry. Wiring ui-v4 means filling `skillExtras` from the payload; nothing else on the page changes.
 */
import type { SkillGraph, SkillGraphNode } from '../model'

export type SkillStepLine = { title: string; passed: boolean }
export type SkillExtras = {
  /** About how long the rest of this skill takes. Undefined: unknown (the page leaves the minutes out). */
  estMinutes?: number
  /** Every step behind the skill, in lesson order. */
  steps: SkillStepLine[]
  /** The check its newest pass met, and when. */
  passedCheck?: { label: string; at: number }
  /** What the learner made for a project (an image URL); the bonsai stands in until then. */
  artifact?: string
}

/** The ui-v4 fields for one skill (placeholders until the view model carries them). */
export function skillExtras(n: SkillGraphNode, g: SkillGraph): SkillExtras {
  const total = n.evidence?.total ?? n.lessons.reduce((s, l) => s + l.stepIds.length, 0)
  const done = n.evidence?.done ?? 0
  const pick = g.next?.skillId === n.id ? g.next : undefined
  return {
    estMinutes: pick?.estMinutes,
    steps: Array.from({ length: total }, (_, i) => ({ title: `Step ${i + 1}`, passed: i < done }))
  }
}

/** The minutes column only shows when every row knows its minutes (never a column of blanks). */
export function everyHasMinutes(ns: SkillGraphNode[], g: SkillGraph): boolean {
  return ns.length > 0 && ns.every((n) => skillExtras(n, g).estMinutes !== undefined)
}
