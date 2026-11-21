/**
 * Prog-Progress-Window: the Progress app window (route `progress`, kind 'app', 1100x760; core/surfaces openProgress()).
 *
 *   left   Skills: one group per track with "N of M mastered" and every skill's state (Mastered green, Practicing
 *          white 55%, Not started a bare track). No percentages: the engine counts states, not fractions, so each bar
 *          is full in its state's tone. Under it, the lesson completed last.
 *   right  This week (days active, minutes and streak only when the engine tracks them) and the Review queue with
 *          the one primary, Start review (disabled unless the engine lists review.start).
 *
 * Everything comes from the engine's `progress` answer. No answer, or a null part, shows that part's empty state.
 */
import { useEffect, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'
import { CodeText, Spinner } from '../../core/ui/atoms'
import { PrimaryButton } from '../../core/ui/buttons'
import { GlassCard } from '../../core/ui/GlassCard'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { StatusGlyph } from '../../core/ui/status'
import { useWindowArgs } from '../../core/surfaces'
import { color, copy, fill, radius2, status, surface, type2 } from '../../core/theme'
import { requestProgress, startReview, useProgress } from './store'
import { shortDate, whenWord, type Progress, type SkillProgressState, type SkillTrack, type Week } from './types'

const STATE_WORD: Record<SkillProgressState, string> = { mastered: 'Mastered', practicing: 'Practicing', not_started: 'Not started' }
const STATE_BAR: Record<SkillProgressState, string | undefined> = { mastered: status.passed, practicing: fill.practicing, not_started: undefined }
const LEGEND: Array<[SkillProgressState, string]> = [
  ['mastered', status.passed],
  ['practicing', fill.practicing],
  ['not_started', fill.hairline]
]
const DAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

const h2 = { fontSize: type2.body, lineHeight: '20px', color: color.text } as const
const caption = { fontSize: type2.xs, color: color.label } as const

function TitleBar(): ReactNode {
  return (
    <div data-drag className="relative flex shrink-0 items-center justify-end px-[20px]" style={{ height: 52, borderBottom: `1px solid ${fill.hairline}` }}>
      <div className="pointer-events-none absolute inset-x-0 flex justify-center">
        <div className="flex items-center gap-[8px]">
          <MiyagiMark size={16} />
          <MiyagiWordmark height={14} className="h-[14px] w-auto" />
          <span style={{ fontSize: type2.md, color: color.faint }}>/</span>
          <span className="font-semibold" style={{ fontSize: type2.md, color: color.text }}>
            Progress
          </span>
        </div>
      </div>
      <button type="button" data-no-drag className="flex cursor-pointer items-center gap-[6px] hover:text-white" style={caption} onClick={() => bridge.emit('launcher:toggle')}>
        <Keycap k="launcher" size="sm" />
        <span>{copy.launcherPlaceholder}</span>
      </button>
    </div>
  )
}

function Track({ t }: { t: SkillTrack }): ReactNode {
  return (
    <GlassCard surface="group" padding={20} className="flex flex-col gap-[16px]" style={{ borderRadius: radius2.chip }}>
      <div data-skill-track={t.track} className="flex items-baseline justify-between gap-[12px]">
        <h2 className="m-0 min-w-0 truncate font-semibold" style={h2}>
          {t.track}
        </h2>
        <span className="shrink-0 tabular-nums" style={caption}>
          {t.mastered} of {t.total} mastered
        </span>
      </div>
      <div className="flex flex-col gap-[14px]">
        {t.items.map((i, k) => {
          const bar = STATE_BAR[i.state]
          return (
            <div key={`${i.label}-${k}`} data-skill-state={i.state} className="flex flex-col gap-[6px]">
              <div className="flex justify-between gap-[12px]" style={{ fontSize: type2.sm, color: color.text }}>
                <span className="min-w-0 truncate">
                  <CodeText text={i.label} />
                </span>
                <span className="shrink-0" style={{ fontSize: type2.xs, fontWeight: i.state === 'mastered' ? 500 : 400, color: i.state === 'mastered' ? status.passed : color.label }}>
                  {STATE_WORD[i.state]}
                </span>
              </div>
              <div style={{ height: 4, borderRadius: radius2.round, background: fill.rule }}>
                {bar && <div style={{ width: '100%', height: 4, borderRadius: radius2.round, background: bar }} />}
              </div>
            </div>
          )
        })}
      </div>
    </GlassCard>
  )
}

function Empty({ title, body }: { title: string; body: string }): ReactNode {
  return (
    <div data-empty className="flex flex-col gap-[4px]">
      <span className="font-semibold" style={{ fontSize: type2.sm, color: color.text }}>
        {title}
      </span>
      <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>{body}</span>
    </div>
  )
}

function Skills({ data, loading }: { data?: Progress; loading: boolean }): ReactNode {
  const tracks = data?.skills.filter((t) => t.items.length || t.total) ?? []
  const recent = [...(data?.completed ?? [])].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))[0]
  return (
    <section aria-labelledby="progress-skills" className="flex min-h-0 min-w-0 flex-col gap-[20px]">
      <div className="flex items-end justify-between gap-[16px]">
        <div className="flex flex-col gap-[4px]">
          <h1 id="progress-skills" className="m-0 font-semibold" style={{ fontSize: 22, lineHeight: '28px', letterSpacing: '-0.01em', color: color.text }}>
            Skills
          </h1>
          <p className="m-0" style={{ fontSize: type2.sm, color: color.label }}>
            Checked in your own work, not quizzes.
          </p>
        </div>
        <div className="flex items-center gap-[16px]" style={caption}>
          {LEGEND.map(([s, bg]) => (
            <span key={s} className="flex items-center gap-[6px]">
              <span className="block" style={{ width: 16, height: 4, borderRadius: radius2.round, background: bg }} />
              {STATE_WORD[s]}
            </span>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center gap-[10px]" style={caption}>
            <Spinner size={14} />
            Reading your progress
          </div>
        ) : tracks.length ? (
          <div className="grid gap-[16px]" style={{ gridTemplateColumns: '1fr 1fr' }}>
            {tracks.map((t) => (
              <Track key={t.track} t={t} />
            ))}
          </div>
        ) : (
          <GlassCard surface="group" padding={20} style={{ borderRadius: radius2.chip }}>
            <Empty title="No skills yet" body="Finish a lesson. The skills its checks proved show up here." />
          </GlassCard>
        )}
      </div>

      {recent && (
        <div data-recent-lesson className="flex shrink-0 items-center justify-between gap-[12px] px-[16px] py-[12px]" style={{ borderRadius: radius2.card, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
          <div className="flex min-w-0 items-center gap-[12px]">
            <StatusGlyph state="passed" size={16} />
            <span className="truncate" style={{ fontSize: type2.sm, color: color.text }}>
              {recent.title}
            </span>
          </div>
          {recent.at && (
            <span className="shrink-0" style={caption}>
              Completed {shortDate(recent.at)}
            </span>
          )}
        </div>
      )}
    </section>
  )
}

function ThisWeek({ week }: { week?: Week | null }): ReactNode {
  // days[0] is Monday (the mockup's M T W T F S S); today is the learner's weekday.
  const today = (new Date().getDay() + 6) % 7
  return (
    <GlassCard surface="group" padding={20} className="flex shrink-0 flex-col gap-[16px]" style={{ borderRadius: radius2.chip }}>
      <section aria-labelledby="progress-week" className="flex flex-col gap-[16px]">
        <div className="flex items-baseline justify-between">
          <h2 id="progress-week" className="m-0 font-semibold" style={h2}>
            This week
          </h2>
          {week?.minutes != null && (
            <span className="tabular-nums" style={caption}>
              {week.minutes} min
            </span>
          )}
        </div>
        {!week ? (
          <Empty title="Not tracked yet" body="miyagi doesn’t keep activity yet. Lessons still count." />
        ) : (
          <>
            {week.streak != null && (
              <div className="flex items-baseline gap-[8px]">
                <span className="font-semibold tabular-nums" style={{ fontSize: type2.xxl, lineHeight: '32px', letterSpacing: '-0.01em', color: color.text }}>
                  {week.streak}
                </span>
                <span style={{ fontSize: type2.sm, color: color.label }}>day streak</span>
              </div>
            )}
            <div>
              <div role="img" aria-label={`Active ${week.days.filter(Boolean).length} of 7 days`} className="grid items-end gap-[8px]" style={{ gridTemplateColumns: 'repeat(7, 1fr)', height: 56 }}>
                {week.days.map((on, i) => (
                  <div
                    key={i}
                    data-day={on ? 'active' : 'idle'}
                    style={{ height: on ? 44 : 6, borderRadius: on ? radius2.keycap - 2 : radius2.round, background: on ? (i === today ? color.text : status.ring) : fill.chipHover }}
                  />
                ))}
              </div>
              <div className="mt-[6px] grid gap-[8px] text-center" style={{ gridTemplateColumns: 'repeat(7, 1fr)', fontSize: type2.micro, color: color.label }}>
                {DAYS.map((d, i) => (
                  <span key={i} style={i === today ? { color: color.text, fontWeight: 600 } : undefined}>
                    {d}
                  </span>
                ))}
              </div>
            </div>
          </>
        )}
      </section>
    </GlassCard>
  )
}

function Review({ review, canStart }: { review?: Progress['review']; canStart: boolean }): ReactNode {
  const items = review?.items ?? []
  const due = Math.min(review?.due ?? 0, items.length)
  return (
    <GlassCard surface="group" padding={20} className="flex min-h-0 flex-1 flex-col" style={{ borderRadius: radius2.chip }}>
      <section aria-labelledby="progress-review" className="flex min-h-0 flex-1 flex-col gap-[12px]">
        <div className="flex flex-col gap-[4px]">
          <div className="flex items-baseline justify-between">
            <h2 id="progress-review" className="m-0 font-semibold" style={h2}>
              Review
            </h2>
            {due > 0 && (
              <span className="tabular-nums" style={caption}>
                {due} due
              </span>
            )}
          </div>
          <p className="m-0" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
            Short checks in your own work, spaced so they stick.
          </p>
        </div>
        {!items.length ? (
          <Empty title="Nothing to review yet" body="Reviews show up here once miyagi schedules them." />
        ) : (
          <ul className="m-0 flex min-h-0 list-none flex-col overflow-y-auto p-0">
            {items.map((it, i) =>
              i < due ? (
                <li key={`${it.label}-${i}`} data-review-item="due" className="flex shrink-0 items-center justify-between gap-[12px]" style={{ height: 48, borderTop: `1px solid ${fill.hairline}` }}>
                  <div className="flex min-w-0 flex-col gap-[2px]">
                    <span className="truncate" style={{ fontSize: type2.sm, color: color.text }}>
                      <CodeText text={it.label} />
                    </span>
                    <span className="truncate" style={{ fontSize: type2.micro, color: color.label }}>
                      {[it.file, it.checks > 0 ? `${it.checks} check${it.checks === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ')}
                    </span>
                  </div>
                  <span className="shrink-0" style={caption}>
                    {it.when}
                  </span>
                </li>
              ) : (
                <li key={`${it.label}-${i}`} data-review-item="later" className="flex shrink-0 items-center justify-between gap-[12px]" style={{ height: 40, borderTop: `1px solid ${fill.hairline}`, ...caption }}>
                  <span className="truncate">
                    <CodeText text={it.label} />
                  </span>
                  <span className="shrink-0">{it.when}</span>
                </li>
              )
            )}
          </ul>
        )}
        <div className="flex-1" />
        {items.length > 0 && (
          <PrimaryButton
            label="Start review"
            size="lg"
            block
            disabled={!canStart || due === 0}
            title={canStart ? (due ? `Review ${items[0].label.split(String.fromCharCode(96)).join('')}, due ${whenWord(items[0].when)}` : undefined) : 'miyagi can’t start reviews yet'}
            onClick={() => startReview(items[0])}
          />
        )}
      </section>
    </GlassCard>
  )
}

export function ProgressWindow(_: { layout: Layout }): ReactNode {
  const data = useProgress((s) => s.data)
  const load = useProgress((s) => s.load)
  const canStart = useProgress((s) => s.caps.review)
  // Every open (and re-open) of the window asks again, and so does an engine that says hello after it opened.
  const canAsk = useProgress((s) => s.caps.progress)
  const args = useWindowArgs('progress')
  useEffect(() => {
    void requestProgress()
  }, [args, canAsk])
  const loading = load === 'loading' && !data
  return (
    <div data-progress="window" className="flex h-full w-full flex-col text-white" style={{ background: surface.window }}>
      <TitleBar />
      <div className="grid min-h-0 flex-1" style={{ gridTemplateColumns: '1fr 320px', gap: 24, padding: 32 }}>
        <Skills data={data} loading={loading} />
        <div className="flex min-h-0 flex-col gap-[16px]">
          <ThisWeek week={loading ? undefined : data?.week} />
          <Review review={data?.review} canStart={canStart} />
        </div>
      </div>
    </div>
  )
}
