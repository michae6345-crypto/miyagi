// trackOverlayLifecycle: display swap, lock/unlock and the launch gate (a hidden overlay must stay hidden).
import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { EventEmitter } from 'node:events'
import { OVERLAY_RESTORE_MS, trackOverlayLifecycle } from '../src/main/platform'

const mac = process.platform === 'darwin'
const opts = { skip: !mac }

function setup(visible: boolean, canShow?: () => boolean) {
  const log: string[] = []
  const st = { visible, destroyed: false }
  const win = {
    isDestroyed: () => st.destroyed,
    isVisible: () => st.visible,
    setOpacity: (o: number) => void log.push(`opacity:${o}`),
    setBounds: () => undefined,
    showInactive: () => {
      st.visible = true
      log.push('show')
    },
    hide: () => {
      st.visible = false
      log.push('hide')
    },
    moveTop: () => void log.push('moveTop'),
    setAlwaysOnTop: () => undefined,
    setVisibleOnAllWorkspaces: () => undefined
  }
  const screen = new EventEmitter()
  const power = new EventEmitter()
  let refits = 0
  const stop = trackOverlayLifecycle(win as never, { screen, powerMonitor: power, canShow }, () => void refits++)
  return { win, st, log, screen, power, stop, refits: () => refits }
}
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
const settle = () => wait(OVERLAY_RESTORE_MS + 60)
let stops: Array<() => void> = []
beforeEach(() => void (stops = []))
afterEach(() => stops.forEach((f) => f()))

test('display swap fades the overlay, then refits and restores it', opts, async () => {
  const t = setup(true)
  stops.push(t.stop)
  t.screen.emit('display-metrics-changed')
  assert.deepEqual(t.log, ['opacity:0'])
  await settle()
  assert.equal(t.refits(), 1)
  assert.equal(t.log.at(-1), 'opacity:1')
  assert.equal(t.st.visible, true)
})

test('a burst of display events is one restore', opts, async () => {
  const t = setup(true)
  stops.push(t.stop)
  t.screen.emit('display-added')
  t.screen.emit('display-removed')
  t.screen.emit('display-metrics-changed')
  await settle()
  assert.equal(t.refits(), 1)
})

test('display change while the gate keeps the overlay hidden does not show it', opts, async () => {
  const t = setup(false)
  stops.push(t.stop)
  t.screen.emit('display-added')
  await settle()
  assert.equal(t.st.visible, false)
  assert.ok(!t.log.includes('show'))
  // ...but the fade is undone, so when the gate shows it later it is not invisible
  assert.equal(t.log.filter((l) => l.startsWith('opacity:')).at(-1), 'opacity:1')
})

test('lock then unlock while the overlay was hidden does not show it', opts, async () => {
  const t = setup(false)
  stops.push(t.stop)
  t.power.emit('lock-screen')
  t.power.emit('unlock-screen')
  await settle()
  assert.equal(t.st.visible, false)
  assert.ok(!t.log.includes('show'))
  assert.equal(t.log.filter((l) => l.startsWith('opacity:')).at(-1), 'opacity:1')
})

test('lock hides a visible overlay and unlock shows it again', opts, async () => {
  const t = setup(true)
  stops.push(t.stop)
  t.power.emit('lock-screen')
  assert.equal(t.st.visible, false)
  await settle()
  assert.equal(t.st.visible, false, 'stays hidden while locked')
  t.power.emit('unlock-screen')
  await settle()
  assert.equal(t.st.visible, true)
  assert.equal(t.log.at(-1), 'opacity:1')
})

test('canShow false (gate closed during the pause) keeps it hidden', opts, async () => {
  let open = true
  const t = setup(true, () => open)
  stops.push(t.stop)
  t.power.emit('lock-screen')
  open = false
  t.power.emit('unlock-screen')
  await settle()
  assert.equal(t.st.visible, false)
})

test('stop cancels a pending restore and removes listeners', opts, async () => {
  const t = setup(true)
  t.screen.emit('display-added')
  t.stop()
  await settle()
  assert.equal(t.refits(), 0)
  assert.equal(t.screen.listenerCount('display-added'), 0)
})

test('a destroyed window is left alone', opts, async () => {
  const t = setup(true)
  stops.push(t.stop)
  t.st.destroyed = true
  t.screen.emit('display-added')
  t.power.emit('lock-screen')
  await settle()
  assert.deepEqual(t.log, [])
})
