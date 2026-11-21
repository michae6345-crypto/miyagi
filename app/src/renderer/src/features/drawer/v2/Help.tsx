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
 * Every tile keeps the same height and a keycap-height slot (Watch has no key yet: an empty slot, Core request), so the
 * five labels share one baseline.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { useShallow } from 'zustand/react/shallow'
import { notify, useLesson, useThinking } from '../../../core/lesson'
import { triggerShortcut, usePressed, type ActionShortcut } from '../../../core/shortcuts'
import { actionTone, color, fill, radius2, type2, type OptionAction } from '../../../core/theme'
import { Spinner } from '../../../core/ui/atoms'
import { Keycap, keyLabel, type KeyName } from '../../../core/ui/Keycap'
import { useCards } from '../../cards/store'
import { useDiagram } from '../../diagrams/store'
import { openSource } from '../store'
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

/** `waiting`: useWaitingOn(), called once by the panel (its timer notifies, so it must run in one place only). */
export function Help({ pressed, watchStart, waiting }: { pressed?: OptionAction; watchStart?: number; waiting?: OptionAction }): ReactNode {
  const explainOpen = useCards((c) => c.card?.kind === 'explain')
  const diagramOpen = useDiagram((d) => d.open)
  const watch = useWatchUrl(watchStart)
  const actions: OptionAction[] = watch ? [...TILES, 'watch'] : TILES
  const isPressed = (a: OptionAction): boolean => a === pressed || (a === 'explain' && explainOpen) || (a === 'diagram' && diagramOpen)
  return (
    <div data-part="panel-help" className="flex flex-col gap-[12px]" style={{ padding: '16px 16px 16px 20px' }}>
      <Caption>Need help</Caption>
      <div className="flex items-stretch gap-[6px]" role="group" aria-label="Need help">
        {actions.map((a) => (
          <HelpTile
            key={a}
            action={a}
            k={a === 'watch' ? undefined : a}
            busy={waiting === a}
            pressed={isPressed(a)}
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
function HelpTile({ action, k, busy, pressed, onClick }: { action: OptionAction; k?: KeyName; busy?: boolean; pressed?: boolean; onClick: () => void }): ReactNode {
  const label = LABEL[action]
  const key = k ? keyLabel(k) : undefined
  return (
    <motion.button
      type="button"
      data-option={action}
      data-pressed={pressed ? action : undefined}
      aria-pressed={pressed || undefined}
      aria-busy={busy || undefined}
      aria-label={key ? `${label} (${key})` : action === 'watch' ? 'Watch this step in the video' : label}
      title={key ? `${label}  ${key}` : undefined}
      className="relative flex min-w-0 flex-1 cursor-pointer flex-col items-center justify-center gap-[4px] outline-none focus-visible:[box-shadow:0_0_0_2px_var(--tile-focus)]"
      style={{
        height: 56,
        padding: '0 6px',
        borderRadius: radius2.card,
        background: actionTone[action],
        color: color.onAccent,
        boxShadow: pressed ? `0 0 0 2px ${actionTone[action]}, inset 0 0 0 2px ${color.onAccent}` : undefined,
        ['--tile-focus' as string]: color.text
      }}
      whileHover={{ filter: 'brightness(0.95)' }}
      whileTap={{ scale: 0.95, filter: 'brightness(0.9)' }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <span className="max-w-full truncate" style={{ fontSize: type2.xs, fontWeight: 600, lineHeight: '15px' }}>
        {label}
      </span>
      <span className="flex h-[18px] items-center justify-center" aria-hidden>
        {busy ? <Spinner size={12} c={color.onAccent} track={fill.onAccentKey} /> : k ? <Keycap k={k} on="accent" size="sm" /> : null}
      </span>
    </motion.button>
  )
}
