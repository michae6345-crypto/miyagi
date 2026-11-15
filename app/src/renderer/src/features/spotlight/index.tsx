/** Feature: spotlight (screen-first). Dim + rounded cut-out with a hairline ring at the engine's rect + caption. */
import { useEffect, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { notify, useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { dockRect } from '../player/dock'
import { hole, isUsableRect, MIN_VISIBLE_SHARE, overlapShare, sameRect, toLocal } from './place'
import { Spotlight, type Extra } from './Spotlight'
import { spotlightMode, useSpotlight } from './store'

const mode = spotlightMode()

function SpotlightLayer({ layout }: { layout: Layout }): ReactNode {
  const t = useSpotlight((s) => s.target)
  const targets = useSpotlight((s) => s.targets)
  // A text lesson's "type here" target: the soft dim. A Show me answer keeps the strong one (audit A6).
  const showMe = useSpotlight((s) => s.showMe)
  const textLesson = useLesson((s) => s.lesson?.mode === 'lesson')
  const screen = { x: 0, y: 0, w: layout.width, h: layout.height }
  const wa = layout.workArea
  // Engine rects are screen points from the primary display's top-left; this window starts at layout.origin
  // (core opens the overlay on the primary display).
  const local = t && isUsableRect(t.rect) ? toLocal(t.rect, layout.origin) : undefined
  // Draw only what's really on this display; a hole mostly off-screen isn't worth a dim.
  const here = local && overlapShare(hole(local), screen) >= MIN_VISIBLE_SHARE ? local : undefined

  // Nothing to point at (an empty or zero-size rect, or off the primary display): say it on the pill
  // instead of showing nothing. Once per target: a re-sent identical spotlight keeps the same object.
  useEffect(() => {
    if (t && !here) notify(t.caption?.trim() || 'Not on this screen')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t])

  // The coach's other targets (card.targets / offtrack.targets), minus the one the spotlight is on.
  const extras: Extra[] = here
    ? targets
        .filter((x) => !(t && sameRect(x.rect, t.rect, 12)))
        .map((x) => ({ id: String(x.boxId), label: x.label, rect: toLocal(x.rect, layout.origin) }))
        .filter((x) => overlapShare(hole(x.rect), screen) >= MIN_VISIBLE_SHARE)
    : []

  // In Electron the lesson player is its own window (docked right 40%), so the overlay DOM can't see it:
  // keep the caption off it using the player's own dock math. (In the stage it's also in the DOM.)
  // A "Just teach me" lesson has no player (main/features/player.ts keeps it hidden): avoiding its empty dock
  // flipped the caption left, over the Explorer (Michael's audit A7).
  const playerOn = useLesson((s) => !!s.lesson && s.lesson.mode !== 'lesson')
  const dock = playerOn ? dockRect(wa) : undefined
  const avoid = dock ? [{ x: dock.x, y: dock.y, w: dock.width, h: dock.height }] : []
  return (
    <Spotlight
      target={here && t}
      rect={here}
      extras={extras}
      bounds={{ x: wa.x, y: wa.y, w: wa.width, h: wa.height }}
      avoid={avoid}
      mode={mode}
      soft={textLesson && !showMe}
      showCaption={!!here}
    />
  )
}

export default defineFeature({ id: 'spotlight', overlayLayers: [{ id: 'spotlight', z: 10, Component: SpotlightLayer }] })
