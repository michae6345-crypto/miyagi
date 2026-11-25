/**
 * Feature: skills. The Skills page, flat (Adrian's round 3, Nov 23: "16-skill-tree-r3-*", Notion style).
 *
 *   header      (the shell's page header, right side: SkillsHeaderTools) the page's one primary, Continue <skill>,
 *               only while a view is on show
 *   lede        Goal <name> · 6 of 11 skills · Change
 *   tabs        Path | Map | List (underlined); on the Map the zoom (Tracks | Skills | Steps); the search
 *   view        Path (the goal's path left to right, then "Still to go" and "Keep fresh"), Map (bottom up, by zoom) or
 *               List (one card per track)
 *   peek        a skill's page over the right of the view (Esc or × closes it)
 * No goal yet: the goal picker fills the page. Change opens the same picker. Esc closes the peek, then the picker,
 * then clears the search (never the window).
 */
import { Play } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { color, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { Skeleton } from '../library/parts'
import { useShell, setPage } from '../shell/store'
import { PageColumn, V4_W } from '../shell/ui'

/** The page's column: the v4 column (V4_W), so the title and the content start where every v4 page's do (MIC-54). */
const COL = { maxWidth: V4_W }

/** While the first `progress` is on its way: a lede and three rows that breathe (no bare title, no hue). */
export function SkillsSkeleton(): ReactNode {
  return (
    <PageColumn wide style={COL}>
      <div data-shell-skills-loading aria-busy aria-label="Loading your skills" className="flex flex-col" style={{ gap: 12 }}>
        <Skeleton h={20} w={240} />
        <Skeleton h={14} w={160} />
        <div style={{ height: 12 }} />
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} h={44} />
        ))}
      </div>
    </PageColumn>
  )
}
import type { SkillGraph } from './model'
import { GoalPicker } from './Goal'
import { ListView } from './ListView'
import { Lede, MapView, PathView, Peek, Tabs } from './flat/views'
import { chooseGoal, closePicker, openPicker, select, setQuery, showTools, startSkill, useSkills } from './store'
import { useSkillGraph } from './store'
import { useDashView } from '../dashboard/Dashboard'

/** The shell header's right side on the Skills page: the page's one primary, Continue (or Start) the next skill. */
export function SkillsHeaderTools(): ReactNode {
  const tools = useSkills((s) => s.tools)
  const { now } = useDashView()
  const g = useSkillGraph(now)
  const n = g?.next ? g.byId[g.next.skillId] : undefined
  if (!tools || !g || !n) return null
  return <PrimaryButton icon={Play} label={`${g.next!.practicing ? 'Continue' : 'Start'} ${g.next!.label}`} onClick={() => startSkill(n, g)} />
}

/** No skills at all yet: the bonsai, one line, the way to a lesson. */
function NoSkills(): ReactNode {
  return (
    <PageColumn wide style={COL}>
      <div data-shell-skills-empty className="flex flex-col items-start" style={{ gap: 8 }}>
        <MiyagiMark size={40} />
        <span className="font-semibold" style={{ marginTop: 8, fontSize: type2.lg, color: color.text }}>
          No skills yet
        </span>
        <span style={{ fontSize: type2.sm, color: color.label, maxWidth: 360 }}>Finish a lesson. The skills its checks proved show up here.</span>
        <div style={{ marginTop: 16 }}>
          <QuietButton label="Browse lessons" onClick={() => setPage('lessons')} />
        </div>
      </div>
    </PageColumn>
  )
}

export function SkillsView({ g, now }: { g: SkillGraph | undefined; now: number }): ReactNode {
  const view = useSkills((s) => s.view)
  const zoom = useSkills((s) => s.zoom)
  const query = useSkills((s) => s.query)
  const selected = useSkills((s) => s.selected)
  const picker = useSkills((s) => s.picker)
  const active = useShell((s) => s.page === 'skills')

  // Esc: the peek, then the picker, then the search. Only while this page is the one on show.
  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape') return
      const s = useSkills.getState()
      if (s.selected) select(undefined)
      else if (s.picker) closePicker()
      else if (s.query) setQuery('')
      else return
      e.preventDefault()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [active])

  const tools = !!g && g.nodes.length > 0 && !!g.goal && !picker
  useEffect(() => {
    showTools(tools)
    return () => showTools(false)
  }, [tools])

  // No graph, or one with no skills yet (the page waits on the first `progress` itself): one empty state, one way on.
  if (!g || !g.nodes.length) return <NoSkills />

  const noGoal = !g.goal
  const canChange = g.source === 'graph' && g.capstones.length > 1
  const open = (id: string): void => select(selected === id ? undefined : id)
  const peek = selected && g.byId[selected] ? selected : undefined

  if (noGoal || picker)
    return (
      <div data-skills-page="picker" className="flex h-full min-h-0 flex-col overflow-y-auto">
        <PageColumn wide top={noGoal ? 64 : 40} style={COL}>
          <GoalPicker g={g} onPick={chooseGoal} onCancel={noGoal ? undefined : closePicker} />
        </PageColumn>
      </div>
    )

  const head = (
    <PageColumn wide top={0} bottom={0} style={COL}>
      <Lede g={g} onChange={canChange ? openPicker : undefined} />
      <Tabs view={view} zoom={zoom} />
    </PageColumn>
  )

  return (
    <div data-skills-page={view} className="relative flex h-full min-h-0 flex-col">
      {view === 'path' ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {head}
          <PageColumn wide top={0} bottom={48} style={COL}>
            <PathView g={g} query={query} selected={peek} onOpen={open} />
          </PageColumn>
        </div>
      ) : view === 'map' ? (
        <div className="flex min-h-0 flex-1 flex-col">
          {head}
          <div className="flex min-h-0 flex-1 flex-col" style={{ paddingInline: 'var(--page-gutter, 40px)' }}>
            <MapView key={zoom} g={g} query={query} selected={peek} onOpen={open} />
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          {head}
          <div className="relative min-h-0 flex-1">
            <ListView g={g} query={query} now={now} onOpen={open} />
          </div>
        </div>
      )}
      {peek && <Peek key={peek} g={g} id={peek} now={now} onClose={() => select(undefined)} onOpen={(id) => select(id)} />}
    </div>
  )
}
