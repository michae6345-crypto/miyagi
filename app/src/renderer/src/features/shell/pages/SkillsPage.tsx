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
import { useEffect, type ReactNode } from 'react'
import { color } from '../../../core/theme'
import { useDashView } from '../../dashboard/Dashboard'
import { primeSkills, useSkillGraph } from '../../skills/store'
import { SkillsView } from '../../skills/SkillsView'

export { SkillsHeaderTools } from '../../skills/SkillsView'

export function SkillsPage(): ReactNode {
  // The dashboard's asks keep `progress` fresh (on open, on (re)connect, on focus); the skills store keeps the raw payload.
  const { load, now } = useDashView()
  useEffect(() => void primeSkills(), [])
  const g = useSkillGraph(now)
  return (
    <div data-shell-skills className="relative h-full min-h-0" style={{ color: color.text }}>
      {load === 'loading' && !g ? null : <SkillsView g={g} now={now} />}
    </div>
  )
}
