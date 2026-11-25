/**
 * Feature: shell. The Skills page: the skill tree (features/skills, Nov 22). Path | Map | List sit in the page header
 * beside the search (SkillsHeaderTools, handed to the shell's PageHeader); the page itself is the goal, the view, the
 * panel and the dock (SkillsView). The view model comes from the engine's `progress` payload (features/skills/model.ts
 * buildSkillGraph: the new `progress.graph`, or today's tracks as short chains). The constellation
 * (features/dashboard/Constellation.tsx) is no longer used here; it stays for the dashboard.
 *
 * Layout: the goal and the dock sit on the shell's wide column (1040 with the gutters, the title's own column); the
 * trees fill the pane edge to edge between them, and the List scrolls in one centered column.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { color } from '../../../core/theme'
import { useDashView } from '../../dashboard/Dashboard'
import { primeSkills, useSkillGraph } from '../../skills/store'
import { SkillsSkeleton, SkillsView } from '../../skills/SkillsView'
import { useAskPlanGoal } from '../../skills/planGoal'

/** How long the page waits on its first `progress` before it shows "No skills yet". */
const WAIT_MS = 1500

export { SkillsHeaderTools } from '../../skills/SkillsView'

export function SkillsPage(): ReactNode {
  // The dashboard's asks keep `progress` fresh (on open, on (re)connect, on focus); the skills store keeps the raw payload.
  const { load, now } = useDashView()
  useEffect(() => void primeSkills(), [])
  useAskPlanGoal()
  const g = useSkillGraph(now)
  // An answer that never comes (offline, an engine with no `progress`) must not leave a bare title: a skeleton while it
  // waits, then after a short wait the empty state (QA Q02); the graph replaces either as soon as it lands.
  const [waited, setWaited] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setWaited(true), WAIT_MS)
    return () => clearTimeout(t)
  }, [])
  return (
    <div data-shell-skills className="relative h-full min-h-0" style={{ color: color.text }}>
      {load === 'loading' && !g && !waited ? <SkillsSkeleton /> : <SkillsView g={g} now={now} />}
    </div>
  )
}
