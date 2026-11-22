/**
 * app-harden: Electron fuses (electron-builder.yml), DevTools and the packaged-startup debug guard (main/index.ts).
 * Offline: reads the files; index.ts is never imported (that would start the app).
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { DEBUG_SWITCHES, debugFlagIn } from '../src/main/safeOpen'

const APP = join(__dirname, '..')
// js-yaml comes with electron-builder (already in node_modules; nothing is installed for this test).
const yaml = createRequire(join(APP, 'package.json'))('js-yaml') as { load: (s: string) => unknown }

describe('electron-builder.yml fuses', () => {
  const config = yaml.load(readFileSync(join(APP, 'electron-builder.yml'), 'utf8')) as Record<string, unknown>
  const fuses = config.electronFuses as Record<string, unknown>

  test('every fuse is set the hardened way', () => {
    assert.ok(fuses && typeof fuses === 'object', 'electronFuses is set')
    assert.equal(fuses.runAsNode, false)
    assert.equal(fuses.enableNodeOptionsEnvironmentVariable, false)
    assert.equal(fuses.enableNodeCliInspectArguments, false)
    assert.equal(fuses.enableEmbeddedAsarIntegrityValidation, true)
    assert.equal(fuses.onlyLoadAppFromAsar, true)
    assert.equal(fuses.enableCookieEncryption, true)
    assert.equal(fuses.grantFileProtocolExtraPrivileges, false)
    assert.equal(fuses.loadBrowserProcessSpecificV8Snapshot, false)
  })

  test('an unsigned build stays launchable: the flipped binary is re-signed ad hoc', () => {
    // mac.identity is null, so electron-builder signs nothing after the fuse flip; without this the Electron Framework
    // keeps a broken ad-hoc signature and Apple Silicon kills npm run dist:mac / CI builds at launch.
    assert.equal(fuses.resetAdHocDarwinSignature, true)
  })

  test('the app is packed in an asar (integrity validation needs one) and signing is unchanged', () => {
    assert.notEqual(config.asar, false)
    const mac = config.mac as Record<string, unknown>
    assert.equal(mac.identity, null, 'no Developer ID here: Michael decides that')
    assert.equal(mac.hardenedRuntime, undefined)
  })
})

describe('index.ts: DevTools, menu, debug flags', () => {
  const index = readFileSync(join(APP, 'src', 'main', 'index.ts'), 'utf8')

  test('every window gets devTools: !app.isPackaged, after the callers’ webPreferences (none can turn it back on)', () => {
    // index.ts's createWindow is the only BrowserWindow constructor in main (player and settings use ctx.createWindow).
    assert.equal(index.match(/new BrowserWindow\(/g)?.length, 1)
    const ctor = index.slice(index.indexOf('new BrowserWindow('))
    const prefs = ctor.slice(ctor.indexOf('webPreferences: {'), ctor.indexOf('\n    }\n  })'))
    assert.match(prefs, /\.\.\.options\.webPreferences,[\s\S]*devTools: !app\.isPackaged/)
  })

  test('no menu offers Reload or DevTools; Windows / Linux get no menu at all', () => {
    assert.doesNotMatch(index, /toggleDevTools|toggledevtools|forceReload|forcereload|role: 'reload'/)
    const menu = index.slice(index.indexOf('function setupMenu'), index.indexOf('\n}\n', index.indexOf('function setupMenu')))
    assert.match(menu, /if \(platform\.os !== 'mac'\) return Menu\.setApplicationMenu\(null\)/)
  })

  test('a packaged build quits at startup on a debug flag', () => {
    assert.match(index, /if \(app\.isPackaged\) \{\s*const flag = debugFlagIn\(process\.argv\)\s*if \(flag\) \{[\s\S]*?app\.exit\(1\)/)
  })
})

describe('debugFlagIn (the packaged argv guard)', () => {
  const app = '/Applications/miyagi.app/Contents/MacOS/miyagi'

  test('ATTACK each debug switch is caught, in every spelling', () => {
    for (const a of ['--inspect', '--inspect=9229', '--inspect-brk', '--inspect-brk=0.0.0.0:9229', '--remote-debugging-port=9222', '--remote-debugging-pipe', '--js-flags=--allow-natives-syntax', '--INSPECT', '-inspect', '--inspect-port=1', '--remote-debugging-address=0.0.0.0', '--inspect-brk-node', '--inspect-brk-node=9229', '--inspect-wait', '--inspect-wait=9229', '--debug', '--debug=5858', '--debug-brk', '--debug-brk=5858', '--debug-port=5858']) {
      assert.ok(debugFlagIn([app, a], false), a)
    }
    assert.equal(debugFlagIn([app, '--remote-debugging-port=9222'], false), 'remote-debugging-port')
    assert.equal(debugFlagIn([app, '--', '--inspect'], false), 'inspect', 'also after --')
    assert.equal(debugFlagIn(['C:\\miyagi.exe', '/remote-debugging-port=9222'], true), 'remote-debugging-port', 'Windows /switch')
    assert.equal(debugFlagIn([app, '--inspect-brk-node'], false), 'inspect-brk-node')
    assert.equal(debugFlagIn([app, '--debug-port=5858'], false), 'debug-port')
    for (const s of ['inspect', 'inspect-brk', 'inspect-brk-node', 'inspect-wait', 'debug', 'debug-brk', 'debug-port', 'remote-debugging-port', 'remote-debugging-pipe', 'js-flags']) assert.ok((DEBUG_SWITCHES as readonly string[]).includes(s))
  })

  test('a normal launch is not caught', () => {
    assert.equal(debugFlagIn([app], false), undefined)
    assert.equal(debugFlagIn([app, '-psn_0_12345', '--hidden', '--inspector-theme', '--js-flagsy', '/remote-debugging-port=1'], false), undefined)
    assert.equal(debugFlagIn([app, 'inspect', 'file:///tmp/--inspect'], false), undefined)
    assert.equal(debugFlagIn([], false), undefined)
  })
})
