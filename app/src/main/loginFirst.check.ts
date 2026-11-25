/**
 * Login-first source check (lane login-first): `npx tsx src/main/loginFirst.check.ts` from app/. Exits 1 on a failure.
 *
 * Scans main/index.ts so the launch gate (main/gate.ts) can't be bypassed by a later edit:
 *   - overlay.showInactive (and any direct globalShortcut.register(platform.accelerators.launcher, …)) appears only inside
 *     a gate guard: a gateCore({…}) or onGate(…) call, or an `if (gateIsOpen())` block
 *   - live custom shortcuts (main/shortcutKeys.ts): globalShortcut.register is called only from the createShortcutKeys({…})
 *     ops (plus the quit key), that controller's `live` is shortcutLive, shortcutLive starts with
 *     `if (!gateIsOpen()) return false`, and launcherWanted (the launcher's say) is set only inside gateCore({…})
 *   - no app.on('second-instance', …) handler (features/launch.ts owns it: it opens home, not the launcher)
 *   - openLauncher() and registerActionShortcuts() return early while the gate is closed
 *   - the lesson.ready → registerActionShortcuts hook and the pill's launcher:toggle check the gate
 * Not run in the app: a plain node script, no Electron.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const file = join(__dirname, 'index.ts')
/** Comments blanked out (same length, so offsets stay put): only code counts. */
const src = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, (m) => m.replace(/[^\n]/g, ' '))

const failures: string[] = []
const fail = (why: string): void => void failures.push(why)
const lineOf = (at: number): number => src.slice(0, at).split('\n').length

/** The index just past the bracket that closes the one at `open`. */
function closeOf(open: number): number {
  const pairs: Record<string, string> = { '(': ')', '{': '}', '[': ']' }
  const stack: string[] = []
  for (let i = open; i < src.length; i++) {
    const c = src[i]
    if (c === "'" || c === '"' || c === '`') {
      // Skip a string literal (template literals here carry no nested backticks).
      const q = c
      for (i++; i < src.length && src[i] !== q; i++) if (src[i] === '\\') i++
      continue
    }
    if (pairs[c]) stack.push(pairs[c])
    else if (c === stack[stack.length - 1]) {
      stack.pop()
      if (stack.length === 0) return i + 1
    }
  }
  return src.length
}

/** Spans of code under a gate guard. */
function guarded(): [number, number][] {
  const spans: [number, number][] = []
  for (const m of src.matchAll(/\b(gateCore|onGate)\s*\(/g)) {
    const open = (m.index ?? 0) + m[0].length - 1
    spans.push([open, closeOf(open)])
  }
  for (const m of src.matchAll(/\bif\s*\(\s*gateIsOpen\(\)\s*\)\s*\{/g)) {
    const open = (m.index ?? 0) + m[0].length - 1
    spans.push([open, closeOf(open)])
  }
  return spans
}

const spans = guarded()
const inGuard = (at: number): boolean => spans.some(([a, b]) => at > a && at < b)

for (const [what, re] of [
  ['overlay.showInactive', /\boverlay\.showInactive\b/g],
  ['globalShortcut.register(platform.accelerators.launcher', /globalShortcut\.register\(\s*platform\.accelerators\.launcher\b/g]
] as const) {
  for (const m of src.matchAll(re)) {
    if (!inGuard(m.index ?? 0)) fail(`index.ts:${lineOf(m.index ?? 0)} ${what} outside a gateIsOpen()/onGate/gateCore guard`)
  }
}

if (!/\bgateCore\s*\(\s*\{/.test(src)) fail('index.ts never calls gateCore({...}): the overlay and launcher key do not follow the gate')
for (const m of src.matchAll(/\bapp\.on\(\s*['"]second-instance['"]/g)) fail(`index.ts:${lineOf(m.index ?? 0)} app.on('second-instance') is back (features/launch.ts owns it)`)

/** The first statement of a function body must be a return while the gate is closed. */
function guardsFirst(fn: string): void {
  const m = new RegExp(`function ${fn}\\(\\)[^{]*\\{`).exec(src)
  if (!m) return fail(`index.ts: function ${fn} not found`)
  const body = src.slice(m.index + m[0].length, closeOf(m.index + m[0].length - 1))
  const first = body.trim().split('\n')[0] ?? ''
  if (!/^if \(.*!gateIsOpen\(\).*\) return\b/.test(first)) fail(`index.ts: ${fn}() must start with an early return while !gateIsOpen() (found: ${first.trim()})`)
}
guardsFirst('openLauncher')
guardsFirst('registerActionShortcuts')

// Live custom shortcuts: every launcher / lesson key registers through the shortcutKeys controller, which asks
// shortcutLive, which is shut while the gate is.
const keysCall = /\bcreateShortcutKeys\s*\(\s*\{/.exec(src)
if (!keysCall) fail('index.ts never calls createShortcutKeys({...}): the shortcut keys do not follow the gate')
else {
  const open = keysCall.index + keysCall[0].length - 1
  const span: [number, number] = [open, closeOf(open)]
  const body = src.slice(span[0], span[1])
  if (!/\blive\s*:\s*shortcutLive\b/.test(body)) fail('index.ts: createShortcutKeys({...}) must take live: shortcutLive')
  for (const m of src.matchAll(/\bglobalShortcut\.register\s*\(/g)) {
    const at = m.index ?? 0
    const inKeys = at > span[0] && at < span[1]
    const quit = /^globalShortcut\.register\s*\(\s*quitKey\b/.test(src.slice(at))
    if (!inKeys && !quit) fail(`index.ts:${lineOf(at)} globalShortcut.register outside the shortcutKeys controller (or the quit key)`)
  }
}
const live = /function shortcutLive\([^)]*\)[^{]*\{/.exec(src)
if (!live) fail('index.ts: function shortcutLive not found')
else {
  const body = src.slice(live.index + live[0].length, closeOf(live.index + live[0].length - 1))
  const first = body.trim().split('\n')[0] ?? ''
  if (!/^if \(!gateIsOpen\(\)\) return false\b/.test(first)) fail(`index.ts: shortcutLive() must start with if (!gateIsOpen()) return false (found: ${first.trim()})`)
}
for (const m of src.matchAll(/\blauncherWanted\s*=(?!=)/g)) {
  const at = m.index ?? 0
  const decl = /\blet\s+$/.test(src.slice(Math.max(0, at - 8), at))
  if (!decl && !inGuard(at)) fail(`index.ts:${lineOf(at)} launcherWanted set outside a gate guard`)
}

if (!/e\.type === 'lesson\.ready' && gateIsOpen\(\)\) registerActionShortcuts\(\)/.test(src)) fail("index.ts: the lesson.ready hook must check gateIsOpen() before registerActionShortcuts()")
const toggle = /case 'launcher:toggle':([\s\S]*?)break/.exec(src)
if (!toggle || !/gateIsOpen\(\)\) openLauncher\(\)/.test(toggle[1])) fail("index.ts: case 'launcher:toggle' must open the launcher only while gateIsOpen()")

if (failures.length) {
  for (const f of failures) console.error(`FAIL ${f}`)
  process.exit(1)
}
console.log('loginFirst.check: ok (index.ts keeps the overlay, the launcher and lesson keys and second-instance behind the gate)')
