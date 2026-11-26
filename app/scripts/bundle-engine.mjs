#!/usr/bin/env node
/**
 * Put the engine inside the Mac app, ready to run offline (DISTRIBUTION-PLAN.md section 2, "The bundle"):
 *
 *   app/build/engine/
 *     src/            engine source from git (server, shared, cli, scripts, demo, blender-addon), .pyc precompiled
 *                     (checked-hash; server, shared and cli only: blender-addon runs in Blender's own Python)
 *     python/         standalone CPython 3.12 (python-build-standalone, pinned version + sha256) with the engine's
 *                     packages already in python/lib/python3.12/site-packages, all precompiled (unchecked-hash)
 *     vscode/         the VS Code companion: <publisher>.<name>-<version>.vsix + companion.json
 *     VERSION         <ref>@<sha> of the engine source
 *     PYTHON.json     what python/ is: version, arch, archive sha256, and every package as name==version
 *     install.sh      the old uv installer, kept only as the fallback for a --no-python build
 *
 * electron-builder copies engine/ (minus vscode/) to miyagi.app/Contents/Resources/engine and vscode/ to
 * Resources/vscode (electron-builder.yml, mac.extraResources). On first launch main/localEngine.ts copies src/ to
 * ~/miyagi/engine/src and starts `Resources/engine/python/bin/python3 -s -B -m server.orchestrator.main` there: no uv,
 * no Python download, no network. Nothing is ever written inside the signed bundle (everything is precompiled here
 * and the engine runs with -B). A build that couldn't precompile and import-check the Python stops, unless
 * --allow-unchecked (then PYTHON.json says precompiled: false and the app never uses that Python).
 *
 *   node scripts/bundle-engine.mjs                     # engine from this commit (HEAD): one trunk, so the app and engine ship together
 *   node scripts/bundle-engine.mjs --windows           # the Windows bundle (python.exe, Lib\\site-packages, PYTHON.json os: win32);
 *                                                      #   also MIYAGI_BUNDLE_PLATFORM=win32; arch x64 (MIYAGI_PY_ARCH=arm64 for Arm).
 *                                                      #   Default platform: Windows on a Windows PC, else macOS. See bundle-target.mjs.
 *   node scripts/bundle-engine.mjs --dry-run           # print every step, download and write nothing (no git fetch)
 *   node scripts/bundle-engine.mjs --no-python         # source + install.sh only (the old first-run install)
 *   node scripts/bundle-engine.mjs --offline           # packages from uv's cache only
 *   MIYAGI_ENGINE_REF=my-branch node scripts/bundle-engine.mjs
 *   MIYAGI_PY_ARCH=x64 …                               # Intel Python (default arm64; build arm64 first, universal later)
 *   … --allow-unchecked                                # a Python this machine can't run: no precompile, no import check;
 *                                                      #   PYTHON.json precompiled: false, so the app won't start it
 *   MIYAGI_INSTALL_REF=origin/claude/distribution …    # where install.sh comes from if the engine ref lacks it
 *   MIYAGI_BUNDLE_CACHE=<dir>                          # where the Python archive is cached (default ~/.cache/miyagi-bundle)
 *
 * Needs: git, tar, zip (all on macOS), and uv for the packages (https://docs.astral.sh/uv/; build machine only, the
 * learner never needs it). Only git-tracked files go in (git archive): no .env, no venv, no caches the learner made.
 * No paid API calls: the only downloads are the Python archive and the packages from PyPI.
 */
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { chmodSync, closeSync, existsSync, mkdirSync, openSync, readdirSync, readFileSync, readSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { basename, delimiter, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { BUNDLE_EXCLUDE, PY, bundleRequirements, libPath, pickPlatform, prune, pruneDirNames, pruneLists, pruneSrc, pythonPath, resolveTarget, runnableHere, sitePath } from './bundle-target.mjs'

const args = new Set(process.argv.slice(2))
for (const a of args) {
  if (!['--dry-run', '--no-python', '--offline', '--allow-unchecked', '--windows'].includes(a)) {
    console.error(`[bundle-engine] unknown option: ${a}`)
    process.exit(1)
  }
}
const DRY = args.has('--dry-run')
const WITH_PYTHON = !args.has('--no-python')
const OFFLINE = args.has('--offline')
const ALLOW_UNCHECKED = args.has('--allow-unchecked')

const app = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repo = resolve(app, '..')
const out = join(app, 'build', 'engine')
const REF = process.env.MIYAGI_ENGINE_REF || 'HEAD' // one trunk (Nov 25): the engine from this same commit, so each build pins its engine
const INSTALL_REFS = [process.env.MIYAGI_INSTALL_REF, REF, 'origin/claude/distribution'].filter(Boolean)
/** What the engine needs at runtime (docs/DISTRIBUTION.md: server imports shared/contracts; demo/cache ships lessons;
 * blender-addon: the Blender bridge (start_bridge.py) and the headless scene dump (dump_scene.py), which
 * server/workspace/blender_ext.py and blender.py find at <src>/blender-addon). */
const PATHS = ['server', 'shared', 'cli', 'scripts', 'demo', 'blender-addon']

const PLATFORM = args.has('--windows') ? 'win32' : pickPlatform({ env: process.env, hostPlatform: process.platform })
if (!PLATFORM) {
  console.error(`[bundle-engine] MIYAGI_BUNDLE_PLATFORM=${process.env.MIYAGI_BUNDLE_PLATFORM}: use darwin or win32`)
  process.exit(1)
}
const T = resolveTarget({ platform: PLATFORM, arch: process.env.MIYAGI_PY_ARCH })
if (T.error) {
  console.error(`[bundle-engine] ${T.error}`)
  process.exit(1)
}
const { arch: ARCH, triple: TRIPLE, file: PY_FILE, url: PY_URL, minor: PY_MINOR } = T
const CACHE = process.env.MIYAGI_BUNDLE_CACHE || join(homedir(), '.cache', 'miyagi-bundle')

/** Imported with the bundled Python before we call the bundle good (bundle-target.mjs: no pyobjc on Windows). */
const SMOKE = T.smoke

const say = (m) => console.log(`[bundle-engine] ${m}`)
const die = (m) => {
  console.error(`[bundle-engine] ${m}`)
  process.exit(1)
}
const git = (...a) => execFileSync('git', a, { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
const has = (ref, path) => {
  try {
    git('cat-file', '-e', `${ref}:${path}`)
    return true
  } catch {
    return false
  }
}
const run = (cmd, a, opts = {}) => {
  if (DRY) return say(`would run: ${cmd} ${a.map((x) => (/\s/.test(x) ? JSON.stringify(x) : x)).join(' ')}`)
  execFileSync(cmd, a, { stdio: 'inherit', ...opts })
}
const which = (cmd) => {
  const extra = [join(homedir(), '.local', 'bin'), join(homedir(), '.cargo', 'bin'), '/opt/homebrew/bin', '/usr/local/bin']
  const names = process.platform === 'win32' ? [`${cmd}.exe`, cmd] : [cmd]
  for (const d of [...(process.env.PATH ?? '').split(delimiter), ...extra]) {
    for (const n of names) if (d && existsSync(join(d, n))) return join(d, n)
  }
  return null
}
const sha256 = (file) => createHash('sha256').update(readFileSync(file)).digest('hex')
const du = (p) => {
  try {
    return execFileSync('du', ['-sh', p], { encoding: 'utf8' }).split('\t')[0]
  } catch {
    return '?'
  }
}
const readText = (p) => {
  try {
    return readFileSync(p, 'utf8')
  } catch {
    return ''
  }
}
const xml = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

// ---------------------------------------------------------------------------------------------------------------------
// 1. The engine source

// A dry run uses the network for nothing and moves no refs: it reads the refs this clone already has.
if (DRY) {
  say('would run: git fetch --quiet origin (dry run: using the refs this clone already has)')
} else {
  try {
    git('fetch', '--quiet', 'origin')
  } catch {
    console.warn('[bundle-engine] git fetch failed (offline?): using the refs this clone already has')
  }
}

let sha
try {
  sha = git('rev-parse', '--short', REF).trim()
} catch {
  die(`no such ref: ${REF}. Set MIYAGI_ENGINE_REF to the engine branch.`)
}
if (!has(REF, 'server/pyproject.toml')) die(`${REF} has no server/pyproject.toml: that's not the engine.`)
const installRef = INSTALL_REFS.find((r) => has(r, 'scripts/install.sh'))
if (!installRef && !WITH_PYTHON) {
  die(`no scripts/install.sh in ${INSTALL_REFS.join(', ')}. Merge Michael's installer (PR #66), set MIYAGI_INSTALL_REF, or drop --no-python.`)
}
const version = `${REF}@${sha}`
const paths = PATHS.filter((p) => has(REF, p))

say(`engine ${version} (${paths.join(', ')}) → app/build/engine/src${DRY ? ' [dry run: nothing is written]' : ''}`)
if (!DRY) {
  rmSync(out, { recursive: true, force: true })
  mkdirSync(join(out, 'src'), { recursive: true })
  const tar = join(app, 'build', 'engine.tar')
  execFileSync('git', ['archive', '--format=tar', '-o', tar, REF, ...paths], { cwd: repo, stdio: 'inherit' })
  // Relative path + cwd: GNU tar on Windows reads 'C:' as a remote host.
  execFileSync('tar', ['-xf', join('..', '..', 'engine.tar')], { cwd: join(out, 'src'), stdio: 'inherit' })
  rmSync(tar, { force: true })
  say(`pruned ${pruneSrc(join(out, 'src'))} test folders/files from the engine source`)
  writeFileSync(join(out, 'VERSION'), version + '\n')
  if (installRef) {
    writeFileSync(join(out, 'install.sh'), git('show', `${installRef}:scripts/install.sh`))
    chmodSync(join(out, 'install.sh'), 0o755)
  }
}
if (installRef) say(`install.sh (fallback only) from ${installRef}`)

// ---------------------------------------------------------------------------------------------------------------------
// 2. Standalone Python with the engine's packages

/** Download (or reuse the cached copy of) the pinned archive and check its sha256. → path */
async function pythonArchive() {
  const file = join(CACHE, PY_FILE)
  const want = T.sha256
  if (DRY) {
    say(`would ${existsSync(file) ? 'reuse' : 'download'} ${PY_URL}`)
    say(`would check sha256 ${want}`)
    return file
  }
  mkdirSync(CACHE, { recursive: true })
  if (existsSync(file) && sha256(file) === want) {
    say(`python archive cached: ${file}`)
    return file
  }
  if (OFFLINE) die(`--offline and no verified ${PY_FILE} in ${CACHE}`)
  say(`downloading ${PY_FILE}`)
  const res = await fetch(PY_URL, { redirect: 'follow' })
  if (!res.ok) die(`download failed (${res.status}): ${PY_URL}`)
  const buf = Buffer.from(await res.arrayBuffer())
  const got = createHash('sha256').update(buf).digest('hex')
  if (got !== want) die(`sha256 mismatch for ${PY_FILE}: got ${got}, pinned ${want}. Not using it.`)
  const part = `${file}.part`
  writeFileSync(part, buf)
  renameSync(part, file)
  return file
}

/**
 * Can this machine run the bundled interpreter (same OS; same arch, or arm64 Mac with Rosetta for x64, or Windows on Arm for x64)? -B and
 * PYTHONDONTWRITEBYTECODE: starting it must not write timestamp .pycs into python/lib (-I ignores the variable, -B
 * doesn't). The compileall -f below rewrites any that slip in anyway.
 */
function runnable(python) {
  if (DRY || !runnableHere(T, process.platform)) return false
  try {
    execFileSync(python, ['-I', '-B', '-c', 'import sys'], { stdio: 'ignore', timeout: 20_000, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } })
    return true
  } catch {
    return false
  }
}

/**
 * .pyc files under `dir` whose header flags are 0 (timestamp-checked). electron-builder doesn't keep mtimes, so in
 * miyagi.app every one of these is stale and a Python started without PYTHONDONTWRITEBYTECODE (a lesson .venv in
 * VS Code) would rewrite it inside the signed bundle. → relative paths
 */
function timestampPycs(dir) {
  const bad = []
  const head = Buffer.alloc(8)
  const walk = (d) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, e.name)
      if (e.isDirectory() && !e.isSymbolicLink()) walk(p)
      else if (e.isFile() && e.name.endsWith('.pyc')) {
        const fd = openSync(p, 'r')
        try {
          // PEP 552: bytes 4..7 are the flags word: 0 = timestamp, 1 = unchecked-hash, 3 = checked-hash.
          if (readSync(fd, head, 0, 8, 0) < 8 || head.readUInt32LE(4) === 0) bad.push(p.slice(dir.length + 1))
        } finally {
          closeSync(fd)
        }
      }
    }
  }
  walk(dir)
  return bad
}

/**
 * Mach-O files under python/ that load a library prune() removed (libpython3.12.dylib, Tcl/Tk). The import check
 * only loads what the engine imports; this covers every extension. → "file → library" lines
 */
function prunedLinks(pyDir) {
  const gone = /libpython3|libtcl|libtk|tcl9tk/
  const files = []
  const walk = (d) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, e.name)
      if (e.isDirectory() && !e.isSymbolicLink()) walk(p)
      else if (e.isFile() && (/\.(so|dylib)$/.test(e.name) || d.endsWith('/bin'))) files.push(p)
    }
  }
  walk(pyDir)
  const bad = []
  for (const f of files) {
    let links = ''
    try {
      links = execFileSync('otool', ['-L', f], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
    } catch {
      continue // not Mach-O (a shell script in bin/)
    }
    for (const line of links.split('\n').slice(1)) if (gone.test(line)) bad.push(`${f.slice(pyDir.length + 1)} → ${line.trim().split(' ')[0]}`)
  }
  return bad
}

/** Every package in site-packages as name==version, sorted (from each *.dist-info/METADATA). */
function frozen(site) {
  const out = []
  for (const name of readdirSync(site)) {
    if (!name.endsWith('.dist-info')) continue
    const meta = readText(join(site, name, 'METADATA'))
    const field = (k) => meta.match(new RegExp(`^${k}:\\s*(.+)$`, 'mi'))?.[1].trim()
    const [dn, dv] = name.slice(0, -'.dist-info'.length).split('-')
    out.push(`${field('Name') ?? dn}==${field('Version') ?? dv}`)
  }
  return out.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
}

async function bundlePython() {
  const uv = which('uv')
  if (!uv) die('needs uv on the build machine to install the packages (https://docs.astral.sh/uv/), or use --no-python')
  const archive = await pythonArchive()
  const pyDir = join(out, 'python')
  const python = pythonPath(T, pyDir)
  const site = sitePath(T, pyDir)

  // The archive's top folder is python/.
  run('tar', ['-xzf', archive, '-C', out])
  if (!DRY && !existsSync(python)) die(`no python/${T.pythonRel.join('/')} in ${PY_FILE}`)
  const canRun = runnable(python)

  // Only the engine's dependencies (`-r` installs them, not the server package itself: the source runs
  // from ~/miyagi/engine/src, the cwd of `python3 -m`). Wheels only, for the target platform, so an x64 build works on arm64.
  // A requirements file from pyproject's dependencies minus BUNDLE_EXCLUDE (google-genai: Gemini is opt-in only).
  const req = join(out, 'requirements.bundle.txt')
  const reqs = bundleRequirements(git('show', `${REF}:server/pyproject.toml`))
  if (DRY) say(`would install: ${reqs.join(' ')} (left out: ${BUNDLE_EXCLUDE.join(', ')})`)
  else writeFileSync(req, reqs.join('\n') + '\n')
  const uvArgs = ['pip', 'install', '--quiet', '--target', site, '--python-version', PY_MINOR, '--python-platform', TRIPLE, '--only-binary', ':all:', '-r', req]
  // Resolve against the bundled interpreter itself when this machine can run it (uv finds another one otherwise).
  if (canRun) uvArgs.push('--python', python)
  if (OFFLINE) uvArgs.push('--offline')
  say(`installing the engine's packages into python/${T.libRel.join('/')}/site-packages`)
  // A throwaway venv context: uv must not pick up this checkout's .venv or a VIRTUAL_ENV from the shell. uv starts the
  // bundled interpreter to read its tags: it must not leave timestamp .pycs behind either.
  const uvEnv = { ...process.env, VIRTUAL_ENV: '', UV_NO_CONFIG: '1', PYTHONDONTWRITEBYTECODE: '1' }
  run(uv, uvArgs, { cwd: tmpdir(), env: uvEnv })
  if (!DRY) rmSync(req, { force: true })

  if (DRY) {
    say(`would prune: site-packages/**/{${pruneDirNames().join(',')}}, psycopg_binary, pip, site-packages/${T.win ? 'Scripts' : 'bin'}, stubs and C/Cython sources, dist-info RECORD; stdlib ${pruneLists(T).stdlib.join(', ')}; python/{${pruneLists(T).python.join(',')}}, Tcl/Tk; src/**/tests`)
    say(`would precompile python/ (unchecked-hash) and src/ (checked-hash), then import-check: ${SMOKE.replace('import ', '')}`)
    return { python, ran: false }
  }
  say(`pruned ${prune(T, pyDir)} folders/files the engine never loads (SIZE.md)`)

  if (!canRun) {
    // Without precompiling, a lesson .venv made from this Python would write .pycs inside the signed app, and nothing
    // checked that the engine imports. localEngine.ts refuses a PYTHON.json without precompiled: true.
    const why = `can't run the ${ARCH} Python on this machine, so it can't be precompiled or import-checked`
    if (!ALLOW_UNCHECKED) die(`${why}. Build on a Mac that runs ${ARCH} (Rosetta for x64), or pass --allow-unchecked for a bundle the app won't use.`)
    console.warn(`[bundle-engine] ${why}: --allow-unchecked, so PYTHON.json says precompiled: false and the app falls back.`)
    return { python, ran: false }
  }

  const pyEnv = { ...process.env, PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '', PYTHONPATH: '' }
  // unchecked-hash: never re-validated, so Python never tries to rewrite a .pyc inside the signed app. -f: rewrite the
  // timestamp .pycs that starting the interpreter above (runnable, uv) may have left (compileall skips them otherwise).
  run(python, ['-I', '-m', 'compileall', '-f', '-q', '-j', '0', '--invalidation-mode', 'unchecked-hash', libPath(T, pyDir)], { env: pyEnv, stdio: ['ignore', 'ignore', 'inherit'] })
  // checked-hash: src/ is copied to ~/miyagi/engine/src (timestamps change), and a hash check stays valid there.
  const srcDirs = ['server', 'shared', 'cli'].map((d) => join(out, 'src', d)).filter((d) => existsSync(d))
  run(python, ['-I', '-m', 'compileall', '-q', '-j', '0', '--invalidation-mode', 'checked-hash', ...srcDirs], { env: pyEnv, stdio: ['ignore', 'ignore', 'inherit'] })

  // The import check: the packages, then the engine itself with no keys (no network, no model calls on import).
  const noKeys = { ANTHROPIC_API_KEY: '', GEMINI_API_KEY: '', TIGER_DATABASE_URL: '', ELEVENLABS_API_KEY: '' }
  const checkEnv = { ...pyEnv, ...noKeys, PYTHONDONTWRITEBYTECODE: '1' }
  try {
    execFileSync(python, ['-I', '-B', '-c', SMOKE], { env: checkEnv, stdio: ['ignore', 'ignore', 'pipe'], timeout: 120_000 })
    execFileSync(python, ['-B', '-c', 'import server.orchestrator.main'], {
      cwd: join(out, 'src'),
      env: { ...checkEnv, PYTHONPATH: join(out, 'src') },
      stdio: ['ignore', 'ignore', 'pipe'],
      timeout: 120_000,
    })
  } catch (err) {
    die(`the bundled Python can't import the engine:\n${String(err.stderr ?? err).slice(-1500)}`)
  }
  const stale = timestampPycs(pyDir)
  if (stale.length) die(`${stale.length} timestamp .pyc files left in python/ (they'd be rewritten inside the signed app), e.g. ${stale.slice(0, 5).join(', ')}`)
  say('python/: every .pyc is hash-based (0 timestamp .pycs)')
  if (T.checksLinks) {
    const dangling = prunedLinks(pyDir)
    if (dangling.length) die(`binaries still link pruned libraries (put them back in PRUNE_*): ${dangling.slice(0, 5).join('; ')}`)
    say('python/: no binary links a pruned library (libpython, Tcl/Tk)')
  } else say('python/: skipped the pruned-library link check (needs otool, macOS only)')
  return { python, ran: true }
}

// ---------------------------------------------------------------------------------------------------------------------
// 3. The VS Code companion .vsix (a zip: [Content_Types].xml + extension.vsixmanifest + extension/<files>), built
//    with plain zip like scripts/package-vscode-ext.sh (PR #66): no npm, no vsce.

function bundleCompanion() {
  if (!has(REF, 'vscode-ext/package.json')) {
    console.warn(`[bundle-engine] ${REF} has no vscode-ext/: the app ships without the companion (onboarding shows it as unavailable)`)
    return null
  }
  const pkg = JSON.parse(git('show', `${REF}:vscode-ext/package.json`))
  const { name, publisher, version: ver } = pkg
  if (!name || !publisher || !ver) die('vscode-ext/package.json needs name, publisher and version')
  const id = `${publisher}.${name}`
  const file = `${id}-${ver}.vsix`
  const dir = join(out, 'vscode')
  if (DRY) {
    say(`would pack ${REF}:vscode-ext → app/build/engine/vscode/${file}`)
    return { id, version: ver, file }
  }
  const stage = join(tmpdir(), `miyagi-vsix-${process.pid}`)
  rmSync(stage, { recursive: true, force: true })
  mkdirSync(join(stage, 'extension'), { recursive: true })
  // Only what runs: the tests and dev files stay out.
  const files = ['package.json', 'extension.js', 'README.md', 'LICENSE', pkg.icon].filter((f, i, a) => f && a.indexOf(f) === i && has(REF, `vscode-ext/${f}`))
  for (const f of files) {
    if (f.includes('/') || f.startsWith('.')) continue
    writeFileSync(join(stage, 'extension', f), execFileSync('git', ['show', `${REF}:vscode-ext/${f}`], { cwd: repo, maxBuffer: 64 << 20 }))
  }
  writeFileSync(
    join(stage, '[Content_Types].xml'),
    `<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".png" ContentType="image/png"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
  <Default Extension="" ContentType="text/plain"/>
</Types>
`
  )
  const icon = pkg.icon && files.includes(pkg.icon) ? `\n    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default" Path="extension/${xml(pkg.icon)}" Addressable="true"/>` : ''
  writeFileSync(
    join(stage, 'extension.vsixmanifest'),
    `<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="${xml(name)}" Version="${xml(ver)}" Publisher="${xml(publisher)}"/>
    <DisplayName>${xml(pkg.displayName ?? name)}</DisplayName>
    <Description xml:space="preserve">${xml(pkg.description)}</Description>
    <Categories>Other</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="${xml(pkg.engines?.vscode ?? '*')}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value=""/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value=""/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>${icon}
  </Assets>
</PackageManifest>
`
  )
  mkdirSync(dir, { recursive: true })
  const members = ['[Content_Types].xml', 'extension.vsixmanifest', 'extension']
  // Windows has no zip: its bsdtar writes zip archives.
  if (process.platform === 'win32') execFileSync('tar', ['-a', '-c', '--format', 'zip', '-f', join(dir, file), ...members], { cwd: stage, stdio: 'inherit' })
  else execFileSync('zip', ['-qrXD', join(dir, file), ...members], { cwd: stage, stdio: 'inherit' })
  rmSync(stage, { recursive: true, force: true })
  // main/localEngine.ts reads this to compare with what VS Code has installed.
  writeFileSync(join(dir, 'companion.json'), JSON.stringify({ id, version: ver, file }, null, 2) + '\n')
  say(`companion ${id}@${ver} → app/build/engine/vscode/${file} (${(statSync(join(dir, file)).size / 1024).toFixed(0)} KB)`)
  return { id, version: ver, file }
}

// ---------------------------------------------------------------------------------------------------------------------

const companion = bundleCompanion()
let py = null
if (WITH_PYTHON) {
  if (T.platform === 'darwin' && process.platform !== 'darwin' && !DRY) die('the macOS bundled Python needs a Mac to build: run this on a Mac, or use --no-python')
  py = await bundlePython()
  if (!DRY) {
    const site = sitePath(T, join(out, 'python'))
    // What shipped, exactly: pyproject.toml has only lower bounds (no lock yet, see agents/bundle.md core requests).
    const freeze = frozen(site)
    const packages = freeze.length
    const manifest = { python: PY.version, release: PY.release, ...T.manifestExtra, arch: ARCH, archive: PY_FILE, sha256: T.sha256, packages, precompiled: py.ran, engine: version, freeze }
    writeFileSync(join(out, 'PYTHON.json'), JSON.stringify(manifest, null, 2) + '\n')
    say(`python ${PY.version} (${ARCH}) with ${packages} packages: ${du(join(out, 'python'))} on disk`)
  }
}
if (!DRY) say(`done: app/build/engine ${du(out)} (${basename(out)}/: src${py ? ', python' : ''}${companion ? ', vscode' : ''}, VERSION)`)
