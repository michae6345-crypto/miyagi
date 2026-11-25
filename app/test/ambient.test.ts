/**
 * features/ambient (help outside a lesson; shared/contracts/AMBIENT-HELP.md), offline:
 *
 *   model     the chip's words, the calm lines, the launcher's two commands, the setup rows, the muted apps
 *   prefs     ambient.set goes out on every engine.hello (only when the hello lists it) and on every change
 *   chip      one at a time, never during a lesson or for a muted app, the same id again only updates it, an id that
 *             had its turn never comes back, {id, clear} fades it, it hides after 20 s
 *   explain   one error.explain per click (the same id again answers from what the card holds), dismiss on close
 *   setup     setup.scan opens the card, Fix sends setup.fix, Fix all goes one by one, a closed card stays closed
 *   help      help.ask with the app, help.steps points bon at the current step, close sends help.nav and ignores re-sends
 * No model is called anywhere: the app only sends commands, and only on a click.
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { beforeEach, describe, test } from 'node:test'
import { pathToFileURL } from 'node:url'

const dir = mkdtempSync(join(tmpdir(), 'ambient-'))
writeFileSync(join(dir, 'scenarios.mjs'), 'export const scenarios = {}')
const SCENARIOS = pathToFileURL(join(dir, 'scenarios.mjs')).href
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier)) return { url: SCENARIOS, shortCircuit: true }
    return next(specifier, context)
  }
})

type Sent = { type: string; payload: Record<string, unknown> }
const sent: Sent[] = []
const store = new Map<string, string>()
const g = globalThis as Record<string, unknown>
g.localStorage = {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, String(v)),
  removeItem: (k: string) => void store.delete(k)
}
g.window = {
  tut: {
    platform: { os: 'darwin', keys: {}, pillTop: 0 },
    onEvent: () => () => {},
    onStatus: () => () => {},
    on: () => () => {},
    emit: () => {},
    ready: () => {},
    send: (m: Sent) => void sent.push(m),
    invoke: (): Promise<unknown> => Promise.resolve(null),
    onFeature: () => () => {}
  },
  addEventListener: () => {},
  removeEventListener: () => {}
}
g.document = { hasFocus: () => true }
g.location = { hash: '', search: '', pathname: '/' }

const M = require('../src/renderer/src/features/ambient/model') as typeof import('../src/renderer/src/features/ambient/model')
const P = require('../src/renderer/src/features/ambient/prefs') as typeof import('../src/renderer/src/features/ambient/prefs')
const S = require('../src/renderer/src/features/ambient/store') as typeof import('../src/renderer/src/features/ambient/store')
const C = require('../src/renderer/src/features/ambient/commands') as typeof import('../src/renderer/src/features/ambient/commands')
const bus = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const lesson = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
const annotate = require('../src/renderer/src/features/annotate/store') as typeof import('../src/renderer/src/features/annotate/store')

const ALL = ['ambient.set', 'error.explain', 'error.dismiss', 'setup.scan', 'setup.fix', 'help.ask', 'help.nav']
const msg = (type: string, payload: unknown): void => bus.dispatch({ type, payload } as never)
const hello = (caps: string[] = ALL): void => msg('engine.hello', { version: 't', contract: '2026-11-20', capabilities: caps })
const of = (type: string): Sent[] => sent.filter((m) => m.type === type)
const words = (s: string): number => s.trim().split(/\s+/).length

const ERR = {
  id: 'err-7c1e09',
  app: 'Terminal',
  kind: 'python_traceback',
  title: "ModuleNotFoundError: No module named 'pandas'",
  lines: ['Traceback (most recent call last):', "ModuleNotFoundError: No module named 'pandas'"],
  file: '~/code/weather-app/app.py',
  line: 3,
  lang: 'python',
  rect: { x: 212, y: 618, w: 520, h: 72, label: 'The error', app: 'Terminal', via: 'ax' },
  at: '2026-11-24T10:42:05-08:00'
} as const
const row = (tool: string, ok: boolean, method = 'pip', extra: Record<string, unknown> = {}): Record<string, unknown> => ({
  tool,
  label: tool,
  kind: 'python_package',
  why: `uses ${tool}`,
  needed: true,
  installed: ok,
  ok,
  install: { method },
  ...extra
})

function fresh(): void {
  S.resetAmbient()
  sent.length = 0
  lesson.useLesson.setState({ lesson: undefined, building: false, stepId: undefined, connected: true })
  P.useAmbientPrefs.setState({ ...M.DEFAULT_AMBIENT })
  hello()
  sent.length = 0
}

describe('model', () => {
  test('the chip and the card speak calmly, from the error itself', () => {
    assert.equal(M.chipLine({ app: 'Terminal' }), 'Error in Terminal')
    assert.equal(M.chipLine({ app: '' }), 'An error')
    assert.equal(M.stopLine(ERR as never), 'Python stopped at line 3')
    assert.equal(M.stopLine({ kind: 'shell_exit', exitCode: 127, app: 'Terminal' }), 'The command stopped (exit 127)')
    assert.equal(M.stopLine({ kind: 'app_dialog', app: 'Blender' }), 'Blender showed an error')
    assert.equal(M.stopLine({ kind: 'compiler', file: 'src/main.ts', line: 12, app: 'Code' }), 'main.ts has an error at line 12')
    assert.equal(M.stopLine({ kind: 'notebook_cell', app: 'Code' }), 'The cell stopped')
  })
  test('every fail is a calm line of 12 words or fewer, with no alarm words', () => {
    for (const f of ['cap', 'offline', 'busy', 'gone', 'no_app', 'failed', undefined])
      for (const what of ['explain', 'help'] as const) {
        const line = M.failLine(f, 1200, what)
        assert.ok(words(line) <= 12, line)
        assert.ok(!/error!|fail|crash|wrong/i.test(line), line)
      }
    assert.match(M.failLine('cap', 1200), /in 20 minutes/)
    assert.equal(M.canRetry('cap'), false)
    assert.equal(M.canRetry('busy'), true)
  })
  test('"set up this project" and friends are the setup command; a topic is not', () => {
    for (const t of ['set up this project', 'set up', 'setu', 'Set up this project.', 'install dependencies', 'install the deps', 'check my environment', 'setup the project'])
      assert.ok(M.isSetupQuery(t), t)
    for (const t of ['se', 'set up a react app', 'install pytorch', 'how do I set up docker', 'settings', 'project management'])
      assert.ok(!M.isSetupQuery(t), t)
  })
  test('"how do I ..." is the help command, with something after it', () => {
    for (const t of ['how do I export this as an STL?', 'How can I undo', 'where is the export button', 'how to add a layer'])
      assert.ok(M.isHowDoI(t), t)
    for (const t of ['how do i', 'neural networks', 'what is a tensor', 'x'.repeat(301)]) assert.ok(!M.isHowDoI(t), t)
  })
  test('setup rows: missing first, installable vs a page vs by hand, never a licensed app installed', () => {
    const items = [row('requests', true), row('pandas', false), row('autocad', false, 'download', { setupKind: 'licensed_app', install: { method: 'download', url: 'https://x' } }), row('mystery', false, 'none'), row('node_modules', false, 'npm')]
    assert.deepEqual(
      M.sortRows(items as never).map((x) => x.tool),
      ['pandas', 'autocad', 'mystery', 'node_modules', 'requests']
    )
    assert.equal(M.rowFix(items[1] as never), 'install')
    assert.equal(M.rowFix(items[2] as never), 'link')
    assert.equal(M.rowFix(items[3] as never), 'none')
    assert.equal(M.rowFix(items[0] as never), 'none')
    assert.deepEqual(M.fixable(items as never), ['pandas', 'node_modules'])
    assert.equal(M.readyLine(3, 7), '3 of 7 ready')
    assert.equal(M.readyLine(7, 7), 'All 7 ready')
    assert.equal(M.readyLine(0, 0), 'Nothing to set up')
    assert.equal(M.rowDetail({ why: 'reads data', from: 'requirements.txt:3' }), 'reads data · requirements.txt:3')
    assert.match(M.scanError('no_project') ?? '', /Open a project folder/)
  })
  test('muted apps: trimmed, no case-duplicates, at most 50; junk prefs fall back to on', () => {
    assert.deepEqual(M.cleanMuted([' Terminal ', 'terminal', '', 3, '1Password']), ['Terminal', '1Password'])
    assert.equal(M.cleanMuted(Array.from({ length: 80 }, (_, i) => `app${i}`)).length, M.MUTED_MAX)
    assert.deepEqual(M.cleanPrefs('junk'), { errors: true, mutedApps: [] })
    assert.deepEqual(M.cleanPrefs({ errors: false, mutedApps: ['A'] }), { errors: false, mutedApps: ['A'] })
  })
})

describe('prefs: ambient.set', () => {
  beforeEach(fresh)
  test('every hello that lists it gets the setting (on by default); one that does not, nothing', () => {
    hello()
    assert.deepEqual(of('ambient.set').at(-1)?.payload, { errors: true, mutedApps: [] })
    sent.length = 0
    hello(['health.get'])
    assert.equal(of('ambient.set').length, 0)
    hello()
  })
  test('turning it off or muting an app tells the engine and is saved', () => {
    P.setOfferErrors(false)
    assert.deepEqual(of('ambient.set').at(-1)?.payload, { errors: false, mutedApps: [] })
    P.muteApp('1Password')
    P.muteApp('1password')
    assert.deepEqual(of('ambient.set').at(-1)?.payload, { errors: false, mutedApps: ['1Password'] })
    assert.deepEqual(JSON.parse(store.get(P.KEY) ?? '{}'), { errors: false, mutedApps: ['1Password'] })
    P.unmuteApp('1PASSWORD')
    assert.deepEqual(P.useAmbientPrefs.getState().mutedApps, [])
  })
})

describe('the error chip', () => {
  beforeEach(fresh)
  test('error.seen outside a lesson shows the chip; nothing is sent', () => {
    msg('error.seen', ERR)
    const s = S.useAmbient.getState()
    assert.equal(s.chip, true)
    assert.equal(s.error?.id, ERR.id)
    assert.equal(sent.length, 0)
  })
  test('never during a lesson, never with the setting off, never for a muted app', () => {
    lesson.useLesson.setState({ stepId: 's1' })
    msg('error.seen', ERR)
    assert.equal(S.useAmbient.getState().chip, false)
    lesson.useLesson.setState({ stepId: undefined })
    P.setOfferErrors(false)
    msg('error.seen', { ...ERR, id: 'err-2' })
    assert.equal(S.useAmbient.getState().chip, false)
    P.setOfferErrors(true)
    P.muteApp('terminal')
    msg('error.seen', { ...ERR, id: 'err-3' })
    assert.equal(S.useAmbient.getState().chip, false)
  })
  test('one at a time: a newer error takes the chip; the same id again only updates it', () => {
    msg('error.seen', ERR)
    msg('error.seen', { ...ERR, again: 2 })
    assert.equal(S.useAmbient.getState().error?.again, 2)
    msg('error.seen', { ...ERR, id: 'err-b', app: 'Code', title: "NameError: name 'df' is not defined" })
    assert.equal(S.useAmbient.getState().error?.id, 'err-b')
    // The first one had its turn: it never comes back as a chip.
    msg('error.seen', ERR)
    assert.equal(S.useAmbient.getState().error?.id, 'err-b')
  })
  test('{id, clear} fades it; a lesson starting takes it away', () => {
    msg('error.seen', ERR)
    msg('error.seen', { id: ERR.id, clear: true })
    assert.equal(S.useAmbient.getState().chip, false)
    msg('error.seen', { ...ERR, id: 'err-c' })
    msg('lesson.ready', { lesson: { id: 'l', title: 't', sources: [] }, steps: [] })
    assert.equal(S.useAmbient.getState().chip, false)
  })
  test('it hides after 20 s unless the pointer rests on it', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] })
    msg('error.seen', ERR)
    S.holdChip(true)
    t.mock.timers.tick(M.CHIP_MS + 100)
    assert.equal(S.useAmbient.getState().chip, true)
    S.holdChip(false)
    t.mock.timers.tick(1600)
    assert.equal(S.useAmbient.getState().chip, false)
    t.mock.timers.reset()
  })
  test('turning the setting off takes the chip away at once', () => {
    msg('error.seen', ERR)
    P.setOfferErrors(false)
    assert.equal(S.useAmbient.getState().chip, false)
  })
})

describe('explain', () => {
  beforeEach(fresh)
  test('Explain sends error.explain once, with the id only; the answer fills the card', () => {
    msg('error.seen', ERR)
    S.explain()
    assert.equal(of('error.explain').length, 1)
    assert.deepEqual(Object.keys(of('error.explain')[0].payload).sort(), ['id', 'reqId'])
    assert.equal(S.useAmbient.getState().explanation?.pending, true)
    msg('error.explanation', { id: ERR.id, title: "pandas isn't installed here", why: 'w', fix: 'f', command: 'pip install pandas' })
    assert.equal(S.useAmbient.getState().explanation?.title, "pandas isn't installed here")
    // Pressing Explain again on the open card costs nothing.
    S.explain()
    assert.equal(of('error.explain').length, 1)
  })
  test('an answer for another id is ignored; a fail can be retried (once per press)', () => {
    msg('error.seen', ERR)
    S.explain()
    msg('error.explanation', { id: 'other', title: 'x' })
    assert.equal(S.useAmbient.getState().explanation?.pending, true)
    msg('error.explanation', { id: ERR.id, error: 'busy' })
    S.retryExplain()
    assert.equal(of('error.explain').length, 2)
  })
  test('without the capability: no command, a calm offline line', () => {
    hello(['ambient.set'])
    sent.length = 0
    msg('error.seen', ERR)
    S.explain()
    assert.equal(of('error.explain').length, 0)
    assert.equal(S.useAmbient.getState().explanation?.error, 'offline')
    hello()
  })
  test('close sends error.dismiss and the error never comes back; Show me points bon at it', () => {
    msg('error.seen', ERR)
    S.explain()
    msg('error.explanation', { id: ERR.id, title: 't', target: { x: 10, y: 20, w: 30, h: 40, label: 'Line 3' } })
    assert.equal(S.showError(), true)
    const mark = annotate.useAnnotate.getState().marks.find((m) => m.id?.startsWith('amb-'))
    assert.deepEqual(mark?.rect, { x: 10, y: 20, w: 30, h: 40 })
    S.closeExplain()
    assert.deepEqual(of('error.dismiss').at(-1)?.payload, { id: ERR.id })
    assert.equal(annotate.useAnnotate.getState().marks.some((m) => m.id?.startsWith('amb-')), false)
    msg('error.seen', ERR)
    assert.equal(S.useAmbient.getState().chip, false)
  })
  test('the chip ✕ dismisses too', () => {
    msg('error.seen', ERR)
    S.dismissChip()
    assert.deepEqual(of('error.dismiss').at(-1)?.payload, { id: ERR.id })
    assert.equal(S.useAmbient.getState().chip, false)
  })
  test('Esc closes the open card first', () => {
    msg('error.seen', ERR)
    S.explain()
    bus.emitUi('dismiss')
    assert.equal(S.useAmbient.getState().explainOpen, false)
  })
})

describe('set up this project', () => {
  beforeEach(fresh)
  const report = (items: Record<string, unknown>[], extra: Record<string, unknown> = {}): void =>
    msg('setup.report', { reqId: 'scan-1', root: '~/code/app', name: 'app', files: ['requirements.txt'], items, ready: items.filter((x) => x.ok).length, total: items.length, ...extra })
  test('the launcher command scans (no model call) and opens the card at once', () => {
    const c = C.ambientCommand('set up this project', false)
    assert.equal(c?.kind, 'setup')
    assert.equal(C.ambientCommand('set up this project', true), undefined, 'not during a lesson')
    assert.equal(C.runAmbientCommand(c!), true)
    assert.equal(of('setup.scan').length, 1)
    assert.equal(S.useAmbient.getState().setupOpen, true)
    assert.equal(S.useAmbient.getState().report?.scanning, true)
  })
  test('a report opens the card (the launcher window may have asked); Fix sends setup.fix with the root', () => {
    report([row('pandas', false), row('requests', true)])
    assert.equal(S.useAmbient.getState().setupOpen, true)
    S.fixRow('pandas')
    S.fixRow('pandas') // a second press while it runs does nothing
    assert.equal(of('setup.fix').length, 1)
    assert.equal(of('setup.fix')[0].payload.tool, 'pandas')
    assert.equal(of('setup.fix')[0].payload.root, '~/code/app')
    msg('setup.progress', { tool: 'pandas', line: 'Collecting pandas' })
    assert.equal(S.useAmbient.getState().installs.pandas?.line, 'Collecting pandas')
    msg('setup.progress', { tool: 'pandas', done: true, ok: true })
    assert.equal(S.useAmbient.getState().installs.pandas?.ok, true)
  })
  test('Fix all goes one after another, never a licensed app', () => {
    report([row('pandas', false), row('node', false, 'brew'), row('autocad', false, 'download', { setupKind: 'licensed_app', install: { method: 'download', url: 'https://x' } })])
    S.fixAll()
    assert.deepEqual(of('setup.fix').map((m) => m.payload.tool), ['pandas'])
    msg('setup.progress', { tool: 'pandas', done: true, ok: true })
    assert.deepEqual(of('setup.fix').map((m) => m.payload.tool), ['pandas', 'node'])
    // The fresh report says node is there now: that install is over even without its done line.
    report([row('pandas', true), row('node', true, 'brew')])
    assert.equal(S.useAmbient.getState().installs.node, undefined)
    assert.equal(of('setup.fix').length, 2)
  })
  test("a lesson's setup.progress is not ours", () => {
    report([row('pandas', false)])
    msg('setup.progress', { tool: 'numpy', line: 'Collecting numpy' })
    assert.equal(S.useAmbient.getState().installs.numpy, undefined)
  })
  test('a closed card stays closed for that scan; a new scan opens it again', () => {
    report([row('pandas', false)])
    S.closeSetup()
    report([row('pandas', true)])
    assert.equal(S.useAmbient.getState().setupOpen, false)
    report([], { scanning: true, reqId: 'scan-2' })
    assert.equal(S.useAmbient.getState().setupOpen, true)
  })
})

describe('how do I', () => {
  beforeEach(fresh)
  const STEPS = {
    reqId: 'help-1',
    app: 'Blender',
    goal: 'Export as STL',
    current: 0,
    steps: [
      { id: 'h1', text: 'Click File in the top bar', advance: 'click', target: { x: 34, y: 31, w: 38, h: 22, label: 'File' } },
      { id: 'h2', text: 'Point to Export', advance: 'screen', target: { x: 34, y: 418, w: 220, h: 24, label: 'Export' } }
    ]
  }
  const ours = (): string[] =>
    annotate.useAnnotate
      .getState()
      .marks.filter((m) => m.id?.startsWith('amb-'))
      .map((m) => m.label ?? '')
  test('the launcher command asks about the app in front, typed', () => {
    const c = C.ambientCommand('how do I export this as an STL?', false, 'Blender')
    assert.equal(c?.kind, 'help')
    assert.equal(c?.title, 'Show me in Blender')
    C.runAmbientCommand(c!)
    assert.deepEqual({ ...of('help.ask')[0].payload, reqId: 'x' }, { text: 'how do I export this as an STL?', reqId: 'x', app: 'Blender', source: 'typed' })
    assert.equal(S.useAmbient.getState().help?.pending, true)
  })
  test('without the capability there is no command', () => {
    hello(['ambient.set'])
    assert.equal(C.ambientCommand('how do I undo', false, 'Blender'), undefined)
    hello()
  })
  test('bon points at the current step; Next moves it; a target that did not move is not redrawn', () => {
    msg('help.steps', { ...STEPS, pending: true, steps: [], goal: '' })
    msg('help.steps', STEPS)
    assert.deepEqual(ours(), ['File'])
    S.helpNav('next')
    assert.deepEqual(of('help.nav').at(-1)?.payload, { reqId: 'help-1', to: 'next' })
    assert.equal(S.useAmbient.getState().help?.current, 1)
    assert.deepEqual(ours(), ['Export'])
    msg('help.steps', { ...STEPS, current: 1 })
    assert.deepEqual(ours(), ['Export'])
  })
  test('close sends help.nav close, takes the marks away, and a late re-send does not reopen it', () => {
    msg('help.steps', STEPS)
    S.helpNav('close')
    assert.deepEqual(of('help.nav').at(-1)?.payload, { reqId: 'help-1', to: 'close' })
    assert.equal(S.useAmbient.getState().helpOpen, false)
    assert.deepEqual(ours(), [])
    msg('help.steps', { ...STEPS, current: 1 })
    assert.equal(S.useAmbient.getState().helpOpen, false)
  })
  test('done closes it a moment later; a fail says so calmly and closes', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] })
    msg('help.steps', { ...STEPS, reqId: 'help-2', current: 1, done: true })
    assert.equal(S.useAmbient.getState().helpOpen, true)
    t.mock.timers.tick(M.HELP_DONE_MS + 10)
    assert.equal(S.useAmbient.getState().helpOpen, false)
    msg('help.steps', { reqId: 'help-3', app: 'Blender', goal: '', steps: [], current: 0, error: 'cap', retryInS: 600 })
    assert.equal(S.useAmbient.getState().help?.error, 'cap')
    t.mock.timers.tick(M.FAIL_MS + 10)
    assert.equal(S.useAmbient.getState().helpOpen, false)
    t.mock.timers.reset()
  })
})
