/**
 * Feature: errors. A window's uncaught errors and unhandled promise rejections go to main's error log
 * (errors:renderer → userData/errors/errors.json), scrubbed here first and again in main. Local only: the log leaves
 * this Mac only through main/features/telemetry.ts, and only while Settings › Privacy "Share crash reports and usage"
 * is on. The same message is reported once per window.
 */
import { bridge, isElectron } from '../../bridge'
import { scrub } from './scrub'

const seen = new Set<string>()

function report(message: unknown, stack: unknown): void {
  const text = typeof message === 'string' ? scrub(message.replace(/\s+/g, ' ').trim(), 300) : ''
  if (!text || seen.has(text) || seen.size >= 20) return
  seen.add(text)
  const frames = typeof stack === 'string' ? scrub(stack, 600) : undefined
  bridge.invoke('errors:renderer', { message: text, stack: frames }).catch(() => undefined)
}

function describe(reason: unknown): { message: string; stack?: string } {
  if (reason instanceof Error) return { message: `${reason.name}: ${reason.message}`, stack: reason.stack }
  return { message: typeof reason === 'string' ? reason : 'unhandled rejection' }
}

if (isElectron && typeof window !== 'undefined') {
  window.addEventListener('error', (e) => {
    const d = e.error ? describe(e.error) : { message: e.message }
    report(d.message, d.stack)
  })
  window.addEventListener('unhandledrejection', (e) => {
    const d = describe(e.reason)
    report(`unhandled: ${d.message}`, d.stack)
  })
}
