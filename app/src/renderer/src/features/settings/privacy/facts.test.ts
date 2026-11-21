/**
 * Privacy facts: the panel's rows, the copy rules, and that web/privacy.md says the same lines.
 *   cd app && node --import tsx --test src/renderer/src/features/settings/privacy/facts.test.ts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { DELETE, FACTS, KEYS_NO_KEYCHAIN, POLICY_LINE, ROUTE, STAYS } from './facts'

const here = dirname(fileURLToPath(import.meta.url))
const policy = readFileSync(join(here, '../../../../../../../web/privacy.md'), 'utf8')
const words = (s: string): number => s.trim().split(/\s+/).length
/** Built from char codes so this file passes the brand lint it checks for. */
const EM_DASH = String.fromCharCode(0x2014)
const CAPITAL_BRAND = new RegExp(String.fromCharCode(77) + 'iyagi')
const lines = [...FACTS.flatMap((f) => [f.label, f.line, f.where]), KEYS_NO_KEYCHAIN, ROUTE, POLICY_LINE, ...Object.values(DELETE)]

test('the panel has every source the brief names, once', () => {
  const ids = FACTS.map((f) => f.id)
  for (const id of ['screen', 'code', 'editor', 'account', 'crash', 'usage']) assert.ok(ids.includes(id as never), id)
  assert.equal(new Set(ids).size, ids.length)
})

test('each row says "On this Mac" or where it goes', () => {
  for (const f of FACTS) {
    if (f.leaves) assert.match(f.where, /^To /, f.id)
    else assert.ok(f.where === STAYS || f.where === 'Read on this Mac', f.id)
  }
})

test('copy: 12 words at most, lowercase miyagi, no em dash, no other editor named', () => {
  for (const s of lines) {
    assert.ok(words(s) <= 12, `too long: ${s}`)
    assert.ok(!CAPITAL_BRAND.test(s), `brand is lowercase: ${s}`)
    assert.ok(!s.includes(EM_DASH), `em dash: ${s}`)
    assert.ok(!/cursor/i.test(s), `no other editor: ${s}`)
  }
})

test('never claims what is not built (5.1 cropping, 5.2 secret redaction, a sent log)', () => {
  for (const s of lines) assert.ok(!/crop|redact|secret|token|log of/i.test(s), s)
})

test('web/privacy.md: a DRAFT, and it says the same lines as the app', () => {
  assert.match(policy.split('\n')[0], /DRAFT/)
  for (const f of FACTS) assert.ok(policy.includes(f.line), `policy is missing: ${f.line}`)
  for (const s of [ROUTE, DELETE.row, DELETE.confirm]) assert.ok(policy.includes(s), `policy is missing: ${s}`)
  for (const s of ['13', 'Anthropic', 'Gemini', 'Supabase', 'miyagi-cloud', 'Contact']) assert.ok(policy.includes(s), s)
  assert.ok(!policy.includes(EM_DASH), 'no em dash in the policy')
})
