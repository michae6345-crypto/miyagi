/**
 * Smart setup (Nov 22, Michael's AutoCAD lesson): the setup card is a companion, not a gate. The video holds only when
 * the engine says setup.holdVideo is true (an older engine's card without the field keeps the old rule), the drawer's
 * "Waiting on setup" skips settled rows and cards that let the video play, and the card draws I have it / Get it /
 * Try FreeCAD (features/cards/setupHold.ts, features/cards/index.tsx ACTION).
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import type { Payload } from '../src/common/wire'
import { drawnOnCard, rowSettled, rowWaiting, setupWaiting, waitingOnSetup } from '../src/renderer/src/features/cards/setupHold'

type Card = Payload<'card'>
type Row = NonNullable<Card['items']>[number]

const VENDOR = 'https://www.autodesk.com/products/autocad/free-trial'

const vscode: Row = {
  tool: 'vscode', label: 'Visual Studio Code', kind: 'editor', why: 'No editor needed: all the work happens in AutoCAD.',
  needed: false, installed: true, ok: true, install: { method: 'brew_cask' }, setupKind: 'free_app', actions: []
}
const autocad = (extra: Partial<Row> = {}): Row => ({
  tool: 'autocad', label: 'AutoCAD', kind: 'app', why: 'Used to draw the car profile.', needed: true, installed: false, ok: false,
  install: { method: 'download', url: VENDOR }, setupKind: 'licensed_app', actions: ['have_it', 'get_it', 'alternative', 'skip'],
  vendorUrl: VENDOR, vendorName: 'Autodesk', alternative: { name: 'FreeCAD', url: 'https://www.freecad.org/downloads.php', tool: 'freecad' },
  ...extra
})

/** The engine's AutoCAD card once the app draws the buttons (server/workspace/setup.py, APP_RENDERS_APP_ACTIONS). */
const autocadCard = (setup: Partial<NonNullable<Card['setup']>> = {}, rows: Row[] = [vscode, autocad()]): Card => ({
  kind: 'setup', title: 'This lesson uses AutoCAD', body: 'Have AutoCAD already? Or try FreeCAD, free.',
  actions: ['have_it', 'get_it', 'alternative', 'skip_setup'],
  setup: {
    editorNeeded: false, items: rows, resources: [],
    actionLabels: { have_it: 'I have it', get_it: 'Get AutoCAD', alternative: 'Try FreeCAD', skip_setup: 'Skip' },
    holdVideo: false, ...setup
  }
})

test('the AutoCAD card lets the video play and the drawer is not waiting', () => {
  const card = autocadCard()
  assert.equal(setupWaiting(card), false)
  assert.equal(waitingOnSetup(card), false)
})

test('holdVideo true holds the video: the step on screen needs a tool Install can get now', () => {
  const card = autocadCard({ holdVideo: true })
  assert.equal(setupWaiting(card), true)
  assert.equal(waitingOnSetup(card), true)
})

test('an older engine without holdVideo holds for a card with something to do, never for Skip alone', () => {
  const skipOnly: Card = { kind: 'setup', title: 'Set up first', body: 'Missing: autocad.', actions: ['skip_setup'],
    setup: { editorNeeded: false, items: [{ tool: 'autocad', label: 'autocad', kind: 'app', why: 'CAD', needed: true,
      installed: false, ok: false, install: { method: 'none' } }] } }
  assert.equal(setupWaiting(skipOnly), false)
})

test('an older engine without holdVideo keeps the old rule: any setup card with buttons holds', () => {
  const old: Card = { kind: 'setup', title: 'Set up first', body: 'Missing: numpy. Install now?', actions: ['install', 'skip_setup'],
    setup: { editorNeeded: true, items: [{ tool: 'numpy', label: 'NumPy', kind: 'python_package', why: 'imported', needed: true,
      installed: false, ok: false, install: { method: 'pip' } }] } }
  assert.equal(setupWaiting(old), true)
  assert.equal(waitingOnSetup(old), true)
  const note: Card = { kind: 'setup', title: 'NumPy installed', body: '', actions: [], dismissAfterMs: 4000 }
  assert.equal(setupWaiting(note), false)
})

test('a row the learner settled never waits: I have it, or FreeCAD instead', () => {
  assert.equal(rowWaiting(autocad()), true)
  for (const row of [autocad({ haveIt: true }), autocad({ using: 'FreeCAD' })]) {
    assert.equal(rowWaiting(row), false)
    assert.equal(rowSettled(row), true)
    assert.equal(waitingOnSetup(autocadCard({ holdVideo: true }, [vscode, row])), false)
  }
})

test('the licensed row keeps no Get it of its own when the card draws Get AutoCAD', () => {
  assert.equal(drawnOnCard(autocadCard().actions, autocad()), true)
  // today's engine (flag off): card actions install / skip_setup, but the row's own actions still draw on the card
  assert.equal(drawnOnCard(['install', 'skip_setup'], autocad()), true)
  // an older engine's row with no actions keeps its own button
  assert.equal(drawnOnCard(['install', 'skip_setup'], autocad({ actions: undefined })), false)
  assert.equal(drawnOnCard(autocadCard().actions, vscode), false)
})

test('the card draws I have it, Get it and the free alternative (CardActions keeps only ACTION keys)', () => {
  const src = readFileSync(join(__dirname, '..', 'src', 'renderer', 'src', 'features', 'cards', 'index.tsx'), 'utf8')
  const map = src.slice(src.indexOf('const ACTION:'), src.indexOf('/** Card actions drawn as pastel'))
  for (const a of autocadCard().actions ?? []) assert.match(map, new RegExp(`\\b${a}: \\{ label:`), `ACTION has no ${a}`)
  // one white primary per surface: on a setup card the calm plan (setupPlan.ts) picks it, so none of them is a primary kind
  for (const a of ['have_it', 'get_it', 'alternative']) assert.doesNotMatch(map, new RegExp(`${a}: \\{[^}]*primary`))
})
