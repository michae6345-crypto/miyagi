/**
 * R33: the YouTube player's host page (main/playerHost.ts). What it serves, who may frame it, where its frames may go,
 * and that the app's own pages no longer load YouTube's scripts.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { request } from 'node:http'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { frameAllowed, HOST_PAGE, HOST_SCRIPT, hostCsp, hostReply, isOrigin, playerHostOrigin, servePlayerHost } from '../src/main/playerHost'
import { csp } from '../src/main/serve'

const APP = join(__dirname, '..')
const SCRIPT = readFileSync(join(APP, 'src', 'main', 'playerHost.page.js'), 'utf8')
const PARENT = 'http://127.0.0.1:53817'

describe('hostReply', () => {
  test('serves the page with its CSP: YouTube only, framed by the app only', () => {
    const r = hostReply('GET', HOST_PAGE, PARENT, SCRIPT)
    assert.equal(r.status, 200)
    assert.match(r.headers['Content-Type'], /^text\/html/)
    const policy = r.headers['Content-Security-Policy']
    assert.equal(policy, hostCsp(PARENT))
    assert.match(policy, /frame-ancestors http:\/\/127\.0\.0\.1:53817(;|$)/)
    assert.match(policy, /default-src 'none'/)
    assert.match(policy, /script-src 'self' https:\/\/www\.youtube\.com https:\/\/s\.ytimg\.com(;|$)/)
    assert.doesNotMatch(policy, /unsafe-inline|unsafe-eval|\*/)
    assert.match(r.body, /<meta name="miyagi-parent" content="http:\/\/127\.0\.0\.1:53817">/)
    assert.doesNotMatch(r.body, /<script>/, 'no inline script')
  })

  test('serves the script, and nothing else', () => {
    assert.equal(hostReply('GET', HOST_SCRIPT, PARENT, SCRIPT).body, SCRIPT)
    for (const path of ['/', '/index.html', '/player-host.html/..', '/../index.html', '/player-host.htm', '/%2e%2e/x']) {
      assert.equal(hostReply('GET', path, PARENT, SCRIPT).status, 404, path)
    }
    assert.equal(hostReply('POST', HOST_PAGE, PARENT, SCRIPT).status, 405)
  })

  test('ATTACK a parent that is not a plain origin is never written into the page', () => {
    for (const bad of ['http://a"><script>alert(1)</script>', "http://x; script-src 'unsafe-inline'", 'javascript:alert(1)', 'http://x/path', '', undefined]) {
      assert.equal(isOrigin(bad), false, String(bad))
      assert.equal(hostReply('GET', HOST_PAGE, bad, SCRIPT).status, 404, String(bad))
    }
    for (const ok of ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://[::1]:8080', 'https://example.test']) assert.ok(isOrigin(ok), ok)
  })
})

describe('frameAllowed (the player window frame lock)', () => {
  const host = 'http://localhost:53911'

  test('a frame in our page: only the host page, on the host origin', () => {
    assert.ok(frameAllowed(`${host}${HOST_PAGE}`, 1, host))
    for (const bad of [`${host}/other.html`, 'http://localhost:1/player-host.html', 'https://www.youtube.com/embed/aircAruvnKk', 'https://evil.example/', 'about:blank']) {
      assert.equal(frameAllowed(bad, 1, host), false, bad)
    }
    assert.equal(frameAllowed(`${host}${HOST_PAGE}`, 1, undefined), false, 'no host serving: nothing')
  })

  test('inside the host page: YouTube hosts over https only', () => {
    for (const ok of ['https://www.youtube.com/embed/aircAruvnKk?enablejsapi=1', 'https://www.youtube-nocookie.com/embed/x', 'https://consent.youtube.com/m', 'about:blank']) {
      assert.ok(frameAllowed(ok, 2, host), ok)
    }
    for (const bad of ['http://www.youtube.com/embed/x', 'https://youtube.com.evil.example/', 'https://evilyoutube.com/', 'https://www.youtube.com:8443/', 'https://user@www.youtube.com/', 'https://accounts.example/', `${host}${HOST_PAGE}`, 'file:///etc/passwd', 'not a url']) {
      assert.equal(frameAllowed(bad, 2, host), false, bad)
      assert.equal(frameAllowed(bad, 3, host), false, bad)
    }
  })

  test('a frame Electron could not place: the host page or a YouTube host, nothing else', () => {
    assert.ok(frameAllowed(`${host}${HOST_PAGE}`, -1, host))
    assert.ok(frameAllowed('https://www.youtube.com/embed/x', -1, host))
    for (const bad of ['https://evil.example/', `${host}/other.html`, 'http://www.youtube.com/embed/x']) assert.equal(frameAllowed(bad, -1, host), false, bad)
    assert.equal(frameAllowed('https://www.youtube.com/embed/x', 0, host), false, 'depth 0 is the main frame: core decides')
  })
})

describe('servePlayerHost', () => {
  test('serves on loopback, on another site than the app, and the app CSP frames exactly it', async () => {
    const origin = await servePlayerHost(SCRIPT, PARENT)
    assert.equal(playerHostOrigin(), origin)
    const u = new URL(origin)
    assert.ok(u.hostname === 'localhost' || u.hostname === '127.0.0.1')
    assert.notEqual(u.origin, PARENT)
    const body = await new Promise<{ status?: number; csp?: string; text: string }>((resolve, reject) => {
      const req = request({ host: '127.0.0.1', port: Number(u.port), path: HOST_PAGE }, (res) => {
        let text = ''
        res.on('data', (c) => (text += c))
        res.on('end', () => resolve({ status: res.statusCode, csp: res.headers['content-security-policy'] as string | undefined, text }))
      })
      req.on('error', reject)
      req.end()
    })
    assert.equal(body.status, 200)
    assert.equal(body.csp, hostCsp(PARENT))
    assert.match(body.text, /miyagi-parent/)
    assert.match(csp(), new RegExp(`frame-src ${origin.replace(/[.]/g, '\\.')}(;|$)`))
  })
})

describe('the app pages no longer run YouTube scripts', () => {
  test('the built app CSP has no YouTube script or frame source', () => {
    const policy = csp()
    assert.match(policy, /script-src 'self'(;|$)/)
    assert.doesNotMatch(policy, /youtube\.com|ytimg\.com\/|s\.ytimg/)
  })

  test('the renderer never loads the IFrame API itself', () => {
    const player = join(APP, 'src', 'renderer', 'src', 'features', 'player')
    for (const f of ['store.ts', 'youtube.ts', 'frame.ts', 'Player.tsx']) {
      const text = readFileSync(join(player, f), 'utf8')
      assert.doesNotMatch(text, /youtube\.com\/iframe_api['"`]|new YT\.Player|window\.YT\b/, f)
    }
  })
})
