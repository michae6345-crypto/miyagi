/**
 * A module-level alias of a namespace import (`import * as store from './store'` then `const s = store`) is read while
 * modules load. In a production bundle a namespace object is built when its own module runs, so across an import cycle
 * the alias can capture undefined for good. The dev server and these tests use native modules, where the namespace
 * exists before any module runs, so nothing fails until the packaged app.
 *
 * This happened in features/cards/panel.ts: `const drawer = drawerStore` made the island crash and hide as soon as a
 * lesson with the panel started ("Cannot read properties of undefined (reading 'usePanel')"). This reads the renderer
 * source and fails on any such alias, so the namespace is always read at call time.
 */
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { test } from 'node:test'

const SRC = join(__dirname, '..', 'src', 'renderer', 'src')

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return walk(p)
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [p] : []
  })
}

/** Top-level `const x = ns` / `const x: T = ns` lines, for every relative `import * as ns`. */
export function namespaceAliases(text: string): string[] {
  const names = [...text.matchAll(/^import \* as (\w+) from '\.{1,2}\//gm)].map((m) => m[1])
  return names.flatMap((ns) => {
    const alias = new RegExp(`^(?:export )?(?:const|let|var) \\w+(?:: [^=\\n]+)? = ${ns}[ \\t]*;?[ \\t]*$`, 'gm')
    return [...text.matchAll(alias)].map((m) => m[0])
  })
}

test('the check sees the alias that crashed the island, and not the fix', () => {
  const imp = "import * as drawerStore from '../drawer/store'\n"
  assert.deepEqual(namespaceAliases(`${imp}const drawer: Record<string, unknown> = drawerStore\n`), ['const drawer: Record<string, unknown> = drawerStore'])
  assert.deepEqual(namespaceAliases(`${imp}const drawer = drawerStore;\n`), ['const drawer = drawerStore;'])
  assert.deepEqual(namespaceAliases(`${imp}const drawer = (): Record<string, unknown> => drawerStore ?? {}\n`), [])
  assert.deepEqual(namespaceAliases(`${imp}function read() {\n  const d = drawerStore\n  return d\n}\n`), [])
})

test('no module-level alias of a namespace import in the renderer', () => {
  const files = walk(SRC)
  assert.ok(files.length > 100, 'the walk found the renderer source')
  const hits = files.flatMap((p) => namespaceAliases(readFileSync(p, 'utf8')).map((line) => `${relative(SRC, p).split(sep).join('/')}: ${line}`))
  assert.deepEqual(hits, [], 'read the namespace inside a function instead')
})
