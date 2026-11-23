/**
 * The calm setup card (Michael, Nov 22, the AutoCAD video lesson: "this whole UI looks very bad, very inefficient").
 * features/cards/setupPlan.ts: one white primary per card by tool kind, the quiet "Needs AutoCAD" line, the body
 * without promises the card can't keep, and the card's width between the drawer and the player. The fixtures are the
 * four engine shapes in mock/scenarios/setup-calm*.json.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import type { Payload } from '../src/common/wire'
import { needsLine, planSetup, setupBody, setupCardWidth, toolKind, SETUP_MIN_W } from '../src/renderer/src/features/cards/setupPlan'
import { drawnOnCard, setupWaiting, waitingOnSetup } from '../src/renderer/src/features/cards/setupHold'
import { isSetupDownloadUrl } from '../src/main/safeOpen'

type Card = Payload<'card'>

/** The setup card a stage scenario sends (mock/scenarios/<name>.json). */
function fixture(name: string): Card {
  const s = JSON.parse(readFileSync(join(__dirname, '..', 'mock', 'scenarios', `${name}.json`), 'utf8'))
  const events = Object.values(s.segments as Record<string, Array<{ type: string; payload: unknown }>>).flat()
  return events.find((e) => e.type === 'card')!.payload as Card
}

test('AutoCAD with the app buttons: Get AutoCAD leads, Try FreeCAD and I have it stay quiet', () => {
  const c = fixture('setup-calm')
  const p = planSetup(c)
  assert.deepEqual(p.primary, { do: 'card', action: 'get_it', tool: 'autocad', label: 'Get AutoCAD' })
  assert.deepEqual(p.secondary.map((b) => b.label), ['Try FreeCAD', 'I have it'])
  assert.deepEqual(p.owns, ['autocad'])
  // the video plays, the drawer reads as usual with one quiet line
  assert.equal(setupWaiting(c), false)
  assert.equal(waitingOnSetup(c), false)
  assert.equal(needsLine(c), 'Needs AutoCAD')
})

test('I have it leads only when the scan saw AutoCAD on this Mac', () => {
  const c = fixture('setup-calm')
  const seen: Card = { ...c, setup: { ...c.setup!, items: c.setup!.items.map((x) => (x.tool === 'autocad' ? { ...x, installed: true } : x)) } }
  assert.equal(planSetup(seen).primary?.label, 'I have it')
  assert.deepEqual(planSetup(seen).secondary.map((b) => b.label), ['Try FreeCAD', 'Get AutoCAD'])
})

test('no Mac version: the free alternative leads, Get is not offered', () => {
  const c = fixture('setup-calm')
  const win: Card = { ...c, setup: { ...c.setup!, items: c.setup!.items.map((x) => (x.tool === 'autocad' ? { ...x, noMac: true } : x)) } }
  assert.equal(planSetup(win).primary?.label, 'Try FreeCAD')
  assert.deepEqual(planSetup(win).secondary, [])
})

test("today's engine: the AutoCAD row's own actions draw Get AutoCAD, Try FreeCAD and I have it", () => {
  // integration/live with APP_RENDERS_APP_ACTIONS False: card.actions is [install, skip_setup], the row still offers
  // [have_it, get_it, alternative, skip] (server/workspace/apps.py item_actions) and the engine handles all three.
  const c = fixture('setup-calm-today')
  assert.deepEqual(c.actions, ['install', 'skip_setup'])
  const p = planSetup(c)
  assert.deepEqual(p.primary, { do: 'card', action: 'get_it', tool: 'autocad', label: 'Get AutoCAD' })
  assert.deepEqual(p.secondary, [
    { do: 'card', action: 'alternative', tool: 'autocad', label: 'Try FreeCAD' },
    { do: 'card', action: 'have_it', tool: 'autocad', label: 'I have it' }
  ])
  // the AutoCAD row draws no second Get, FreeCAD's offered row no second Install
  assert.deepEqual(p.owns.sort(), ['autocad', 'freecad'])
  assert.equal(drawnOnCard(c.actions, c.setup!.items.find((x) => x.tool === 'autocad')!), true)
  // FreeCAD is the other choice, not a second need
  assert.equal(needsLine(c), 'Needs AutoCAD')
  assert.equal(setupWaiting(c), false)
  // once the learner picks FreeCAD (using), its row's Install leads
  const picked: Card = { ...c, setup: { ...c.setup!, items: c.setup!.items.map((x) => (x.tool === 'autocad' ? { ...x, using: 'FreeCAD', actions: [] } : x)) } }
  assert.deepEqual(planSetup(picked).primary, { do: 'install', tool: 'freecad', label: 'Install FreeCAD' })
})

// A smart-setup row always carries actions; a licensed row without them only comes from an engine older than both.
// Main may refuse its page (Copy link then), which is still better than a card with nothing to press.
test('an older engine row without actions still gets Get <app> as a link', () => {
  const c = fixture('setup-calm-today')
  const old: Card = { ...c, setup: { ...c.setup!, items: c.setup!.items.map(({ actions: _a, ...x }) => x) } }
  const p = planSetup(old)
  assert.equal(p.primary?.do, 'link')
  assert.equal(p.primary?.label, 'Get AutoCAD')
  assert.deepEqual(p.secondary, [{ do: 'install', tool: 'freecad', label: 'Install FreeCAD' }])
})

test("every link a plan draws is one main's setup list opens (no primary main would refuse)", () => {
  // Fix round 1: Get AutoCAD went to main's open:external, which has no autodesk.com: the first click opened nothing.
  const states = [{}, { freecad: { running: true } }, { numpy: { ok: true } }]
  for (const name of ['setup-calm', 'setup-calm-today', 'setup-calm-install', 'setup-calm-old']) {
    const c = fixture(name)
    for (const installs of states) {
      const p = planSetup(c, installs)
      for (const b of [p.primary, ...p.secondary]) {
        if (b?.do !== 'link') continue
        assert.equal(isSetupDownloadUrl(b.url), true, `${name}: ${b.label} -> ${b.url} is not on main's setup list`)
      }
    }
  }
})

test("the old engine in Michael's screenshot: no editor talk, no Install now?, the video plays", () => {
  const c = fixture('setup-calm-old')
  assert.equal(setupBody(c), 'Missing: autocad.')
  assert.equal(planSetup(c).primary, undefined) // nothing can get AutoCAD here: Skip stays a quiet link
  assert.equal(setupWaiting(c), false)
  assert.equal(needsLine(c), 'Needs autocad')
  assert.equal(toolKind(c.setup!.items[0]), 'none')
})

test('packages: Install all leads and the video waits; one left, Install <it>', () => {
  const c = fixture('setup-calm-install')
  assert.deepEqual(planSetup(c).primary, { do: 'install_all', label: 'Install all' })
  assert.equal(setupWaiting(c), true)
  assert.equal(needsLine(c), 'Needs NumPy, pandas')
  assert.equal(setupBody(c), 'Missing: NumPy, pandas. Install now?')
  const one = planSetup(c, { numpy: { ok: true } })
  assert.deepEqual(one.primary, { do: 'install', tool: 'pandas', label: 'Install pandas' })
  assert.equal(needsLine(c, (x) => x.label.toUpperCase()), 'Needs NUMPY, PANDAS')
})

test('a web app opens; a ready card has no plan (its own actions decide)', () => {
  const web: Card = { kind: 'setup', title: 'This lesson uses Figma', body: 'Nothing to install.', actions: ['skip_setup'],
    setup: { editorNeeded: false, items: [{ tool: 'figma', label: 'Figma', kind: 'web_app', why: 'Design in the browser.', needed: true, installed: false, ok: false,
      install: { method: 'open', url: 'https://www.figma.com' }, setupKind: 'web_app' }] } }
  assert.deepEqual(planSetup(web).primary, { do: 'link', tool: 'figma', url: 'https://www.figma.com', label: 'Open Figma' })
  const ready: Card = { ...web, setup: { ...web.setup!, items: web.setup!.items.map((x) => ({ ...x, ok: true })) } }
  assert.equal(planSetup(ready).primary, undefined)
  assert.equal(needsLine(ready), undefined)
})

test('the setup card fits between the drawer and the player', () => {
  const left = { open: true, at: 'left' as const, w: 340 }
  // 1440 wide: drawer 8..348, player from 872: room 492, the card keeps 420
  assert.equal(setupCardWidth(1440, true, left, 420), 420)
  // 1280 wide: player from 776, room 396: the card narrows
  assert.equal(setupCardWidth(1280, true, left, 420), 396)
  // never below the minimum; a "Just teach me" lesson keeps the usual width
  assert.equal(setupCardWidth(900, true, left, 420), SETUP_MIN_W)
  // attached to the notch (never steps aside): it grows evenly from the centre, so half of it fits left of the player
  // 1512 wide (MacBook Pro 14): player from 915, centre 756: 2 x (899 - 756) = 286
  assert.equal(setupCardWidth(1512, true, left, 420, 756), 286)
  // 1728 wide (MacBook Pro 16): player from 1045, centre 864: 2 x 165 = 330
  assert.equal(setupCardWidth(1728, true, left, 420, 864), 330)
  assert.equal(setupCardWidth(1280, false, left, 420), 420)
  assert.equal(setupCardWidth(1280, true, { ...left, open: false }, 420), 420)
})

test('no editor wording and no "Set up first" in the player or drawer copy', () => {
  const read = (...p: string[]): string => readFileSync(join(__dirname, '..', 'src', 'renderer', 'src', 'features', ...p), 'utf8')
  const player = read('player', 'Player.tsx')
  const drawer = read('drawer', 'Drawer.tsx')
  assert.doesNotMatch(player.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, ''), /Set up first/)
  assert.doesNotMatch(drawer.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, ''), /Waiting on setup/)
})
