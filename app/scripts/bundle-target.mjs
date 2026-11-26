/**
 * Which Python bundle bundle-engine.mjs builds, and what its folder looks like: macOS (the shipped one) or Windows.
 * Pure functions and constants only (no downloads, no writes beyond prune()), so app/test/bundleTarget.test.ts can
 * check them offline on any machine.
 *
 * The Mac target's values are exactly what bundle-engine.mjs had inline before Windows existed.
 */
import { existsSync, readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'

/**
 * The pinned interpreter: python-build-standalone, install_only_stripped (relocatable, no debug symbols). To move it,
 * take the new release's SHA256SUMS (github.com/astral-sh/python-build-standalone/releases) and change every hash:
 * macOS arm64, macOS x64, Windows x64, Windows arm64 (the install_only_stripped.tar.gz line of each).
 */
export const PY = {
  version: '3.12.16',
  release: '20261026',
  sha256: {
    darwin: {
      arm64: '353d5f1b4fd2715e7053f12f068435d5bbad16b91e057006b5d01e0925709a7e',
      x64: '37c38fda76fec1fbf310adcbafb7f0d96af13b5511bf8ea954c3aa8eec185734',
    },
    win32: {
      x64: '1f2ab53880fc67ea323398c6388e05af28addc99a8e389209f08a51fdff4b149',
      arm64: '3b2e4da9209cec3e0eaf4db31176977a88df32d598ff94a7899c34cd8304db04',
    },
  },
}

const TRIPLES = {
  darwin: { arm64: 'aarch64-apple-darwin', x64: 'x86_64-apple-darwin' },
  win32: { arm64: 'aarch64-pc-windows-msvc', x64: 'x86_64-pc-windows-msvc' },
}

/** Imported with the bundled Python before we call the bundle good. */
// google.genai is not here: the bundle leaves it out (BUNDLE_EXCLUDE). The engine's own import check covers its absence.
const SMOKE_COMMON = 'fastapi, uvicorn, websockets, pydantic, httpx, anthropic, jsonschema, watchdog, rapidfuzz, PIL'
/** macOS only: pyobjc frameworks (Quartz, Vision, ScreenCaptureKit, ApplicationServices; HIServices and AppKit, which server/screen/ax.py imports directly) don't exist on Windows. */
const SMOKE_MAC_ONLY = 'Quartz, Vision, ScreenCaptureKit, ApplicationServices, HIServices, AppKit'

/**
 * The target platform: MIYAGI_BUNDLE_PLATFORM (darwin | win32; also win / windows / mac / macos), else the machine
 * running the build when that is Windows, else macOS (what every existing build gets). → 'darwin' | 'win32', or null
 */
export function pickPlatform({ env = {}, hostPlatform = 'darwin' } = {}) {
  const want = String(env.MIYAGI_BUNDLE_PLATFORM ?? '').trim().toLowerCase()
  if (!want) return hostPlatform === 'win32' ? 'win32' : 'darwin'
  if (['darwin', 'mac', 'macos'].includes(want)) return 'darwin'
  if (['win32', 'win', 'windows'].includes(want)) return 'win32'
  return null
}

/**
 * Everything that depends on the target: archive name and URL, the pinned hash, the folder layout under python/, the
 * prune lists and the import check. arch defaults to arm64 on macOS (as before) and x64 on Windows (a Windows PC that
 * is Arm runs the x64 Python too; PYTHON.json arch tells localEngine.ts which one this is). → target, or { error }
 */
export function resolveTarget({ platform = 'darwin', arch } = {}) {
  if (platform !== 'darwin' && platform !== 'win32') return { error: `unknown platform ${platform}: use darwin or win32` }
  const a = arch || (platform === 'win32' ? 'x64' : 'arm64')
  if (!(a in PY.sha256[platform])) return { error: `MIYAGI_PY_ARCH=${a}: use ${Object.keys(PY.sha256[platform]).join(' or ')} for ${platform}` }
  const win = platform === 'win32'
  const triple = TRIPLES[platform][a]
  const minor = PY.version.split('.').slice(0, 2).join('.')
  const file = `cpython-${PY.version}+${PY.release}-${triple}-install_only_stripped.tar.gz`
  return {
    platform,
    arch: a,
    win,
    triple,
    minor,
    file,
    url: `https://github.com/astral-sh/python-build-standalone/releases/download/${PY.release}/${encodeURIComponent(file)}`,
    sha256: PY.sha256[platform][a],
    // python/ layout. Mac: bin/python3, lib/python3.12/site-packages. Windows: python.exe next to its DLLs, Lib\site-packages.
    pythonRel: win ? ['python.exe'] : ['bin', 'python3'],
    libRel: win ? ['Lib'] : ['lib', `python${minor}`],
    binRel: win ? ['Scripts'] : ['bin'],
    // PYTHON.json: the Mac manifest has never had an os field (localEngine.ts reads a missing one as darwin); Windows says win32.
    manifestExtra: win ? { os: 'win32' } : {},
    smoke: `import ${SMOKE_COMMON}${win ? '' : `, ${SMOKE_MAC_ONLY}`}`,
    // otool (Mach-O) and the pruned-library link check are macOS only.
    checksLinks: !win,
  }
}

export const pythonPath = (t, pyDir) => join(pyDir, ...t.pythonRel)
export const libPath = (t, pyDir) => join(pyDir, ...t.libRel)
export const sitePath = (t, pyDir) => join(libPath(t, pyDir), 'site-packages')

/**
 * Engine dependencies the bundled app leaves out (SIZE.md, "What was cut"). google-genai pulls in google-auth,
 * cryptography, pyasn1 and rsa (about 28 MB on disk). Gemini is opt-in only (LESSON_ENGINE, FINDER_SKIM_TOP,
 * FINDER_GEMINI_FALLBACK) and every call site imports the SDK lazily; without it the engine reports Gemini as off
 * (server/lesson/gemini.sdk_available, server/finder/env.sdk_available). Dev checkouts still install it from pyproject.
 */
export const BUNDLE_EXCLUDE = ['google-genai']

/** The `dependencies = [...]` of a pyproject.toml, minus BUNDLE_EXCLUDE, as requirements.txt lines (markers kept). */
export function bundleRequirements(pyproject, exclude = BUNDLE_EXCLUDE) {
  const block = pyproject.match(/^dependencies\s*=\s*\[([\s\S]*?)^\]/m)
  if (!block) throw new Error('no dependencies = [...] in pyproject.toml')
  const deps = [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1].trim())
  const name = (d) => d.match(/^[A-Za-z0-9._-]+/)?.[0].toLowerCase().replace(/[._]/g, '-')
  const drop = new Set(exclude.map((e) => e.toLowerCase().replace(/[._]/g, '-')))
  return deps.filter((d) => !drop.has(name(d)))
}

/** Where the bundle can be run for the precompile and import check: this machine's OS is the target's. */
export function runnableHere(t, hostPlatform) {
  return hostPlatform === t.platform
}

/**
 * Pruned after the packages are in (app/SIZE.md has the reasons and the sizes):
 *   site-packages: tests (PyObjCTest alone is ~16 MB), Tiger's Postgres driver (Tiger is gone; psycopg is only
 *     imported when TIGER_DATABASE_URL is set), console scripts whose shebangs point at this build machine, pip (the
 *     standalone Python ships it; the engine never runs it, and lesson .venvs get their own pip from ensurepip),
 *     build-only sources (.pyi stubs, Cython .pyx/.pxd, C sources) and each dist-info's RECORD (lists files we pruned).
 *     .py and .pyc both stay: anyio builds its lazy-import map from its own source (inspect.getsource), so a
 *     sourceless site-packages breaks it; the .pyc keep the engine import at about 1 s instead of 2 to 2.5 s.
 *   stdlib: tests, IDLE, Tk (tkinter, turtle and the Tcl/Tk libraries), lib2to3, pydoc_data. ensurepip and venv stay:
 *     lesson .venvs are made from this Python when the machine has no other (MIYAGI_BUNDLED_PYTHON).
 *   python/: Mac: libpython3.12.dylib (bin/python3.12 is statically linked; it is only for embedding), the C headers,
 *     man pages and pkg-config files (only for building extensions against this Python), and the 2to3, pydoc, pip
 *     and *-config scripts. Windows: include/ and libs/ (headers and import libraries, only for building extensions),
 *     tcl/ and the Tcl/Tk DLLs, and Scripts/ (pip launchers). python312.dll, python3.dll, vcruntime and the rest of
 *     DLLs/ stay: python.exe doesn't start without them.
 */
const PRUNE_SITE_DIRS = new Set(['PyObjCTest', 'tests', 'test', '__tests__'])
const PRUNE_SITE_TOP_MAC = [/^psycopg_binary/, /^bin$/, /^pip$/, /^pip-.*\.dist-info$/]
// uv --target puts console scripts in Scripts on Windows.
const PRUNE_SITE_TOP_WIN = [...PRUNE_SITE_TOP_MAC, /^Scripts$/]
const PRUNE_SITE_FILES = [/\.pyi$/, /\.pyx$/, /\.pxd$/, /\.c$/, /\.cpp$/]
const PRUNE_DIST_INFO_FILES = new Set(['RECORD'])
const PRUNE_STDLIB_COMMON = ['test', 'idlelib', 'turtledemo', 'tkinter', 'turtle.py', 'lib2to3', 'pydoc_data']
// Paths are relative to the stdlib folder (lib/python3.12 or Lib); the Windows Tk extension and DLLs sit in python/DLLs.
const PRUNE_STDLIB = {
  darwin: [...PRUNE_STDLIB_COMMON, 'lib-dynload/_tkinter.cpython-312-darwin.so'],
  win32: PRUNE_STDLIB_COMMON,
}
// Relative to python/.
const PRUNE_PYTHON = {
  darwin: ['include', 'share', 'lib/pkgconfig', 'lib/libpython3.12.dylib', 'lib/libtcl9.0.dylib', 'lib/libtcl9tk9.0.dylib'],
  win32: ['include', 'libs', 'tcl', 'DLLs/_tkinter.pyd', 'DLLs/tcl86t.dll', 'DLLs/tk86t.dll'],
}
const PRUNE_PYTHON_LIB = [/^tcl\d/, /^tk\d/, /^itcl\d/, /^thread\d/]
const PRUNE_BIN = [/^idle3/, /^2to3/, /^pydoc3/, /^pip/, /-config$/]
/** Engine source: the tests stay in git (no runtime module imports them). */
const PRUNE_SRC_DIRS = new Set(['tests'])
const PRUNE_SRC_FILES = new Set(['conftest.py'])

export const pruneLists = (t) => ({
  siteTop: t.win ? PRUNE_SITE_TOP_WIN : PRUNE_SITE_TOP_MAC,
  stdlib: PRUNE_STDLIB[t.platform],
  python: PRUNE_PYTHON[t.platform],
})
export const pruneDirNames = () => [...PRUNE_SITE_DIRS]

/** Remove what the engine never needs (PRUNE_* above). → files removed */
export function prune(t, pyDir) {
  let removed = 0
  const lists = pruneLists(t)
  const lib = libPath(t, pyDir)
  for (const d of lists.stdlib) {
    if (existsSync(join(lib, d))) {
      rmSync(join(lib, d), { recursive: true, force: true })
      removed++
    }
  }
  for (const p of lists.python) {
    if (existsSync(join(pyDir, p))) {
      rmSync(join(pyDir, p), { recursive: true, force: true })
      removed++
    }
  }
  // Mac only: Tcl/Tk live in python/lib next to the stdlib folder. (Windows keeps them in python/tcl, removed above.)
  if (!t.win) {
    for (const name of readdirSync(join(pyDir, 'lib'))) {
      if (PRUNE_PYTHON_LIB.some((re) => re.test(name))) {
        rmSync(join(pyDir, 'lib', name), { recursive: true, force: true })
        removed++
      }
    }
  }
  // Their scripts in bin/ (Scripts\ on Windows) would point at the pruned idlelib, lib2to3, pydoc_data and pip.
  const bin = join(pyDir, ...t.binRel)
  if (existsSync(bin)) {
    for (const name of readdirSync(bin)) {
      if (PRUNE_BIN.some((re) => re.test(name))) {
        rmSync(join(bin, name), { force: true })
        removed++
      }
    }
  }
  const site = sitePath(t, pyDir)
  for (const name of readdirSync(site)) {
    if (lists.siteTop.some((re) => re.test(name))) {
      rmSync(join(site, name), { recursive: true, force: true })
      removed++
    }
  }
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (e.isSymbolicLink()) continue
      const p = join(dir, e.name)
      const drop = e.isDirectory()
        ? PRUNE_SITE_DIRS.has(e.name)
        : PRUNE_SITE_FILES.some((re) => re.test(e.name)) || (PRUNE_DIST_INFO_FILES.has(e.name) && /\.dist-info$/.test(dir.replace(/[\\/]+$/, '')))
      if (drop) {
        rmSync(p, { recursive: true, force: true })
        removed++
      } else if (e.isDirectory()) walk(p)
    }
  }
  walk(site)
  return removed
}

/** The engine source minus its tests (PRUNE_SRC_*). → files removed */
export function pruneSrc(srcDir) {
  let removed = 0
  const walk = (dir) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (e.isSymbolicLink()) continue
      const p = join(dir, e.name)
      if (e.isDirectory() ? PRUNE_SRC_DIRS.has(e.name) : PRUNE_SRC_FILES.has(e.name)) {
        rmSync(p, { recursive: true, force: true })
        removed++
      } else if (e.isDirectory()) walk(p)
    }
  }
  for (const d of ['server', 'shared', 'cli']) if (existsSync(join(srcDir, d))) walk(join(srcDir, d))
  return removed
}
