/**
 * Feature: skills. The skill panel: opens from any node (tree or list), over the right of the view. Esc or × closes it.
 *
 *   top        track · where it stands, the name, one line on what it is
 *   example    what you'll be able to write (the engine's example), in a well
 *   progress   the steps behind it so far ("2 of 4 steps")
 *   needs      for a locked skill: what it still needs, each one opens its own panel
 *   learned in the lessons that build it (the one in progress first)
 *   opens      what it unlocks
 *   project    for a capstone: the brief, the checks, the time, the starter file
 *   action     the panel's one primary: Continue / Start (its saved lesson, else a lesson built for it), Start project;
 *              a project that isn't the goal offers "Make this my goal" (quiet)
 */
import { motion, useReducedMotion } from 'motion/react'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { color, elevation, fill, font, highlight, radius2, spring, surface, type2, typeScale } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { pressMotion } from '../../core/ui/motion'
import { useDash } from '../dashboard/store'
import { StepBar } from '../shell/ui'
import type { SkillGraph, SkillGraphNode } from './model'
import { names, stateWord } from './copy'
import { Glyph } from './SkillNode'
import { chooseGoal, startProject, startSkill } from './store'

const sectionLabel = { fontSize: type2.xs, fontWeight: 600, color: color.label, margin: 0 } as const

function Section({ title, children }: { title: string; children: ReactNode }): ReactNode {
  return (
    <section className="flex flex-col" style={{ gap: 8 }}>
      <h3 style={sectionLabel}>{title}</h3>
      {children}
    </section>
  )
}

function SkillLink({ n, onOpen }: { n: SkillGraphNode; onOpen: (id: string) => void }): ReactNode {
  return (
    <button
      type="button"
      className="mg-press flex cursor-pointer items-center gap-[8px] text-left"
      style={{ height: 30, padding: '0 10px 0 6px', borderRadius: radius2.control, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, fontSize: type2.sm, color: n.state === 'locked' ? color.label : color.text }}
      onClick={() => onOpen(n.id)}
    >
      <Glyph n={n} size={16} />
      {n.label}
    </button>
  )
}

export function SkillPanel({ g, id, onClose, onOpen }: { g: SkillGraph; id: string; onClose: () => void; onOpen: (id: string) => void }): ReactNode {
  const reduce = useReducedMotion() ?? false
  const starting = useDash((s) => s.starting)
  const startError = useDash((s) => s.startError?.text)
  const n = g.byId[id]
  if (!n) return null
  const track = g.tracks.find((t) => t.id === n.track)
  const cap = n.kind === 'capstone' ? g.capstones.find((c) => c.id === n.id) : undefined
  const opens = g.links.filter((l) => l.from === n.id).map((l) => g.byId[l.to]).filter((x): x is SkillGraphNode => !!x)
  const needs = n.needs.map((x) => g.byId[x]).filter((x): x is SkillGraphNode => !!x)
  const lessons = [...n.lessons].sort((a, b) => Number(b.inProgress) - Number(a.inProgress))
  const pick = g.next?.skillId === n.id ? g.next : undefined
  const lib = pick?.libraryId ?? lessons.find((l) => l.libraryId && l.role !== 'uses')?.libraryId
  const startable = n.kind === 'skill' && (n.state === 'ready' || n.state === 'practicing')
  const projectReady = n.kind === 'capstone' && n.state === 'ready'
  const primary = startable
    ? { label: n.state === 'practicing' ? (pick?.stepIndex !== undefined ? `Continue step ${pick.stepIndex + 1}` : 'Continue') : 'Start', run: () => startSkill(n, g) }
    : projectReady
      ? { label: 'Start project', run: () => startProject(n.id, g) }
      : undefined
  const head = n.kind === 'capstone' ? (n.isGoal ? 'Your goal' : 'Project') : stateWord(n)
  return (
    <motion.aside
      data-skills-panel={n.id}
      aria-label={n.label}
      className="absolute flex flex-col overflow-hidden"
      style={{
        right: 16,
        top: 0,
        bottom: 16,
        width: 'min(380px, calc(100% - 32px))',
        zIndex: 10,
        borderRadius: radius2.panel,
        background: 'var(--l-overlay)',
        boxShadow: `${highlight.top}, inset 0 0 0 1px var(--l-border), ${elevation.panel}`
      }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={reduce ? { opacity: 0 } : { opacity: 0, x: 16 }}
      transition={reduce ? { duration: 0.12 } : spring}
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto" style={{ padding: '20px 24px 16px', gap: 20, scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
        <div className="flex flex-col" style={{ gap: 6 }}>
          <div className="flex items-center gap-[8px]">
            <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.xs, color: color.label }}>
              {[track?.label, head].filter(Boolean).join(' · ')}
            </span>
            <motion.button type="button" aria-label="Close" title="Close" className="mg-press flex shrink-0 cursor-pointer items-center justify-center" style={{ width: 28, height: 28, borderRadius: radius2.control, color: color.label, marginRight: -6 }} onClick={onClose} {...pressMotion()}>
              <X size={15} strokeWidth={1.8} />
            </motion.button>
          </div>
          <h2 className="m-0" style={{ ...typeScale.pageTitle, fontSize: 22, lineHeight: '28px', color: color.text }}>
            {n.label}
          </h2>
          {(cap?.brief ?? n.summary) && <p className="m-0" style={{ fontSize: type2.md, lineHeight: '20px', color: color.label }}>{cap?.brief ?? n.summary}</p>}
        </div>

        {n.example?.code && (
          <Section title="You’ll be able to">
            <pre className="m-0 overflow-x-auto" style={{ padding: '10px 12px', borderRadius: radius2.row, background: surface.well, boxShadow: highlight.well, fontFamily: font.mono, fontSize: type2.sm, color: color.text, whiteSpace: 'pre-wrap' }}>
              {n.example.code}
            </pre>
            {n.example.caption && <span style={{ fontSize: type2.sm, color: color.label }}>{n.example.caption}</span>}
          </Section>
        )}

        {n.evidence && n.kind === 'skill' && n.state !== 'mastered' && (
          <Section title="Steps">
            <div className="flex items-center gap-[12px]">
              <StepBar done={n.evidence.done} total={n.evidence.total} width={160} label={`${n.evidence.done} of ${n.evidence.total} steps`} />
              <span style={{ fontSize: type2.sm, color: color.label, fontVariantNumeric: 'tabular-nums' }}>
                {n.evidence.done} of {n.evidence.total} steps
              </span>
            </div>
          </Section>
        )}

        {cap && (cap.checks.length > 0 || cap.estMinutes || cap.starterFile) && (
          <Section title="The project">
            <ul className="m-0 flex list-none flex-col p-0" style={{ gap: 6 }}>
              {cap.checks.map((c) => (
                <li key={c} className="flex items-center gap-[8px]" style={{ fontSize: type2.sm, color: color.text }}>
                  <Glyph n={{ state: n.state === 'mastered' ? 'mastered' : 'ready', review: false }} size={16} />
                  {c}
                </li>
              ))}
            </ul>
            <span style={{ fontSize: type2.xs, color: color.label }}>{[cap.estMinutes ? `About ${cap.estMinutes} min` : undefined, cap.starterFile].filter(Boolean).join(' · ')}</span>
          </Section>
        )}

        {needs.length > 0 && (
          <Section title={n.kind === 'capstone' ? 'Skills to go' : 'Needs first'}>
            <div className="flex flex-wrap gap-[6px]">
              {needs.map((x) => (
                <SkillLink key={x.id} n={x} onOpen={onOpen} />
              ))}
            </div>
          </Section>
        )}

        {lessons.length > 0 && (
          <Section title="Learned in">
            <ul className="m-0 flex list-none flex-col p-0">
              {lessons.map((l, i) => (
                <li key={l.lessonId} className="flex flex-col py-[8px]" style={i ? { borderTop: `1px solid ${fill.hairline}` } : undefined}>
                  <span style={{ fontSize: type2.md, fontWeight: 500, color: color.text }}>{l.title ?? 'A lesson'}</span>
                  <span style={{ fontSize: type2.xs, color: color.label }}>{l.inProgress ? 'In progress' : l.role === 'uses' ? 'Uses it' : l.role === 'practices' ? 'Practices it' : 'Teaches it'}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {opens.length > 0 && (
          <Section title="Opens">
            <div className="flex flex-wrap gap-[6px]">
              {opens.map((x) => (
                <SkillLink key={x.id} n={x} onOpen={onOpen} />
              ))}
            </div>
          </Section>
        )}
      </div>

      <div className="flex shrink-0 flex-col" style={{ padding: '12px 24px 20px', gap: 10, borderTop: `1px solid ${fill.hairline}` }}>
        {primary ? (
          <PrimaryButton label={primary.label} size="lg" block busy={!!starting && starting === lib} onClick={primary.run} />
        ) : (
          <span style={{ fontSize: type2.sm, color: color.label }}>
            {n.state === 'mastered' ? (n.review ? 'Due for a short review.' : 'Mastered. It stays yours.') : needs.length ? `Needs ${names(needs.map((x) => x.id), g)} first.` : 'Not open yet.'}
          </span>
        )}
        {n.kind === 'capstone' && !n.isGoal && n.state !== 'mastered' && <QuietButton label="Make this my goal" block onClick={() => chooseGoal(n.id)} />}
        {startError && (
          <span role="status" style={{ fontSize: type2.xs, color: color.label }}>
            {startError}
          </span>
        )}
      </div>
    </motion.aside>
  )
}
