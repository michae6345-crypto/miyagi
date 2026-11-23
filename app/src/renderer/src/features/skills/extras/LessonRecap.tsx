/**
 * The lesson-end recap (mockup skills-07-extras, 2): what this lesson moved on the skill tree, inside the lesson-complete
 * card (features/complete). One row per skill: its ring, its name, and one word on the right ("mastered", "ready now",
 * "2 skills away"), hairlines between. This is where the unlock motion plays first: rows arrive in turn and each ring
 * fills (SkillRing play). The card's one primary becomes "Next: <skill> · N min" (complete/Panel.tsx Actions).
 */
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { canSend, useLesson } from '../../../core/lesson'
import { color, fade, spring, type2 } from '../../../core/theme'
import { lessonRecap, recapWord, type Recap } from './recap'
import { SkillRing, ringState } from './SkillRing'
import { refreshSkillGraph, useSkillGraph } from './store'

/** How long the card waits for the engine's fresh graph before it settles for the one it already has. */
export const RECAP_WAIT_MS = 1500

/**
 * The recap for the open lesson-complete card, or undefined (no graph, or nothing on it belongs to this lesson: the
 * card then keeps its own Skills and Next up). `lessonId`: card.result.lessonId when the engine sent one.
 * The graph in the store is usually from before the lesson ended (the skill just mastered still practicing, or
 * missing), so the recap waits for a `progress` that arrived after the card opened (useSkillGraph.at). It settles for
 * the cached graph after RECAP_WAIT_MS, or at once when the engine can't send progress.get. Until then the card keeps
 * its own Skills block, so the recap's rows never jump under the learner.
 */
export function useLessonRecap(open: boolean, lessonId?: string): Recap | undefined {
  const graph = useSkillGraph((s) => s.graph)
  const at = useSkillGraph((s) => s.at)
  const id = useLesson((s) => s.lesson?.id)
  const skills = useLesson(useShallow((s) => s.steps.flatMap((x) => (x as { skillIds?: string[] }).skillIds ?? [])))
  // When this card opened, and whether it stopped waiting for a fresh graph. Both reset when the card closes.
  const [since, setSince] = useState<number>()
  const [settled, setSettled] = useState(false)
  // The lesson just changed what is mastered: ask for the graph again once per card.
  useEffect(() => {
    if (!open) {
      setSince(undefined)
      setSettled(false)
      return
    }
    setSince(Date.now())
    setSettled(false)
    refreshSkillGraph()
    if (!canSend('progress.get')) {
      setSettled(true)
      return
    }
    const t = setTimeout(() => setSettled(true), RECAP_WAIT_MS)
    return () => clearTimeout(t)
  }, [open])
  const ready = open && since !== undefined && (settled || at >= since)
  return useMemo(() => (ready ? lessonRecap(graph, { lessonIds: [id ?? '', lessonId ?? ''], skillIds: skills }) : undefined), [ready, graph, id, lessonId, skills])
}

const caption = { fontSize: type2.xs, color: color.label } as const

/** `from`: the card's entrance index this block starts at (its rows follow 60 ms apart). */
export function LessonRecap({ recap, from = 0 }: { recap: Recap; from?: number }): ReactNode {
  const reduce = useReducedMotion()
  const at = (i: number): number => (reduce ? 0 : 0.12 + (from + i) * 0.06)
  return (
    <div className="flex flex-col gap-[6px]" data-skill-recap>
      <span className="font-semibold" style={caption}>
        Skills
      </span>
      <ul className="m-0 flex list-none flex-col p-0">
        {recap.rows.map((r, i) => (
          <motion.li
            key={r.node.id}
            data-recap-row={r.kind}
            className="flex items-center gap-[12px]"
            style={{ height: 40, borderTop: i ? `1px solid ${color.hairline}` : undefined, fontSize: type2.md }}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...spring, delay: at(i), opacity: { ...fade.in, delay: at(i) } }}
          >
            <SkillRing
              state={r.kind === 'away' ? 'locked' : r.kind === 'ready' ? 'ready' : ringState(r.node)}
              size={16}
              play={r.kind !== 'away'}
              delay={at(i) + 0.08}
              fraction={r.node.evidence && r.node.evidence.total ? r.node.evidence.done / r.node.evidence.total : undefined}
            />
            <span className="min-w-0 flex-1 truncate" style={{ color: r.kind === 'away' ? color.label : color.text }}>
              {r.node.label}
            </span>
            <span className="shrink-0" style={{ ...caption, fontVariantNumeric: 'tabular-nums' }}>
              {recapWord(r)}
            </span>
          </motion.li>
        ))}
      </ul>
    </div>
  )
}
