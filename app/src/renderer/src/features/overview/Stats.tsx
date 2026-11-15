/**
 * The overview footer's "Stats" link (Michael, audit "new asks": Tiger Data track): the engine's live stats page,
 * http://<engine>/stats, opened in the default browser. Electron: src/main/features/overview.ts resolves the engine's
 * http origin from ENGINE_URL. Browser stage: the local engine on :8787.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { ChartColumn } from 'lucide-react'
import { bridge, registerWebHandler } from '../../bridge'
import { color } from '../../core/theme'

const STAGE_STATS = 'http://localhost:8787/stats'

registerWebHandler('overview:open-stats', () => {
  window.open(STAGE_STATS, '_blank', 'noopener,noreferrer')
  return true
})

export function Stats(): ReactNode {
  return (
    <motion.button
      type="button"
      title="Live stats"
      className="flex cursor-pointer items-center gap-[5px]"
      style={{ color: color.label }}
      whileHover={{ color: color.text }}
      transition={{ duration: 0.15 }}
      onClick={() => {
        bridge.invoke('overview:open-stats').catch(() => {})
      }}
    >
      <ChartColumn size={13} strokeWidth={1.8} />
      Stats
    </motion.button>
  )
}
