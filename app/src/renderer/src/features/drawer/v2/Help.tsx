/**
 * Feature: drawer (v2, A1). "Need help" (Les-Anatomy "Help row, pastel"): Explain, Hint, Show me, Diagram, Watch as
 * pastel tiles (BRAND.md mapping, theme.actionTone), each a label over a keycap slot.
 *
 *   Explain / Hint / Show me / Diagram  triggerShortcut(kind): the same path as the keys, so the Diagram flyout and the
 *                                       engine behave as before. Hint pressed while a hint is open asks for the next rung.
 *   Watch                               the step's clip in the browser (a "Just teach me" lesson has no player): the
 *                                       lesson's video at the step's start. Hidden when the step has no clip.
 *
 * Never looks dead (persona QA): a tile is busy from the moment it is pressed (core usePressed, so a key press counts
 * too), not only once the engine says "thinking". The spinner takes the keycap's slot, so nothing shifts. With no
 * answer and no thinking after ANSWER_MS, notify("No answer yet. Try again.") and the tile is quiet again.
 * The tile whose answer is on screen is drawn pressed (an ink ring inside, its pastel around it): Hint while the hint
 * shows, Explain while its card is open, Diagram while the flyout is out.
 * Every tile keeps the same height and a keycap-height slot (Watch has no key yet: its play glyph fills the slot, Core
 * request), so the labels share one baseline. Five tiles wrap to two rows (three over two): one row truncated labels.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { useShallow } from 'zustand/react/shallow'
import { notify, useLesson, useThinking } from '../../../core/lesson'
import { triggerShortcut, usePressed, type ActionShortcut } from '../../../core/shortcuts'
import { actionTone, color, elevation, fill, highlight, radius2, type2, type OptionAction } from '../../../core/theme'
import { pressMotion } from '../../../core/ui/motion'
import { Spinner } from '../../../core/ui/atoms'
import { WatchIcon } from '../../../core/ui/HelpRow'
import { Keycap, keyLabel, type KeyName } from '../../../core/ui/Keycap'
import { useCards } from '../../cards/store'
import { useDiagram } from '../../diagrams/store'
import { HOST_MAX_NARROW, linkHost } from '../links'
import { openSource } from '../store'
import type { Gate } from '../../errors/gate'
import { Caption } from './ui'

type Tile = Exclude<OptionAction, 'watch'> & ActionShortcut
const TILES: Tile[] = ['explain', 'hint', 'show_me', 'diagram']
const LABEL: Record<OptionAction, string> = { explain: 'Explain', hint: 'Hint', show_me: 'Show me', diagram: 'Diagram', watch: 'Watch' }

/** How long a press may go with no answer and no "thinking" before the tile says so. */
export const ANSWER_MS = 8000

/** The lesson's video at `start` seconds, as a link (YouTube's t parameter), or undefined. */
export function useWatchUrl(start: number | undefined): string | undefined {
  return useLesson((s) => {
    if (start === undefined) return undefined
    const v = s.lesson?.sources.find((x) => x.kind === 'video')
    if (!v?.url) return undefined
    try {
      const u = new URL(v.url)
      if (u.protocol !== 'https:') return undefined
      u.searchParams.set('t', `${Math.max(0, Math.floor(start))}s`)
      return u.toString()
    } catch {
      return undefined
    }
  })
}

/**
 * The option the learner pressed and is still waiting on: from the press itself until the engine answers (core clears
 * usePressed on a card, diagram, video.seek or the end of its thinking), or ANSWER_MS with nothing at all.
 */
export function useWaitingOn(): OptionAction | undefined {
  const press = usePressed(useShallow((p) => ({ kind: p.kind, at: p.at })))
  const thinking = useThinking()
  const [expired, setExpired] = useState(0)
  const option = press.kind && (TILES as string[]).includes(press.kind) ? (press.kind as Tile) : undefined
  useEffect(() => {
    if (!option) return
    const left = ANSWER_MS - (Date.now() - press.at)
    if (left <= 0) return
    const id = setTimeout(() => {
      const p = usePressed.getState()
      if (p.kind !== option || p.at !== press.at) return
      if (useLesson.getState().engineState === 'thinking') return // still working on it: keep the spinner
      setExpired(press.at)
      notify('No answer yet. Try again.')
    }, left)
    return () => clearTimeout(id)
  }, [option, press.at])
  if (!option || expired === press.at) return undefined
  const fresh = Date.now() - press.at < ANSWER_MS
  return fresh || thinking ? option : undefined
}

/**
 * `waiting`: useWaitingOn(), called once by the panel (its timer notifies, so it must run in one place only).
 * `gate`: the link gate (features/errors/gate.ts), so the tiles wait while miyagi can't answer.
 */
export function Help({ pressed, watchStart, waiting, gate }: { pressed?: OptionAction; watchStart?: number; waiting?: OptionAction; gate?: Gate }): ReactNode {
  const explainOpen = useCards((c) => c.card?.kind === 'explain')
  const diagramOpen = useDiagram((d) => d.open)
  const watch = useWatchUrl(watchStart)
  const actions: OptionAction[] = watch ? [...TILES, 'watch'] : TILES
  // The link gate (features/errors/gate.ts): while miyagi can't answer, Explain, Hint, Show me and Diagram wait
  // (dimmed, disabled, the caption says why). Watch only needs the browser, so it stays unless the Mac is offline.
  const waits = !!gate && gate.kind !== 'ok'
  const off = (a: OptionAction): boolean => waits && (a !== 'watch' || !!gate?.offline)
  const isPressed = (a: OptionAction): boolean => a === pressed || (a === 'explain' && explainOpen) || (a === 'diagram' && diagramOpen)
  // Five tiles in 320 px leave "Show me" and "Diagram" truncated (persona QA): two rows then, three over two, on a
  // six-column grid so both rows fill the width. Four tiles stay one row.
  const two = actions.length > 4
  return (
    <div data-part="panel-help" className="flex flex-col gap-[12px]" style={{ padding: '16px 20px' }}>
      <Caption>{waits ? gate?.help ?? 'Help waits a moment' : 'Need help'}</Caption>
      <div className={two ? 'grid grid-cols-6 gap-[6px]' : 'flex items-stretch gap-[6px]'} role="group" aria-label="Need help" data-rows={two ? 2 : 1}>
        {actions.map((a, i) => (
          <HelpTile
            key={a}
            action={a}
            k={a === 'watch' ? undefined : a}
            busy={!off(a) && waiting === a}
            disabled={off(a)}
            pressed={isPressed(a)}
            height={two ? 48 : 56}
            span={two ? (i < 3 ? 2 : 3) : undefined}
            host={a === 'watch' ? linkHost(watch, HOST_MAX_NARROW) : undefined}
            onClick={() => (a === 'watch' ? watch && openSource(watch) : triggerShortcut(a))}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * One tile: flex-1, 56 high, radius 12, a solid pastel with ink text. Label 12/600, then an 18 px slot for the keycap
 * (or the spinner while busy, or nothing): the label never moves. 6 px side padding, so "Show me" and "Diagram" keep
 * air at their edges. Pressed = an ink ring inside and the pastel ring around it, with aria-pressed.
 */
function HelpTile({
  action,
  k,
  busy,
  disabled,
  pressed,
  height,
  span,
  host,
  onClick
}: {
  action: OptionAction
  k?: KeyName
  busy?: boolean
  disabled?: boolean
  pressed?: boolean
  height: number
  /** Grid columns to span (the two-row layout), or undefined in the one-row flex. */
  span?: number
  /** Watch: where the video opens (linkHost of the URL), shown in the tile so the click's destination is in view. */
  host?: string
  onClick: () => void
}): ReactNode {
  const label = LABEL[action]
  const key = k ? keyLabel(k) : undefined
  return (
    <motion.button
      type="button"
      data-option={action}
      data-pressed={pressed ? action : undefined}
      disabled={disabled}
      aria-pressed={pressed || undefined}
      aria-busy={busy || undefined}
      aria-label={key ? `${label} (${key})` : action === 'watch' ? `Watch this step in the video${host ? ` on ${host}` : ''}` : label}
      title={key ? `${label}  ${key}` : host ? `${label} on ${host}` : undefined}
      // Polish: the core pastel press tint (.mg-press-light), depth and press dip, as core OptionTile; the keyboard focus
      // ring is the global :focus-visible one (styles.css), so the panel has a single ring style.
      className="mg-press mg-press-light relative flex min-w-0 flex-1 cursor-pointer flex-col items-center justify-center gap-[4px] disabled:cursor-default"
      style={{
        height,
        gridColumn: span ? `span ${span} / span ${span}` : undefined,
        padding: '0 6px',
        borderRadius: radius2.card,
        background: actionTone[action],
        color: color.onPastel,
        opacity: disabled ? 0.4 : 1,
        boxShadow: pressed
          ? `0 0 0 2px ${actionTone[action]}, inset 0 0 0 2px ${color.onPastel}`
          : disabled
            ? undefined
            : busy
              ? highlight.base
              : `${highlight.onLight}, ${highlight.base}, ${elevation.raised}`
      }}
      // A busy tile is already pressed in (held tint), so it does not dip again and a second click does not re-ask.
      {...pressMotion(disabled || busy, true)}
      onMouseDown={(e) => e.preventDefault()}
      onClick={busy ? undefined : onClick}
    >
      <span className="max-w-full truncate" style={{ fontSize: type2.xs, fontWeight: 600, lineHeight: '15px' }}>
        {label}
      </span>
      <span className="flex h-[18px] items-center justify-center gap-[4px]" aria-hidden>
        {busy ? <Spinner size={12} c={color.onPastel} track={fill.onPastelKey} /> : k ? <Keycap k={k} on="pastel" size="sm" /> : action === 'watch' ? <WatchIcon size={14} /> : null}
        {!busy && host && (
          <span data-link-host className="whitespace-nowrap text-[11px] font-medium leading-[14px]">
            {host}
          </span>
        )}
      </span>
    </motion.button>
  )
}
