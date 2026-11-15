/**
 * The lesson-complete panel (Michael's NEW 2, mockup 12 "Lesson complete"), grown out of the notch island:
 *   header   a green check tile and a "Lesson complete" chip (the lesson passed), the card's title and body (the real
 *            evidence), a meta line (Just teach me · track · steps done · minutes), and on the right the lesson's
 *            own network as it last came from the engine ("Your network 1-4-4-1 · loss …" and a thumbnail)
 *   left     the skill map (SkillMap.tsx); under it, when the data has them: the loss over training, the trained
 *            network's fit against the lesson's targets, and the checks this lesson passed
 *   right    Up next: the first two lessons of skillMap.next; "Start: <first>" sends learn {query: goal,
 *            mode: "lesson"}, End lesson sends action end_lesson
 * Every number comes from the engine's card, its diagrams or the checks it sent; a piece without data is left out.
 */
import { motion } from 'motion/react'
import { useMemo, type ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, Check, ChevronRight, LogOut } from 'lucide-react'
import { useLesson } from '../../core/lesson'
import { CloseButton, Spinner } from '../../core/ui/atoms'
import { color, fill, font, radius } from '../../core/theme'
import { useOverlayWidth } from '../cards/store'
import { FitChart, LossChart, NetThumb } from './Charts'
import { fitCurve, lossSeries, short } from './net'
import { SkillMapView } from './SkillMap'
import { endLesson, startLesson, useComplete } from './store'

const PAD = 24
const GAP = 16
const SIDE = 300
const INNER = 20
/** Below this the Up next column moves under the map. */
const STACK_BELOW = 960
/** Without a skill map: just the header and the buttons. */
const PLAIN_W = 520
const CHECKS_SHOWN = 3

/** The panel's width on an overlay this wide (the island keeps 16 px from each edge). */
export function panelWidth(overlay: number, hasMap: boolean): number {
  if (!hasMap) return Math.min(PLAIN_W, overlay - 32)
  return Math.max(560, Math.min(1260, overlay - 32))
}

const caps = 'text-[11px] font-semibold uppercase tracking-[0.07em]'

function Primary({ label, onClick }: { label: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      data-complete-primary
      className="flex h-[40px] w-full cursor-pointer items-center justify-center rounded-full px-[16px] text-[14px] font-medium"
      style={{ background: color.accent, color: color.onAccent }}
      whileHover={{ filter: 'brightness(0.96)' }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      title={label}
    >
      <span className="truncate">{label}</span>
    </motion.button>
  )
}

function Quiet({ label, busy, onClick }: { label: string; busy: boolean; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      data-complete-end
      className="flex h-[40px] w-full cursor-pointer items-center justify-center gap-[8px] rounded-full text-[14px] font-medium"
      style={{ background: fill.button, color: color.text }}
      whileHover={{ backgroundColor: fill.chipHover }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {busy ? <Spinner size={14} c={color.text} /> : <LogOut size={14} strokeWidth={1.8} />}
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
          <div className={`mb-[12px] flex items-baseline gap-[8px] ${caps}`} style={{ color: color.faint }}>
            Up next
            <span className="flex-1" />
            <span className="font-normal normal-case tracking-normal">
              {next.length} lesson{next.length === 1 ? '' : 's'}
            </span>
          </div>
          <div className="flex flex-col gap-[8px]">
            {next.map((n, i) => (
              <motion.button
                key={n.goal}
                type="button"
                data-next={i}
                className="flex w-full cursor-pointer items-start gap-[12px] rounded-[14px] p-[12px] text-left"
                style={i === 0 ? { background: fill.highlight, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}` } : { background: fill.clear }}
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
                  {i === 0 && (
                    <span className={`mb-[3px] block ${caps}`} style={{ color: color.faint }}>
                      Recommended
                    </span>
                  )}
                  <span className="block text-[14px] font-medium leading-[19px]" style={{ color: color.text }}>
                    {n.title}
                  </span>
                  <span className="mt-[3px] block overflow-hidden text-[12.5px] leading-[17px]" style={{ color: color.label, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 3 }}>
                    {n.goal}
                  </span>
                </span>
                <ChevronRight size={15} strokeWidth={1.8} className="mt-[6px] shrink-0" style={{ color: color.faint }} />
              </motion.button>
            ))}
          </div>
        </>
      )}
      <div className="mt-auto flex flex-col gap-[8px] pt-[18px]">
        {next.length > 0 && <Primary label={`Start: ${next[0].title}`} onClick={() => startLesson(next[0].goal)} />}
        <Quiet label={endLabel} busy={ending} onClick={endLesson} />
      </div>
    </div>
  )
}

/** "Just teach me · Machine learning · 6 of 6 steps · 41 min": only what's known. */
function useMeta(track?: string): string {
  const l = useLesson(useShallow((s) => ({ mode: s.lesson?.mode, total: s.steps.length, passed: s.passed, skipped: s.skipped })))
  const startedAt = useComplete((s) => s.startedAt)
  const cardAt = useComplete((s) => s.card) // re-read the minutes when the card comes
  return useMemo(() => {
    const done = l.passed.filter((id) => !l.skipped.includes(id)).length
    const mins = startedAt ? Math.round((Date.now() - startedAt) / 60000) : 0
    return [l.mode === 'lesson' ? 'Just teach me' : '', track ?? '', l.total ? `${Math.min(done, l.total)} of ${l.total} steps` : '', mins >= 1 ? `${mins} min` : '']
      .filter(Boolean)
      .join(' · ')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [l, startedAt, track, cardAt])
}

function Header(): ReactNode {
  const card = useComplete((s) => s.card)!
  const net = useComplete((s) => s.net)
  const meta = useMeta(card.map?.track)
  const last = net?.frames[net.frames.length - 1]
  return (
    <div className="flex items-start gap-[16px]">
      <span className="grid h-[52px] w-[52px] shrink-0 place-items-center rounded-[16px]" style={{ background: color.greenTint, boxShadow: `inset 0 0 0 1px ${color.green}` }}>
        <Check size={26} strokeWidth={2.4} style={{ color: color.green }} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-[12px] gap-y-[4px]">
          <span className="text-[26px] font-semibold leading-[32px] tracking-[-0.02em]" style={{ color: color.text }}>
            {card.title}
          </span>
          <span className="flex items-center gap-[5px] rounded-full px-[9px] py-[3px] text-[12px] font-semibold" style={{ background: color.greenTint, color: color.green }}>
            <Check size={12} strokeWidth={2.6} />
            Lesson complete
          </span>
        </div>
        {card.body && (
          <div className="mt-[4px] text-[15px] leading-[21px]" style={{ color: color.label }}>
            {card.body}
          </div>
        )}
        {meta && (
          <div className="mt-[4px] text-[13px] leading-[18px]" style={{ color: color.faint }}>
            {meta}
          </div>
        )}
      </div>
      {net && last && (
        <div className="flex shrink-0 items-center gap-[14px]" data-your-network>
          <div className="text-right text-[13px] leading-[19px]">
            <div style={{ color: color.label }}>Your network</div>
            <div style={{ color: color.faint, fontFamily: font.mono }}>
              {net.layers.join('-')}
              {last.loss !== undefined && ` · loss ${short(last.loss)}`}
            </div>
          </div>
          <div className="overflow-hidden rounded-[14px]" style={{ background: fill.field, boxShadow: `inset 0 0 0 1px ${fill.fieldBorder}` }}>
            <NetThumb net={net} />
          </div>
        </div>
      )}
      <CloseButton />
    </div>
  )
}

/** Mockup 12's bottom row: loss, fit, checks passed. Only the pieces the data backs. */
function Evidence({ width }: { width: number }): ReactNode {
  const net = useComplete((s) => s.net)
  const trained = useComplete((s) => s.trained)
  const checks = useComplete((s) => s.checks)
  const pts = useMemo(() => lossSeries(trained), [trained])
  const fit = useMemo(() => fitCurve(net) ?? fitCurve(trained), [net, trained])
  const passed = useMemo(() => Object.values(checks).sort((a, b) => a.at - b.at), [checks])
  const parts = [pts ? 'loss' : '', fit ? 'fit' : '', passed.length ? 'checks' : ''].filter(Boolean)
  if (!parts.length) return null
  const gap = 20
  const colW = Math.floor((width - gap * (parts.length - 1)) / parts.length)
  const head = (left: string, right?: string): ReactNode => (
    <div className={`mb-[8px] flex items-baseline gap-[8px] ${caps}`} style={{ color: color.faint }}>
      {left}
      <span className="flex-1" />
      {right && <span className="font-normal normal-case tracking-normal">{right}</span>}
    </div>
  )
  return (
    <div className="mt-[14px] flex border-t pt-[12px]" style={{ borderColor: fill.rule, gap }} data-complete-evidence>
      {pts && (
        <div style={{ width: colW }}>
          {head('Loss', 'log scale')}
          <LossChart pts={pts} w={colW} />
        </div>
      )}
      {fit && (
        <div style={{ width: colW }}>
          {head('Fit', `max error ${short(fit.maxError)}`)}
          <FitChart fit={fit} w={colW} />
        </div>
      )}
      {passed.length > 0 && (
        <div style={{ width: colW }} data-checks-passed>
          {head('Checks you passed', `${passed.length} check${passed.length === 1 ? '' : 's'}`)}
          <div className="flex flex-col gap-[7px]">
            {passed.slice(-CHECKS_SHOWN).map((c) => (
              <div key={`${c.stepId}:${c.label}`} className="flex items-center gap-[9px] text-[13px] leading-[17px]" style={{ color: color.text }}>
                <span className="grid h-[16px] w-[16px] shrink-0 place-items-center rounded-full" style={{ background: color.green }}>
                  <Check size={10} strokeWidth={3} style={{ color: color.onAccent }} />
                </span>
                <span className="truncate">{c.label}</span>
              </div>
            ))}
            {passed.length > CHECKS_SHOWN && (
              <div className="pl-[25px] text-[12px]" style={{ color: color.faint }}>
                and {passed.length - CHECKS_SHOWN} more
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function CompletePanel(): ReactNode {
  const card = useComplete((s) => s.card)
  const overlay = useOverlayWidth((s) => s.w)
  if (!card) return null
  const map = card.map
  const w = panelWidth(overlay, !!map)
  const stacked = !map || w < STACK_BELOW
  const mapW = (stacked ? w - 2 * PAD : w - 2 * PAD - GAP - SIDE) - 2 * INNER
  const box = { background: fill.chip, boxShadow: `inset 0 0 0 1px ${fill.chipBorder}`, borderRadius: radius.card, padding: INNER }

  return (
    <div data-complete="panel" style={{ width: w, padding: `16px ${PAD}px 20px` }}>
      <Header />
      <div className={`mt-[16px] flex ${stacked ? 'flex-col' : 'flex-row items-stretch'}`} style={{ gap: GAP }}>
        {map && (
          <div className="min-w-0 flex-1" style={box}>
            <SkillMapView map={map} width={mapW} />
            <Evidence width={mapW} />
          </div>
        )}
        <div style={stacked ? undefined : { width: SIDE, flexShrink: 0, ...box }}>
          <UpNext />
        </div>
      </div>
    </div>
  )
}
