/**
 * apps lane (agents/app-apps-sidebar.md): the sidebar's Apps, the Add app picker's pins and the app page's data.
 * The pinned list is a pref (common/prefs.ts, sanitized like the rest); which app a lesson works in is read from the
 * lesson's own fields; main's scan only checks fixed bundle names; the sidebar section renders from plain data.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { before, describe, test } from 'node:test'
import * as React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import type { LibraryItem, PlanState } from '../../shared/contracts/events'
import { cleanAppIds, DEFAULT_PREFS, MAX_PREF_APPS, sanitizePrefs } from '../src/common/prefs'
import { APP_BUNDLES, installedApps } from '../src/main/features/apps'
import { appContent, appForTool, APPS, catalogApps, hasActivity, installState, lessonApp, libraryNavResets, sidebarApps, togglePinned, toolIndex } from '../src/renderer/src/features/apps/model'
import { planStateFromCatalog, PLANS, planById, START_HERE } from '../src/renderer/src/features/plans/catalog'
import scenario from '../mock/scenarios/apps.json'

;(globalThis as { React?: unknown }).React = React
const h = React.createElement
let SidebarApps: typeof import('../src/renderer/src/features/apps/SidebarApps').SidebarApps
before(async () => {
  SidebarApps = (await import('../src/renderer/src/features/apps/SidebarApps')).SidebarApps
})

const item = (over: Partial<LibraryItem> & { id: string; title: string }): LibraryItem => ({ steps: 5, tools: [], ready: true, ...over })

describe('prefs: pinnedApps and haveApps', () => {
  test('defaults: no pins (miyagi picks), nobody said "I have it"', () => {
    assert.equal(DEFAULT_PREFS.pinnedApps, null)
    assert.deepEqual(DEFAULT_PREFS.haveApps, [])
  })
  test('a clean list survives, in order, each once', () => {
    assert.deepEqual(sanitizePrefs({ pinnedApps: ['blender', 'vscode', 'blender'] }).pinnedApps, ['blender', 'vscode'])
    assert.deepEqual(sanitizePrefs({ haveApps: ['fusion'] }).haveApps, ['fusion'])
  })
  test('null resets the pins to the default; an empty list is kept (the learner unpinned all)', () => {
    assert.equal(sanitizePrefs({ pinnedApps: null }).pinnedApps, null)
    assert.deepEqual(sanitizePrefs({ pinnedApps: [] }).pinnedApps, [])
  })
  test('junk is dropped: not a list, not a string, paths, capitals, too long', () => {
    assert.equal('pinnedApps' in sanitizePrefs({ pinnedApps: 'vscode' }), false)
    assert.equal('haveApps' in sanitizePrefs({ haveApps: { vscode: true } }), false)
    assert.deepEqual(sanitizePrefs({ pinnedApps: ['vscode', 3, '../etc', 'VSCode', 'a'.repeat(40), '', null] }).pinnedApps, ['vscode'])
  })
  test('a list is capped', () => {
    const many = Array.from({ length: 60 }, (_, i) => `app-${i}`)
    assert.equal(cleanAppIds(many)?.length, MAX_PREF_APPS)
  })
})

describe('main: apps:installed', () => {
  test('macOS: an app is installed when one of its bundles is in /Applications or ~/Applications', () => {
    const seen: string[] = []
    const on = new Set(['/Applications/Blender.app', '/Users/me/Applications/Autodesk Fusion.app'])
    const r = installedApps({ platform: 'darwin', home: '/Users/me', exists: (p) => (seen.push(p), on.has(p)) })
    assert.deepEqual(r, { vscode: false, blender: true, freecad: false, fusion: true })
    assert.ok(seen.every((p) => p.startsWith('/Applications/') || p.startsWith('/Users/me/Applications/')), 'only the two app folders')
    assert.ok(seen.every((p) => p.endsWith('.app')))
  })
  test('elsewhere it says nothing (unknown, never "not installed")', () => {
    assert.deepEqual(installedApps({ platform: 'win32', home: 'C:/Users/me', exists: () => true }), {})
  })
  test('every supported app has a bundle to look for', () => {
    for (const a of APPS) assert.ok(APP_BUNDLES[a.id]?.length, a.id)
  })
})

describe('the apps the catalog names', () => {
  const apps = catalogApps(PLANS)
  test('the four supported apps first, named by the catalog', () => {
    assert.deepEqual(
      apps.filter((a) => !a.soon).map((a) => a.name),
      ['VS Code', 'Blender', 'FreeCAD', 'Fusion']
    )
  })
  test('the rest are "soon", and a tool that feeds VS Code (Jupyter, Terminal) is not listed apart', () => {
    const soon = apps.filter((a) => a.soon).map((a) => a.id)
    assert.ok(soon.includes('xcode') && soon.includes('unity'))
    assert.ok(!soon.includes('jupyter') && !soon.includes('terminal'))
    assert.equal(appForTool('jupyter')?.id, 'vscode')
  })
  test('VS Code counts its notebook and terminal plans', () => {
    const vs = apps.find((a) => a.id === 'vscode')!
    assert.equal(vs.plans, PLANS.filter((p) => ['vscode', 'jupyter', 'terminal'].includes(p.tool.id)).length)
  })
})

describe('filtering by app', () => {
  const index = toolIndex(PLANS)
  test('a lesson is placed from its own fields: plan, skills, title, then tools', () => {
    assert.equal(lessonApp(item({ id: 'a', title: 'Anything', tools: ['jupyter'] }), index, 'blender'), 'blender', 'the plan that holds it wins')
    assert.equal(lessonApp(item({ id: 'b', title: 'Subdivision and smooth shading', teaches: ['bl.modifiers'] }), index), 'blender')
    assert.equal(lessonApp(item({ id: 'c', title: 'Your first sketch' }), index), 'freecad', 'a catalog lesson title')
    assert.equal(lessonApp(item({ id: 'd', title: 'Some notebook', tools: ['jupyter'] }), index), 'vscode')
    assert.equal(lessonApp(item({ id: 'e', title: 'A spreadsheet', tools: ['excel'] }), index), undefined, 'Excel is not supported yet')
  })
  test('Blender: its three plans, Intro first, its skills, and only its lessons', () => {
    const items = (scenario.segments.apps_library[0].payload as { items: LibraryItem[] }).items
    const c = appContent('blender', PLANS, items, [], START_HERE)
    assert.deepEqual(
      c.plans.map((p) => p.id),
      ['intro-blender', ...PLANS.filter((p) => p.tool.id === 'blender' && p.id !== 'intro-blender').map((p) => p.id)]
    )
    assert.equal(c.start?.id, 'intro-blender')
    assert.ok(c.lessons.length > 0 && c.lessons.every((l) => !l.tools.includes('jupyter')))
    assert.ok(c.lessons.some((l) => l.teaches?.some((t) => t.startsWith('bl.'))))
    assert.ok(c.skills.length > 0 && new Set(c.skills.map((s) => s.id)).size === c.skills.length, 'each skill once')
    assert.equal(c.lessonCount, c.plans.reduce((n, p) => n + p.lessons.length, 0))
  })
  test('VS Code starts with the featured plan, and its notebook lessons are its own', () => {
    const items = (scenario.segments.apps_library[0].payload as { items: LibraryItem[] }).items
    const c = appContent('vscode', PLANS, items, [], START_HERE)
    assert.equal(c.start?.id, 'intro-python')
    assert.ok(c.lessons.some((l) => l.tools.includes('jupyter')))
    const blender = appContent('blender', PLANS, items, [], START_HERE)
    assert.equal(c.lessons.filter((l) => blender.lessons.includes(l)).length, 0, 'no lesson in two apps')
  })
  test('a plan the learner has going comes first', () => {
    const cad = planById('cad-3d-printing')!
    const going: PlanState = { ...planStateFromCatalog(cad, 2) }
    const c = appContent('freecad', PLANS, [], [going], START_HERE)
    assert.equal(c.start?.id, 'cad-3d-printing')
    assert.ok(hasActivity(c))
  })
})

describe('installed?', () => {
  test('"I have it" wins, then main\'s scan, then the engine\'s VS Code rows, else unknown', () => {
    assert.equal(installState('fusion', { fusion: false }, {}, ['fusion']), 'installed')
    assert.equal(installState('blender', { blender: true }, {}, []), 'installed')
    assert.equal(installState('blender', { blender: false }, {}, []), 'missing')
    assert.equal(installState('vscode', {}, { companion: { state: 'missing', fix: 'get_vscode' } }, []), 'missing')
    assert.equal(installState('vscode', undefined, { companion: { state: 'missing', fix: 'install_companion' } }, []), 'installed')
    assert.equal(installState('vscode', undefined, { vscode: { state: 'missing' } }, []), 'missing')
    assert.equal(installState('freecad', undefined, { companion: { state: 'ok' } }, []), 'unknown', 'health speaks for VS Code only')
  })
})

describe('the sidebar list', () => {
  const st = (m: Record<string, 'installed' | 'missing' | 'unknown'>) => (id: string) => m[id] ?? 'unknown'
  test('default: installed apps, plus unknown ones with lessons; never a missing one', () => {
    assert.deepEqual(sidebarApps(null, st({ vscode: 'installed', blender: 'unknown', freecad: 'missing', fusion: 'unknown' }), (id) => id === 'blender' || id === 'freecad'), ['vscode', 'blender'])
  })
  test('default with nothing known and nothing done: every supported app', () => {
    assert.deepEqual(sidebarApps(null, st({}), () => false), APPS.map((a) => a.id))
  })
  test('pinned: exactly those, in the sidebar order, unknown ids dropped', () => {
    assert.deepEqual(sidebarApps(['fusion', 'vscode', 'xcode'], st({}), () => false), ['vscode', 'fusion'])
    assert.deepEqual(sidebarApps([], st({ vscode: 'installed' }), () => true), [])
  })
  test('the picker toggles from what is shown, keeps order, ignores apps that are not supported', () => {
    assert.deepEqual(togglePinned(['vscode', 'blender'], 'fusion'), ['vscode', 'blender', 'fusion'])
    assert.deepEqual(togglePinned(['fusion', 'vscode'], 'freecad'), ['vscode', 'freecad', 'fusion'])
    assert.deepEqual(togglePinned(['vscode', 'blender'], 'vscode'), ['blender'])
    assert.deepEqual(togglePinned(['vscode'], 'xcode'), ['vscode'])
  })
})

describe('picking Library from an app page', () => {
  // goToPage (apps/store) shows the Library list when libraryNavResets says so, then sets the page.
  type View = { kind: 'library' } | { kind: 'plans' } | { kind: 'plan'; id: string } | { kind: 'app'; id: string }
  const pick = (target: string, page: string, view: View): View => (libraryNavResets(target, page, view) ? { kind: 'library' } : view)
  test('the Library row (or ⌘2) on an app page lands on the Library list', () => {
    assert.deepEqual(pick('lessons', 'lessons', { kind: 'app', id: 'blender' }), { kind: 'library' })
  })
  test('from another page, an app page left open is not where Library lands', () => {
    assert.deepEqual(pick('lessons', 'home', { kind: 'app', id: 'blender' }), { kind: 'library' })
  })
  test('Library again from its own views goes back to the list', () => {
    assert.deepEqual(pick('lessons', 'lessons', { kind: 'plans' }), { kind: 'library' })
    assert.deepEqual(pick('lessons', 'lessons', { kind: 'plan', id: 'intro-blender' }), { kind: 'library' })
  })
  test('from another page, a plan left open comes back as it was', () => {
    assert.deepEqual(pick('lessons', 'home', { kind: 'plan', id: 'intro-blender' }), { kind: 'plan', id: 'intro-blender' })
  })
  test('other pages never touch the Library view', () => {
    for (const target of ['home', 'skills', 'progress', 'settings', 'account']) assert.deepEqual(pick(target, 'lessons', { kind: 'app', id: 'vscode' }), { kind: 'app', id: 'vscode' })
  })
  test('the sidebar rows, its arrow keys and ⌘1..⌘6 all pick pages through goToPage', () => {
    const src = (p: string): string => readFileSync(new URL(`../src/renderer/src/features/${p}`, import.meta.url), 'utf8')
    const sidebar = src('shell/Sidebar.tsx')
    assert.match(sidebar, /onClick=\{\(\) => goToPage\(id\)\}/)
    assert.match(sidebar, /goToPage\(MAIN\[to\]\)/)
    assert.match(src('shell/Shell.tsx'), /goToPage\(PAGES\[n - 1\]\.id\)/)
    assert.match(src('apps/store.ts'), /if \(libraryNavResets\(id, useShell\.getState\(\)\.page, usePlans\.getState\(\)\.view\)\) showLibrary\(\)/)
  })
})

describe('sidebar rendering', () => {
  const apps = [
    { id: 'vscode', name: 'VS Code', state: 'installed' as const },
    { id: 'blender', name: 'Blender', state: 'installed' as const },
    { id: 'fusion', name: 'Fusion', state: 'missing' as const }
  ]
  test('a row per app, the open one marked, Not installed where it is missing, then Add app', () => {
    const html = renderToStaticMarkup(h(SidebarApps, { apps, openId: 'blender', compact: false, onOpen: () => {}, onAdd: () => {} }))
    for (const s of ['data-shell-apps', 'Apps', 'data-shell-app="vscode"', 'VS Code', 'Blender', 'Fusion', 'Not installed', 'data-shell-add-app', 'Add app', 'aria-haspopup="dialog"']) assert.ok(html.includes(s), s)
    assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1)
    assert.match(html, /aria-current="page"[^>]*data-shell-app="blender"/)
    assert.equal((html.match(/Not installed/g) ?? []).length, 1)
    assert.ok(html.indexOf('VS Code') < html.indexOf('Blender') && html.indexOf('Fusion') < html.indexOf('Add app'))
  })
  test('compact: no label text, names as tooltips', () => {
    const html = renderToStaticMarkup(h(SidebarApps, { apps, compact: true, onOpen: () => {}, onAdd: () => {} }))
    assert.ok(html.includes('aria-label="VS Code"') && html.includes('title="Add app"'))
    assert.ok(!html.includes('Not installed'))
  })
  test('copy stays calm: no em dashes, lowercase brand', () => {
    const html = renderToStaticMarkup(h(SidebarApps, { apps, compact: false, onOpen: () => {}, onAdd: () => {} }))
    assert.ok(!html.includes('\u2014') && !html.includes('Miyagi'))
  })
})
