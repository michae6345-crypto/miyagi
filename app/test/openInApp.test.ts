/**
 * open_in_app (Nov 24, agents/app-blender-polish.md): an app lesson's setup card opens the lesson's scene in its desktop
 * app. The card draws ONE white primary (ACTION.open_in_app, primary), labelled by the engine (setup.actionLabels), and
 * the press sends action {kind: "open_in_app"} with no text, once, then settles (store SETTLE) like Open VS Code. The card
 * sends holdVideo false, so the video never holds. Offline, no window.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'
import type { Payload } from '../src/common/wire'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'open-in-app-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
// features/cards' panel routing (import.meta.glob, the drawer) is not under test: nothing is routed to a panel.
const PANEL = stub('panel.mjs', 'export const isRouted = () => false\nexport const panelShown = () => false')
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === './panel' && context.parentURL?.includes('/features/cards/store')) return { url: PANEL, shortCircuit: true }
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

const sends: { type: string; payload: Record<string, unknown> }[] = []
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const tut = {
  platform: { os: 'darwin', keys: {}, pillTop: 0 },
  onEvent: noop,
  onStatus: noop,
  on: noop,
  onFeature: () => () => {},
  emit: () => {},
  ready: () => {},
  send: (m: { type: string; payload: Record<string, unknown> }) => void sends.push(m),
  invoke: (): Promise<unknown> => Promise.resolve(null)
}
g.window ??= { tut, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document ??= { documentElement: { dataset: { route: 'overlay' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location ??= { search: '' }

mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 2_000_000 })

const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { cardAct, useCards } = require('../src/renderer/src/features/cards/store') as typeof import('../src/renderer/src/features/cards/store')
const { setupWaiting, waitingOnSetup } = require('../src/renderer/src/features/cards/setupHold') as typeof import('../src/renderer/src/features/cards/setupHold')
const { planSetup, PLAN_ACTIONS } = require('../src/renderer/src/features/cards/setupPlan') as typeof import('../src/renderer/src/features/cards/setupPlan')

type Card = Payload<'card'>

/** The engine's Blender card (engine data: the app's name comes only from the engine, never from UI code). */
const openCard = (extra: Partial<Card> = {}): Card => ({
  kind: 'setup', title: 'Blender is ready', body: 'Open the lesson scene to start.', actions: ['open_in_app'],
  setup: { editorNeeded: false, items: [], resources: [], actionLabels: { open_in_app: 'Open in Blender' }, holdVideo: false },
  ...extra
})

const actions = (): { type: string; payload: Record<string, unknown> }[] => sends.filter((m) => m.type === 'action')

const CARDS = join(__dirname, '..', 'src', 'renderer', 'src', 'features', 'cards')
const index = readFileSync(join(CARDS, 'index.tsx'), 'utf8')
const ACTION_MAP = index.slice(index.indexOf('const ACTION:'), index.indexOf('/** Card actions drawn as pastel'))

describe('open_in_app', () => {
  beforeEach(() => {
    sends.length = 0
    dispatch({ type: 'lesson.ended', payload: {} } as never)
    mock.timers.runAll()
  })
  afterEach(() => mock.timers.runAll())

  test('the ACTION map draws it as the white primary, with an icon, out of the setup plan', () => {
    assert.match(ACTION_MAP, /open_in_app: \{ label: 'Open in app', Icon: \w+, primary: true \}/)
    assert.equal(PLAN_ACTIONS.has('open_in_app'), false, 'the calm setup plan never draws it itself')
    // The card has no rows waiting: the plan picks no primary, so CardActions' primaryOf picks open_in_app.
    assert.equal(planSetup(openCard()).primary, undefined)
    // The engine's label wins (actionLabel): no app name is typed in UI code.
    assert.doesNotMatch(index, /Blender/)
  })

  test('a press sends action {kind: open_in_app} with no text, once, and the card settles', () => {
    dispatch({ type: 'card', payload: openCard() } as never)
    assert.equal(useCards.getState().card?.title, 'Blender is ready')
    cardAct('open_in_app')
    cardAct('open_in_app') // a double click: still one action
    assert.deepEqual(actions().map((m) => m.payload), [{ kind: 'open_in_app' }])
    assert.equal(useCards.getState().pending?.kind, 'open_in_app', 'spins while it opens')
    mock.timers.tick(900)
    mock.timers.tick(200)
    assert.equal(useCards.getState().pending, undefined, 'settled: no endless spinner')
    assert.equal(useCards.getState().card, undefined, 'its only job is done: the card goes back into the island')
  })

  test('beside another button the card stays after the spin; beside Skip alone it goes', () => {
    dispatch({ type: 'card', payload: openCard({ title: 'Blender is ready.', actions: ['open_in_app', 'download'] }) } as never)
    cardAct('open_in_app')
    mock.timers.tick(900)
    mock.timers.tick(200)
    assert.equal(useCards.getState().pending, undefined)
    assert.equal(useCards.getState().card?.title, 'Blender is ready.', 'Download is still a choice')

    dispatch({ type: 'card', payload: openCard({ title: 'Blender is ready!', actions: ['open_in_app', 'skip_setup'] }) } as never)
    cardAct('open_in_app')
    mock.timers.tick(900)
    mock.timers.tick(200)
    assert.equal(useCards.getState().card, undefined, 'Skip only ends the card: nothing is left to do on it')
  })

  test('holdVideo false never holds the video or the drawer', () => {
    assert.equal(setupWaiting(openCard()), false)
    assert.equal(waitingOnSetup(openCard()), false)
  })

  test('cards without it are unchanged: Open VS Code still settles, a plain card still waits on the engine', () => {
    dispatch({ type: 'card', payload: { kind: 'where', title: 'Open calc.py', body: '', actions: ['open_editor'] } } as never)
    cardAct('open_editor')
    assert.deepEqual(actions().map((m) => m.payload), [{ kind: 'open_editor' }])
    mock.timers.tick(900)
    mock.timers.tick(200)
    assert.equal(useCards.getState().card, undefined)

    dispatch({ type: 'card', payload: { kind: 'step', title: 'Not yet', body: '', actions: ['check_step'] } } as never)
    cardAct('check_step')
    mock.timers.tick(900)
    mock.timers.tick(200)
    assert.equal(useCards.getState().pending?.kind, 'check_step', 'waits for the engine, as before')
  })
})
