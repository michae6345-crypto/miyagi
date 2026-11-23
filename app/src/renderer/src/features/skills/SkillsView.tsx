/**
 * Feature: skills. The Skills page.
 *
 *   header      (the shell's page header, right side: SkillsHeaderTools) Path | Map | List and "Find a skill"
 *   goal        GoalHeader on the page column, Change goal on its right
 *   view        Path (default: the skills on the way to the goal, left to right, the goal at the right end), Map (every
 *               track grown up from one trunk) or List (one card per track); the trees fill the pane edge to edge
 *   panel       a node's panel over the right of the view (Esc or × closes it); the dock steps aside while it is open
 *   dock        the page's one primary (Continue: <skill>) with its why, Also ready, Keep fresh
 * No goal yet: the goal picker fills the page ("What do you want to make first?"). Change goal opens the same picker
 * over the page. Esc closes the panel, then the picker, then clears the search (never the window).
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Search } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { color, fade, focus, highlight, layout, radius2, surface, type2 } from '../../core/theme'
import { Segmented } from '../../core/ui/controls'
import { QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { useShell, setPage } from '../shell/store'
import { PageColumn, WIDE_W } from '../shell/ui'
import type { SkillGraph } from './model'
import { Dock } from './Dock'
import { GoalHeader, GoalPicker } from './Goal'
import { ListView } from './ListView'
import { SkillPanel } from './Panel'
import { TreeCanvas } from './TreeCanvas'
import { chooseGoal, closePicker, openPicker, select, setQuery, setView, useSkills, VIEWS } from './store'

/** The shell header's right side on the Skills page: the view switch and the search. */
export function SkillsHeaderTools(): ReactNode {
  const view = useSkills((s) => s.view)
  const query = useSkills((s) => s.query)
  return (
    <div className="flex min-w-0 items-center" style={{ gap: 12 }}>
      <Segmented label="Skills view" options={VIEWS} value={view} onChange={setView} />
      <div className="relative min-w-0" style={{ width: 220 }}>
        <Search aria-hidden size={16} strokeWidth={1.8} className="pointer-events-none absolute" style={{ left: 12, top: 10, color: color.label }} />
        <input
          type="search"
          aria-label="Find a skill"
          placeholder="Find a skill"
          autoComplete="off"
          spellCheck={false}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape' && query) {
              e.preventDefault()
              e.stopPropagation()
              setQuery('')
            }
            if (e.key === 'Enter') {
              const first = document.querySelector<HTMLElement>('[data-skills-match="first"]')?.dataset.skillsId
              if (first) select(first)
            }
          }}
          className="w-full outline-offset-1 focus-visible:outline-2 focus-visible:outline-solid"
          style={{ height: 36, padding: '0 12px 0 36px', borderRadius: radius2.row, background: surface.well, boxShadow: `inset 0 0 0 1px ${surface.border}, ${highlight.well}`, color: color.text, fontSize: type2.sm, outlineColor: focus.dark }}
        />
      </div>
    </div>
  )
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(1040)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const read = (): void => setW(el.clientWidth)
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

/** No skills at all yet: the bonsai, one line, the way to a lesson. */
function NoSkills(): ReactNode {
  return (
    <PageColumn wide>
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

/** The hidden first match for search's Enter (the canvas lights matches; Enter opens the first). */
function FirstMatch({ g, query }: { g: SkillGraph; query: string }): ReactNode {
  const q = query.trim().toLowerCase()
  const n = q ? g.nodes.find((x) => x.label.toLowerCase().includes(q)) : undefined
  return n ? <span hidden data-skills-match="first" data-skills-id={n.id} /> : null
}

export function SkillsView({ g, now }: { g: SkillGraph | undefined; now: number }): ReactNode {
  const reduce = useReducedMotion() ?? false
  const view = useSkills((s) => s.view)
  const query = useSkills((s) => s.query)
  const selected = useSkills((s) => s.selected)
  const picker = useSkills((s) => s.picker)
  const active = useShell((s) => s.page === 'skills')
  const [ref, width] = useWidth<HTMLDivElement>()

  // Esc: the panel, then the picker, then the search. Only while this page is the one on show.
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

  if (!g || !g.nodes.length) return <div ref={ref}>{g ? <NoSkills /> : null}</div>

  const noGoal = !g.goal
  const canChange = g.source === 'graph' && g.capstones.length > 1
  const open = (id: string): void => select(selected === id ? undefined : id)
  const panel = selected && g.byId[selected] ? selected : undefined

  if (noGoal || picker)
    return (
      <div ref={ref} data-skills-page="picker" className="flex h-full min-h-0 flex-col overflow-y-auto">
        <PageColumn wide top={noGoal ? 64 : 40}>
          <GoalPicker g={g} onPick={chooseGoal} onCancel={noGoal ? undefined : closePicker} />
        </PageColumn>
      </div>
    )

  return (
    <div ref={ref} data-skills-page={view} className="relative flex h-full min-h-0 flex-col">
      <FirstMatch g={g} query={query} />
      <PageColumn wide bottom={8}>
        <GoalHeader g={g} onChange={canChange ? openPicker : undefined} />
      </PageColumn>
      {/* The stage: the view, then the dock; the panel lies over both (the dock fades and keeps its room, so the view never refits). */}
      <div className="relative flex min-h-0 flex-1 flex-col">
        <div className="relative min-h-0 flex-1">
          {view === 'list' ? (
            <ListView g={g} query={query} now={now} onOpen={open} />
          ) : (
            // Remount per view, so each opens fitted and plays what it has to play.
            <TreeCanvas key={view} g={g} view={view} query={query} selected={panel} onOpen={open} />
          )}
        </div>
        <motion.div inert={!!panel} aria-hidden={!!panel || undefined} initial={false} animate={{ opacity: panel ? 0 : 1, y: panel && !reduce ? 6 : 0 }} transition={panel ? fade.out : fade.in}>
          <PageColumn wide top={0} bottom={0}>
            <Dock g={g} width={Math.min(width, WIDE_W) - 2 * layout.page.gutter} onOpen={open} />
          </PageColumn>
        </motion.div>
        <AnimatePresence>{panel && <SkillPanel key={panel} g={g} id={panel} onClose={() => select(undefined)} onOpen={(id) => select(id)} />}</AnimatePresence>
      </div>
    </div>
  )
}
