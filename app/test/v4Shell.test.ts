/** The v4 frame (features/shell ui.tsx, core/theme.ts v4): tokens exist in both themes, inks stay readable, primitives render. */
import assert from 'node:assert/strict'
import { before, describe, test } from 'node:test'
import * as React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { themeCss, v4, v4c } from '../src/renderer/src/core/theme'

// tsx compiles the .tsx files with the classic JSX runtime (React.createElement): give it a global React, then load ui.tsx.
;(globalThis as { React?: unknown }).React = React
const h = React.createElement
let ui: typeof import('../src/renderer/src/features/shell/ui')
before(async () => {
  ui = await import('../src/renderer/src/features/shell/ui')
})
const V4_W = v4.page.w + 2 * v4.page.gutter

const css = themeCss()
const block = (which: 'dark' | 'light'): string => (which === 'light' ? css.slice(css.indexOf(':root[data-appearance="light"]')) : css.slice(0, css.indexOf('[data-theme="dark"]{--c-text')))

function rgba(which: 'dark' | 'light', name: string): number[] {
  const m = block(which).match(new RegExp(`--${name}:\\s*(?:rgba?\\(([^)]+)\\)|#([0-9a-fA-F]{6}))`))
  assert.ok(m, `--${name} not found (${which})`)
  if (m[2]) return [0, 2, 4].map((i) => parseInt(m[2].slice(i, i + 2), 16)).concat(1)
  const p = m[1].split(',').map((s) => Number(s.trim()))
  return [p[0], p[1], p[2], p[3] ?? 1]
}
const lum = (c: number[]): number => {
  const f = (v: number): number => ((v /= 255) <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4))
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
}
function contrast(which: 'dark' | 'light', ink: string, bg: string): number {
  const b = rgba(which, bg)
  const [r, g, bl, a] = rgba(which, ink)
  const mix = [r, g, bl].map((v, i) => v * a + b[i] * (1 - a))
  const [hi, lo] = [lum(b), lum(mix)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('v4 tokens', () => {
  test('every v4c token is a palette variable in both themes', () => {
    for (const v of Object.values(v4c)) {
      const name = v.slice(6, -1)
      assert.ok(block('dark').includes(`--${name}:`), `${name} dark`)
      assert.ok(block('light').includes(`--${name}:`), `${name} light`)
    }
  })
  test('the light page stays the cream paper (Michael: cream default kept)', () => assert.deepEqual(rgba('light', 'v4-page').slice(0, 3), [246, 246, 243]))
  test('the frame numbers are the mock rules: 240 sidebar, 44 top bar, 1040 content, 684 + 316 + 40', () => {
    assert.equal(v4.sidebar.w, 240)
    assert.equal(v4.top, 44)
    assert.equal(v4.page.main + v4.page.rail + v4.page.colGap, v4.page.w)
    assert.equal(V4_W, 1040 + 2 * 40)
  })
  for (const which of ['light', 'dark'] as const)
    for (const bg of ['v4-page', 'v4-side'])
      test(`${which}: label and faint ink are 4.5:1 on ${bg}`, () => {
        assert.ok(contrast(which, 'c-label', bg) >= 4.5, String(contrast(which, 'c-label', bg)))
        assert.ok(contrast(which, 'c-faint', bg) >= 4.5, String(contrast(which, 'c-faint', bg)))
      })
})

describe('v4 primitives render', () => {
  test('a page: frame, header, section, rows, table, stats, bar, tag', () => {
    const rows = [{ id: 'a', name: 'Add one row', when: 'Today' }]
    const html = renderToStaticMarkup(
      h(ui.PageFrame, null,
        h(ui.PageHeader, { title: 'Library', lede: 'Two plans.' }),
        h(ui.TwoCol, {
          main: h(ui.Section, { title: 'Up next', count: 4, link: { label: 'Library', onClick: () => {} } }, h(ui.Rows, null, h(ui.ListRow, { onClick: () => {}, label: 'open' }, 'Plot'), h(ui.ListRow, null, 'Matrices'))),
          rail: h(ui.Stats, { size: 'sm', items: [{ value: 6, label: 'steps passed' }] })
        }),
        h(ui.Table<{ id: string; name: string; when: string }>, { columns: [{ key: 'w', label: 'When', width: 120, cell: (r) => r.when }, { key: 'n', label: 'Step', cell: (r) => h('span', null, h(ui.PassedMark), r.name) }], rows, rowKey: (r) => r.id }),
        h(ui.Bar, { value: 0.5, width: 72 }),
        h(ui.Tag, null, 'Broadcasting')
      )
    )
    for (const s of ['data-v4-frame', 'Library', 'Two plans.', 'Up next', 'mg-v4-two', 'mg-v4-rows', 'mg-v4-tbl', 'When', 'Add one row', 'steps passed', 'Broadcasting', 'aria-label="Passed"'])
      assert.ok(html.includes(s), s)
  })
  test('the top bar marks the last crumb as the current page', () => {
    const html = renderToStaticMarkup(h(ui.TopBar, { crumbs: ['Settings', 'General'] }))
    assert.match(html, /aria-current="page"[^>]*>General</)
  })
  test('a bar is never green unless it means passed', () => {
    assert.ok(!renderToStaticMarkup(h(ui.Bar, { value: 1 })).includes('--c-green'))
    assert.ok(renderToStaticMarkup(h(ui.Bar, { value: 1, passed: true })).includes('--c-green'))
  })
})
