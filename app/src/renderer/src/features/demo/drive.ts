/**
 * Feature: demo. Drives the real UI the way a person would: opens the launcher from the island, types into its
 * field, presses keys, clicks buttons. The walkthrough never reaches into another feature's store.
 */
import { bridge } from '../../bridge'
import { emitUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'

export const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

/** Thrown when the walkthrough is restarted mid-beat. */
export class Cancelled extends Error {}

/** Polls until `ok()` (or gives up quietly after `ms`, so a slow beat never wedges the demo). */
export async function until(ok: () => boolean, ms = 8000, alive: () => boolean = () => true): Promise<boolean> {
  const end = Date.now() + ms
  while (Date.now() < end) {
    if (!alive()) throw new Cancelled()
    if (ok()) return true
    await sleep(50)
  }
  return false
}

const visible = (el: Element | null): el is HTMLElement => !!el && (el as HTMLElement).getClientRects().length > 0

/** The launcher's text field, if it's open. */
export function launcherInput(): HTMLInputElement | null {
  const all = Array.from(document.querySelectorAll<HTMLInputElement>('input[aria-label]'))
  return all.find((el) => visible(el) && /learn|Ask about/i.test(el.getAttribute('aria-label') ?? '')) ?? null
}

export async function openLauncher(alive: () => boolean): Promise<HTMLInputElement | null> {
  if (!launcherInput()) bridge.emit('launcher:toggle')
  await until(() => !!launcherInput(), 3000, alive)
  await sleep(350)
  const input = launcherInput()
  input?.focus()
  return input
}

/** Types like a person: React sees every keystroke as an input event. */
export async function typeInto(input: HTMLInputElement, text: string, alive: () => boolean, perChar = 45): Promise<void> {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  for (let i = 1; i <= text.length; i++) {
    if (!alive()) throw new Cancelled()
    setter.call(input, text.slice(0, i))
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await sleep(perChar + (text[i - 1] === ' ' ? 30 : 0))
  }
}

export function press(el: HTMLElement, key: string, mods: Partial<Pick<KeyboardEventInit, 'metaKey' | 'ctrlKey' | 'shiftKey' | 'altKey'>> = {}): void {
  const code = key.length === 1 ? `Key${key.toUpperCase()}` : key
  el.dispatchEvent(new KeyboardEvent('keydown', { key, code, bubbles: true, cancelable: true, ...mods }))
}

/** The visible button whose text (or aria-label) contains `label`. */
export function findButton(label: string): HTMLButtonElement | null {
  const all = Array.from(document.querySelectorAll<HTMLButtonElement>('button'))
  return all.find((b) => visible(b) && ((b.textContent ?? '').includes(label) || (b.getAttribute('aria-label') ?? '').includes(label))) ?? null
}

/** Any visible element whose own text is exactly `text` (e.g. a section header). */
export function findText(text: string): HTMLElement | null {
  const all = Array.from(document.querySelectorAll<HTMLElement>('button, [role="button"], summary, div, span'))
  return all.find((el) => visible(el) && el.childElementCount <= 2 && (el.textContent ?? '').trim() === text) ?? null
}

export const dismiss = (): void => {
  emitUi('dismiss')
}

export const lesson = useLesson.getState
