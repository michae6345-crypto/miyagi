/**
 * Feature: tips. Browser stage only (never in Electron).
 *
 *   ?scenario=tips                 idle pill: the launcher's tip, then the menu bar item's
 *   ?scenario=tips&tipsDemo=lesson  a lesson panel from the start: Check my work, then Need help
 *   &panel=mini                    (the drawer's own stage switch) collapses it: the Mini tip
 *   &tips=reset                    forget what was seen (any ?tips turns tips on in another scenario)
 *
 * Stands in for main's menu bar item position (Core request 2: `launch:tray-bounds`) with a spot in the stage
 * desktop's menu bar, where the layer also draws a stand-in tree (StageTray) so the mark points at something.
 */
import type { Outgoing } from '../../../../common/wire'
import { bridge, isElectron, registerWebHandler, STAGE } from '../../bridge'
import { onMessage } from '../../core/bus'
import { tipsEnabled } from './store'

export const TRAY_CHANNEL = 'launch:tray-bounds'

/** Screen rect of the stand-in menu bar item: left of the stage desktop's battery, in the 28 px menu bar. */
export const stageTray = !isElectron && tipsEnabled ? { x: STAGE.width - 276, y: 3, width: 24, height: 22 } : undefined

if (stageTray) registerWebHandler(TRAY_CHANNEL, () => stageTray)

const demo = !isElectron && typeof location !== 'undefined' ? new URLSearchParams(location.search).get('tipsDemo') : null
if (demo === 'lesson') {
  let sent = false
  // After the scenario's idle status: the mock is connected and listening.
  onMessage('status', () => {
    if (sent) return
    sent = true
    setTimeout(() => bridge.send({ type: 'stage.tips:lesson', payload: {} } as unknown as Outgoing), 200)
  })
}
