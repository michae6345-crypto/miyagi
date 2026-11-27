/**
 * Developer ID signing (scripts/sign-mac.sh, env-gated by MIYAGI_DEVID in scripts/ship-mac.sh). No codesign, no
 * keychain, no network: the scripts are syntax-checked, the inside-out order is read from `sign-mac.sh order` on a
 * fake .app, and ship-mac.sh is read to pin that the unset path is still today's ad-hoc / MIYAGI_SIGN_ID signing.
 * Run from app/:
 *   node --import tsx --import ./test/setup.mjs --test --test-force-exit test/signMac.test.ts
 */
import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, describe, test } from 'node:test'

const APP = join(__dirname, '..')
const SIGN = join(APP, 'scripts', 'sign-mac.sh')
const SHIP = join(APP, 'scripts', 'ship-mac.sh')
const ENTITLEMENTS = join(APP, 'build', 'entitlements.mac.plist')

const MACHO = Buffer.from([0xcf, 0xfa, 0xed, 0xfe, 0, 0, 0, 0]) // 64-bit little-endian Mach-O magic
const FAT = Buffer.from([0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 2]) // universal binary

/** A tiny .app shaped like the real one: Electron framework + helper, bundled Python, miyagi-listen, plus non-code files. */
function fakeApp(): string {
  const root = mkdtempSync(join(tmpdir(), 'miyagi-sign-'))
  const app = join(root, 'miyagi.app')
  const put = (rel: string, data: Buffer | string): void => {
    const p = join(app, rel)
    mkdirSync(join(p, '..'), { recursive: true })
    writeFileSync(p, data)
  }
  put('Contents/MacOS/miyagi', MACHO)
  put('Contents/Info.plist', '<plist/>')
  const fw = 'Contents/Frameworks/Electron Framework.framework'
  put(`${fw}/Versions/A/Electron Framework`, MACHO)
  put(`${fw}/Versions/A/Libraries/libEGL.dylib`, MACHO)
  put(`${fw}/Versions/A/Helpers/chrome_crashpad_handler`, MACHO)
  put(`${fw}/Versions/A/Resources/Info.plist`, '<plist/>')
  symlinkSync('A', join(app, fw, 'Versions/Current'))
  symlinkSync('Versions/Current/Electron Framework', join(app, fw, 'Electron Framework'))
  put('Contents/Frameworks/miyagi Helper (Renderer).app/Contents/MacOS/miyagi Helper (Renderer)', MACHO)
  put('Contents/Resources/app.asar', 'not code')
  put('Contents/Resources/engine/python/bin/python3.12', MACHO)
  symlinkSync('python3.12', join(app, 'Contents/Resources/engine/python/bin/python3'))
  put('Contents/Resources/engine/python/lib/python3.12/lib-dynload/_ctypes.cpython-312-darwin.so', MACHO)
  put('Contents/Resources/engine/python/lib/libpython3.12.dylib', MACHO)
  put('Contents/Resources/engine/python/lib/python3.12/os.py', 'import abc\n')
  put('Contents/Resources/helpers/miyagi-listen', FAT)
  return app
}

describe('sign-mac.sh', () => {
  const app = fakeApp()
  after(() => rmSync(join(app, '..'), { recursive: true, force: true }))

  test('both scripts parse (bash -n)', () => {
    execFileSync('bash', ['-n', SIGN])
    execFileSync('bash', ['-n', SHIP])
  })

  test('signs every Mach-O and bundle once, inside-out, the app last', () => {
    const out = execFileSync('bash', [SIGN, 'order', app], { encoding: 'utf8' }).trim().split('\n')
    const rel = out.map((p) => (p === app ? '.' : p.slice(app.length + 1)))
    const fw = 'Contents/Frameworks/Electron Framework.framework'
    const helper = 'Contents/Frameworks/miyagi Helper (Renderer).app'
    const expected = [
      'Contents/Resources/engine/python/lib/python3.12/lib-dynload/_ctypes.cpython-312-darwin.so',
      'Contents/Resources/engine/python/lib/libpython3.12.dylib',
      'Contents/Resources/engine/python/bin/python3.12',
      'Contents/Resources/helpers/miyagi-listen',
      `${fw}/Versions/A/Electron Framework`,
      `${fw}/Versions/A/Libraries/libEGL.dylib`,
      `${fw}/Versions/A/Helpers/chrome_crashpad_handler`,
      `${helper}/Contents/MacOS/miyagi Helper (Renderer)`,
      fw,
      helper,
      'Contents/MacOS/miyagi',
      '.'
    ]
    assert.deepEqual([...rel].sort(), [...expected].sort(), 'exactly the code: no symlinks, no .py/.plist/.asar')
    assert.equal(rel.at(-1), '.', 'the app is sealed last')
    const at = (p: string): number => rel.indexOf(p)
    for (const inner of [`${fw}/Versions/A/Electron Framework`, `${fw}/Versions/A/Libraries/libEGL.dylib`, `${fw}/Versions/A/Helpers/chrome_crashpad_handler`]) {
      assert.ok(at(inner) < at(fw), `${inner} before its framework`)
    }
    assert.ok(at(`${helper}/Contents/MacOS/miyagi Helper (Renderer)`) < at(helper), 'helper binary before the helper app')
  })

  test('has-notary needs a profile or all three API key variables', () => {
    const run = (env: Record<string, string>): number | null => {
      const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('APPLE_API') && k !== 'MIYAGI_NOTARY_PROFILE'))
      return spawnSync('bash', [SIGN, 'has-notary'], { env: { ...clean, ...env } }).status
    }
    assert.equal(run({}), 1)
    assert.equal(run({ MIYAGI_NOTARY_PROFILE: 'miyagi-notary' }), 0)
    assert.equal(run({ APPLE_API_KEY: '/k.p8', APPLE_API_KEY_ID: 'ABC' }), 1)
    assert.equal(run({ APPLE_API_KEY: '/k.p8', APPLE_API_KEY_ID: 'ABC', APPLE_API_ISSUER: 'uuid' }), 0)
  })
})

describe('entitlements.mac.plist', () => {
  const plist = readFileSync(ENTITLEMENTS, 'utf8')
  const keys = [...plist.replace(/<!--[\s\S]*?-->/g, '').matchAll(/<key>([^<]+)<\/key>\s*<true\/>/g)].map((m) => m[1])

  test('exactly the hardened-runtime exceptions Electron, the bundled Python and push to talk need', () => {
    assert.deepEqual(keys.sort(), [
      'com.apple.security.automation.apple-events',
      'com.apple.security.cs.allow-jit',
      'com.apple.security.cs.allow-unsigned-executable-memory',
      'com.apple.security.cs.disable-library-validation',
      'com.apple.security.device.audio-input'
    ])
    assert.ok(!keys.some((k) => k.includes('get-task-allow')), 'notarization rejects get-task-allow')
  })
})

describe('ship-mac.sh without MIYAGI_DEVID', () => {
  const ship = readFileSync(SHIP, 'utf8')

  test('still signs ad hoc, or with MIYAGI_SIGN_ID (install:local, the auto-install loop)', () => {
    assert.match(ship, /SIGN_ID="\$\{MIYAGI_SIGN_ID:--\}"\n\s*codesign --force --deep -s "\$SIGN_ID" "\$APP"/)
    assert.match(ship, /DEVID="\$\{MIYAGI_DEVID:-\}"/)
    assert.match(ship, /if \[ -n "\$DEVID" \]; then\n\s*bash scripts\/sign-mac\.sh app "\$APP"\nelse\n\s*SIGN_ID=/)
  })

  test('every sign-mac.sh call sits behind MIYAGI_DEVID', () => {
    const lines = ship.split('\n')
    lines.forEach((line, i) => {
      if (!line.includes('scripts/sign-mac.sh') || line.trim().startsWith('#')) return
      const before = lines.slice(0, i).reverse()
      const gate = before.findIndex((l) => /^if \[ -n "\$DEVID" \]; then$/.test(l))
      const closed = before.findIndex((l) => /^fi$/.test(l))
      assert.ok(gate !== -1 && (closed === -1 || gate < closed), `line ${i + 1} runs only with MIYAGI_DEVID: ${line.trim()}`)
    })
  })
})
