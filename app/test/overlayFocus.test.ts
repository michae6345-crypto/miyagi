/**
 * Overlay focus (user report, main 1d453ca0: over a full-screen VS Code, using the right-side overlay switched Spaces to
 * miyagi). Surfaces over the learner's app are non-activating panels and get the keyboard without activating miyagi.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { focusPanel, holdKeyboard, KEY_RETRY_MS, keyStep, overlayWindowOptions, panelType } from '../src/main/platform'

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
    // The one activation left is holdKeyboard's guarded last resort (keyStep), and never while an app window is open.
    assert.match(open, /holdKeyboard\(launcher,[\s\S]*appWindowOpen: \(\) => !!appWindows\?\.anyVisible\(\)/)
    const settings = code(read('main/features/settings.ts'))
    assert.match(settings, /focusPanel\(win\)/)
    assert.doesNotMatch(settings, /win\.show\(\)/)
    assert.match(settings, /holdKeyboard\(win, \{[^}]*fieldFocused: \(\) => false/) // Settings never activates miyagi
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

  describe('keyboard retries (a tester, Nov 25: "It\'s coffee. I can\'t even type coffee.")', () => {
    const base = { mac: true, open: true, focused: false, attempt: 0, fieldFocused: true, appWindowOpen: false, activated: false }
    const last = KEY_RETRY_MS.length - 1

    test('a panel that has the keys, closed, or not on a Mac: nothing', () => {
      assert.equal(keyStep({ ...base, focused: true, attempt: last }), 'stop')
      assert.equal(keyStep({ ...base, open: false, attempt: last }), 'stop')
      assert.equal(keyStep({ ...base, mac: false, attempt: last }), 'stop')
    })

    test('the first retries only ask again as a panel', () => {
      for (let attempt = 0; attempt < last; attempt++) assert.equal(keyStep({ ...base, attempt }), 'focus')
    })

    test('still not key at the last retry, with the caret in a field and no app window: activate miyagi once', () => {
      assert.equal(keyStep({ ...base, attempt: last }), 'activate')
      assert.equal(keyStep({ ...base, attempt: last, activated: true }), 'focus')
    })

    test('never activates with an app window open (the Space switch over full-screen VS Code) or no field focused', () => {
      assert.equal(keyStep({ ...base, attempt: last, appWindowOpen: true }), 'focus')
      assert.equal(keyStep({ ...base, attempt: last, fieldFocused: false }), 'focus')
    })

    type Pending = { fn: () => void; ms: number; cleared: boolean }
    const fakeTimers = (): { timers: { set: (fn: () => void, ms: number) => unknown; clear: (t: unknown) => void }; run: () => void; all: Pending[] } => {
      const all: Pending[] = []
      return {
        all,
        timers: { set: (fn, ms) => (all.push({ fn, ms, cleared: false }), all[all.length - 1]), clear: (t) => void ((t as Pending).cleared = true) },
        run: () => [...all].sort((a, b) => a.ms - b.ms).forEach((p) => !p.cleared && p.fn())
      }
    }
    const keyWin = (keyAfter = Infinity): { win: Parameters<typeof holdKeyboard>[0]; focuses: () => number } => {
      let n = 0
      return { win: { isDestroyed: () => false, isFocused: () => n >= keyAfter, focus: () => void n++ } as never, focuses: () => n }
    }

    test('holdKeyboard: a panel that never becomes key gets every retry, and miyagi is activated once at the end', () => {
      asPlatform('darwin', () => {
        const t = fakeTimers()
        const w = keyWin()
        const steals: unknown[] = []
        let handBack = 0
        holdKeyboard(w.win, { app: { focus: (o?: unknown) => void steals.push(o) }, isOpen: () => true, fieldFocused: () => true, appWindowOpen: () => false, onActivate: () => handBack++, timers: t.timers })
        assert.deepEqual(t.all.map((p) => p.ms), [...KEY_RETRY_MS])
        t.run()
        assert.equal(w.focuses(), KEY_RETRY_MS.length)
        assert.deepEqual(steals, [{ steal: true }])
        assert.equal(handBack, 1)
      })
    })

    test('holdKeyboard: once the panel is key, no more retries and no activation', () => {
      asPlatform('darwin', () => {
        const t = fakeTimers()
        const w = keyWin(1) // key after the first retry
        const steals: unknown[] = []
        holdKeyboard(w.win, { app: { focus: (o?: unknown) => void steals.push(o) }, isOpen: () => true, fieldFocused: () => true, appWindowOpen: () => false, timers: t.timers })
        t.run()
        assert.equal(w.focuses(), 1)
        assert.deepEqual(steals, [])
      })
    })

    test('holdKeyboard: closed before the retries, the cancel drops them all', () => {
      asPlatform('darwin', () => {
        const t = fakeTimers()
        const w = keyWin()
        const steals: unknown[] = []
        const cancel = holdKeyboard(w.win, { app: { focus: (o?: unknown) => void steals.push(o) }, isOpen: () => true, fieldFocused: () => true, appWindowOpen: () => false, timers: t.timers })
        cancel()
        t.run()
        assert.equal(w.focuses(), 0)
        assert.deepEqual(steals, [])
      })
    })

    test('holdKeyboard: with an app window open it keeps asking as a panel and never activates', () => {
      asPlatform('darwin', () => {
        const t = fakeTimers()
        const w = keyWin()
        const steals: unknown[] = []
        holdKeyboard(w.win, { app: { focus: (o?: unknown) => void steals.push(o) }, isOpen: () => true, fieldFocused: () => true, appWindowOpen: () => true, timers: t.timers })
        t.run()
        assert.equal(w.focuses(), KEY_RETRY_MS.length)
        assert.deepEqual(steals, [])
      })
    })

    test('app windows (Library, Progress, onboarding) re-ask for the keyboard after every show + focus', () => {
      const wins = code(read('main/appWindows.ts'))
      const shows = wins.match(/\.show\(\)\s*\n\s*\w+\.focus\(\)\s*\n\s*takeKeys\(\w+\)/g) ?? []
      assert.equal(shows.length, 3)
      assert.equal((wins.match(/\.show\(\)/g) ?? []).length, 3)
    })

    test('the launcher hands the keyboard back on close (hideLauncher returns focus to the previous app)', () => {
      const index = code(read('main/index.ts'))
      const hide = index.slice(index.indexOf('function hideLauncher'), index.indexOf('function onLauncherKey'))
      assert.match(hide, /stopHoldingKeys\?\.\(\)/)
      assert.match(hide, /returnFocus\(app, overlay, previousApp\(\)\)/)
    })
  })
})
