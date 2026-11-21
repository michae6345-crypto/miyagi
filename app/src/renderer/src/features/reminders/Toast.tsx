/**
 * Feature: reminders. The in-app stand-in for the macOS notification: the browser stage's simulation, and a dev
 * build's toast (main never posts a real notification while developing). Placed where macOS puts a banner (top
 * right, under the menu bar) and shaped like one, so what is reviewed here is what a learner sees. A click opens
 * Home, like the real one. It says it is a preview, so nobody mistakes it for the system's own.
 */
import { AnimatePresence, motion } from 'motion/react'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { color, fill, radius2, shadows, spring, surface, type2 } from '../../core/theme'
import { MiyagiMark } from '../../core/ui/Mark'
import { closeToast, openHome, useReminders } from './store'

const W = 356

export function ReminderToast({ layout }: { layout: Layout }): ReactNode {
  const toast = useReminders((r) => r.toast)
  const top = layout.workArea.y - layout.origin.y + 12
  return (
    <div className="pointer-events-none absolute" style={{ top, right: 16, width: W }}>
      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.id}
            data-hit
            data-reminders="toast"
            role="status"
            aria-live="polite"
            className="group pointer-events-auto relative"
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 24 }}
            transition={spring}
          >
            <button
              type="button"
              className="mg-press flex w-full cursor-pointer items-start gap-[12px] text-left"
              style={{ padding: '12px 14px', borderRadius: radius2.group, background: surface.sheet, boxShadow: `inset 0 0 0 1px ${surface.border}, ${shadows.card}` }}
              onClick={openHome}
              title="Open Home"
            >
              <span aria-hidden className="grid h-[36px] w-[36px] shrink-0 place-items-center" style={{ borderRadius: radius2.row, background: fill.tile }}>
                <MiyagiMark size={24} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                <span className="flex items-center justify-between gap-[8px]">
                  <span className="font-semibold" style={{ fontSize: type2.sm, color: color.text }}>
                    {toast.title}
                  </span>
                  <span style={{ fontSize: type2.micro, color: color.faint }}>now</span>
                </span>
                <span style={{ fontSize: type2.sm, lineHeight: '18px', color: color.text }}>{toast.body}</span>
                <span style={{ fontSize: type2.micro, color: color.faint, marginTop: 2 }}>Preview of the notification</span>
              </span>
            </button>
            <button
              type="button"
              aria-label="Close"
              className="absolute grid h-[20px] w-[20px] cursor-pointer place-items-center opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
              style={{ top: -6, left: -6, borderRadius: radius2.round, background: surface.sheet, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.label }}
              onClick={closeToast}
            >
              <X size={11} strokeWidth={2} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
