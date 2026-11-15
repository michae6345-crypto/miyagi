/**
 * The lesson-complete panel (Michael's NEW 2, mockup 10 "Your skills" layout), grown out of the notch island:
 *   header   a green "Lesson complete" chip (the lesson passed), the card's title and body (the real evidence)
 *   left     the skill map (SkillMap.tsx): one track, other tracks' shared ideas above it
 *   right    Up next: the first two lessons of skillMap.next; the primary button starts next[0]
 *            (learn {query: goal, mode: "lesson"}), End lesson sends action end_lesson
 * Everything shown comes from the card; nothing about any one lesson is written here.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { ArrowRight, BookOpen, Check, ChevronRight } from 'lucide-react'
import { useLesson } from '../../core/lesson'
import { CloseButton, Spinner } from '../../core/ui/atoms'
import { color, fill, radius } from '../../core/theme'
import { useOverlayWidth } from '../cards/store'
import { SkillMapView } from './SkillMap'
import { endLesson, startLesson, useComplete } from './store'

const PAD = 24
const GAP = 16
const SIDE = 284
const INNER = 20
/** Below this the Up next column moves under the map. */
const STACK_BELOW = 960
/** Without a skill map: just the header and the buttons. */
const PLAIN_W = 460

/** The panel's width on an overlay this wide (the island keeps 16 px from each edge). */
export function panelWidth(overlay: number, hasMap: boolean): number {
  if (!hasMap) return Math.min(PLAIN_W, overlay - 32)
  return Math.max(560, Math.min(1240, overlay - 32))
}

function Primary({ label, onClick }: { label: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      data-complete-primary
      className="flex h-[38px] w-full cursor-pointer items-center justify-center gap-[8px] rounded-full text-[14px] font-medium"
      style={{ background: color.accent, color: color.onAccent }}
      whileHover={{ filter: 'brightness(0.96)' }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
      <ArrowRight size={14} strokeWidth={1.9} />
    </motion.button>
  )
}

function Quiet({ label, busy, onClick }: { label: string; busy: boolean; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      data-complete-end
      className="flex h-[38px] w-full cursor-pointer items-center justify-center gap-[8px] rounded-full text-[14px] font-medium"
      style={{ background: fill.button, color: color.text }}
      whileHover={{ backgroundColor: fill.chipHover }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {busy && <Spinner size={14} c={color.text} />}
      {label}
    </motion.button>
  )
}

function UpNext(): ReactNode {
  const card = useComplete((s) => s.card)
  const ending = useComplete((s) => s.ending)
  if (!card) return null
  const next = (card.map?.next ?? []).slice(0, 2)
  const endLabel = card.endLabel || 'End lesson'
  return (
    <div data-up-next className="flex h-full flex-col">
      {next.length > 0 && (
        <>
          <div className="mb-[10px] flex items-baseline gap-[8px] text-[11px] font-semibold uppercase tracking-[0.07em]" style={{ color: color.faint }}>
            Up next
            <span className="flex-1" />
            {card.map?.track && <span className="truncate font-normal normal-case tracking-normal">{card.map.track}</span>}
          </div>
          <div className="flex flex-col gap-[8px]">
            {next.map((n, i) => (
              <motion.button
                key={n.goal}
                type="button"
                data-next={i}
                className="flex w-full cursor-pointer items-start gap-[11px] rounded-[14px] p-[11px] text-left"
                style={{ background: i === 0 ? fill.highlight : fill.chip, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}` }}
                whileHover={{ backgroundColor: fill.chipHover }}
                transition={{ duration: 0.12 }}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => startLesson(n.goal)}
                title={n.goal}
              >
                <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[9px]" style={{ background: fill.tile, color: fill.tileGlyph }}>
                  <BookOpen size={15} strokeWidth={1.8} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[14px] font-medium leading-[18px]" style={{ color: color.text }}>
                    {n.title}
                  </span>
                  <span className="mt-[2px] block overflow-hidden text-[12px] leading-[16px]" style={{ color: color.label, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2 }}>
                    {n.goal}
                  </span>
                </span>
                <ChevronRight size={15} strokeWidth={1.8} className="mt-[8px] shrink-0" style={{ color: color.faint }} />
              </motion.button>
            ))}
          </div>
        </>
      )}
      <div className="mt-auto flex flex-col gap-[8px] pt-[16px]">
        {next.length > 0 && <Primary label="Start next lesson" onClick={() => startLesson(next[0].goal)} />}
        <Quiet label={endLabel} busy={ending} onClick={endLesson} />
      </div>
    </div>
  )
}

export function CompletePanel(): ReactNode {
  const card = useComplete((s) => s.card)
  const overlay = useOverlayWidth((s) => s.w)
  const steps = useLesson((s) => s.steps.length)
  if (!card) return null
  const map = card.map
  const w = panelWidth(overlay, !!map)
  const stacked = !map || w < STACK_BELOW
  const mapW = (stacked ? w - 2 * PAD : w - 2 * PAD - GAP - SIDE) - 2 * INNER
  const meta = [steps ? `${steps} steps` : '', map?.track ?? ''].filter(Boolean).join(' · ')
  const box = { background: fill.chip, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}`, borderRadius: radius.card, padding: INNER }

  return (
    <div data-complete="panel" style={{ width: w, padding: `18px ${PAD}px ${PAD}px` }}>
      <div className="flex h-[24px] items-center gap-[10px]">
        <span className="flex items-center gap-[6px] rounded-full px-[9px] py-[3px] text-[12px] font-semibold" style={{ background: color.greenTint, color: color.green }}>
          <Check size={12} strokeWidth={2.6} />
          Lesson complete
        </span>
        {meta && (
          <span className="truncate text-[13px]" style={{ color: color.label }}>
            {meta}
          </span>
        )}
        <span className="flex-1" />
        <CloseButton />
      </div>
      <div className="mt-[10px] text-[24px] font-semibold leading-[30px] tracking-[-0.015em]" style={{ color: color.text }}>
        {card.title}
      </div>
      {card.body && (
        <div className="mt-[4px] max-w-[860px] text-[14px] leading-[20px]" style={{ color: color.label }}>
          {card.body}
        </div>
      )}
      <div className={`mt-[18px] flex ${stacked ? 'flex-col' : 'flex-row items-stretch'}`} style={{ gap: GAP }}>
        {map && (
          <div className="min-w-0 flex-1" style={box}>
            <SkillMapView map={map} width={mapW} />
          </div>
        )}
        <div style={stacked ? undefined : { width: SIDE, flexShrink: 0, ...box }}>
          <UpNext />
        </div>
      </div>
    </div>
  )
}
