/**
 * Feature: dashboard. The top band: Today (the daily ring), This week (strip, or the 12-week grid), Reps, Rhythm.
 * Forgiving by design: missing a day changes nothing, a short week spends a rest token, a pause counts for nothing
 * either way, and a rhythm that ends is "paused", never lost.
 */
import { Minus, Plus } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { color, type2 } from '../../core/theme'
import { MAX_TOKENS, shortDay, weekGrid, weekStrip, type Goals, type Rhythm, type Totals } from './model'
import { caption, DayCellBox, TextButton, Tile, TodayRing, TokenDot } from './parts'
import { pauseRhythm, resumeRhythm, setDailyGoal, toggleGrid, useDash } from './store'
import type { DashData } from './types'

const DAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const big = { fontSize: type2.xxl, lineHeight: '32px', letterSpacing: '-0.01em', color: color.text, fontWeight: 600 } as const
const plural = (n: number, one: string, many = `${one}s`): string => `${n} ${n === 1 ? one : many}`

function Today({ tracked, today, goals }: { tracked: boolean; today: number; goals: Goals }): ReactNode {
  const closed = tracked && today >= goals.daily
  return (
    <Tile
      label="Today"
      right={
        <div className="flex items-center gap-[4px]" style={caption}>
          <span className="mr-[2px]">Goal</span>
          <TextButton label={<Minus size={12} aria-hidden />} title="Lower the daily goal" disabled={goals.daily <= 1} onClick={() => setDailyGoal(goals.daily - 1)} />
          <span className="tabular-nums" aria-label={`Daily goal ${goals.daily} reps`} style={{ minWidth: 14, textAlign: 'center', color: color.text }}>
            {goals.daily}
          </span>
          <TextButton label={<Plus size={12} aria-hidden />} title="Raise the daily goal" disabled={goals.daily >= 10} onClick={() => setDailyGoal(goals.daily + 1)} />
        </div>
      }
    >
      <div className="flex items-center gap-[14px]">
        <TodayRing fraction={tracked ? today / goals.daily : 0} closed={closed}>
          <span className="tabular-nums" style={{ fontSize: type2.md, fontWeight: 600, color: color.text }}>
            {tracked ? today : ''}
          </span>
        </TodayRing>
        <div className="flex min-w-0 flex-col gap-[2px]">
          {tracked ? (
            <>
              <span data-ring={closed ? 'closed' : 'open'} style={{ fontSize: type2.sm, color: color.text }}>
                {closed ? 'Goal met today' : `${today} of ${plural(goals.daily, 'rep')}`}
              </span>
              <span style={caption}>Missing a day costs nothing.</span>
            </>
          ) : (
            <>
              <span style={{ fontSize: type2.sm, color: color.text }}>Not tracked yet</span>
              <span style={caption}>Daily reps show up here.</span>
            </>
          )}
        </div>
      </div>
    </Tile>
  )
}

function Week({ data, now, goals, r }: { data?: DashData; now: number; goals: Goals; r: Rhythm }): ReactNode {
  const showGrid = useDash((s) => s.showGrid)
  const tracked = !!data?.activity
  const strip = weekStrip(data?.activity ?? null, now, goals.daily)
  const active = strip.filter((d) => d.state === 'active' || d.state === 'closed').length
  return (
    <Tile label={showGrid ? 'Last 12 weeks' : 'This week'} right={tracked ? <TextButton label={showGrid ? 'This week' : '12 weeks'} pressed={showGrid} onClick={toggleGrid} /> : undefined}>
      {!tracked ? (
        <div className="flex flex-col gap-[2px]">
          <span style={{ fontSize: type2.sm, color: color.text }}>Not tracked yet</span>
          <span style={caption}>miyagi doesn’t keep activity per day yet.</span>
        </div>
      ) : showGrid ? (
        <Grid data={data} now={now} goals={goals} rested={r.rested} />
      ) : (
        <div className="flex flex-col gap-[6px]">
          <div role="img" aria-label={`Active ${active} of 7 days this week`} className="grid gap-[6px]" style={{ gridTemplateColumns: 'repeat(7, 1fr)' }}>
            {strip.map((d, i) => (
              <div key={d.date} className="flex flex-col items-center gap-[4px]">
                <DayCellBox state={d.state} size={24} today={d.today} title={`${shortDay(new Date(`${d.date}T12:00:00`).getTime())}: ${plural(d.reps, 'rep')}`} />
                <span style={{ fontSize: type2.micro, color: d.today ? color.text : color.label, fontWeight: d.today ? 600 : 400 }}>{DAYS[i]}</span>
              </div>
            ))}
          </div>
          <span style={caption}>{active ? `${plural(active, 'active day')}. ${r.thisWeekCounts ? 'This week counts.' : `${goals.weekly} make the week count.`}` : `${goals.weekly} active days make the week count.`}</span>
        </div>
      )}
    </Tile>
  )
}

function Grid({ data, now, goals, rested }: { data?: DashData; now: number; goals: Goals; rested: number[] }): ReactNode {
  const grid = weekGrid(data?.activity ?? null, now, goals.daily)
  const restedKeys = new Set(rested.map((t) => new Date(t).toDateString()))
  return (
    <div role="img" aria-label="Activity over the last 12 weeks" className="flex gap-[3px]">
      {grid.map((week, w) => (
        <div key={w} className="flex flex-col gap-[3px]" title={restedKeys.has(new Date(`${week[0].date}T00:00:00`).toDateString()) ? 'A rest token covered this week' : undefined}>
          {week.map((d) => (
            <DayCellBox key={d.date} state={d.state} size={9} title={`${shortDay(new Date(`${d.date}T12:00:00`).getTime())}: ${plural(d.reps, 'rep')}`} />
          ))}
        </div>
      ))}
    </div>
  )
}

function Reps({ t }: { t: Totals }): ReactNode {
  return (
    <Tile label="Reps">
      {t.reps === null ? (
        <div className="flex flex-col gap-[2px]">
          <span style={{ fontSize: type2.sm, color: color.text }}>Not counted yet</span>
          <span style={caption}>One rep per step you pass yourself.</span>
        </div>
      ) : (
        <div className="flex flex-col gap-[2px]">
          <span data-reps={t.reps} className="tabular-nums" style={big}>
            {t.reps}
          </span>
          <span style={caption}>{t.week ? `${t.week} this week, from your own work` : 'Steps you passed yourself'}</span>
        </div>
      )}
    </Tile>
  )
}

function RhythmTile({ r, goals, tracked, t, mastered, now }: { r: Rhythm; goals: Goals; tracked: boolean; t: Totals; mastered: number; now: number }): ReactNode {
  const [choosing, setChoosing] = useState(false)
  const pausing = !!goals.pause && goals.pause.from <= now && now < goals.pause.until
  const right = !tracked ? undefined : pausing ? (
    <TextButton label="Resume" onClick={resumeRhythm} />
  ) : (
    <TextButton label={choosing ? 'Cancel' : 'Pause'} pressed={choosing} title="Pause your rhythm for 1 to 4 weeks" onClick={() => setChoosing(!choosing)} />
  )
  return (
    <Tile label="Rhythm" right={right}>
      {!tracked ? (
        <div className="flex flex-col gap-[2px]">
          <span style={{ fontSize: type2.sm, color: color.text }}>Not tracked yet</span>
          <span style={caption}>Weeks of steady practice show up here.</span>
        </div>
      ) : (
        <div className="flex flex-col gap-[4px]">
          <div className="flex items-baseline gap-[8px]">
            <span data-rhythm={r.weeks} className="tabular-nums" style={big}>
              {r.weeks}
            </span>
            <span style={{ fontSize: type2.sm, color: color.label }}>{r.weeks === 1 ? 'week' : 'weeks'}</span>
            <span className="ml-auto flex items-center gap-[4px]" role="img" aria-label={plural(r.tokens, 'rest token')} title="A short week uses a rest token. Nothing is lost.">
              {Array.from({ length: MAX_TOKENS }, (_, i) => (
                <TokenDot key={i} held={i < r.tokens} />
              ))}
            </span>
          </div>
          {choosing ? (
            <div className="flex items-center gap-[4px]" role="group" aria-label="Pause rhythm for">
              <span className="mr-[2px]" style={caption}>
                Pause for
              </span>
              {[1, 2, 3, 4].map((w) => (
                <TextButton
                  key={w}
                  label={`${w} wk`}
                  title={`Pause your rhythm for ${plural(w, 'week')}`}
                  onClick={() => {
                    pauseRhythm(w, now)
                    setChoosing(false)
                  }}
                />
              ))}
            </div>
          ) : (
            <span style={caption}>
              {pausing && goals.pause
                ? `Paused until ${shortDay(goals.pause.until)}. Nothing counts against you.`
                : r.weeks === 0 && r.pausedAt > 0
                  ? `Your rhythm paused at ${r.pausedAt} weeks. Your ${t.reps ?? 0} reps and ${mastered} skills are still yours.`
                  : `${plural(r.tokens, 'rest token')}. ${r.thisWeekCounts ? 'This week counts.' : `${r.thisWeek} of ${goals.weekly} days this week.`}`}
            </span>
          )}
        </div>
      )}
    </Tile>
  )
}

export function Band({ data, now, goals, r, t }: { data?: DashData; now: number; goals: Goals; r: Rhythm; t: Totals }): ReactNode {
  const tracked = !!data?.activity
  const mastered = data?.tracks.reduce((n, x) => n + x.mastered, 0) ?? 0
  return (
    <div data-band className="grid shrink-0 gap-[12px]" style={{ gridTemplateColumns: '1.15fr 1.3fr 0.8fr 1.1fr' }}>
      <Today tracked={tracked} today={t.today} goals={goals} />
      <Week data={data} now={now} goals={goals} r={r} />
      <Reps t={t} />
      <RhythmTile r={r} goals={goals} tracked={tracked} t={t} mastered={mastered} now={now} />
    </div>
  )
}
