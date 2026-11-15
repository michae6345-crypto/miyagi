/**
 * The lesson-complete panel, grown out of the notch island. Direction C, "Network":
 *   left    the network the learner trained, drawn from the engine's own weights (Network.tsx), and its loss
 *           from the first to the last frame in large tabular numerals
 *   right   the track as the title, how many skills are mastered, and the skills as a quiet wrap; a click shows
 *           a skill's detail under it. One next action at the bottom right: "Start: <next lesson>", and End lesson.
 * No network (a lesson that isn't a neural net): the right column alone, centered. No skill map: the card's title
 * and body. Every number comes from the engine's card or its network diagrams; a piece without data is left out.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useMemo, useState, type ReactNode } from 'react'
import { CloseButton, CodeText, Spinner } from '../../core/ui/atoms'
import { color, fill } from '../../core/theme'
import { useOverlayWidth, useSeries, type Point } from '../cards/store'
import { NetGraph } from './Network'
import { lossStat, plain, type Net } from './net'
import { endLesson, startLesson, useComplete, type CompleteCard } from './store'
import type { SkillNode } from './types'

const PAD = 40
const COL_GAP = 64
const NET_W = 300
/** Two columns: the network and the skills. */
const WIDE = 960
/** The skills alone (no network), or a card without a map. */
const SINGLE = 600
const PLAIN = 520
/** Below this the network sits above the skills. */
const STACK_BELOW = 760

/** The panel's width on an overlay this wide (the island keeps 16 px from each edge). */
export function panelWidth(overlay: number, hasMap: boolean, hasNet = false): number {
  const room = overlay - 32
  if (!hasMap) return Math.min(PLAIN, room)
  if (!hasNet) return Math.min(SINGLE, room)
  return Math.max(360, Math.min(WIDE, room))
}

const tab = { fontVariantNumeric: 'tabular-nums' } as const

/**
 * What the learner's own run printed (the newest metric series, never the tutorial's run): its first and last point,
 * labelled with the metric's own name. That's the number the terminal, the step card and the write-up show
 * (0.82 → 0.0009), so it wins over the network panel's frames, whose counter runs on past the last printed line.
 */
function printedRun(points: Point[] | undefined, name: string | undefined): { from?: number; to: number; label: string } | undefined {
  if (!points?.length || !name) return undefined
  const a = points[0]
  const b = points[points.length - 1]
  return { ...(points.length > 1 && a.value !== b.value ? { from: a.value } : {}), to: b.value, label: `Your run's ${name}` }
}

/** The network and its loss, e.g. "0.82 → 0.0009" over "Your run's loss". */
function NetworkColumn({ net, trained, w }: { net: Net; trained?: Net; w: number }): ReactNode {
  const { name, series } = useSeries()
  const loss = useMemo(() => {
    const printed = printedRun(series?.run.points, name)
    if (printed) return printed
    const s = lossStat(trained?.frames ?? []) ?? lossStat(net.frames)
    return s && { ...s, label: s.epochs ? `Loss over ${s.epochs.toLocaleString('en-US')} epochs` : 'Loss' }
  }, [series, name, trained, net])
  return (
    <div className="flex h-full flex-col" data-your-network>
      <NetGraph net={net} w={w} />
      {loss && (
        <div className="mt-auto pt-[32px]" data-complete-loss>
          <div className="flex items-baseline gap-[10px] text-[28px] font-medium leading-[32px] tracking-[-0.02em]" style={tab}>
            {loss.from !== undefined && (
              <>
                <span style={{ color: color.label }}>{plain(loss.from)}</span>
                <span className="text-[20px]" style={{ color: color.faint }}>
                  →
                </span>
              </>
            )}
            <span style={{ color: color.text }}>{plain(loss.to)}</span>
          </div>
          <div className="mt-[6px] text-[13px] leading-[18px]" style={{ color: color.faint, ...tab }}>
            {loss.label}
          </div>
        </div>
      )}
    </div>
  )
}

/** One skill: a quiet fill when mastered; "learning" (typed for the learner) is fainter with no fill. */
function Skill({ node, on, onClick }: { node: SkillNode; on: boolean; onClick: () => void }): ReactNode {
  const learning = node.state === 'learning'
  const rest = learning ? fill.clear : fill.chip
  return (
    <motion.button
      type="button"
      data-skill={node.id}
      data-skill-state={node.state}
      aria-pressed={on}
      className="h-[32px] cursor-pointer whitespace-nowrap rounded-full px-[14px] text-[14px] leading-[32px]"
      style={{ color: on ? color.text : learning ? color.faint : fill.chipText, boxShadow: learning ? `inset 0 0 0 1px ${fill.chipBorder}` : undefined }}
      initial={false}
      animate={{ backgroundColor: on ? fill.chipHover : rest }}
      whileHover={{ backgroundColor: fill.chipHover }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {node.label}
    </motion.button>
  )
}

function Actions({ card, align }: { card: CompleteCard; align: 'end' | 'center' }): ReactNode {
  const ending = useComplete((s) => s.ending)
  const next = card.map?.next[0]
  const endLabel = card.endLabel || 'End lesson'
  return (
    <div className={`flex items-center gap-[24px] ${align === 'end' ? 'justify-end' : 'justify-center'}`}>
      <button
        type="button"
        data-complete-end
        className={`flex h-[36px] cursor-pointer items-center gap-[8px] rounded-full text-[14px] font-medium ${next ? 'transition-colors hover:text-white' : 'px-[18px]'}`}
        style={next ? { color: color.label } : { background: color.accent, color: color.onAccent }}
        onMouseDown={(e) => e.preventDefault()}
        onClick={endLesson}
      >
        {ending && <Spinner size={14} c={next ? color.text : color.onAccent} track={next ? fill.trackSoft : fill.onAccentKey} />}
        {endLabel}
      </button>
      {next && (
        <motion.button
          type="button"
          data-complete-primary
          className="flex h-[36px] min-w-0 cursor-pointer items-center rounded-full px-[18px] text-[14px] font-medium"
          style={{ background: color.accent, color: color.onAccent, maxWidth: 380 }}
          whileHover={{ filter: 'brightness(0.94)' }}
          whileTap={{ scale: 0.98 }}
          transition={{ duration: 0.12 }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => startLesson(next.goal)}
          title={next.goal}
        >
          <span className="truncate">Start: {next.title}</span>
        </motion.button>
      )}
    </div>
  )
}

/** The track, its mastered count, the skills and the selected one's detail. */
function Skills({ card, center }: { card: CompleteCard; center: boolean }): ReactNode {
  const map = card.map!
  const [picked, setPicked] = useState<string>()
  const skills = map.nodes.filter((n) => n.state !== 'next')
  const mastered = skills.filter((n) => n.state === 'mastered').length
  const detail = skills.find((n) => n.id === picked)?.detail
  return (
    <div className={center ? 'text-center' : undefined}>
      <div className="text-[28px] font-semibold leading-[34px] tracking-[-0.02em]" style={{ color: color.text }} data-complete-head>
        {map.track || card.title}
      </div>
      {/* The engine's body ("6 of 7 steps, 1 skipped", the result) when it sends one; the mastered count only
          without it, since it overclaims a skipped step (Michael, test 10). */}
      {card.body ? (
        <div className="mt-[6px] text-[15px] leading-[21px]" style={{ color: color.label, ...tab }}>
          <CodeText text={card.body} />
        </div>
      ) : (
        mastered > 0 && (
          <div className="mt-[6px] text-[15px] leading-[20px]" style={{ color: color.label, ...tab }}>
            {mastered} skill{mastered === 1 ? '' : 's'} mastered
          </div>
        )
      )}
      {skills.length > 0 && (
        <div className={`mt-[24px] flex flex-wrap gap-[8px] ${center ? 'justify-center' : ''}`} data-skills>
          {skills.map((n) => (
            <Skill key={n.id} node={n} on={picked === n.id} onClick={() => setPicked((p) => (p === n.id ? undefined : n.id))} />
          ))}
        </div>
      )}
      <div className="relative mt-[14px] min-h-[20px] text-[13px] leading-[20px]" style={{ color: color.label }} data-skill-detail>
        <AnimatePresence initial={false} mode="wait">
          {detail && (
            <motion.div key={picked} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
              <CodeText text={detail} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

export function CompletePanel(): ReactNode {
  const card = useComplete((s) => s.card)
  const net = useComplete((s) => s.net)
  const trained = useComplete((s) => s.trained)
  const overlay = useOverlayWidth((s) => s.w)
  if (!card) return null
  const map = card.map
  const shown = map ? net : undefined
  const w = panelWidth(overlay, !!map, !!shown)
  const close = (
    <div className="absolute right-[16px] top-[16px]">
      <CloseButton />
    </div>
  )

  // No skill map: the card's own title and body.
  if (!map)
    return (
      <div data-complete="panel" className="relative text-center" style={{ width: w, padding: `${PAD}px ${PAD - 8}px 28px` }}>
        {close}
        <div className="text-[20px] font-semibold leading-[26px] tracking-[-0.01em]" style={{ color: color.text }} data-complete-head>
          {card.title}
        </div>
        {card.body && (
          <div className="mx-auto mt-[8px] max-w-[400px] text-[15px] leading-[21px]" style={{ color: color.label }}>
            <CodeText text={card.body} />
          </div>
        )}
        <div className="mt-[28px]">
          <Actions card={card} align="center" />
        </div>
      </div>
    )

  // A map but no network: the skills alone, centered.
  if (!shown)
    return (
      <div data-complete="panel" className="relative" style={{ width: w, padding: `${PAD}px ${PAD - 8}px 28px` }}>
        {close}
        <Skills card={card} center />
        <div className="mt-[18px]">
          <Actions card={card} align="center" />
        </div>
      </div>
    )

  const stacked = w < STACK_BELOW
  const netW = stacked ? Math.min(NET_W, w - 2 * PAD) : NET_W
  return (
    <div data-complete="panel" className="relative" style={{ width: w, padding: `${PAD}px ${PAD}px 32px` }}>
      {close}
      <div className={stacked ? 'flex flex-col gap-[32px]' : 'flex items-stretch'} style={stacked ? undefined : { gap: COL_GAP }}>
        <div className="shrink-0" style={{ width: netW }}>
          <NetworkColumn net={shown} trained={trained} w={netW} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <Skills card={card} center={false} />
          <div className="mt-auto pt-[18px]">
            <Actions card={card} align="end" />
          </div>
        </div>
      </div>
    </div>
  )
}
