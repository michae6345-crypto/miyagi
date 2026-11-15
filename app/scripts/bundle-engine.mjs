#!/usr/bin/env node
/**
 * Put the engine inside the Mac app: app/build/engine/{install.sh, src/, VERSION}. electron-builder copies it to
 * miyagi.app/Contents/Resources/engine (electron-builder.yml, mac.extraResources). On first launch the app copies
 * src/ to ~/miyagi/engine/src and runs install.sh on it (main/localEngine.ts).
 *
 *   node scripts/bundle-engine.mjs                     # engine from origin/integration/live (fetched first)
 *   MIYAGI_ENGINE_REF=my-branch node scripts/bundle-engine.mjs
 *   MIYAGI_INSTALL_REF=origin/claude/distribution …    # where install.sh comes from if the engine ref lacks it
 *
 * Only git-tracked files go in (git archive): no .env, no venv, no caches the learner made.
 */
import { execFileSync } from 'node:child_process'
import { chmodSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const app = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repo = resolve(app, '..')
const out = join(app, 'build', 'engine')
const REF = process.env.MIYAGI_ENGINE_REF || 'origin/integration/live'
const INSTALL_REFS = [process.env.MIYAGI_INSTALL_REF, REF, 'origin/claude/distribution'].filter(Boolean)
/** What the engine needs at runtime (docs/DISTRIBUTION.md: server imports shared/contracts; demo/cache ships lessons). */
const PATHS = ['server', 'shared', 'cli', 'scripts', 'demo']

const git = (...args) => execFileSync('git', args, { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
const has = (ref, path) => {
  try {
    git('cat-file', '-e', `${ref}:${path}`)
    return true
  } catch {
    return false
  }
}

try {
  git('fetch', '--quiet', 'origin')
} catch {
  console.warn('[bundle-engine] git fetch failed (offline?): using the refs this clone already has')
}

let sha
try {
  sha = git('rev-parse', '--short', REF).trim()
} catch {
  console.error(`[bundle-engine] no such ref: ${REF}. Set MIYAGI_ENGINE_REF to the engine branch.`)
  process.exit(1)
}
if (!has(REF, 'server/pyproject.toml')) {
  console.error(`[bundle-engine] ${REF} has no server/pyproject.toml: that's not the engine.`)
  process.exit(1)
}
const installRef = INSTALL_REFS.find((r) => has(r, 'scripts/install.sh'))
if (!installRef) {
  console.error(`[bundle-engine] no scripts/install.sh in ${INSTALL_REFS.join(', ')}. Merge Michael's installer (PR #66) or set MIYAGI_INSTALL_REF.`)
  process.exit(1)
}

rmSync(out, { recursive: true, force: true })
mkdirSync(join(out, 'src'), { recursive: true })

const paths = PATHS.filter((p) => has(REF, p))
const tar = join(app, 'build', 'engine.tar')
execFileSync('git', ['archive', '--format=tar', '-o', tar, REF, ...paths], { cwd: repo, stdio: 'inherit' })
// Relative path + cwd: GNU tar on Windows reads 'C:' as a remote host.
execFileSync('tar', ['-xf', join('..', '..', 'engine.tar')], { cwd: join(out, 'src'), stdio: 'inherit' })
rmSync(tar, { force: true })

writeFileSync(join(out, 'install.sh'), git('show', `${installRef}:scripts/install.sh`))
chmodSync(join(out, 'install.sh'), 0o755)
const version = `${REF}@${sha}`
writeFileSync(join(out, 'VERSION'), version + '\n')

console.log(`[bundle-engine] ${version} → app/build/engine (${paths.join(', ')}); install.sh from ${installRef}`)
