/**
 * Feature: updates. Browser-stage stand-ins for src/main/features/updates.ts (nothing here runs in Electron).
 *
 *   ?scenario=updates                 an idle desktop and a newer release: the card grows from the pill after a beat
 *   &upd=available (default) | current | failed | off | snoozed | pre
 *   &os=win                           the Windows install steps (.exe)
 *
 * The sample is a GitHub release object (the shape api.github.com returns for the "mac" tag), read through the same
 * readRelease() main uses, so the stage also exercises the parser. Every other scenario gets 'off': no card.
 */
import { isElectron, registerWebHandler } from '../../bridge'
import { isNewer, readRelease, SNOOZE_MS, type UpdateOs, type UpdateView } from './manifest'

const CURRENT = '0.1.0'

const SAMPLE_RELEASE = {
  tag_name: 'mac',
  name: 'miyagi 0.2.0',
  draft: false,
  prerelease: false,
  body: [
    '## What\'s new',
    '- Lessons open about twice as fast.',
    '- The panel remembers where you left it.',
    '- Clearer "Not yet" notes when a check fails.',
    '- Fixes a stall when VS Code was closed mid-step.',
    '',
    'Version: 0.2.0'
  ].join('\n'),
  assets: [
    {
      name: 'Miyagi-Mac.dmg',
      size: 182_400_000,
      digest: 'sha256:6f1c2b0e9a8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b',
      browser_download_url: 'https://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg'
    },
    {
      name: 'Miyagi-Windows.exe',
      size: 141_000_000,
      browser_download_url: 'https://github.com/adrian-erlikhman/miyagi/releases/download/windows/Miyagi-Windows.exe'
    },
    { name: 'Miyagi-Mac.zip', size: 176_000_000, browser_download_url: 'https://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.zip' }
  ]
}

function setupWeb(): void {
  const params = new URLSearchParams(location.search)
  const on = params.get('scenario') === 'updates' || params.has('upd')
  const mode = params.get('upd') ?? 'available'
  const os: UpdateOs = params.get('os') === 'win' ? 'windows' : 'mac'
  const rel = readRelease(mode === 'pre' ? { ...SAMPLE_RELEASE, prerelease: true } : SAMPLE_RELEASE, os, 'arm64')
  const offer = rel && isNewer(rel, CURRENT) ? rel : undefined

  let snoozedUntil = mode === 'snoozed' ? Date.now() + SNOOZE_MS : undefined
  let opened = false
  const phase = (): UpdateView['phase'] => {
    if (!on || mode === 'off') return 'off'
    if (mode === 'failed') return 'failed'
    if (mode === 'current' || !offer) return 'current'
    return 'available'
  }
  const view = (): UpdateView => {
    const p = phase()
    const show = p === 'available' && offer
    return {
      phase: p,
      current: CURRENT,
      latest: show
        ? { version: offer.version, notes: offer.notes, host: new URL(offer.url).hostname, size: offer.size, file: offer.file, sha256: offer.sha256 }
        : undefined,
      snoozedUntil: snoozedUntil && snoozedUntil > Date.now() ? snoozedUntil : undefined,
      opened,
      checkedAt: Date.now(),
      os
    }
  }

  registerWebHandler('updates:get', view)
  registerWebHandler('updates:check', () => {
    if (phase() === 'available') snoozedUntil = undefined
    return view()
  })
  registerWebHandler('updates:download', () => {
    if (phase() === 'available' && offer) {
      console.info(`[updates] stage: would open ${offer.url}`)
      opened = true
    }
    return view()
  })
  registerWebHandler('updates:later', () => {
    snoozedUntil = Date.now() + SNOOZE_MS
    return view()
  })
  registerWebHandler('updates:quit', () => {
    console.info('[updates] stage: would quit miyagi')
    return true
  })
}

if (!isElectron) setupWeb()
