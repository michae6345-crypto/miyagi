/**
 * Windows engine bundle: target selection and layout (scripts/bundle-target.mjs). Offline: no download, no uv, no Python;
 * prune() runs on fake folder trees in a temp dir. The Mac target must stay exactly what bundle-engine.mjs always built.
 */
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, test } from 'node:test'
// @ts-expect-error plain .mjs build script, no types
import * as bt from '../scripts/bundle-target.mjs'

const APP = join(__dirname, '..')
const touch = (p: string) => {
  mkdirSync(join(p, '..'), { recursive: true })
  writeFileSync(p, 'x')
}

describe('pickPlatform', () => {
  test('defaults: Windows host builds Windows, anything else builds macOS', () => {
    assert.equal(bt.pickPlatform({ env: {}, hostPlatform: 'win32' }), 'win32')
    assert.equal(bt.pickPlatform({ env: {}, hostPlatform: 'darwin' }), 'darwin')
    assert.equal(bt.pickPlatform({ env: {}, hostPlatform: 'linux' }), 'darwin')
  })
  test('MIYAGI_BUNDLE_PLATFORM wins, junk is rejected', () => {
    assert.equal(bt.pickPlatform({ env: { MIYAGI_BUNDLE_PLATFORM: 'win32' }, hostPlatform: 'darwin' }), 'win32')
    assert.equal(bt.pickPlatform({ env: { MIYAGI_BUNDLE_PLATFORM: 'Windows' }, hostPlatform: 'darwin' }), 'win32')
    assert.equal(bt.pickPlatform({ env: { MIYAGI_BUNDLE_PLATFORM: 'mac' }, hostPlatform: 'win32' }), 'darwin')
    assert.equal(bt.pickPlatform({ env: { MIYAGI_BUNDLE_PLATFORM: 'beos' }, hostPlatform: 'darwin' }), null)
  })
})

describe('resolveTarget', () => {
  test('Mac targets are unchanged (same archives, hashes, layout, smoke)', () => {
    const arm = bt.resolveTarget({ platform: 'darwin' })
    assert.equal(arm.arch, 'arm64')
    assert.equal(arm.file, 'cpython-3.12.16+20261026-aarch64-apple-darwin-install_only_stripped.tar.gz')
    assert.equal(arm.sha256, '353d5f1b4fd2715e7053f12f068435d5bbad16b91e057006b5d01e0925709a7e')
    assert.deepEqual(arm.pythonRel, ['bin', 'python3'])
    assert.deepEqual(arm.libRel, ['lib', 'python3.12'])
    assert.deepEqual(arm.manifestExtra, {})
    assert.equal(arm.checksLinks, true)
    assert.match(arm.smoke, /Quartz, Vision, ScreenCaptureKit, ApplicationServices, HIServices, AppKit$/)
    const x64 = bt.resolveTarget({ platform: 'darwin', arch: 'x64' })
    assert.equal(x64.triple, 'x86_64-apple-darwin')
    assert.equal(x64.sha256, '37c38fda76fec1fbf310adcbafb7f0d96af13b5511bf8ea954c3aa8eec185734')
    assert.match(arm.url, /^https:\/\/github\.com\/astral-sh\/python-build-standalone\/releases\/download\/20261026\/cpython-3\.12\.16%2B20261026-aarch64-apple-darwin/)
  })
  test('Windows x64 is the default Windows arch and uses the msvc install_only_stripped asset', () => {
    const w = bt.resolveTarget({ platform: 'win32' })
    assert.equal(w.arch, 'x64')
    assert.equal(w.triple, 'x86_64-pc-windows-msvc')
    assert.equal(w.file, 'cpython-3.12.16+20261026-x86_64-pc-windows-msvc-install_only_stripped.tar.gz')
    assert.equal(w.sha256, '1f2ab53880fc67ea323398c6388e05af28addc99a8e389209f08a51fdff4b149')
    assert.deepEqual(w.pythonRel, ['python.exe'])
    assert.deepEqual(w.libRel, ['Lib'])
    assert.deepEqual(w.manifestExtra, { os: 'win32' })
    assert.equal(w.checksLinks, false)
    assert.equal(bt.resolveTarget({ platform: 'win32', arch: 'arm64' }).triple, 'aarch64-pc-windows-msvc')
    assert.equal(bt.resolveTarget({ platform: 'win32', arch: 'arm64' }).sha256, '3b2e4da9209cec3e0eaf4db31176977a88df32d598ff94a7899c34cd8304db04')
  })
  test('smoke import skips the macOS-only modules on Windows, keeps the rest', () => {
    const w = bt.resolveTarget({ platform: 'win32' })
    for (const m of ['Quartz', 'Vision', 'ScreenCaptureKit', 'ApplicationServices', 'HIServices', 'AppKit', 'objc']) assert.doesNotMatch(w.smoke, new RegExp(`\\b${m}\\b`))
    for (const m of ['fastapi', 'uvicorn', 'websockets', 'pydantic', 'anthropic', 'google.genai', 'PIL']) assert.match(w.smoke, new RegExp(m.replace('.', '\\.')))
  })
  test('bad arch or platform gives an error, not a throw', () => {
    assert.match(bt.resolveTarget({ platform: 'win32', arch: 'universal2' }).error, /use x64 or arm64/)
    assert.match(bt.resolveTarget({ platform: 'linux' }).error, /unknown platform/)
  })
  test('every pinned hash is 64 hex chars and the four are distinct', () => {
    const all = [bt.PY.sha256.darwin.arm64, bt.PY.sha256.darwin.x64, bt.PY.sha256.win32.x64, bt.PY.sha256.win32.arm64]
    for (const h of all) assert.match(h, /^[0-9a-f]{64}$/)
    assert.equal(new Set(all).size, 4)
  })
})

describe('layout and runnable', () => {
  test('paths', () => {
    const m = bt.resolveTarget({ platform: 'darwin' })
    const w = bt.resolveTarget({ platform: 'win32' })
    assert.equal(bt.pythonPath(m, '/p'), join('/p', 'bin', 'python3'))
    assert.equal(bt.sitePath(m, '/p'), join('/p', 'lib', 'python3.12', 'site-packages'))
    assert.equal(bt.pythonPath(w, '/p'), join('/p', 'python.exe'))
    assert.equal(bt.sitePath(w, '/p'), join('/p', 'Lib', 'site-packages'))
    assert.equal(bt.libPath(w, '/p'), join('/p', 'Lib'))
  })
  test('the bundle is only run on its own OS', () => {
    const m = bt.resolveTarget({ platform: 'darwin' })
    const w = bt.resolveTarget({ platform: 'win32' })
    assert.equal(bt.runnableHere(m, 'darwin'), true)
    assert.equal(bt.runnableHere(m, 'win32'), false)
    assert.equal(bt.runnableHere(w, 'win32'), true)
    assert.equal(bt.runnableHere(w, 'darwin'), false)
  })
})

describe('prune on a fake tree', () => {
  test('Windows: drops Tk, headers, import libs, pip and tests; keeps python.exe, DLLs, Lib, engine packages', () => {
    const root = mkdtempSync(join(tmpdir(), 'miyagi-win-prune-'))
    try {
      const t = bt.resolveTarget({ platform: 'win32' })
      const keep = ['python.exe', 'python312.dll', 'python3.dll', 'vcruntime140.dll', 'DLLs/_ssl.pyd', 'Lib/os.py', 'Lib/ensurepip/__init__.py', 'Lib/venv/__init__.py',
        'Lib/site-packages/fastapi/__init__.py', 'Lib/site-packages/fastapi-0.1.dist-info/METADATA']
      const drop = ['include/Python.h', 'libs/python312.lib', 'tcl/tcl8.6/init.tcl', 'DLLs/_tkinter.pyd', 'DLLs/tcl86t.dll', 'DLLs/tk86t.dll', 'Scripts/pip.exe', 'Scripts/pip3.12.exe',
        'Lib/test/test_x.py', 'Lib/idlelib/a.py', 'Lib/tkinter/__init__.py', 'Lib/turtle.py', 'Lib/lib2to3/a.py', 'Lib/pydoc_data/a.py',
        'Lib/site-packages/pip/__init__.py', 'Lib/site-packages/pip-24.0.dist-info/METADATA', 'Lib/site-packages/Scripts/uvicorn.exe', 'Lib/site-packages/psycopg_binary/x.pyd',
        'Lib/site-packages/fastapi/tests/t.py', 'Lib/site-packages/fastapi/a.pyi', 'Lib/site-packages/fastapi-0.1.dist-info/RECORD', 'Lib/site-packages/x/speed.c']
      for (const f of [...keep, ...drop]) touch(join(root, f))
      const n = bt.prune(t, root)
      assert.ok(n >= 14, `removed ${n}`)
      for (const f of keep) assert.ok(existsSync(join(root, f)), `kept ${f}`)
      for (const f of drop) assert.ok(!existsSync(join(root, f)), `dropped ${f}`)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })
  test('macOS: same behavior as before (bin scripts, libpython, Tcl/Tk, tests)', () => {
    const root = mkdtempSync(join(tmpdir(), 'miyagi-mac-prune-'))
    try {
      const t = bt.resolveTarget({ platform: 'darwin' })
      const keep = ['bin/python3', 'lib/python3.12/os.py', 'lib/python3.12/ensurepip/__init__.py', 'lib/python3.12/site-packages/fastapi/__init__.py', 'lib/python3.12/site-packages/fastapi-0.1.dist-info/METADATA']
      const drop = ['include/python3.12/Python.h', 'share/man/m', 'lib/pkgconfig/p.pc', 'lib/libpython3.12.dylib', 'lib/tcl9.0/init.tcl', 'lib/tk9.0/tk.tcl', 'bin/pip3', 'bin/2to3', 'bin/idle3', 'bin/python3.12-config',
        'lib/python3.12/test/a.py', 'lib/python3.12/lib-dynload/_tkinter.cpython-312-darwin.so', 'lib/python3.12/site-packages/bin/uvicorn', 'lib/python3.12/site-packages/PyObjCTest/a.py',
        'lib/python3.12/site-packages/fastapi-0.1.dist-info/RECORD']
      for (const f of [...keep, ...drop]) touch(join(root, f))
      bt.prune(t, root)
      for (const f of keep) assert.ok(existsSync(join(root, f)), `kept ${f}`)
      for (const f of drop) assert.ok(!existsSync(join(root, f)), `dropped ${f}`)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })
})

describe('bundle-engine.mjs wiring', () => {
  const src = readFileSync(join(APP, 'scripts', 'bundle-engine.mjs'), 'utf8')
  test('imports the target module and has no inline pins or otool on the Windows path', () => {
    assert.match(src, /from '\.\/bundle-target\.mjs'/)
    assert.doesNotMatch(src, /353d5f1b4fd2715e/)
    assert.match(src, /if \(T\.checksLinks\)/)
  })
  test('ships the Blender add-on (bridge + scene dump) with the engine source, not precompiled', () => {
    const m = src.match(/const PATHS = \[([^\]]*)\]/)
    assert.ok(m, 'PATHS is declared')
    const paths = [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1])
    assert.ok(paths.includes('blender-addon'), `PATHS: ${paths.join(', ')}`)
    for (const p of ['server', 'shared', 'cli', 'scripts', 'demo']) assert.ok(paths.includes(p), p)
    // The add-on runs in Blender's own Python: the bundled CPython never compiles it.
    assert.match(src, /const srcDirs = \['server', 'shared', 'cli'\]/)
  })
})
