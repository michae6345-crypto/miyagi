/**
 * Overlay focus (user report, main 1d453ca0: over a full-screen VS Code, using the right-side overlay switched Spaces to
 * miyagi). Surfaces over the learner's app are non-activating panels and get the keyboard without activating miyagi.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { focusPanel, overlayWindowOptions, panelType } from '../src/main/platform'

const SRC = join(__dirname, '..', 'src')
const read = (p: string): string => readFileSync(join(SRC, p), 'utf8')
/** Code only: comment lines may name the APIs this guards against. */
const code = (text: string): string =>
  text
    .split('\n')
    .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
    .join('\n')

type Call = string
function fakeWin(opts: { visible?: boolean; showsAt?: 'now' | 'later' } = {}): { win: Parameters<typeof focusPanel>[0]; calls: Call[]; fireShow: () => void } {
  const calls: Call[] = []
  let visible = !!opts.visible
  let onShow: (() => void) | undefined
  const win = {
    isDestroyed: () => false,
    isVisible: () => visible,
    show: () => {
      calls.push('show')
      visible = true
    },
    showInactive: () => {
      calls.push('showInactive')
      if (opts.showsAt !== 'later') visible = true
    },
    focus: () => void calls.push('focus'),
    once: (event: string, fn: () => void) => {
      calls.push(`once:${event}`)
      onShow = fn
      return win
    }
  }
  return {
    win: win as unknown as Parameters<typeof focusPanel>[0],
    calls,
    fireShow: () => {
      visible = true
      onShow?.()
    }
  }
}

function asPlatform<T>(platform: NodeJS.Platform, fn: () => T): T {
  const was = Object.getOwnPropertyDescriptor(process, 'platform')!
  Object.defineProperty(process, 'platform', { value: platform })
  try {
    return fn()
  } finally {
    Object.defineProperty(process, 'platform', was)
  }
}

describe('overlay focus', () => {
  test('macOS: every floating surface is a panel; Windows: a plain window', () => {
    asPlatform('darwin', () => {
      assert.equal(panelType().type, 'panel')
      assert.equal(overlayWindowOptions({ x: 0, y: 0, width: 10, height: 10 }).type, 'panel')
    })
    asPlatform('win32', () => assert.equal(panelType().type, undefined))
  })

  test('macOS: focusPanel never calls show() (it activates the app); showInactive, then focus', () => {
    asPlatform('darwin', () => {
      const f = fakeWin()
      focusPanel(f.win)
      assert.deepEqual(f.calls, ['showInactive', 'focus'])
    })
  })

  test('macOS: already on screen, it only takes the keys', () => {
    asPlatform('darwin', () => {
      const f = fakeWin({ visible: true })
      focusPanel(f.win)
      assert.deepEqual(f.calls, ['focus'])
    })
  })

  test('macOS: a show held until first paint gets the keys when it lands', () => {
    asPlatform('darwin', () => {
      const f = fakeWin({ showsAt: 'later' })
      focusPanel(f.win)
      assert.deepEqual(f.calls, ['showInactive', 'once:show'])
      f.fireShow()
      assert.deepEqual(f.calls, ['showInactive', 'once:show', 'focus'])
    })
  })

  test('Windows: show + focus as before', () => {
    asPlatform('win32', () => {
      const f = fakeWin()
      focusPanel(f.win)
      assert.deepEqual(f.calls, ['show', 'focus'])
    })
  })

  test('the launcher and Settings open through focusPanel, never show() or app.focus({steal})', () => {
    const index = code(read('main/index.ts'))
    const open = index.slice(index.indexOf('function openLauncher'), index.indexOf('function closeLauncher'))
    assert.match(open, /focusPanel\(launcher\)/)
    assert.doesNotMatch(open, /launcher\.show\(\)/)
    assert.doesNotMatch(open, /steal/)
    const settings = code(read('main/features/settings.ts'))
    assert.match(settings, /focusPanel\(win\)/)
    assert.doesNotMatch(settings, /win\.show\(\)/)
  })

  test('front-app never re-activates another app on its own (the old handBack flip-flop)', () => {
    const front = code(read('main/features/front-app.ts'))
    assert.doesNotMatch(front, /execFile\(\s*'open'/)
  })

  test('every overlay-kind window (launcher, Settings, player) is created as a panel on macOS', () => {
    const index = code(read('main/index.ts'))
    assert.match(index, /platform\.os === 'mac' && kind === 'overlay' \? \{ type: 'panel' \}/)
  })

  test('macOS: a second focusPanel while the first show is still held adds no second listener', () => {
    asPlatform('darwin', () => {
      const f = fakeWin({ showsAt: 'later' })
      focusPanel(f.win)
      focusPanel(f.win)
      assert.equal(f.calls.filter((c) => c === 'once:show').length, 1)
      f.fireShow()
      assert.equal(f.calls.filter((c) => c === 'focus').length, 1)
    })
  })
})
