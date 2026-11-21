/**
 * Feature: shell / flow. The bonsai as a shared element (layoutId MARK_ID): the same tree travels from the intro to
 * the login header, to the strip's step indicator, and lands as the sidebar's logo. Only one is mounted at a time;
 * motion glides the new one from where the last one was (reduced motion: it simply appears, the views crossfade).
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { spring } from '../../../core/theme'
import { MiyagiMark } from '../../../core/ui/Mark'
import { MARK_ID } from './motion'

export function FlowMark({ size, className }: { size: number; className?: string }): ReactNode {
  return (
    <motion.span data-flow-mark layoutId={MARK_ID} className={`relative block shrink-0 ${className ?? ''}`} style={{ width: size, height: size }} transition={{ layout: spring }}>
      <MiyagiMark size={size} />
    </motion.span>
  )
}
