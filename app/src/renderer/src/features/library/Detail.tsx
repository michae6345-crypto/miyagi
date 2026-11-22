/**
 * Feature: library. A lesson's preview (mockup Home-LessonDetail), inside the Library window: what it teaches, its
 * steps, where it works, and Start lesson (the one primary). Start sends library.start {id} (zero model calls) and
 * nothing else: no `learn`, no build. Deviations from the mockup, by rule: "Saved on this Mac" instead of "Built
 * once, shared" (A6: no cross-user claim); no Enter keycap (keycaps only from bridge.platform.keys, which has no Enter;
 * Enter still starts); no Level row (the engine doesn't send one); the step's check name is not in the contract, so a
 * step shows its minutes when the engine sends them.
 */
import { ArrowUpRight, ChevronLeft, Play } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { PrimaryButton } from '../../core/ui/buttons'
import { color, copy, fill, highlight, radius2, surface, type2 } from '../../core/theme'
import { Column, PAGE_TOP, Pane, rhythm } from './layout'
import { youtubeId, youtubeWatchUrl } from './sanitize'
import { TOOL_NAME, minutesLabel, soft, stepsLabel } from './parts'
import { foldLabel, previewSteps } from './stepsPreview'
import { closeDetail, itemFor, start, useLibrary } from './store'
import { thisDevice } from '../onboarding/device'

const KICKER = { youtube: 'Lesson from a YouTube tutorial', goal: 'Lesson built for a goal', library: 'Lesson from the library' } as const

/** `vid`: a checked 11-character YouTube id. Only the canonical watch link built from it is opened, never the engine's URL. */
function Video({ vid, by }: { vid: string; by?: string }): ReactNode {
  return (
    <button
      type="button"
      aria-label="Open the original video in your browser"
      onClick={() => void bridge.invoke('open:external', youtubeWatchUrl(vid)).catch(() => undefined)}
      className="mg-press flex w-full cursor-pointer items-center gap-[16px] text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      // Home's card surface (white in light), radius 16 around an 8 px inset, so the thumbnail's 8 is concentric.
      style={{ padding: 8, borderRadius: radius2.group, background: 'var(--l-overlay)', boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}`, outlineColor: color.text }}
    >
      <span className="relative flex shrink-0 items-center justify-center overflow-hidden" style={{ width: 160, height: 90, borderRadius: radius2.control, background: fill.thumb }}>
        <img src={`https://i.ytimg.com/vi/${vid}/hqdefault.jpg`} alt="" draggable={false} referrerPolicy="no-referrer" className="absolute inset-0 h-full w-full object-cover" />
        <span className="relative flex items-center justify-center" style={{ width: 32, height: 32, borderRadius: radius2.round, background: fill.thumbArt, color: color.text }}>
          <Play aria-hidden size={12} fill="currentColor" strokeWidth={0} />
        </span>
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-[4px]">
        <span style={{ fontSize: type2.md, lineHeight: '20px', color: color.text }}>The original video</span>
        <span className="truncate" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
          {by ? `By ${by} · opens in your browser` : 'Opens in your browser'}
        </span>
      </span>
      <ArrowUpRight aria-hidden size={16} strokeWidth={1.8} className="shrink-0" style={{ color: color.label, marginRight: 8 }} />
    </button>
  )
}

/** `back`: the page the preview was opened from (the shell names it); without it the bar leaves room for the traffic lights. */
export function Detail({ id, back }: { id: string; back?: string }): ReactNode {
  const item = useLibrary((s) => itemFor(s, id))
  const detail = useLibrary((s) => s.details[id])
  const canStart = useLibrary((s) => s.caps.start)
  const capsKnown = useLibrary((s) => s.capsKnown)
  const failed = useLibrary((s) => !!s.detailFailed[id])
  const starting = useLibrary((s) => s.starting)
  const err = useLibrary((s) => (s.startError?.id === id ? s.startError.text : undefined))
  const loaded = useLibrary((s) => s.loaded)
  const ready = !!item?.ready && canStart
  const busy = starting === id
  // The step preview folds after a few rows; a different lesson starts folded again.
  const [open, setOpen] = useState<{ id: string; all: boolean }>({ id, all: false })
  const expanded = open.id === id && open.all

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault()
        closeDetail()
      } else if (e.key === 'Enter' && !e.metaKey && !e.ctrlKey && !e.altKey && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLButtonElement)) {
        if (ready && !starting) {
          e.preventDefault()
          void start(id)
        }
      }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [id, ready, starting])

  // Round 3: one back control ("‹ Lessons", chevron and name together, a row-style hover), and no rule under the bar:
  // no other page has a hairline under its header, spacing does the grouping.
  // Layout spec: the back control lives in the page's own column, its chevron on the column's left edge (the title's
  // edge), inside the 52 px drag strip. Clear of the traffic lights: the column never starts left of 80 px.
  const bar = (
    <Column data-drag className="flex shrink-0 items-center" style={{ height: 52 }}>
      <button
        type="button"
        data-no-drag
        aria-label={`Back to ${back ?? 'Library'}`}
        onClick={closeDetail}
        className="flex cursor-pointer items-center gap-[2px] outline-offset-1 transition-colors hover:bg-[var(--s-row-hover)] focus-visible:outline-2 focus-visible:outline-solid"
        style={{ height: 30, marginLeft: -10, padding: '0 10px 0 4px', borderRadius: radius2.control, color: color.label, fontSize: type2.sm, outlineColor: color.text }}
      >
        <ChevronLeft aria-hidden size={16} strokeWidth={1.8} />
        {back ?? 'Library'}
      </button>
    </Column>
  )

  if (!item)
    return (
      <Pane className="flex h-full flex-col" style={{ color: color.text }}>
        {bar}
        <div className="flex flex-1 items-center justify-center" style={{ fontSize: type2.sm, color: color.label }}>
          {loaded ? `That lesson isn’t on ${thisDevice()}.` : 'Loading…'}
        </div>
      </Pane>
    )

  const steps = detail?.steps ?? []
  // Once a step list came back, its length is the count (the page never says 7 steps above 3 rows).
  const stepCount = steps.length || item.steps
  const shown = previewSteps(steps, expanded)
  const mins = minutesLabel(item.estMinutes)
  const src = item.source
  const by = src?.channel ?? item.by
  const vid = src?.kind === 'youtube' ? youtubeId(src.url) : undefined
  // Redraft round 2: the caption only speaks when something is wrong (no reassurance copy under the button).
  // Nothing says "can't start" until library:caps has answered; the line keeps its height meanwhile.
  const caption = err ?? (capsKnown && !canStart ? 'This engine can’t start saved lessons yet.' : !item.ready ? 'Not ready yet.' : ' ')

  // One gray line under the title: the tools in words, the steps, the minutes, who made it.
  const meta = [item.tools.map((t) => TOOL_NAME[t]).join(', '), stepsLabel(stepCount), mins, item.by ? `by ${item.by}` : ''].filter(Boolean).join(' · ')

  // Redraft (Michael's audit: "a large empty area on the left, a tiny preview box at top right; hard to scan"): one
  // centered column, as on Home. The title, one meta line, Start lesson right under it (no trip to the bottom-right
  // corner), then the steps. A YouTube lesson shows its video as a source row under the start row.
  // Layout spec (Nov 22): the same 720 column as Home and Lessons, back link included; the kicker's top is 80 from the
  // window's top (8 panel inset + 52 strip + 20), where every page's first line sits; steps 40 under the start row.
  return (
    <Pane className="flex h-full flex-col" style={{ color: color.text }}>
      {bar}
      <section aria-labelledby="lib-title" className="min-h-0 flex-1 overflow-y-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }}>
        <Column className="flex flex-col" style={{ paddingTop: PAGE_TOP - 8 - 52, paddingBottom: rhythm.bottom }}>
          <div style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>{KICKER[src?.kind ?? 'library']}</div>
          <h1 id="lib-title" className="m-0 font-semibold" style={{ marginTop: 8, fontSize: 26, lineHeight: '32px', letterSpacing: '-0.4px' }}>
            {item.title}
          </h1>
          <div style={{ marginTop: 8, fontSize: type2.sm, lineHeight: '18px', color: color.label }}>{meta}</div>
          {detail?.overview && (
            <p className="m-0" style={{ marginTop: 16, fontSize: type2.md, lineHeight: '22px', color: soft, maxWidth: 560 }}>
              {detail.overview}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-[12px]" style={{ marginTop: 24 }}>
            <PrimaryButton label="Start lesson" icon={Play} busy={busy} disabled={!ready || (!!starting && !busy)} onClick={() => void start(id)} />
            {caption.trim() && (
              <span role={err ? 'status' : undefined} style={{ fontSize: type2.xs, color: color.label }}>
                {caption}
              </span>
            )}
          </div>
          {vid && (
            <div style={{ marginTop: 32 }}>
              <Video vid={vid} by={by} />
            </div>
          )}
          <h2 className="m-0 font-medium" style={{ margin: `${rhythm.section}px 0 4px`, fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
            {stepCount ? stepsLabel(stepCount) : 'Steps'}
          </h2>
          {steps.length > 0 ? (
            <>
              <ol className="m-0 list-none p-0" aria-label="Steps">
                {shown.rows.map((st, i) => (
                  <li key={`${st.index}-${i}`} className="flex items-start gap-[14px]" style={{ minHeight: 48, padding: '12px 0', borderBottom: i === shown.rows.length - 1 && !shown.hidden ? 'none' : `1px solid ${fill.hairline}` }}>
                    <span className="w-[20px] shrink-0 text-right tabular-nums" style={{ fontSize: type2.sm, lineHeight: '22px', color: color.label }}>
                      {i + 1}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                      <span className="truncate" style={{ fontSize: type2.md, lineHeight: '22px' }}>
                        {st.title}
                      </span>
                      {st.what && st.what !== st.title && (
                        <span style={{ fontSize: type2.sm, lineHeight: 1.4, color: color.label }}>{st.what}</span>
                      )}
                    </span>
                    {st.estMinutes ? <span className="shrink-0" style={{ fontSize: type2.xs, lineHeight: '22px', color: color.label, fontVariantNumeric: 'tabular-nums' }}>{st.estMinutes} min</span> : null}
                  </li>
                ))}
              </ol>
              {steps.length > shown.rows.length || expanded ? (
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setOpen({ id, all: !expanded })}
                  className="cursor-pointer self-start outline-offset-1 transition-colors hover:bg-[var(--s-row-hover)] focus-visible:outline-2 focus-visible:outline-solid"
                  style={{ marginTop: 8, marginLeft: 24, height: 30, padding: '0 10px', borderRadius: radius2.control, color: color.label, fontSize: type2.sm, outlineColor: color.text }}
                >
                  {foldLabel(steps.length, expanded)}
                </button>
              ) : null}
            </>
          ) : (
            <p className="m-0" style={{ fontSize: type2.sm, lineHeight: 1.5, color: color.label, maxWidth: 520 }}>
              {detail === undefined ? (failed ? `The steps show once ${copy.name} answers.` : 'Loading the steps…') : 'They open one at a time, each checked before the next.'}
            </p>
          )}
        </Column>
      </section>
    </Pane>
  )
}
