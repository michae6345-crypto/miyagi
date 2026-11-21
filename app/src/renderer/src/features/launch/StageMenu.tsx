/**
 * Feature: launch. The browser stage's stand-in for the native pill menu (Electron pops a real macOS menu from main,
 * so this never draws there). Same rows as the menu bar item. Chrome only: black like the island, neutral rows, the
 * launcher's keycap from bridge.platform.keys. Closes on a row, a click elsewhere or Esc.
 */
import { motion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { bridge } from '../../bridge'
import { openLibrary, openSettings } from '../../core/surfaces'
import { color, fill, radius2, shadows, surface, type2 } from '../../core/theme'
import { Kbd } from '../../core/ui/atoms'
import { startTour } from '../tips/tourStore'
import { closeStageMenu, useStageMenu } from './web'

const W = 220

type Row = { label: string; run: () => void; key?: boolean }
const ROWS: (Row | 'sep')[] = [
  { label: 'Open miyagi', run: () => void openLibrary() },
  { label: 'Start a lesson', run: () => bridge.emit('launcher:toggle'), key: true },
  { label: 'Show me around', run: () => startTour() },
  { label: 'Settings…', run: () => void openSettings() },
  'sep',
  { label: 'Quit miyagi', run: () => undefined }
]

export function StageMenu(): ReactNode {
  const at = useStageMenu((s) => s.at)

  useEffect(() => {
    if (!at) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') closeStageMenu()
    }
    const onDown = (e: PointerEvent): void => {
      if (!(e.target instanceof Element) || !e.target.closest('[data-launch-menu]')) closeStageMenu()
    }
    addEventListener('keydown', onKey)
    addEventListener('pointerdown', onDown, true)
    return () => {
      removeEventListener('keydown', onKey)
      removeEventListener('pointerdown', onDown, true)
    }
  }, [at])

  if (!at) return null
  return (
    <motion.div
      data-launch-menu
      data-hit
      role="menu"
      aria-label="miyagi"
      className="pointer-events-auto absolute"
      style={{
        left: at.x,
        top: at.y,
        width: W,
        padding: 5,
        borderRadius: radius2.row,
        background: color.island,
        boxShadow: `${shadows.card}, inset 0 0 0 1px ${surface.border}`,
        transformOrigin: '0 0'
      }}
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.12, ease: 'easeOut' }}
    >
      {ROWS.map((r, i) =>
        r === 'sep' ? (
          <div key={`sep-${i}`} style={{ height: 1, margin: '5px 8px', background: fill.rule }} />
        ) : (
          <motion.button
            key={r.label}
            type="button"
            role="menuitem"
            className="flex w-full cursor-pointer items-center justify-between text-left"
            style={{ height: 28, padding: '0 9px', borderRadius: radius2.keycap, fontSize: type2.sm, color: color.text, backgroundColor: fill.clear }}
            whileHover={{ backgroundColor: fill.chipHover }}
            transition={{ duration: 0.08 }}
            onClick={() => {
              closeStageMenu()
              r.run()
            }}
          >
            <span>{r.label}</span>
            {r.key && <Kbd>{bridge.platform.keys.launcher}</Kbd>}
          </motion.button>
        )
      )}
    </motion.div>
  )
}
