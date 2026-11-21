/**
 * Feature: building. Home-Building: the build card that grows out of the island while a lesson builds.
 *
 *   top line   the pill's own words, a gray dot and "Building lesson", so the card reads as the pill grown
 *   source     what it is built from (lesson.building source): the video's thumbnail, or a quiet tile for a goal or a
 *              library lesson; "From YouTube" / "From your goal" / "From your library", the title, channel and length
 *   phases     Watching the video · Finding the steps · Writing the checks · Ready to start (lesson.building phases).
 *              done = a white tick in a faint ring (white, never green: nothing has passed yet), active = the gray
 *              ring with a still gray dot (decision 5: never a spinner; only a check in flight moves), next = a faint empty ring. Details on the right.
 *              No phases (a stage alone): one active row with the stage's message.
 *   meter      a white line at lesson.building progress, "Usually a few minutes. Only built once." and about how long
 *              is left (etaS). Never invents a number: no etaS, no time.
 *   footer     "The pill tells you when it is ready." Stop building (quiet, two taps) and Keep working (the one primary).
 *
 * Island card: black like every card born from the pill; neutral fills only (core/theme.ts), no hue anywhere.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { BookOpen, Check, Play } from 'lucide-react'
import type { Payload } from '../../../../common/wire'
import { useLesson } from '../../core/lesson'
import { MiyagiMark } from '../../core/ui/Mark'
import { Thumb } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { color, fill, radius2, spring, status, type2 } from '../../core/theme'
import { parseYouTube, thumbnailFor } from '../launcher/youtube'
import { keepWorking, tapStop, useBuildCard } from './store'

export const CARD_W = 560
const PAD = 28

type Build = Payload<'lesson.building'>
type Phase = NonNullable<Build['phases']>[number]
type Source = NonNullable<Build['source']>

const FROM: Record<Source['kind'], string> = { youtube: 'From YouTube', goal: 'From your goal', library: 'From your library' }

/** "24 min", "1 h 5 min"; under a minute, nothing (a length that rounds to 0 says nothing). */
export function lengthLabel(s?: number): string | undefined {
  if (!s || s < 60) return
  const m = Math.round(s / 60)
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`
}

/** About how long is left, from etaS. No etaS: nothing (never a guess). */
export function etaLabel(etaS?: number): string | undefined {
  if (etaS === undefined || !Number.isFinite(etaS) || etaS < 0) return
  if (etaS < 60) return 'Less than a minute left'
  const m = Math.ceil(etaS / 60)
  return m === 1 ? 'About 1 min left' : `About ${m} min left`
}

export function BuildCard(): ReactNode {
  const b = useLesson(
    useShallow((s) => ({
      build: s.build,
      message: s.buildingMessage,
      progress: s.buildingProgress
    }))
  )
  const armed = useBuildCard((s) => s.armed)
  const source = b.build?.source
  const phases: Phase[] = b.build?.phases?.length
    ? b.build.phases
    : b.message
      ? [{ id: b.build?.stage ?? 'watching', label: b.message, state: 'active' }]
      : []
  const progress = Math.min(1, Math.max(0, b.progress ?? 0))
  const eta = etaLabel(b.build?.etaS)
  return (
    <div data-build-card style={{ padding: `16px ${PAD}px ${PAD - 4}px` }}>
      <div className="flex items-center justify-center gap-[8px]" style={{ fontSize: type2.xs, color: color.label }}>
        <span className="h-[8px] w-[8px] rounded-full" style={{ background: status.watching }} />
        Building lesson
      </div>

      {source && <SourceHeader source={source} />}

      <ol className="mt-[16px] flex flex-col" aria-label="Build progress">
        {phases.map((p, i) => (
          <PhaseRow key={p.id} phase={p} last={i === phases.length - 1} />
        ))}
      </ol>

      <div className="mt-[16px] flex flex-col gap-[8px]">
        <div className="h-[4px] overflow-hidden rounded-full" style={{ background: fill.hairline }} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
          <motion.div
            className="h-full w-full rounded-full"
            style={{ background: color.text, transformOrigin: '0% 50%' }}
            initial={false}
            animate={{ scaleX: progress }}
            transition={spring}
          />
        </div>
        <div className="flex justify-between gap-[12px]" style={{ fontSize: type2.xs, color: color.label }}>
          <span>Usually a few minutes. Only built once.</span>
          {eta && <span className="shrink-0 tabular-nums">{eta}</span>}
        </div>
      </div>

      <div className="mt-[20px] flex items-center justify-between gap-[16px]">
        <span className="min-w-0" style={{ fontSize: type2.sm, color: color.label }}>
          The pill tells you when it is ready.
        </span>
        <div className="flex shrink-0 gap-[8px]">
          <QuietButton
            size="lg"
            label={armed ? 'Tap again to stop' : 'Stop building'}
            title={armed ? 'Click again to stop building this lesson' : 'Stop building this lesson'}
            onClick={tapStop}
          />
          <PrimaryButton size="lg" label="Keep working" onClick={keepWorking} />
        </div>
      </div>
    </div>
  )
}

function SourceHeader({ source }: { source: Source }): ReactNode {
  const link = source.kind === 'youtube' && source.url ? parseYouTube(source.url) : null
  const meta = [source.channel, lengthLabel(source.durationS)].filter(Boolean).join(' · ')
  return (
    <div className="mt-[16px] flex items-center gap-[16px]">
      {link ? (
        <Thumb w={96} h={56} src={thumbnailFor(link.videoId)} />
      ) : (
        <span
          className="grid h-[56px] w-[96px] shrink-0 place-items-center"
          style={{ borderRadius: radius2.row, background: fill.tile, boxShadow: `inset 0 0 0 1px ${fill.hairline}`, color: color.text }}
        >
          {source.kind === 'goal' ? <MiyagiMark size={20} /> : source.kind === 'library' ? <BookOpen size={18} strokeWidth={1.8} /> : <Play size={18} strokeWidth={1.8} />}
        </span>
      )}
      <div className="min-w-0">
        <div style={{ fontSize: type2.xs, color: color.label }}>{FROM[source.kind] ?? 'Your lesson'}</div>
        <div className="mt-[4px] line-clamp-2 font-semibold" style={{ fontSize: 16, lineHeight: 1.3 }}>
          {source.title}
        </div>
        {meta && <div className="mt-[4px] truncate" style={{ fontSize: type2.xs, color: color.label }}>{meta}</div>}
      </div>
    </div>
  )
}

function PhaseRow({ phase, last }: { phase: Phase; last: boolean }): ReactNode {
  const active = phase.state === 'active'
  const done = phase.state === 'done'
  const detail = phase.detail ?? (done ? 'Done' : undefined)
  return (
    <li
      data-phase={phase.id}
      data-state={phase.state}
      className="flex h-[48px] items-center gap-[16px]"
      style={{ borderBottom: last ? undefined : `1px solid ${fill.hairline}` }}
    >
      <PhaseGlyph state={phase.state} />
      <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.md, fontWeight: active ? 500 : 400, color: phase.state === 'next' ? color.label : color.text }}>
        {phase.label}
      </span>
      {detail && (
        <span className="shrink-0 tabular-nums" style={{ fontSize: type2.xs, color: active ? fill.keycapText : color.label }}>
          {detail}
        </span>
      )}
    </li>
  )
}

/** 24 px. done: white tick in a faint ring (never green). active: the gray ring and dot. next: a faint ring. */
function PhaseGlyph({ state }: { state: Phase['state'] }): ReactNode {
  if (state === 'done')
    return (
      <span className="grid h-[24px] w-[24px] shrink-0 place-items-center rounded-full" style={{ boxShadow: `inset 0 0 0 1px ${fill.ring}`, color: color.text }}>
        <Check size={12} strokeWidth={3} />
      </span>
    )
  if (state === 'active')
    return (
      <span className="grid h-[24px] w-[24px] shrink-0 place-items-center rounded-full" style={{ boxShadow: `inset 0 0 0 2px ${status.watching}` }}>
        <span className="h-[8px] w-[8px] rounded-full" style={{ background: status.watching }} />
      </span>
    )
  return <span className="h-[24px] w-[24px] shrink-0 rounded-full" style={{ boxShadow: `inset 0 0 0 1px ${fill.ring}` }} />
}
