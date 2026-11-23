import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cliEnvFor, cliInvocation, findCodeCli, stepLabel, type CliDeps } from '../src/main/features/vscodeCli'

const fsOf = (files: string[], dirs: Record<string, string[]> = {}) => ({
  exists: (p: string) => files.includes(p),
  readdir: (p: string) => dirs[p] ?? []
})
const win = (env: Record<string, string>, files: string[], dirs: Record<string, string[]> = {}): CliDeps => ({ platform: 'win32', env, home: 'C:\\Users\\a', ...fsOf(files, dirs) })
const LOCAL = 'C:\\Users\\a\\AppData\\Local'
const ROOT = `${LOCAL}\\Programs\\Microsoft VS Code`

test('windows: PATH code.cmd resolves to Code.exe + cli.js with ELECTRON_RUN_AS_NODE', () => {
  const cli = findCodeCli(win({ Path: `C:\\x;${ROOT}\\bin` }, [`${ROOT}\\bin\\code.cmd`, `${ROOT}\\Code.exe`, `${ROOT}\\resources\\app\\out\\cli.js`]))
  assert.equal(cli?.file, `${ROOT}\\Code.exe`)
  assert.deepEqual(cli?.prefix, [`${ROOT}\\resources\\app\\out\\cli.js`])
  assert.equal(cli?.extraEnv.ELECTRON_RUN_AS_NODE, '1')
  assert.equal(cli?.viaCmd, undefined)
})

test('windows: LOCALAPPDATA and ProgramFiles installs, version-folder cli.js', () => {
  const a = findCodeCli(win({ LOCALAPPDATA: LOCAL }, [`${ROOT}\\bin\\code.cmd`, `${ROOT}\\Code.exe`, `${ROOT}\\abc123\\resources\\app\\out\\cli.js`], { [ROOT]: ['bin', 'abc123'] }))
  assert.equal(a?.prefix[0], `${ROOT}\\abc123\\resources\\app\\out\\cli.js`)
  const pf = 'C:\\Program Files\\Microsoft VS Code'
  const b = findCodeCli(win({ ProgramFiles: 'C:\\Program Files' }, [`${pf}\\bin\\code.cmd`, `${pf}\\Code.exe`, `${pf}\\resources\\app\\out\\cli.js`]))
  assert.equal(b?.file, `${pf}\\Code.exe`)
})

test('windows: only code.cmd usable falls back to cmd.exe; nothing found is undefined', () => {
  const cli = findCodeCli(win({ LOCALAPPDATA: LOCAL, ComSpec: 'C:\\Windows\\System32\\cmd.exe' }, [`${ROOT}\\bin\\code.cmd`]))
  assert.equal(cli?.viaCmd, 'C:\\Windows\\System32\\cmd.exe')
  const inv = cliInvocation(cli!, ['--install-extension', 'C:\\a b\\m.vsix', '--force'])
  assert.equal(inv.verbatim, true)
  assert.deepEqual(inv.args.slice(0, 3), ['/d', '/s', '/c'])
  assert.equal(inv.args[3], `""${ROOT}\\bin\\code.cmd" "--install-extension" "C:\\a b\\m.vsix" "--force""`)
  assert.equal(findCodeCli(win({}, [])), undefined)
})

test('mac: fixed bundle path, no prefix, /Applications before ~/Applications', () => {
  const rel = 'Visual Studio Code.app/Contents/Resources/app/bin/code'
  const d = (files: string[]): CliDeps => ({ platform: 'darwin', env: {}, home: '/Users/a', ...fsOf(files) })
  assert.deepEqual(findCodeCli(d([`/Users/a/Applications/${rel}`, `/Applications/${rel}`])), { file: `/Applications/${rel}`, prefix: [], extraEnv: {} })
  assert.equal(findCodeCli(d([`/Users/a/Applications/${rel}`]))?.file, `/Users/a/Applications/${rel}`)
  assert.equal(findCodeCli(d([])), undefined)
  assert.deepEqual(cliInvocation({ file: '/c', prefix: [], extraEnv: {} }, ['--install-extension', 'x']), { file: '/c', args: ['--install-extension', 'x'], verbatim: false })
  assert.equal(findCodeCli({ platform: 'linux', env: {}, home: '/h', ...fsOf([]) }), undefined)
})

test('env is minimal and log labels hide paths', () => {
  const mac = cliEnvFor('darwin', { HOME: '/h', ANTHROPIC_API_KEY: 'k', LANG: 'en' })
  assert.deepEqual(mac, { PATH: '/usr/bin:/bin:/usr/sbin:/sbin', HOME: '/h', LANG: 'en' })
  const w = cliEnvFor('win32', { SystemRoot: 'C:\\Windows', LOCALAPPDATA: LOCAL, GEMINI_API_KEY: 'k', MIYAGI_TOKEN: 't' }, { ELECTRON_RUN_AS_NODE: '1' })
  assert.equal(w.GEMINI_API_KEY, undefined)
  assert.equal(w.MIYAGI_TOKEN, undefined)
  assert.equal(w.ELECTRON_RUN_AS_NODE, '1')
  assert.equal(w.LOCALAPPDATA, LOCAL)
  assert.equal(stepLabel('C:\\Users\\a\\m.vsix'), '(bundled companion)')
  assert.equal(stepLabel('/x/m.vsix'), '(bundled companion)')
  assert.equal(stepLabel('ms-python.python'), 'ms-python.python')
})
