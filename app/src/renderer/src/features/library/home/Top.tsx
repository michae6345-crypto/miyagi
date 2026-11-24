/**
 * Feature: library. Home v4's top: the ask field and the Continue card (Adrian's ui-next mock, `askField` and `contCard`).
 *
 *   Ask       one framed field, the bonsai and "ask miyagi, or paste a YouTube link", the launcher's keycap, and three
 *             suggestion chips inside the same frame (options, so pastels). Typing swaps the keycap for the action.
 *   Continue  the page's one card: a cover, "Step 4 of 7", the lesson, the step, the ONE primary action, and the
 *             lesson's progress as a 3 px edge along the bottom.
 */
import { ArrowRight, Play } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { useLesson } from '../../../core/lesson'
import { useAppearance } from '../../../core/prefs'
import { color, elevation, fill, highlight, layer, surface, tone, type Tone } from '../../../core/theme'
import { Spinner } from '../../../core/ui/atoms'
import { QuietButton } from '../../../core/ui/buttons'
import { Keycap } from '../../../core/ui/Keycap'
import { MiyagiMark } from '../../../core/ui/Mark'
import { groupTracks, nodeStates } from '../../dashboard/model'
import type { DashData } from '../../dashboard/types'
import { readAsk, setAskText, submitAsk, useAsk } from '../homeModel'
import { useLibrary } from '../store'
import { Cover, T } from './bits'
import type { CoverKind } from './data'

/** The ask field's placeholder on Home (the mock's words; the launcher keeps "ask miyagi anything"). */
export const ASK_PLACEHOLDER = 'ask miyagi, or paste a YouTube link'

const IDEAS = ['Clean a messy CSV with pandas', 'Build a tiny web server', 'Train an image classifier']
const IDEA_TONES: Tone[] = ['sky', 'lilac', 'pink']

/**
 * The chips, personal first: skills the learner is ready for next (every prerequisite mastered, not started), named
 * with their track ("Broadcasting in numpy"). Topped up with general ideas, always three.
 */
export function pickIdeas(data: DashData | undefined): Array<{ text: string; tone: Tone }> {
  const mine: string[] = []
  for (const g of groupTracks(data)) {
    const st = nodeStates(g.track)
    const where = g.kicker ?? g.track.track
    for (const s of g.track.skills) {
      if (st[s.id] !== 'available') continue
      const label = s.label.split(String.fromCharCode(96)).join('')
      const text = label.toLowerCase().includes(where.toLowerCase()) ? label : `${label} in ${where}`
      if (!mine.includes(text)) mine.push(text)
    }
  }
  return [...mine.slice(0, 3), ...IDEAS].slice(0, 3).map((text, i) => ({ text, tone: IDEA_TONES[i] }))
}

/** Puts the caret in Home's ask field, optionally with text in it. */
export function focusAsk(text?: string): void {
  if (text !== undefined) setAskText(text)
  requestAnimationFrame(() => document.querySelector<HTMLInputElement>('[data-home-ask] input')?.focus())
}

/** The card surface (Continue): white on the cream pane in light with a soft shadow, a lifted gray with an edge in dark. */
export function useCardSurface(): { background: string; boxShadow: string } {
  const light = useAppearance() === 'light'
  return { background: layer.overlay.background, boxShadow: [highlight.topSoft, `inset 0 0 0 1px ${surface.border}`, light ? elevation.raised : ''].filter(Boolean).join(', ') }
}

export function Ask({ ideas }: { ideas: Array<{ text: string; tone: Tone }> }): ReactNode {
  const ask = useAsk()
  const items = useLibrary((s) => s.items)
  const canStart = useLibrary((s) => s.caps.start)
  const connected = useLesson((s) => s.connected)
  const input = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)
  const read = readAsk(ask.text, items, canStart)
  const go = (): void => {
    if (!submitAsk(connected) && !useAsk.getState().sending) input.current?.focus()
  }
  const actionLabel = read.kind === 'link' ? (read.match ? 'Start lesson' : 'Build lesson') : 'Teach me'
  return (
    <section
      aria-label="Learn something new"
      data-home-ask
      style={{ borderRadius: 12, background: layer.overlay.background, boxShadow: `inset 0 0 0 ${focused ? 1.5 : 1}px ${focused ? color.faint : fill.chipBorder}`, transition: 'box-shadow 140ms ease' }}
    >
      <form
        className="flex cursor-text items-center gap-[10px]"
        style={{ height: 48, padding: '0 10px 0 14px' }}
        onClick={() => input.current?.focus()}
        onSubmit={(e) => {
          e.preventDefault()
          go()
        }}
      >
        <span aria-hidden className="flex shrink-0">
          <MiyagiMark size={18} />
        </span>
        <input
          ref={input}
          aria-label={ASK_PLACEHOLDER}
          placeholder={ASK_PLACEHOLDER}
          autoComplete="off"
          spellCheck={false}
          value={ask.text}
          disabled={!!ask.sending}
          onChange={(e) => setAskText(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-[var(--c-faint)]"
          style={{ fontSize: 15, color: color.text }}
        />
        {read.kind === 'idle' ? (
          <span className="flex shrink-0 items-center" style={{ paddingRight: 4 }}>
            <Keycap k="launcher" size="sm" />
          </span>
        ) : (
          <QuietButton label={actionLabel} icon={read.kind === 'link' && read.match ? Play : ArrowRight} busy={!!ask.sending} onClick={go} />
        )}
      </form>
      <div className="flex flex-wrap items-center gap-[8px]" style={{ padding: '0 14px 12px', minHeight: 40 }}>
        {read.kind === 'idle'
          ? ideas.map((t) => (
              <button
                key={t.text}
                type="button"
                data-idea
                onClick={() => focusAsk(t.text)}
                className="mg-press inline-flex cursor-pointer items-center outline-offset-2 focus-visible:outline-2"
                style={{ height: 28, padding: '0 12px', borderRadius: 14, fontSize: 13, fontWeight: 500, background: tone[t.tone].bg, color: tone[t.tone].fg, outlineColor: color.text, whiteSpace: 'nowrap' }}
              >
                {t.text}
              </button>
            ))
          : (
              <span role="status" className="truncate" style={{ fontSize: T.meta, color: ask.note ? color.text : color.label }}>
                {ask.note ?? (read.kind === 'link' && read.match ? read.match.title : !connected ? 'miyagi is offline.' : 'Press Return to start.')}
              </span>
            )}
      </div>
    </section>
  )
}

export type ContView = { kicker: string; title: string; sub?: string; fraction?: number; cover: CoverKind; building?: boolean }

/** The one card on the page. `action` is the hero's primary (Home.tsx ContAction), so every state keeps its one button. */
export function ContinueCard({ view, action }: { view: ContView; action: ReactNode }): ReactNode {
  const card = useCardSurface()
  const f = view.fraction === undefined ? undefined : Math.max(0, Math.min(1, view.fraction))
  return (
    <section aria-labelledby="home-continue" data-home-hero className="relative flex flex-wrap items-center overflow-hidden" style={{ ...card, borderRadius: 12, padding: '14px 16px 14px 14px', columnGap: 16, rowGap: 12 }}>
      <Cover kind={view.cover} width={132} />
      <div className="flex min-w-0 flex-1 flex-col" style={{ minWidth: 180 }}>
        <span style={{ fontSize: T.small, color: color.label, fontVariantNumeric: 'tabular-nums' }}>{view.kicker}</span>
        <h3 id="home-continue" className="m-0 line-clamp-2" style={{ margin: '2px 0', fontSize: 17, fontWeight: 640, letterSpacing: '-0.01em', color: color.text }}>
          {view.title}
        </h3>
        {view.sub && (
          <span className="flex min-w-0 items-center gap-[8px]" style={{ fontSize: T.small, color: color.label }}>
            {view.building && <Spinner size={12} c={color.label} />}
            <span className="truncate">{view.sub}</span>
          </span>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-[6px]">{action}</div>
      {f !== undefined && (
        <div role="img" aria-label={`${Math.round(f * 100)}% done`} className="absolute inset-x-0 bottom-0" style={{ height: 3, background: fill.chipHover }}>
          <div style={{ width: `${f * 100}%`, height: '100%', background: color.text }} />
        </div>
      )}
    </section>
  )
}
