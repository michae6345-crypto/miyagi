/**
 * Feature: skills. The goal: the header over every view, and the picker.
 *
 *   GoalHeader  one line, 36 tall (the trees get the height): the project's square, "Your goal", its name, "6 of 11"
 *               and one short bar per skill (green mastered, ink practicing, a faint track for the rest); Change goal
 *               on the right (quiet)
 *   GoalPicker  "What do you want to make first?": one card per project, the chosen one ringed in ink, and the surface's
 *               one primary, "Make this my goal" (set_goal when the engine lists it, kept on this Mac either way).
 *               It is the empty state for a learner with no goal yet, and the sheet Change goal opens (with Cancel).
 */
import { motion, useReducedMotion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import { color, elevation, fill, highlight, radius2, spring, type2, typeScale } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import type { SkillGraph } from './model'
import { CARD_BG } from './SkillNode'

function ProjectSquare({ size = 40, dashed = false }: { size?: number; dashed?: boolean }): ReactNode {
  return (
    <span
      className="relative flex shrink-0 items-center justify-center"
      style={{ width: size, height: size, borderRadius: radius2.card, background: CARD_BG, boxShadow: dashed ? undefined : `${highlight.card}, inset 0 0 0 1px var(--l-border), ${elevation.raised}` }}
    >
      {dashed && (
        <svg width={size} height={size} className="absolute inset-0" aria-hidden>
          <rect x={0.75} y={0.75} width={size - 1.5} height={size - 1.5} rx={radius2.card - 0.75} fill="none" stroke={fill.ring} strokeWidth={1.5} strokeDasharray="3.2 4" />
        </svg>
      )}
      <MiyagiMark size={Math.round(size * 0.6)} />
    </span>
  )
}

/** One short bar per skill on the way: mastered green, practicing ink, the rest a faint track. */
function GoalBar({ mastered, practicing, total }: { mastered: number; practicing: number; total: number }): ReactNode {
  const n = Math.max(1, Math.min(total, 24))
  return (
    <span role="img" aria-label={`${mastered} of ${total} skills mastered`} className="flex items-center" style={{ gap: 3, width: Math.min(n * 16, 220) }}>
      {Array.from({ length: n }, (_, i) => (
        <span key={i} className="block flex-1" style={{ height: 4, borderRadius: radius2.round, background: i < mastered ? color.green : i < mastered + practicing ? color.text : fill.hairline }} />
      ))}
    </span>
  )
}

export function GoalHeader({ g, onChange }: { g: SkillGraph; onChange?: () => void }): ReactNode {
  const goal = g.goal
  if (!goal) return null
  return (
    <div data-skills-goal className="flex w-full items-center" style={{ gap: 12, height: 36 }}>
      <ProjectSquare size={32} dashed={g.byId[goal.id]?.state === 'locked'} />
      <div className="flex min-w-0 flex-1 items-baseline" style={{ gap: 10 }}>
        <span className="shrink-0" style={{ fontSize: type2.sm, fontWeight: 500, color: color.label }}>
          {goal.inferred ? 'Where you’re headed' : 'Your goal'}
        </span>
        <span className="min-w-0 truncate" style={{ ...typeScale.row, fontSize: type2.body, fontWeight: 600, color: color.text }}>
          {goal.label}
        </span>
        <span className="shrink-0" style={{ fontSize: type2.sm, color: color.label, fontVariantNumeric: 'tabular-nums' }}>
          {goal.mastered} of {goal.total}
        </span>
        <span className="flex shrink-0 self-center">
          <GoalBar mastered={goal.mastered} practicing={goal.practicing} total={goal.total} />
        </span>
      </div>
      {onChange && <QuietButton label="Change goal" onClick={onChange} />}
    </div>
  )
}

export function GoalPicker({ g, onPick, onCancel }: { g: SkillGraph; onPick: (id: string) => void; onCancel?: () => void }): ReactNode {
  const reduce = useReducedMotion() ?? false
  const projects = g.capstones.map((c) => ({ c, n: g.byId[c.id] })).filter((p) => !!p.n && p.n.state !== 'mastered')
  const [chosen, setChosen] = useState<string | undefined>(g.goal && !g.goal.inferred ? g.goal.id : undefined)
  const track = (id: string): string => g.tracks.find((t) => t.id === id)?.label ?? ''
  return (
    <motion.div
      data-skills-picker
      className="flex w-full flex-col items-center text-center"
      style={{ gap: 8, maxWidth: 880, margin: '0 auto' }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduce ? { duration: 0.12 } : spring}
    >
      <MiyagiMark size={56} />
      <h2 className="m-0" style={{ ...typeScale.pageTitle, fontSize: 24, marginTop: 12, color: color.text }}>
        {onCancel ? 'Pick your next goal' : 'What do you want to make first?'}
      </h2>
      <p className="m-0" style={{ fontSize: type2.md, color: color.label }}>
        Pick one. Your tree grows from the skills it needs.
      </p>
      <div role="radiogroup" aria-label="Projects" className="grid w-full" style={{ marginTop: 24, gap: 12, gridTemplateColumns: `repeat(auto-fit, minmax(200px, 1fr))` }}>
        {projects.map(({ c, n }) => {
          const on = chosen === c.id
          const need = c.requires.length ? c.requires : n.requires
          const done = need.filter((id) => g.byId[id]?.state === 'mastered').length
          return (
            <motion.button
              key={c.id}
              type="button"
              role="radio"
              aria-checked={on}
              data-skills-pick={c.id}
              className="flex cursor-pointer flex-col items-start text-left"
              style={{
                gap: 12,
                padding: 16,
                borderRadius: radius2.card,
                background: CARD_BG,
                boxShadow: `${highlight.card}, inset 0 0 0 ${on ? 2 : 1}px ${on ? color.text : 'var(--l-border)'}, ${on ? elevation.overlay : elevation.raised}`
              }}
              onClick={() => setChosen(c.id)}
              whileHover={reduce ? undefined : { y: -2 }}
              whileTap={reduce ? undefined : { scale: 0.98 }}
              transition={spring}
            >
              <ProjectSquare size={36} />
              <span className="flex flex-col" style={{ gap: 4 }}>
                <span style={{ fontSize: type2.body, fontWeight: 600, lineHeight: '20px', color: color.text }}>{n.label}</span>
                <span style={{ fontSize: type2.xs, color: color.label, fontVariantNumeric: 'tabular-nums' }}>
                  {[track(c.track), `${need.length} skills`, done ? `${done} mastered` : undefined].filter(Boolean).join(' · ')}
                </span>
              </span>
            </motion.button>
          )
        })}
      </div>
      <div className="flex items-center" style={{ gap: 10, marginTop: 24 }}>
        {onCancel && <QuietButton label="Cancel" size="lg" onClick={onCancel} />}
        <PrimaryButton label="Make this my goal" size="lg" disabled={!chosen} onClick={() => chosen && onPick(chosen)} />
      </div>
    </motion.div>
  )
}
