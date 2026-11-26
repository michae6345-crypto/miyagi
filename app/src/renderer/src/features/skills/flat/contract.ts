/**
 * Feature: skills. The one place the flat page reads the per-skill fields that `contract: ui-v4` adds to
 * `progress.graph` (shared/contracts/UI-V4.md section 4), through the view model (../model.ts):
 *   steps       SkillInfo.steps (title, passed), in lesson order. With none on the wire, the lessons behind the skill
 *               stand in as rows (a lesson's title, done when the skill is mastered), so every card still lists its work.
 *   estMinutes  only what the engine says: graph.next.estMinutes for the next skill. SkillInfo carries no minutes yet, so
 *               the Time column and the goal's "about N hours left" stay hidden until every row knows its minutes.
 *   review      due (review.dueAt / schedule.dueAt has come) or listed in graph.keepFresh.
 *   artifact    the project's own result (SkillCapstone.artifact) when it is an image.
 */
import type { SkillGraph, SkillGraphNode } from '../model'

export type SkillStepLine = { title: string; passed: boolean; current?: boolean; lesson?: string }
export type SkillExtras = {
  /** About how long the rest of this skill takes. Undefined: unknown (the page leaves the minutes out). */
  estMinutes?: number
  /** Every step behind the skill, in lesson order (or its lessons when the engine sent no steps). */
  steps: SkillStepLine[]
  /** The rows are real steps (SkillInfo.steps), not lessons standing in. */
  real: boolean
  /** Its review is due or it is on Keep fresh. */
  reviewDue: boolean
  /** What the learner made for a project (a local image path); the bonsai stands in until then. */
  artifact?: { path: string; caption?: string }
}

export function skillExtras(n: SkillGraphNode, g: SkillGraph): SkillExtras {
  const pick = g.next?.skillId === n.id ? g.next : undefined
  const mastered = n.state === 'mastered'
  let steps: SkillStepLine[]
  const real = !!n.steps?.length
  if (real) {
    const firstOpen = n.state === 'practicing' ? n.steps!.findIndex((s) => !s.passed) : -1
    steps = n.steps!.map((s, i) => ({ title: s.title, passed: s.passed || mastered, current: i === firstOpen, lesson: s.lessonTitle }))
  } else {
    const titles = [...new Set(n.lessons.map((l) => l.title).filter((t): t is string => !!t))]
    steps = titles.map((t) => ({ title: t, passed: mastered }))
  }
  const cap = n.kind === 'capstone' ? g.capstones.find((c) => c.id === n.id) : undefined
  const art = cap?.artifact?.kind === 'image' && cap.artifact.path ? { path: cap.artifact.path, caption: cap.artifact.caption } : undefined
  return {
    estMinutes: pick?.estMinutes ?? (cap && !mastered ? cap.estMinutes : undefined),
    steps,
    real,
    reviewDue: mastered && (n.review || g.keepFresh.includes(n.id)),
    artifact: art
  }
}

/** The minutes column only shows when every row knows its minutes (never a column of blanks). */
export function everyHasMinutes(ns: SkillGraphNode[], g: SkillGraph): boolean {
  return ns.length > 0 && ns.every((n) => skillExtras(n, g).estMinutes !== undefined)
}
