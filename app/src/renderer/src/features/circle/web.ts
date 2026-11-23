/**
 * Feature: circle. The browser stage's stand-in for a hand and for the engine's answer (nothing here runs in Electron).
 *
 * Push to talk's own stage mock (features/ptt/web.ts, ?ptt=<script>) plays the hold; this draws a loose loop while the
 * circle is armed and, for `answered`, answers the ask the way the engine would (card {kind: "answer", askId}) through
 * the same bus every engine message takes. The answer's words are mock data: mock/scenarios/circle.json, segment
 * `circle_answer` (played here, with the ask's askId added to its card).
 *
 *   ?circle=draw       draw and keep holding (pair with ?ptt=listen): the ink mid-ask
 *   ?circle=answered   draw, let go, get an answer (pair with ?ptt=empty: nothing said, so the ask is "What is this?")
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

  if (mode === 'draw' || mode === 'answered') {
    let drewFor = ''
    const answered = new Set<string>()
    useCircle.subscribe((s) => {
      const st = s.state
      if (st.k === 'armed' && drewFor !== st.session) {
        drewFor = st.session
        setTimeout(draw, 40)
      }
      if (mode === 'answered' && st.k === 'asking' && !answered.has(st.askId)) {
        const { askId } = st
        answered.add(askId)
        let at = 0
        for (const item of scenario.segments.circle_answer) {
          at += item.wait ?? 0
          const payload = item.type === 'card' ? { ...item.payload, askId } : item.payload
          setTimeout(() => dispatch({ type: item.type, payload } as Incoming), at)
        }
      }
    })
  }
}
