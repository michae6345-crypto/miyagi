/**
 * Feature: circle. The browser stage's stand-in for a hand and for the engine's answer (nothing here runs in Electron).
 *
 * Push to talk's own stage mock (features/ptt/web.ts, ?ptt=<script>) plays the hold; this draws a loose loop while the
 * circle is armed and answers the ask the way the engine would, through the same bus every engine message takes. The
 * answer's words are mock data: mock/scenarios/circle.json, segments `circle_answer` (one card) and `circle_stream`
 * (an early annotate mark, answer.delta pieces, then the card), played here with the ask's askId added.
 *
 *   ?circle=draw       draw and keep holding (pair with ?ptt=listen): the ink mid-ask
 *   ?circle=answered   draw, let go, get an answer (pair with ?ptt=empty: nothing said, so the ask is "What is this?")
 *   ?circle=stream     the same, the answer streamed (answer.delta), then the final card
 *   ?circle=streaming  the stream stops at the item marked "pause" (no final card): the card mid-stream, for a shot
 *   ?circle-at=x,y,w,h the box to circle, in stage px (default 96,546,565,88)
 *   ?circle-ms=<ms>    how long the loop takes to draw (default 520; a ptt=empty hold is about 600 ms)
 *
 * `window.__circle()` draws the loop again (with a hold already armed).
 */
import type { Incoming } from '../../../../common/wire'
import scenario from '../../../../../mock/scenarios/circle.json'
import { isElectron } from '../../bridge'
import { dispatch } from '../../core/bus'
import { loopPoints } from './geometry'
import { pointerDown, pointerMove, pointerUp, useCircle } from './store'

type Item = { wait?: number; type: string; payload: Record<string, unknown>; pause?: boolean }

/** The scenario item with the ask's id where the engine would put it (card, answer.delta, annotate marks). */
function withAsk(item: Item, askId: string): Record<string, unknown> {
  if (item.type === 'card' || item.type === 'answer.delta') return { ...item.payload, askId }
  if (item.type === 'annotate' && Array.isArray(item.payload.marks)) return { ...item.payload, marks: (item.payload.marks as Record<string, unknown>[]).map((m) => ({ ...m, askId })) }
  return item.payload
}

if (!isElectron && typeof location !== 'undefined') {
  const params = new URLSearchParams(location.search)
  const mode = params.get('circle')
  const [bx, by, bw, bh] = (params.get('circle-at') ?? '96,546,565,88').split(',').map(Number)
  const ms = Number(params.get('circle-ms') ?? 520)

  const draw = (): void => {
    const pts = loopPoints(bx, by, bw, bh)
    const each = Math.max(4, ms / pts.length)
    pointerDown(pts[0])
    pts.slice(1).forEach((p, i) => setTimeout(() => pointerMove(p), (i + 1) * each))
    setTimeout(pointerUp, (pts.length + 1) * each)
  }
  ;(window as unknown as { __circle: () => void }).__circle = draw

  const segment = mode === 'answered' ? 'circle_answer' : mode === 'stream' || mode === 'streaming' ? 'circle_stream' : undefined
  if (mode === 'draw' || segment) {
    let drewFor = ''
    const answered = new Set<string>()
    useCircle.subscribe((s) => {
      const st = s.state
      if (st.k === 'armed' && drewFor !== st.session) {
        drewFor = st.session
        setTimeout(draw, 40)
      }
      if (segment && st.k === 'asking' && !answered.has(st.askId)) {
        const { askId } = st
        answered.add(askId)
        let at = 0
        for (const item of scenario.segments[segment] as Item[]) {
          at += item.wait ?? 0
          setTimeout(() => dispatch({ type: item.type, payload: withAsk(item, askId) } as Incoming), at)
          if (mode === 'streaming' && item.pause) break
        }
      }
    })
  }
}
