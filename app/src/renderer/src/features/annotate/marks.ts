/**
 * Buddy draws: the pure mark rules (no React, no timers). Tested in geometry.test.ts.
 *
 *   keyOf / validMarks   which marks are drawable and how a mark is known again when the engine re-sends it
 *   mergeMarks           a new annotate replaces the drawn set; a mark with a known key keeps its `born` (it is not
 *                        drawn again); a mark the learner already reached this step stays gone
 *   holdFor / fadeAt     how long the marks stay (holdMs, or the app's 6 s, within sane bounds), counted from the
 *                        newest mark's birth so a re-send does not restart it
 *   createReach          "the learner went there": a click inside, or the pointer coming into the box from outside and
 *                        resting there a moment. In Electron the overlay is click-through, so clicks never reach it; it
 *                        only gets forwarded mouse moves. The move rule is the stand-in until main can say "clicked here".
 *   cleanText / cleanKeys the on-screen coach (Nov 24): a "point" mark in an app lesson may carry the step's action
 *                        (text, <= 12 words) and its shortcut (keys, <= 3 keycap labels). Read defensively (OnscreenFields)
 *                        until the contract fields reach this branch. A mark with text is not timed (timedMarks).
 */
import type { Annotation } from '../../../../../../shared/contracts/events'
import { isDrawable, type Pt, type Rect } from './geometry'

export type { Annotation }

/** One drawn mark. `rect` stays in screen points (global space); the layer maps it to the window. `text` / `keys`: the
 * on-screen coach's step action and shortcut, drawn beside the loop (BuddyLayer TextBox). */
export type DrawMark = {
  key: string
  id?: string
  rect: Rect
  displayId?: number
  label?: string
  text?: string
  keys?: string[]
  why: Annotation['why']
  stepId?: string
  askId?: string
  born: number
}

/**
 * The on-screen coach's Annotation fields (contract, Nov 24: Annotation.text / .keys). Read through this local type
 * until the engine lane's contract commit reaches this branch (Core request (a) in agents/app-onscreen-coach.md).
 */
export type OnscreenFields = { text?: unknown; keys?: unknown }

/** The step's action is 12 words or fewer by contract; keep the first 12 if an engine sends more. */
export const MAX_TEXT_WORDS = 12
/** At most this many keycaps, each label this long at most (a key name, not a sentence). */
export const MAX_KEYS = 3
export const MAX_KEY_CHARS = 12

export function cleanText(s: unknown): string | undefined {
  if (typeof s !== 'string') return undefined
  const words = s.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean).slice(0, MAX_TEXT_WORDS)
  return words.length ? words.join(' ') : undefined
}

/** Keycap labels as the engine spells them: strings only, trimmed, 1 to 12 characters, the first 3. */
export function cleanKeys(k: unknown): string[] | undefined {
  if (!Array.isArray(k)) return undefined
  const out = k
    .filter((v): v is string => typeof v === 'string')
    .map((v) => v.trim())
    .filter((v) => v.length >= 1 && [...v].length <= MAX_KEY_CHARS)
    .slice(0, MAX_KEYS)
  return out.length ? out : undefined
}

/** A mark with the coach's text stays while its step is live: no hold timer (holdMs does not apply to it). */
export const hasText = (m: Pick<DrawMark, 'text'>): boolean => !!m.text

/** The marks the hold timer fades: every mark without text. */
export function timedMarks<T extends Pick<DrawMark, 'text'>>(marks: readonly T[]): T[] {
  return marks.filter((m) => !hasText(m))
}

/** The app's default hold when annotate has no holdMs (the brief: fade after 6 s). */
export const DEFAULT_HOLD_MS = 6000
export const MIN_HOLD_MS = 1500
export const MAX_HOLD_MS = 30_000

export function holdFor(holdMs: unknown): number {
  return typeof holdMs === 'number' && Number.isFinite(holdMs) && holdMs > 0 ? Math.min(MAX_HOLD_MS, Math.max(MIN_HOLD_MS, holdMs)) : DEFAULT_HOLD_MS
}

/**
 * When the drawn set fades: the hold counts from the newest mark's birth. A re-sent mark keeps its birth (mergeMarks),
 * so an engine that re-sends the same marks every few seconds does not push the fade back; only a new mark does.
 */
export function fadeAt(marks: readonly Pick<DrawMark, 'born'>[], holdMs: number): number | undefined {
  if (!marks.length) return undefined
  return Math.max(...marks.map((m) => m.born)) + holdMs
}

/** Labels are 4 words or fewer by contract; keep the first 4 if an engine sends more. */
export function cleanLabel(s: unknown): string | undefined {
  if (typeof s !== 'string') return undefined
  const words = s.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean).slice(0, 4)
  return words.length ? words.join(' ') : undefined
}

/** A key for a mark with no id: its box on a coarse grid. Re-reads that move a few points are matched by SAME_PX instead. */
export const KEY_GRID = 12
/** OCR moves a box a few points between reads: a mark with no id within this of a drawn (or gone) one is that mark. */
export const SAME_PX = 12

export function keyOf(m: Pick<Annotation, 'id' | 'x' | 'y' | 'w' | 'h' | 'why' | 'displayId'>): string {
  if (typeof m.id === 'string' && m.id) return `id:${m.id}`
  const g = (n: number): number => Math.round(n / KEY_GRID)
  return `${m.why}:${m.displayId ?? 'p'}:${g(m.x)},${g(m.y)},${g(m.w)},${g(m.h)}`
}

/** The drawable marks of an annotate, de-duplicated by key, at most MAX_MARKS (the buddy circles a few things, not a page). */
export const MAX_MARKS = 3

export function validMarks(list: unknown): Annotation[] {
  if (!Array.isArray(list)) return []
  const seen = new Set<string>()
  const out: Annotation[] = []
  for (const m of list as Annotation[]) {
    if (!m || (m.why !== 'point' && m.why !== 'answer') || !isDrawable(m)) continue
    const k = keyOf(m)
    if (seen.has(k)) continue
    seen.add(k)
    out.push(m)
    if (out.length >= MAX_MARKS) break
  }
  return out
}

/** What a mark is remembered by (drawn now, or gone this step). */
export type Known = Pick<DrawMark, 'key' | 'id' | 'rect' | 'why'>

const near = (a: Rect, b: Rect): boolean => Math.abs(a.x - b.x) <= SAME_PX && Math.abs(a.y - b.y) <= SAME_PX && Math.abs(a.w - b.w) <= SAME_PX && Math.abs(a.h - b.h) <= SAME_PX

/** The key this mark already has among `pool`: its id, or (no id) a mark of the same kind at nearly the same box. */
export function knownKey(m: Annotation, pool: Iterable<Known>): string | undefined {
  if (typeof m.id === 'string' && m.id) return keyOf(m)
  for (const k of pool) if (!k.id && k.why === m.why && near(k.rect, m)) return k.key
  return undefined
}

/** The keys among `pool` that are this mark: its own key, or (no id) the same kind at nearly the same box. */
export function sameMarkKeys(m: Annotation, pool: Iterable<Known>): string[] {
  const k = keyOf(m)
  const hasId = typeof m.id === 'string' && !!m.id
  return [...pool].filter((p) => p.key === k || (!hasId && !p.id && p.why === m.why && near(p.rect, m))).map((p) => p.key)
}

/** The new drawn set: `incoming` replaces `prev`; a known mark keeps its key and birth (no redraw); a gone one is skipped. */
export function mergeMarks(prev: readonly DrawMark[], incoming: readonly Annotation[], gone: Iterable<Known>, now: number): DrawMark[] {
  const goneList = [...gone]
  const goneKeys = new Set(goneList.map((g) => g.key))
  const out: DrawMark[] = []
  for (const m of incoming) {
    const hasId = typeof m.id === 'string' && !!m.id
    if (goneKeys.has(keyOf(m)) || (!hasId && knownKey(m, goneList))) continue
    const was = prev.find((p) => p.key === (knownKey(m, prev) ?? keyOf(m)))
    if (was && out.includes(was)) continue
    const label = cleanLabel(m.label)
    // The coach's text and keys: "point" marks only (contract). A re-send with new text updates it in place (same key and
    // birth, so the stroke does not redraw).
    const extra = m as Annotation & OnscreenFields
    const text = m.why === 'point' ? cleanText(extra.text) : undefined
    const keys = text ? cleanKeys(extra.keys) : undefined
    out.push({
      key: was ? was.key : keyOf(m),
      ...(hasId ? { id: m.id } : {}),
      // A re-read a few points off keeps the drawn box, so the stroke does not twitch.
      rect: was && near(was.rect, m) ? was.rect : { x: m.x, y: m.y, w: m.w, h: m.h },
      ...(m.displayId !== undefined ? { displayId: m.displayId } : {}),
      ...(label ? { label } : {}),
      ...(text ? { text } : {}),
      ...(keys ? { keys } : {}),
      why: m.why,
      ...(m.stepId ? { stepId: m.stepId } : {}),
      ...(m.askId ? { askId: m.askId } : {}),
      born: was ? was.born : now
    })
  }
  return out
}

/** A drawn mark as the engine sent it (an Annotation, with the coach's text and keys), so it can be drawn again later
 * (store.ts: a text mark withdrawn while the lesson was quiet comes back when it is live again). */
export function asAnnotation(d: DrawMark): Annotation & { text?: string; keys?: string[] } {
  return {
    ...(d.id ? { id: d.id } : {}),
    x: d.rect.x,
    y: d.rect.y,
    w: d.rect.w,
    h: d.rect.h,
    ...(d.displayId !== undefined ? { displayId: d.displayId } : {}),
    ...(d.label ? { label: d.label } : {}),
    why: d.why,
    ...(d.stepId ? { stepId: d.stepId } : {}),
    ...(d.askId ? { askId: d.askId } : {}),
    ...(d.text ? { text: d.text } : {}),
    ...(d.keys ? { keys: [...d.keys] } : {})
  }
}

/** The pointer must rest inside a box this long (after coming in from outside) to count as "went there". */
export const REACH_MS = 280
/** The box counts a little bigger than drawn: the loop itself sits outside it. */
export const REACH_PAD = 6

type Box = { key: string; rect: Rect }

const inside = (r: Rect, p: Pt, pad = REACH_PAD): boolean => p.x >= r.x - pad && p.x <= r.x + r.w + pad && p.y >= r.y - pad && p.y <= r.y + r.h + pad

/**
 * Tracks the pointer against the drawn boxes (window coordinates). `move` returns the keys the learner reached: the
 * pointer was seen OUTSIDE the box first (so a cursor that already rests where the learner circled does not fade the
 * answer at once), then stayed inside for REACH_MS. `press` returns the keys a real click landed in (the browser
 * stage, or a click the overlay does get).
 */
export function createReach(): { move(p: Pt, boxes: readonly Box[], now: number): string[]; press(p: Pt, boxes: readonly Box[]): string[]; reset(): void } {
  const armed = new Set<string>()
  const since = new Map<string, number>()
  return {
    move(p, boxes, now) {
      const hit: string[] = []
      const live = new Set(boxes.map((b) => b.key))
      for (const k of [...armed]) if (!live.has(k)) armed.delete(k)
      for (const k of [...since.keys()]) if (!live.has(k)) since.delete(k)
      for (const b of boxes) {
        if (!inside(b.rect, p)) {
          armed.add(b.key)
          since.delete(b.key)
          continue
        }
        if (!armed.has(b.key)) continue
        const at = since.get(b.key) ?? now
        since.set(b.key, at)
        if (now - at >= REACH_MS) hit.push(b.key)
      }
      return hit
    },
    press(p, boxes) {
      return boxes.filter((b) => inside(b.rect, p)).map((b) => b.key)
    },
    reset() {
      armed.clear()
      since.clear()
    }
  }
}
