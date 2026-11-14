/** The overview footer's gear: opens Settings (the settings feature owns `settings:open`; until it lands, the call fails quietly). */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Settings } from 'lucide-react'
import { bridge } from '../../bridge'
import { color } from '../../core/theme'

export function Gear(): ReactNode {
  return (
    <motion.button
      type="button"
      aria-label="Settings"
      title="Settings"
      className="-mr-[4px] grid h-[22px] w-[22px] cursor-pointer place-items-center rounded-full"
      style={{ color: color.label }}
      whileHover={{ color: color.text }}
      transition={{ duration: 0.15 }}
      onClick={() => {
        bridge.invoke('settings:open').catch(() => {})
      }}
    >
      <Settings size={14} strokeWidth={1.8} />
    </motion.button>
  )
}
