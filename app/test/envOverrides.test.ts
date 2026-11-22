/**
 * Risk A12 (launch register R33), offline: a packaged app ignores an environment-set cloud host, so a `launchctl
 * setenv` can't point install tokens and AI calls at another server. Only the off values still count. Dev keeps any value.
 */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { cloudUrl, DEFAULT_CLOUD_URL, envCloudUrl } from '../src/main/features/cloud'

describe('packaged builds ignore an environment-set cloud host (A12)', () => {
  test('packaged: a URL in MIYAGI_CLOUD_URL is ignored, so the default host is used', () => {
    assert.equal(envCloudUrl({ MIYAGI_CLOUD_URL: 'https://elsewhere.example' }, true), undefined)
    assert.equal(cloudUrl(envCloudUrl({ MIYAGI_CLOUD_URL: 'https://elsewhere.example' }, true)), DEFAULT_CLOUD_URL)
  })
  test('packaged: off still turns the cloud off', () => {
    for (const off of ['off', '0', 'false', 'no', ' OFF ']) {
      assert.equal(cloudUrl(envCloudUrl({ MIYAGI_CLOUD_URL: off }, true)), undefined)
    }
  })
  test('dev: any value is kept', () => {
    assert.equal(envCloudUrl({ MIYAGI_CLOUD_URL: 'http://127.0.0.1:9000' }, false), 'http://127.0.0.1:9000')
    assert.equal(cloudUrl(envCloudUrl({ MIYAGI_CLOUD_URL: 'http://127.0.0.1:9000' }, false)), 'http://127.0.0.1:9000')
  })
  test('unset: the default host either way', () => {
    assert.equal(cloudUrl(envCloudUrl({}, true)), DEFAULT_CLOUD_URL)
    assert.equal(cloudUrl(envCloudUrl({}, false)), DEFAULT_CLOUD_URL)
  })
})
