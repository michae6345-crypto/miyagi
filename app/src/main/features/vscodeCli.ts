/**
 * Finding VS Code's own CLI, per platform, with injected env and fs so it is unit-testable on any OS.
 *
 * macOS: the `code` script inside Visual Studio Code.app (works even if `code` was never added to PATH).
 * Windows: VS Code's `code.cmd` lives in <root>\bin; we find it on PATH or at the two standard install roots, then run
 * the real thing, <root>\Code.exe with ELECTRON_RUN_AS_NODE=1 on resources\app\out\cli.js. That avoids spawning a .cmd
 * (Node refuses to without a shell) and needs no shell quoting. If only code.cmd is usable, it runs through cmd.exe.
 */
import { posix, win32 } from 'node:path'

export type CliDeps = {
  platform: string
  env: NodeJS.ProcessEnv
  home: string
  exists: (p: string) => boolean
  readdir: (p: string) => string[]
}

export type CodeCli = {
  file: string
  /** Put before the caller's own arguments (cli.js path, or the cmd.exe /c wrapper). */
  prefix: string[]
  /** Extra environment for this CLI (ELECTRON_RUN_AS_NODE on Windows). */
  extraEnv: Record<string, string>
  /** cmd.exe wrapper: the whole command line is built by `build`, passed verbatim. */
  viaCmd?: string
}

const envGet = (env: NodeJS.ProcessEnv, key: string): string | undefined => {
  const hit = Object.keys(env).find((k) => k.toLowerCase() === key.toLowerCase())
  return hit ? env[hit] || undefined : undefined
}

/** <root>\bin\code.cmd candidates, in the order the spec lists them. */
export function windowsCodeCmds(deps: CliDeps): string[] {
  const { env, exists } = deps
  const out: string[] = []
  for (const dir of (envGet(env, 'PATH') ?? '').split(';')) {
    const d = dir.trim().replace(/^"|"$/g, '')
    if (d) out.push(win32.join(d, 'code.cmd'))
  }
  const local = envGet(env, 'LOCALAPPDATA')
  if (local) out.push(win32.join(local, 'Programs', 'Microsoft VS Code', 'bin', 'code.cmd'))
  for (const k of ['ProgramFiles', 'ProgramFiles(x86)']) {
    const pf = envGet(env, k)
    if (pf) out.push(win32.join(pf, 'Microsoft VS Code', 'bin', 'code.cmd'))
  }
  return out.filter((p, i, a) => a.indexOf(p) === i && exists(p))
}

/** resources\app\out\cli.js under an install root: directly, or under a version folder (newer per-user installs). */
function cliJsIn(root: string, deps: CliDeps): string | undefined {
  const rel = win32.join('resources', 'app', 'out', 'cli.js')
  const direct = win32.join(root, rel)
  if (deps.exists(direct)) return direct
  try {
    for (const sub of deps.readdir(root)) {
      const p = win32.join(root, sub, rel)
      if (deps.exists(p)) return p
    }
  } catch {
    /* unreadable root: no cli.js */
  }
  return undefined
}

export function findCodeCli(deps: CliDeps): CodeCli | undefined {
  if (deps.platform === 'darwin') {
    const rel = 'Visual Studio Code.app/Contents/Resources/app/bin/code'
    const file = [posix.join('/Applications', rel), posix.join(deps.home, 'Applications', rel)].find((p) => deps.exists(p))
    return file ? { file, prefix: [], extraEnv: {} } : undefined
  }
  if (deps.platform !== 'win32') return undefined
  const cmds = windowsCodeCmds(deps)
  for (const cmd of cmds) {
    const root = win32.dirname(win32.dirname(cmd))
    const exe = win32.join(root, 'Code.exe')
    const js = deps.exists(exe) ? cliJsIn(root, deps) : undefined
    if (js) return { file: exe, prefix: [js], extraEnv: { ELECTRON_RUN_AS_NODE: '1' } }
  }
  if (cmds[0]) return { file: cmds[0], prefix: [], extraEnv: {}, viaCmd: envGet(deps.env, 'ComSpec') ?? 'cmd.exe' }
  return undefined
}

/** execFile arguments for one CLI call. The cmd.exe route passes one verbatim command line. */
export function cliInvocation(cli: CodeCli, args: string[]): { file: string; args: string[]; verbatim: boolean } {
  if (!cli.viaCmd) return { file: cli.file, args: [...cli.prefix, ...args], verbatim: false }
  const q = (s: string) => `"${s.replace(/"/g, '')}"`
  return { file: cli.viaCmd, args: ['/d', '/s', '/c', `"${[cli.file, ...args].map(q).join(' ')}"`], verbatim: true }
}

/** Only what VS Code's CLI needs: never our keys or the engine token. */
export function cliEnvFor(platform: string, env: NodeJS.ProcessEnv, extra: Record<string, string> = {}): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {}
  if (platform === 'win32') {
    const sys = envGet(env, 'SystemRoot') ?? 'C:\\Windows'
    out.PATH = `${win32.join(sys, 'System32')};${sys}`
    for (const k of ['SystemRoot', 'windir', 'ComSpec', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'USERNAME', 'ProgramFiles', 'ProgramData']) {
      const v = envGet(env, k)
      if (v) out[k] = v
    }
  } else {
    out.PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
    for (const k of ['HOME', 'USER', 'LOGNAME', 'LANG', 'TMPDIR']) if (env[k]) out[k] = env[k]
  }
  return { ...out, ...extra }
}

/** A log label that never carries a path: the .vsix location names the user's profile folder. */
export function stepLabel(arg: string | undefined): string {
  if (!arg) return ''
  return /[\\/]|\.vsix$/i.test(arg) ? '(bundled companion)' : arg
}
