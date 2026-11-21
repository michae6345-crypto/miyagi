/**
 * Delete my data, the file part.
 *   cd app && node --import tsx --test src/main/features/settings/erase.test.ts
 */
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { removeFiles, SIGN_IN_FILES } from './erase'

test('SIGN_IN_FILES: the session, the login choice and the account-link note, with their temp files', () => {
  for (const f of ['auth.bin', 'login.json', 'auth.bin.tmp', 'login.json.tmp', 'cloud-link.json', 'cloud-link.json.tmp']) {
    assert.ok(SIGN_IN_FILES.includes(f as never), f)
  }
  assert.ok(!SIGN_IN_FILES.includes('keys.bin' as never)) // the keys go through settings.ts persist()
  assert.ok(!SIGN_IN_FILES.includes('install.bin' as never)) // the anonymous cloud token is not the sign-in
})

test('removeFiles: removes what exists, ignores what is missing, leaves other files', () => {
  const dir = mkdtempSync(join(tmpdir(), 'miyagi-erase-'))
  try {
    writeFileSync(join(dir, 'auth.bin'), 'x')
    writeFileSync(join(dir, 'login.json'), '{"decided":true}')
    writeFileSync(join(dir, 'prefs.json'), '{}')
    assert.equal(removeFiles(dir, SIGN_IN_FILES), true)
    assert.equal(existsSync(join(dir, 'auth.bin')), false)
    assert.equal(existsSync(join(dir, 'login.json')), false)
    assert.equal(existsSync(join(dir, 'prefs.json')), true)
    assert.equal(removeFiles(dir, SIGN_IN_FILES), true) // nothing left: still true
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
})

test('removeFiles: one failure is reported but does not stop the rest', () => {
  const removed: string[] = []
  const fs = {
    existsSync: () => true,
    unlinkSync: (p: string) => {
      if (p.endsWith('auth.bin')) throw new Error('EPERM')
      removed.push(p)
    }
  }
  assert.equal(removeFiles('/u', ['auth.bin', 'login.json'], fs), false)
  assert.deepEqual(removed, [join('/u', 'login.json')])
})
