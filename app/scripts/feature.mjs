#!/usr/bin/env node
/**
 * One git worktree + branch per feature agent.
 *
 *   npm run feature -- new player            → ../tut-player on branch adrian/player, scaffolded + npm ci
 *   npm run feature -- new player --no-install
 *   npm run feature -- new player --from origin/adrian/shell
 *   npm run feature -- list
 *
 * Then: open a Claude Code session in that folder and paste the kickoff line it prints.
 */
import { execSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

const [cmdName, name, ...rest] = process.argv.slice(2)
const sh = (c, opts = {}) => execSync(c, { stdio: 'pipe', encoding: 'utf8', ...opts }).trim()
const root = sh('git rev-parse --show-toplevel')

if (cmdName === 'list') {
  console.log(sh('git worktree list'))
  process.exit(0)
}
if (cmdName !== 'new' || !name || !/^[a-z][a-z0-9-]*$/.test(name)) {
  console.error('usage: npm run feature -- new <name> [--from <ref>] [--no-install]   (name: lowercase, dashes)')
  process.exit(1)
}

const flag = (f) => rest.includes(f)
const fromIdx = rest.indexOf('--from')
sh('git fetch origin', { cwd: root })
// Base on main once the feature infrastructure is merged there; until then on adrian/shell.
const hasInfra = (ref) => {
  try {
    sh(`git cat-file -e ${ref}:app/src/renderer/src/core/registry.ts`, { cwd: root })
    return true
  } catch {
    return false
  }
}
const base = fromIdx >= 0 ? rest[fromIdx + 1] : hasInfra('origin/main') ? 'origin/main' : 'origin/adrian/shell'
const branch = `adrian/${name}`
const dir = resolve(root, '..', `tut-${name}`)

if (existsSync(dir)) {
  console.error(`${dir} already exists (git worktree list to see it)`)
  process.exit(1)
}
console.log(`→ worktree ${dir}\n  branch ${branch} from ${base}`)
sh(`git worktree add "${dir}" -b ${branch} ${base}`, { cwd: root })

// Scaffold the renderer feature folder if it doesn't exist yet.
const featDir = join(dir, 'app/src/renderer/src/features', name)
if (!existsSync(join(featDir, 'index.tsx')) && !existsSync(join(featDir, 'index.ts'))) {
  mkdirSync(featDir, { recursive: true })
  writeFileSync(
    join(featDir, 'index.tsx'),
    `/**
 * Feature: ${name}. Brief: app/agents/${name}.md
 * Contribute islandModes / overlayLayers / windows here (see core/registry.ts). Keep all code in this folder.
 */
import { defineFeature } from '../../core/registry'

export default defineFeature({
  id: '${name}'
})
`
  )
  console.log(`  scaffolded app/src/renderer/src/features/${name}/index.tsx`)
}

const brief = join(dir, 'app/agents', `${name}.md`)
if (!existsSync(brief)) {
  mkdirSync(dirname(brief), { recursive: true })
  writeFileSync(brief, readFileSync(join(dir, 'app/agents/_template.md'), 'utf8').replaceAll('<name>', name))
  console.log(`  created app/agents/${name}.md from the template (fill in the spec)`)
}

if (!flag('--no-install')) {
  console.log('  npm ci in app/ …')
  execSync('npm ci --no-audit --no-fund', { cwd: join(dir, 'app'), stdio: 'inherit' })
}

const ports = JSON.parse(readFileSync(join(dir, 'app/agents/ports.json'), 'utf8'))
const port = ports[name] ?? 5199
console.log(`
Done. Next:
  1. Open a Claude Code session in: ${dir}
  2. Kickoff: "Read app/CLAUDE.md and app/agents/${name}.md, then build it. Stage: npm run dev:web -- --port ${port} → http://localhost:${port}/?scenario=${name}"
`)
