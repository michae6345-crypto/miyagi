/**
 * Feature: drawer (v2, A1). "Need help" (Les-Anatomy "Help row, pastel"): Explain, Hint, Show me, Diagram, Watch as
 * core OptionTiles (BRAND.md pastels, keycaps from the platform; Watch has none, decision 3).
 *
 *   Explain / Hint / Show me / Diagram  triggerShortcut(kind): the same path as the keys, so the spinner, the Diagram
 *                                       flyout and the engine all behave as before.
 *   Watch                               the step's clip in the browser (a "Just teach me" lesson has no player): the
 *                                       lesson's video at the step's start. Hidden when the step has no clip.
 * The open hint's tile is drawn pressed (Les-Hint: an ink ring inside, its pastel around it).
 */
import type { ReactNode } from 'react'
import { useLesson, useThinking } from '../../../core/lesson'
import { triggerShortcut, usePressed, type ActionShortcut } from '../../../core/shortcuts'
import { actionTone, color, radius2, type OptionAction } from '../../../core/theme'
import { OptionTile } from '../../../core/ui/HelpRow'
import { openSource } from '../store'
import { Caption } from './ui'

type Tile = Exclude<OptionAction, 'watch'> & ActionShortcut
const TILES: Tile[] = ['explain', 'hint', 'show_me', 'diagram']

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

export function Help({ pressed, watchStart }: { pressed?: OptionAction; watchStart?: number }): ReactNode {
  const thinking = useThinking()
  const busyKind = usePressed((p) => p.kind)
  const watch = useWatchUrl(watchStart)
  const actions: OptionAction[] = watch ? [...TILES, 'watch'] : TILES
  return (
    <div data-part="panel-help" className="flex flex-col gap-[12px]" style={{ padding: '16px 20px 16px' }}>
      <Caption>Need help</Caption>
      {/*
        Five tiles in 320 px leave each label ~50 px after core OptionTile's 4 px side padding, and "Show me" truncated.
        The mockup's tiles have no side padding: drop it here (Core request 2) and keep a 6 px gap.
      */}
      <div className="flex items-stretch gap-[6px] [&_button[data-option]]:!px-0">
        {actions.map((a) => {
          const tile = (
            <OptionTile
              key={a}
              action={a}
              busy={a !== 'watch' && thinking && busyKind === a}
              onClick={() => (a === 'watch' ? watch && openSource(watch) : triggerShortcut(a))}
            />
          )
          if (a !== pressed) return tile
          return (
            <div
              key={a}
              aria-pressed
              data-pressed={a}
              className="relative flex min-w-0 flex-1"
              style={{ borderRadius: radius2.card, boxShadow: `0 0 0 2px ${actionTone[a]}` }}
            >
              {tile}
              <span aria-hidden className="pointer-events-none absolute inset-0" style={{ borderRadius: radius2.card, boxShadow: `inset 0 0 0 2px ${color.onAccent}` }} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
