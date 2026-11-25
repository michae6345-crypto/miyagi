/**
 * Feature: skills. The goal Home names (the project at the end of the plan the learner works on, library/home/data.ts
 * fromContract), for the Skills page when the graph's goal is only inferred (the learner never picked one). Both
 * pages then state one goal the same way (QA R2-02): "Goal A network that finds a circle · 3 of 9 lessons".
 */
import { useMemo } from 'react'
import { fromContract, planGoalFor, type GoalView } from '../library/home/data'
import { useAskV4, useV4 } from '../library/home/v4'
import type { SkillGraph } from './model'

/** Home's goal, or undefined when the learner picked a goal on Skills (theirs wins) or no plan has a project. */
export function usePlanGoal(g: SkillGraph | undefined): GoalView | undefined {
  const activity = useV4((s) => s.activity)
  const plans = useV4((s) => s.plans)
  const goal = useMemo(() => fromContract({ activity, plans }).goal, [activity, plans])
  return planGoalFor(g, goal)
}

/** Asks for the plans (and the week) when Skills opens on its own, as Home does. */
export const useAskPlanGoal = useAskV4
