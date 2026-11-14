/** Feature: spotlight (screen-first). Dim + rounded cut-out with a hairline ring at the engine's rect + caption. */
import { useEffect, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { notify, useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { dockRect } from '../player/dock'
import { hole, isUsableRect, MIN_VISIBLE_SHARE, overlapShare, toLocal } from './place'
import { Spotlight } from './Spotlight'
import { spotlightMode, useSpotlight } from './store'

const mode = spotlightMode()

function SpotlightLayer({ layout }: { layout: Layout }): ReactNode {
  const t = useSpotlight((s) => s.target)
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

  // In Electron the lesson player is its own window (docked right 40%), so the overlay DOM can't see it:
  // keep the caption off it using the player's own dock math. (In the stage it's also in the DOM.)
  const lessonOn = useLesson((s) => !!s.lesson)
  const dock = lessonOn ? dockRect(wa) : undefined
  const avoid = dock ? [{ x: dock.x, y: dock.y, w: dock.width, h: dock.height }] : []
  return (
    <Spotlight
      target={here && t}
      rect={here}
      bounds={{ x: wa.x, y: wa.y, w: wa.width, h: wa.height }}
      avoid={avoid}
      mode={mode}
      showCaption={!!here}
    />
  )
}

export default defineFeature({ id: 'spotlight', overlayLayers: [{ id: 'spotlight', z: 10, Component: SpotlightLayer }] })
