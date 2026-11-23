/**
 * Feature: circle. The early screen capture, as a small state machine (test/circleCapture.test.ts).
 *
 * When a stroke is done while the keys are still held, the store asks main for a JPEG of the circled region at once
 * (bridge.invoke('ptt:capture', region)), so the file can be ready by the time the keys come up and the engine need not
 * grab its own frame. The rules:
 *   - only the newest capture counts. A newer stroke makes the older one stale; a stale one is released (ok) or
 *     ignored (failed) when it settles;
 *   - at release (take), the capture goes with the ask ONLY if it already settled ok and was taken of the very region
 *     the ask sends (x, y, w, h, displayId). Release never waits for it: still pending means no capture, and the
 *     engine grabs its own frame as before;
 *   - every ok capture that will not be sent is released ('ptt:capture-release'), so the helper deletes the file now.
 *     A capture that is sent is the engine's to delete;
 *   - a failed capture (helper down, busy, timeout, screen denied, a thrown invoke) just means no capture;
 *   - a capture older than MAX_AGE_MS at release is not sent (and is released): the screen may have moved on, and the
 *     helper deletes its file 30 s after writing it, while an ask from 'sealed' can go out up to 70 s after the stroke.
 *
 * The region compared is the one this side asked for. The result's own rect is wider (main adds a margin and clamps
 * it to the display), so it never equals the region and is passed through as is: the engine maps pixels back with it.
 */
import type { AskCapture, ScreenRegion } from '../../../../../../shared/contracts/events'
import type { CaptureResult } from '../../../../main/pttProtocol'

export type CaptureIo = {
  /** bridge.invoke('ptt:capture', region). May reject (no handler, an untrusted sender): that is a failure. */
  capture: (region: ScreenRegion) => Promise<CaptureResult | null | undefined>
  /** bridge.invoke('ptt:capture-release', id). Fire and forget. */
  release: (id: string) => void
  /** The clock (Date.now by default). */
  now?: () => number
}

/** A capture that settled longer ago than this is too old to send (well inside the helper's 30 s file life). */
export const MAX_AGE_MS = 15_000

type Ok = Extract<CaptureResult, { ok: true }>
type Slot = { gen: number; region: ScreenRegion; st: 'pending' } | { gen: number; region: ScreenRegion; st: 'ok'; res: Ok; at: number } | { gen: number; region: ScreenRegion; st: 'failed' }

/** Same circled region: whole screen points and the display (scale is not part of what is captured). */
export const sameRegion = (a: ScreenRegion, b: ScreenRegion): boolean => a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h && (a.displayId ?? 0) === (b.displayId ?? 0)

const toAskCapture = (r: Ok): AskCapture => ({ path: r.path, w: r.w, h: r.h, rect: { x: r.rect.x, y: r.rect.y, w: r.rect.w, h: r.rect.h }, displayId: r.displayId })

const isOk = (r: unknown): r is Ok => !!r && typeof r === 'object' && (r as { ok?: unknown }).ok === true && typeof (r as { path?: unknown }).path === 'string' && typeof (r as { id?: unknown }).id === 'string'

export type CaptureTracker = {
  /** A stroke is done (keys still held): capture this region now. Whatever was there before is stale. */
  begin(region: ScreenRegion): void
  /** The keys are up and the ask goes out with `region`: the capture to attach, or undefined. Never waits. */
  take(region: ScreenRegion): AskCapture | undefined
  /** No ask will use a capture (Esc, a cancel, offline, a new hold): release whatever settled ok, now or later. */
  drop(): void
  /** For tests: the newest slot's state. */
  peek(): 'none' | 'pending' | 'ok' | 'failed'
}

export function createCaptureTracker(io: CaptureIo): CaptureTracker {
  let gen = 0
  let cur: Slot | undefined
  const now = (): number => (io.now ? io.now() : Date.now())

  const releaseSlot = (s: Slot | undefined): void => {
    if (s?.st === 'ok') io.release(s.res.id)
  }

  const settle = (g: number, r: unknown): void => {
    const live = cur && cur.gen === g && cur.st === 'pending' ? cur : undefined
    if (!live) {
      // Stale (a newer stroke, a release, a cancel came first): nobody will send it.
      if (isOk(r)) io.release(r.id)
      return
    }
    cur = isOk(r) ? { gen: g, region: live.region, st: 'ok', res: r, at: now() } : { gen: g, region: live.region, st: 'failed' }
  }

  return {
    begin(region) {
      releaseSlot(cur)
      const g = ++gen
      cur = { gen: g, region: { ...region }, st: 'pending' }
      let p: Promise<CaptureResult | null | undefined>
      try {
        p = io.capture(region)
      } catch {
        settle(g, undefined)
        return
      }
      Promise.resolve(p).then(
        (r) => settle(g, r),
        () => settle(g, undefined)
      )
    },
    take(region) {
      const s = cur
      cur = undefined
      if (s?.st === 'ok' && sameRegion(s.region, region) && now() - s.at <= MAX_AGE_MS) return toAskCapture(s.res)
      releaseSlot(s) // ok but not this region, or too old; a pending one is released when it settles (it is stale now)
      return undefined
    },
    drop() {
      const s = cur
      cur = undefined
      releaseSlot(s)
    },
    peek() {
      return cur ? cur.st : 'none'
    }
  }
}
