/**
 * Core: editing keys that still work when the page doesn't get macOS's edit commands (user report on main 1d453ca0:
 * "Backspace doesn't work in the overlay's text field").
 *
 * Why: miyagi's typing surfaces (the launcher's "ask miyagi" field, Settings' search) are non-activating panels, so
 * VS Code stays the active app while they hold the keyboard (main/platform.ts focusPanel; activating miyagi switched
 * Spaces over a full-screen app). Typed characters reach the field either way, but in a panel of an app that isn't
 * active the editing keys (Backspace, Delete, ⌥/⌘ variants, ←/→, ⌘A) can arrive without the edit command AppKit's
 * text system normally attaches, and Chromium on the Mac does nothing with them then. UNVERIFIED on a Mac (no app runs
 * in this lane): the mechanism is the likely one; the fallback is safe whatever the cause, because it only acts when
 * the key changed nothing.
 *
 * How: on keydown in a text input or textarea, note the value and selection. After the key's own default action has
 * run (next task), if nothing handled it (no beforeinput, value and selection unchanged, not defaultPrevented) apply
 * the edit ourselves: deletions through document.execCommand('delete') so React's onChange and undo see them.
 *
 * editFor is pure (test/editKeys.test.ts); installEditKeys wires it to a document.
 */

export type Mods = { alt: boolean; meta: boolean; shift: boolean; ctrl: boolean }
export type Dir = 'forward' | 'backward' | 'none'
export type Edit = { kind: 'delete'; from: number; to: number } | { kind: 'select'; from: number; to: number; dir: 'forward' | 'backward' | 'none' }

const WORD = /[\p{L}\p{N}_]/u
const isWord = (ch: string | undefined): boolean => !!ch && WORD.test(ch)
const isLow = (code: number): boolean => code >= 0xdc00 && code <= 0xdfff
const isHigh = (code: number): boolean => code >= 0xd800 && code <= 0xdbff

/** One character back from i (a surrogate pair counts as one). */
function charBack(value: string, i: number): number {
  if (i <= 0) return 0
  return i >= 2 && isLow(value.charCodeAt(i - 1)) && isHigh(value.charCodeAt(i - 2)) ? i - 2 : i - 1
}
/** One character forward from i. */
function charFwd(value: string, i: number): number {
  if (i >= value.length) return value.length
  return i + 1 < value.length && isHigh(value.charCodeAt(i)) && isLow(value.charCodeAt(i + 1)) ? i + 2 : i + 1
}
/** ⌥← / ⌥⌫: back over any non-word characters, then over the word. */
export function wordBack(value: string, i: number): number {
  let j = Math.max(0, Math.min(i, value.length))
  while (j > 0 && !isWord(value[j - 1])) j--
  while (j > 0 && isWord(value[j - 1])) j--
  return j
}
/** ⌥→ / ⌥⌦: forward over any non-word characters, then over the word. */
export function wordFwd(value: string, i: number): number {
  let j = Math.max(0, Math.min(i, value.length))
  while (j < value.length && !isWord(value[j])) j++
  while (j < value.length && isWord(value[j])) j++
  return j
}
/** ⌘← / ⌘⌫: the start of the line i is on (a textarea's line; an input is one line). */
export const lineStart = (value: string, i: number): number => (i <= 0 ? 0 : value.lastIndexOf('\n', i - 1) + 1)
/** ⌘→ / ⌘⌦: the end of the line i is on. */
export function lineEnd(value: string, i: number): number {
  const n = value.indexOf('\n', i)
  return n < 0 ? value.length : n
}

/**
 * The edit a key makes in a text field (macOS bindings), or undefined when it makes none here (or isn't an editing
 * key). start/end: the selection (start <= end); dir: its selectionDirection ('backward': the moving end, the focus,
 * is `start`; otherwise it is `end`, as on the Mac).
 */
export function editFor(key: string, mods: Mods, value: string, start: number, end: number, dir: Dir = 'none'): Edit | undefined {
  const len = value.length
  const s = Math.max(0, Math.min(start, len))
  const e = Math.max(s, Math.min(end, len))
  if (mods.ctrl) return undefined // ⌃ bindings (⌃H, ⌃A…) are left alone
  const del = (from: number, to: number): Edit | undefined => (to > from ? { kind: 'delete', from, to } : undefined)
  if (key === 'Backspace' && !mods.shift) {
    if (e > s) return del(s, e)
    if (mods.meta) return del(lineStart(value, s) === s && s > 0 ? s - 1 : lineStart(value, s), s)
    if (mods.alt) return del(wordBack(value, s), s)
    return del(charBack(value, s), s)
  }
  if (key === 'Delete' && !mods.shift) {
    if (e > s) return del(s, e)
    if (mods.meta) return del(s, lineEnd(value, s) === s && s < len ? s + 1 : lineEnd(value, s))
    if (mods.alt) return del(s, wordFwd(value, s))
    return del(s, charFwd(value, s))
  }
  if ((key === 'a' || key === 'A') && mods.meta && !mods.alt && !mods.shift) {
    return s === 0 && e === len ? undefined : { kind: 'select', from: 0, to: len, dir: 'none' }
  }
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const left = key === 'ArrowLeft'
    const step = (i: number): number =>
      mods.meta ? (left ? lineStart(value, i) : lineEnd(value, i)) : mods.alt ? (left ? wordBack(value, i) : wordFwd(value, i)) : left ? charBack(value, i) : charFwd(value, i)
    let next: Edit
    if (mods.shift) {
      // ⇧ moves the selection's focus and keeps its anchor (selectionDirection says which end is which).
      const backward = dir === 'backward' && e > s
      const anchor = backward ? e : s
      const focus = step(backward ? s : e)
      next = focus < anchor ? { kind: 'select', from: focus, to: anchor, dir: 'backward' } : { kind: 'select', from: anchor, to: focus, dir: focus === anchor ? 'none' : 'forward' }
    }
    else if (e > s && !mods.alt && !mods.meta) next = { kind: 'select', from: left ? s : e, to: left ? s : e, dir: 'none' }
    else {
      const at = step(left ? s : e)
      next = { kind: 'select', from: at, to: at, dir: 'none' }
    }
    return next.from === s && next.to === e ? undefined : next
  }
  return undefined
}

/** Input types with a text selection (setSelectionRange works on these only). */
const TEXT_TYPES = new Set(['', 'text', 'search', 'url', 'tel', 'password'])

type Field = HTMLInputElement | HTMLTextAreaElement
function fieldOf(t: EventTarget | null): Field | undefined {
  const el = t as Element | null
  if (!el || typeof (el as Field).setSelectionRange !== 'function') return undefined
  const tag = el.tagName
  if (tag === 'TEXTAREA') return el as HTMLTextAreaElement
  if (tag === 'INPUT' && TEXT_TYPES.has(((el as HTMLInputElement).getAttribute('type') ?? '').toLowerCase())) return el as HTMLInputElement
  return undefined
}

function apply(doc: Document, el: Field, edit: Edit): void {
  if (edit.kind === 'select') return el.setSelectionRange(edit.from, edit.to, edit.dir)
  el.setSelectionRange(edit.from, edit.to)
  let done = false
  try {
    done = doc.execCommand('delete')
  } catch {
    done = false
  }
  if (done) return
  // No execCommand (or it refused): edit the value directly and say so the way the browser would.
  el.setRangeText('', edit.from, edit.to, 'end')
  el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: edit.from < (el.selectionStart ?? edit.from) ? 'deleteContentForward' : 'deleteContentBackward' }))
}

/** Listen on this window. Returns a function that stops. */
export function installEditKeys(win: Window = window): () => void {
  const doc = win.document
  const onKey = (e: KeyboardEvent): void => {
    if (e.defaultPrevented || e.isComposing || e.keyCode === 229) return
    const el = fieldOf(e.target)
    if (!el || el.readOnly || el.disabled) return
    const start = el.selectionStart ?? 0
    const end = el.selectionEnd ?? start
    const dir0 = el.selectionDirection
    const dir: Dir = el.selectionDirection === 'backward' ? 'backward' : el.selectionDirection === 'forward' ? 'forward' : 'none'
    const edit = editFor(e.key, { alt: e.altKey, meta: e.metaKey, shift: e.shiftKey, ctrl: e.ctrlKey }, el.value, start, end, dir)
    if (!edit) return
    const value = el.value
    let handled = false
    const onBefore = (b: Event): void => {
      if (b.target === el) handled = true
    }
    win.addEventListener('beforeinput', onBefore, true)
    win.setTimeout(() => {
      win.removeEventListener('beforeinput', onBefore, true)
      // The key did something (the normal case) or someone took it: leave it.
      if (handled || e.defaultPrevented || doc.activeElement !== el) return
      if (el.value !== value || el.selectionStart !== start || el.selectionEnd !== end || el.selectionDirection !== dir0) return
      apply(doc, el, edit)
    }, 0)
  }
  // Bubble phase on the window: every handler in the page (React's root included) has had the key first.
  win.addEventListener('keydown', onKey)
  return () => win.removeEventListener('keydown', onKey)
}
