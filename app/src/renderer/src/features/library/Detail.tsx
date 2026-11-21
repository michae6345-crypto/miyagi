/**
 * Feature: library. A lesson's preview (mockup Home-LessonDetail), inside the Library window: what it teaches, its
 * steps, where it works, and Start lesson (the one primary). Start sends library.start {id} (zero model calls) and
 * nothing else: no `learn`, no build. Deviations from the mockup, by rule: "Saved on this Mac" instead of "Built
 * once, shared" (A6: no cross-user claim); no Enter keycap (keycaps only from bridge.platform.keys, which has no Enter;
 * Enter still starts); no Level row (the engine doesn't send one); the step's check name is not in the contract, so a
 * step shows its minutes when the engine sends them.
 */
import { ChevronLeft, CircleCheck, Play } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { PrimaryButton } from '../../core/ui/buttons'
import { color, fill, font, radius2, scrim, surface, type2 } from '../../core/theme'
import { youtubeId, youtubeWatchUrl } from './sanitize'
import { TOOL_NAME, ToolTile, minutesLabel, soft, stepsLabel } from './parts'
import { closeDetail, itemFor, start, useLibrary } from './store'

const KICKER = { youtube: 'Lesson from a YouTube tutorial', goal: 'Lesson built for a goal', library: 'Lesson from the library' } as const

/** `vid`: a checked 11-character YouTube id. Only the canonical watch link built from it is opened, never the engine's URL. */
function Video({ vid, by }: { vid: string; by?: string }): ReactNode {
  return (
    <div className="flex flex-col gap-[8px]">
      <button
        type="button"
        aria-label="Open the original video in your browser"
        onClick={() => void bridge.invoke('open:external', youtubeWatchUrl(vid)).catch(() => undefined)}
        className="relative flex cursor-pointer items-center justify-center overflow-hidden"
        style={{ height: 152, borderRadius: radius2.card, background: fill.thumb, boxShadow: `inset 0 0 0 1px ${surface.border}` }}
      >
        <img src={`https://i.ytimg.com/vi/${vid}/hqdefault.jpg`} alt="" draggable={false} referrerPolicy="no-referrer" className="absolute inset-0 h-full w-full object-cover" />
        <span className="relative flex items-center justify-center" style={{ width: 44, height: 44, borderRadius: radius2.round, background: fill.thumbArt, color: color.text }}>
          <Play aria-hidden size={16} fill="currentColor" strokeWidth={0} />
        </span>
      </button>
      {by && <span style={{ fontSize: type2.xs, color: color.label }}>Original video by {by}</span>}
    </div>
  )
}

export function Detail({ id }: { id: string }): ReactNode {
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

  const bar = (
    <div className="flex shrink-0 items-center gap-[16px]" style={{ height: 52, padding: '0 16px 0 84px', borderBottom: `1px solid ${surface.border}` }}>
      <button
        type="button"
        aria-label="Back to library"
        onClick={closeDetail}
        className="flex cursor-pointer items-center justify-center"
        style={{ width: 44, height: 36, borderRadius: radius2.control, color: soft }}
      >
        <ChevronLeft aria-hidden size={16} strokeWidth={1.8} />
      </button>
      <span style={{ fontSize: type2.sm, color: color.label }}>Library</span>
    </div>
  )

  if (!item)
    return (
      <div className="flex h-full w-full flex-col" style={{ color: color.text }}>
        {bar}
        <div className="flex flex-1 items-center justify-center" style={{ fontSize: type2.sm, color: color.label }}>
          {loaded ? 'That lesson isn’t on this Mac.' : 'Loading…'}
        </div>
      </div>
    )

  const steps = detail?.steps ?? []
  // Once a step list came back, its length is the count (the page never says 7 steps above 3 rows).
  const stepCount = steps.length || item.steps
  const mins = minutesLabel(item.estMinutes)
  const src = item.source
  const by = src?.channel ?? item.by
  const vid = src?.kind === 'youtube' ? youtubeId(src.url) : undefined
  const editorNear = item.tools.includes('vscode') || item.tools.includes('jupyter')
  // Nothing says "can't start" until library:caps has answered; the line keeps its height meanwhile.
  const caption =
    err ??
    (capsKnown && !canStart
      ? 'This engine can’t start saved lessons yet.'
      : !item.ready
        ? 'Not ready on this Mac yet.'
        : !capsKnown
          ? ' '
          : editorNear
            ? 'Sits beside VS Code. Never covers your files.'
            : 'Sits beside your work. Never covers your files.')

  return (
    <div className="flex h-full w-full flex-col" style={{ color: color.text }}>
      {bar}
      <div className="grid min-h-0 flex-1" style={{ gridTemplateColumns: '1fr 320px' }}>
        <section aria-labelledby="lib-title" className="flex min-h-0 flex-col overflow-y-auto" style={{ padding: '32px 40px' }}>
          <div style={{ fontSize: type2.xs, color: color.label }}>{KICKER[src?.kind ?? 'library']}</div>
          <h1 id="lib-title" className="m-0 font-semibold" style={{ marginTop: 8, fontSize: type2.xxl, lineHeight: 1.2, letterSpacing: '-0.015em' }}>
            {item.title}
          </h1>
          {detail?.overview && (
            <p className="m-0" style={{ marginTop: 12, fontSize: type2.md, lineHeight: 1.5, color: soft, maxWidth: 520 }}>
              {detail.overview}
            </p>
          )}
          <h2 className="m-0 font-semibold uppercase" style={{ margin: '32px 0 8px', fontSize: type2.micro, letterSpacing: '0.04em', color: color.label }}>
            {stepsLabel(stepCount)}
          </h2>
          {steps.length > 0 ? (
            <ol className="m-0 list-none p-0" style={{ borderTop: `1px solid ${surface.border}` }}>
              {steps.map((st, i) => (
                <li key={`${st.index}-${i}`} className="flex items-center gap-[16px]" style={{ height: 52, borderBottom: i === steps.length - 1 ? 'none' : `1px solid ${surface.border}` }}>
                  <span
                    className="flex shrink-0 items-center justify-center tabular-nums"
                    style={{ width: 28, height: 28, borderRadius: radius2.round, boxShadow: `inset 0 0 0 1px ${fill.trackNextMini}`, fontSize: type2.xs, color: soft }}
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.md }}>
                    {st.title}
                  </span>
                  {st.estMinutes ? <span style={{ fontSize: type2.xs, color: color.label, fontFamily: font.mono }}>{st.estMinutes} min</span> : null}
                </li>
              ))}
            </ol>
          ) : (
            <div style={{ fontSize: type2.sm, color: color.label }}>{detail === undefined ? (failed ? 'The steps show once the engine answers.' : 'Loading the steps…') : 'The steps show once the lesson starts.'}</div>
          )}
        </section>

        <aside className="flex min-h-0 flex-col gap-[24px] overflow-y-auto" style={{ padding: '32px 24px', borderLeft: `1px solid ${surface.border}`, background: scrim.launcher }}>
          {vid && <Video vid={vid} by={by} />}

          <dl className="m-0 grid gap-x-[16px] gap-y-[12px]" style={{ gridTemplateColumns: 'auto 1fr', fontSize: type2.sm }}>
            {mins && (
              <>
                <dt style={{ color: color.label }}>Time</dt>
                <dd className="m-0">{mins}</dd>
              </>
            )}
            <dt style={{ color: color.label }}>Steps</dt>
            <dd className="m-0">{stepCount}</dd>
            {item.by && (
              <>
                <dt style={{ color: color.label }}>Made by</dt>
                <dd className="m-0">{item.by}</dd>
              </>
            )}
          </dl>

          {item.tools.length > 0 && (
            <div>
              <div style={{ fontSize: type2.xs, color: color.label, marginBottom: 8 }}>Works in</div>
              <div className="flex flex-wrap gap-[8px]">
                {item.tools.map((t) => (
                  <span key={t} className="inline-flex items-center gap-[8px]" style={{ height: 28, padding: '0 10px 0 4px', borderRadius: radius2.control, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, fontSize: type2.xs, color: soft }}>
                    <ToolTile tool={t} size={20} />
                    {TOOL_NAME[t]}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="mt-auto flex flex-col gap-[12px]">
            {ready && (
              <div className="flex items-center gap-[8px]" style={{ fontSize: type2.xs, color: soft }}>
                <CircleCheck aria-hidden size={14} strokeWidth={1.8} />
                Ready instantly. Saved on this Mac.
              </div>
            )}
            <PrimaryButton label="Start lesson" size="lg" block busy={busy} disabled={!ready || (!!starting && !busy)} onClick={() => void start(id)} />
            <div role={err ? 'status' : undefined} className="text-center" style={{ fontSize: type2.xs, color: color.label }}>
              {caption}
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
