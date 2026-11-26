#!/usr/bin/env node
// CI guard for the unit tests' TAP report (app-ci.yml): a test file whose report stopped part-way fails the job.
//
//   node scripts/check-test-report.mjs <report.tap> [min-tests]
//
// `node --test` runs each file in a child process and counts only what that child reported. When a child's report is
// cut short (test/setup.mjs: async pipe writes dropped at --test-force-exit), the run still ends green with
// "fail 0", just fewer tests. Two checks catch it:
//   1. every "# Subtest: X" has its own "ok N - X" / "not ok N - X" at the same depth (a cut-off file leaves the
//      suite it was in without one);
//   2. "# tests" is at least `min-tests` (a cut that lands between two top-level tests leaves nothing open). Raise the
//      floor in app-ci.yml as the suite grows; lower it only when tests are deleted on purpose.
import { readFileSync } from 'node:fs'

const [file, minArg] = process.argv.slice(2)
if (!file) {
  console.error('usage: check-test-report.mjs <report.tap> [min-tests]')
  process.exit(2)
}
const min = Number(minArg ?? 0)
const lines = readFileSync(file, 'utf8').split('\n')

const problems = []
/** Open subtests, innermost last: { indent, name, line } */
const open = []
const unescape = (s) => s.replace(/\\#/g, '#').replace(/\\\\/g, '\\')
let total

for (let i = 0; i < lines.length; i++) {
  const line = lines[i]
  const indent = line.length - line.trimStart().length
  const text = line.trimStart()
  let m
  if ((m = /^# Subtest: (.*)$/.exec(text))) {
    open.push({ indent, name: unescape(m[1]), line: i + 1 })
  } else if ((m = /^(not ok|ok) \d+ - (.*?)(?: # (?:SKIP|TODO)\b.*)?$/.exec(text))) {
    const name = unescape(m[2])
    // Close everything deeper than this result first: those subtests never reported (a cut-off file).
    while (open.length && open.at(-1).indent > indent) {
      const o = open.pop()
      problems.push(`line ${o.line}: "${o.name}" started but never reported a result`)
    }
    const top = open.at(-1)
    if (top && top.indent === indent && top.name === name) open.pop()
    else if (top && top.indent === indent) {
      problems.push(`line ${top.line}: "${top.name}" started but never reported a result (next result: "${name}")`)
      open.pop()
    }
  } else if (indent === 0 && (m = /^# tests (\d+)$/.exec(text))) {
    total = Number(m[1])
  }
}
for (const o of open) problems.push(`line ${o.line}: "${o.name}" started but never reported a result`)
if (total === undefined) problems.push('no "# tests N" summary: the run itself was cut off')
else if (total < min) problems.push(`# tests ${total} is below the floor of ${min}: whole test files did not report`)

if (problems.length) {
  console.error(`check-test-report: ${file} is incomplete (${problems.length} problem${problems.length > 1 ? 's' : ''}):`)
  for (const p of problems.slice(0, 50)) console.error(`  ${p}`)
  process.exit(1)
}
console.log(`check-test-report: ${total} tests, every subtest reported a result (floor ${min})`)
