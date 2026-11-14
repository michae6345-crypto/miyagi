/**
 * Plays `speak` clips, one at a time, and measures how loud they are.
 *
 * Only a window that attach()es plays anything: the overlay (index.tsx mounts the attach), so a clip never
 * plays twice when several windows hear the same `speak`. The loudness comes from an AnalyserNode; that needs
 * the audio to be readable (same origin, data:, or CORS from the engine). When it isn't, the clip still plays,
 * level stays undefined, and the origin is remembered so later clips skip the extra try.
 */
export type PlayerReport = (s: { speaking: boolean; level?: number }) => void

type Clip = { el: HTMLAudioElement; node?: MediaElementAudioSourceNode; timer?: number }

const originOf = (url: string): string => {
  try {
    return new URL(url, location.href).origin
  } catch {
    return ''
  }
}
const isCrossOrigin = (url: string): boolean => /^https?:/i.test(url) && originOf(url) !== location.origin

export function createPlayer(report: PlayerReport): { attach(): () => void; warm(): void; play(url: string): void; stop(): void } {
  let attached = 0
  let seq = 0
  let clip: Clip | undefined
  let ctx: AudioContext | undefined
  let analyser: AnalyserNode | undefined
  const unreadable = new Set<string>()

  /** The analyser, if the audio context may run (it needs a user gesture in the browser stage). */
  const meter = (): AnalyserNode | undefined => {
    try {
      ctx ??= new AudioContext()
      if (ctx.state === 'suspended') ctx.resume().catch(() => undefined)
      if (ctx.state !== 'running') return undefined
      if (!analyser) {
        analyser = ctx.createAnalyser()
        analyser.fftSize = 512
        analyser.connect(ctx.destination)
      }
      return analyser
    } catch {
      return undefined
    }
  }

  const release = (c: Clip): void => {
    window.clearInterval(c.timer)
    c.el.onplaying = c.el.onended = c.el.onerror = null
    c.el.pause()
    c.el.removeAttribute('src')
    c.el.load() // aborts the download
    c.node?.disconnect()
  }

  const stop = (): void => {
    seq++
    if (clip) release(clip)
    clip = undefined
    report({ speaking: false, level: undefined })
  }

  const start = (url: string, id: number, measure: boolean): void => {
    const cross = isCrossOrigin(url)
    const an = measure && !unreadable.has(originOf(url)) ? meter() : undefined
    const el = new Audio()
    if (an && cross) el.crossOrigin = 'anonymous'
    el.src = url
    const c: Clip = { el }
    clip = c
    if (an && ctx) {
      try {
        c.node = ctx.createMediaElementSource(el)
        c.node.connect(an)
      } catch {
        c.node = undefined
      }
    }

    let level = 0
    let shown = 0
    const buf = new Uint8Array(analyser?.fftSize ?? 0)
    const tick = (): void => {
      if (id !== seq || !analyser) return
      analyser.getByteTimeDomainData(buf)
      let sum = 0
      for (const v of buf) sum += ((v - 128) / 128) ** 2
      // Fast attack, slow release, in 0.05 steps: the store only changes when the bar would visibly move.
      level = Math.max(Math.min(1, Math.sqrt(sum / buf.length) * 4), level * 0.8)
      const q = Math.round(level * 20) / 20
      if (q !== shown) report({ speaking: true, level: (shown = q) })
    }

    el.onplaying = () => {
      if (id !== seq) return
      if (!measure && cross) unreadable.add(originOf(url)) // played only once the meter was dropped: no CORS there
      report({ speaking: true, level: c.node ? 0 : undefined })
      if (c.node && c.timer === undefined) c.timer = window.setInterval(tick, 50)
    }
    el.onended = () => id === seq && stop()
    el.onerror = () => {
      if (id !== seq) return
      // A cross-origin clip without CORS fails to load as "anonymous": play it once more, unmeasured.
      if (el.crossOrigin) {
        release(c)
        start(url, id, false)
      } else stop() // missing or unplayable: fail quietly
    }
    el.play().catch((e: unknown) => {
      // Load errors arrive via onerror; only an autoplay refusal ends up here alone.
      if (id === seq && (e as DOMException)?.name === 'NotAllowedError') stop()
    })
  }

  return {
    attach() {
      attached++
      return () => {
        attached--
        if (!attached) stop()
      }
    },
    /** Call from the toggle (a user gesture in the browser stage) so the meter can run when the first clip lands. */
    warm() {
      if (attached) meter()
    },
    play(url) {
      if (!attached) return
      stop()
      start(url, seq, true)
    },
    stop
  }
}
