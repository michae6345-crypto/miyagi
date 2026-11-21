/**
 * Feature: drawer (v2, A1). Browser stage only: `?panel=working|checking|notyet|hint|passed|mini` puts the lesson
 * panel in that state once the scenario's first step starts, for review and screenshots:
 *   ?scenario=lesson-panel&panel=notyet&os=mac&size=1440x900&clean
 * It asks the inline mock for the scenario's own segment (a `stage.panel:<state>` trigger in
 * mock/scenarios/lesson-panel.json), so every state is made of real engine events. Checking is held (no answer comes).
 * Never in Electron, and only once per page load.
 */
import type { Outgoing } from '../../../../../common/wire'
import { bridge, isElectron } from '../../../bridge'
import { onMessage } from '../../../core/bus'
import { collapsePanel } from '../store'
import { setStageChecking } from './panelStore'

const STATES = ['working', 'checking', 'notyet', 'hint', 'passed', 'mini'] as const
type StageState = (typeof STATES)[number]

const wanted = ((): StageState | undefined => {
  if (isElectron || typeof location === 'undefined') return undefined
  const v = new URLSearchParams(location.search).get('panel')
  return STATES.find((s) => s === v)
})()

/** After the step's own spotlight and checks have settled. */
const SETTLE_MS = 400

if (wanted && wanted !== 'working') {
  let done = false
  onMessage('step.started', () => {
    if (done) return
    done = true
    setTimeout(() => {
      if (wanted === 'mini') return collapsePanel()
      if (wanted === 'checking') setStageChecking(true)
      bridge.send({ type: `stage.panel:${wanted}`, payload: {} } as unknown as Outgoing)
    }, SETTLE_MS)
  })
}
