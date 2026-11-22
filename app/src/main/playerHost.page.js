/**
 * The YouTube player host page's script (R33). main/playerHost.ts serves it with the page at /player-host.js; the
 * browser stage's Vite middleware serves the same file. Plain browser JS, no build step: it is sent as written.
 *
 * Runs only framed by the app's page (the origin in <meta name="miyagi-parent">). Loads YouTube's IFrame API here,
 * never in the app's page, and makes one player with the quiet embed settings. The channel to the app's page
 * (renderer features/player/frame.ts) is postMessage, both ways checked for source and origin:
 *
 *   in   {miyagiPlayer: 1, op: 'play' | 'pause' | 'seek' {t} | 'load' {videoId, t} | 'cue' {videoId, t}
 *                              | 'mute' | 'unmute' | 'volume' {v} | 'rate' {rate}}
 *   out  {miyagiPlayer: 1, ev: 'ready' | 'state' {data} | 'error' {data} | 'info' | 'fail', info}
 *        info = {state, t, duration, rate, volume, muted, title, videoId}, sent with every event and whenever it
 *        changes (checked every 100 ms)
 *
 * Anything else is ignored. Arguments are checked here too (an 11-character video id, finite numbers in range).
 */
'use strict'
;(() => {
  const meta = document.querySelector('meta[name="miyagi-parent"]')
  const parentOrigin = meta ? meta.getAttribute('content') : null
  // Opened on its own, or framed by anyone else (frame-ancestors already refuses that): do nothing.
  if (!parentOrigin || window.parent === window) return

  const VIDEO_ID = /^[\w-]{11}$/
  const num = (v, lo, hi) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi
  const post = (msg) => window.parent.postMessage(Object.assign({ miyagiPlayer: 1 }, msg), parentOrigin)

  // CSSOM, not a style attribute or a <style> (the page's CSP allows no inline style).
  for (const el of [document.documentElement, document.body]) {
    el.style.margin = '0'
    el.style.padding = '0'
    el.style.width = '100%'
    el.style.height = '100%'
    el.style.overflow = 'hidden'
  }
  const mount = document.createElement('div')
  document.body.appendChild(mount)

  let player = null
  let ready = false
  let last = ''

  const read = (fn, fallback) => {
    try {
      const v = fn()
      return v === undefined || v === null ? fallback : v
    } catch {
      return fallback
    }
  }
  const info = () => {
    const data = read(() => player.getVideoData(), {})
    return {
      state: read(() => player.getPlayerState(), -1),
      t: read(() => player.getCurrentTime(), 0),
      duration: read(() => player.getDuration(), 0),
      rate: read(() => player.getPlaybackRate(), 1),
      volume: read(() => player.getVolume(), 100),
      muted: read(() => player.isMuted(), false),
      title: typeof data.title === 'string' ? data.title : '',
      videoId: typeof data.video_id === 'string' ? data.video_id : ''
    }
  }
  const tell = (ev, data) => {
    if (!player) return
    const i = info()
    last = JSON.stringify(i)
    post({ ev, data, info: i })
  }

  window.addEventListener('message', (e) => {
    if (e.source !== window.parent || e.origin !== parentOrigin) return
    const m = e.data
    if (!m || typeof m !== 'object' || m.miyagiPlayer !== 1 || typeof m.op !== 'string') return
    if (!player || !ready) return
    try {
      switch (m.op) {
        case 'play':
          player.playVideo()
          break
        case 'pause':
          player.pauseVideo()
          break
        case 'seek':
          if (num(m.t, 0, 1e6)) player.seekTo(m.t, true)
          break
        case 'load':
          if (typeof m.videoId === 'string' && VIDEO_ID.test(m.videoId) && num(m.t, 0, 1e6)) player.loadVideoById({ videoId: m.videoId, startSeconds: m.t })
          break
        case 'cue':
          if (typeof m.videoId === 'string' && VIDEO_ID.test(m.videoId) && num(m.t, 0, 1e6)) player.cueVideoById({ videoId: m.videoId, startSeconds: m.t })
          break
        case 'mute':
          player.mute()
          break
        case 'unmute':
          player.unMute()
          break
        case 'volume':
          if (num(m.v, 0, 100)) player.setVolume(m.v)
          break
        case 'rate':
          if (num(m.rate, 0.25, 2)) player.setPlaybackRate(m.rate)
          break
        default:
          break
      }
    } catch {
      // the player isn't ready for that call yet: the app's next command or the next info decides
    }
  })

  const create = () => {
    if (player || !window.YT || !window.YT.Player) return
    // Quiet embed (Michael's desktop test 9): no controls (the panel's drive it), related videos from the same channel
    // only (rel 0), no annotations or cards (iv_load_policy 3), no keyboard, no fullscreen. Created empty: the panel
    // cues or loads the step's clip once it's ready.
    player = new window.YT.Player(mount, {
      width: '100%',
      height: '100%',
      playerVars: { controls: 0, disablekb: 1, fs: 0, rel: 0, iv_load_policy: 3, modestbranding: 1, playsinline: 1, enablejsapi: 1, origin: location.origin },
      events: {
        onReady: () => {
          ready = true
          tell('ready')
        },
        onStateChange: (e) => tell('state', e.data),
        onError: (e) => tell('error', e.data)
      }
    })
    setInterval(() => {
      if (!ready) return
      const i = info()
      const key = JSON.stringify(i)
      if (key === last) return
      last = key
      post({ ev: 'info', info: i })
    }, 100)
  }

  window.onYouTubeIframeAPIReady = create
  const s = document.createElement('script')
  s.src = 'https://www.youtube.com/iframe_api'
  s.async = true
  s.onerror = () => post({ ev: 'fail' })
  document.head.appendChild(s)
})()
