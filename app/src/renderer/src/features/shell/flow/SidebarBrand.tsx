/**
 * Feature: shell / flow. The sidebar's logo row (the bonsai and the lowercase wordmark), with the first run's landing
 * choreography: when home arrives from the flow (phase 'leaving' as this row mounts), the bonsai glides in from the
 * step strip (FlowMark, layoutId MARK_ID) while the sidebar slides in under it, and the wordmark writes in beside the
 * tree only once it has landed. So the tree is never drawn over the wordmark: the wordmark is not there yet while the
 * tree crosses its spot and while the sidebar is still catching up (round 5 review, the hand-off glitch).
 * Any other mount (a normal open of home, a page switch, setup again over home): the wordmark is simply there.
 */
import { motion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import { MiyagiWordmark } from '../../../core/ui/Mark'
import { FlowMark } from './FlowMark'
import { wordIn } from './motion'
import { useFlow } from './store'

export function SidebarBrand({ compact }: { compact: boolean }): ReactNode {
  // Read once, at mount: the row is born in the hand-off or it isn't.
  const [landing] = useState(() => {
    const s = useFlow.getState()
    return s.phase === 'leaving' && !s.again
  })
  return (
    <>
      <FlowMark size={compact ? 22 : 20} />
      {!compact && (
        <motion.span data-shell-wordmark className="flex" initial={landing ? { opacity: 0, x: -6 } : false} animate={{ opacity: 1, x: 0 }} transition={wordIn}>
          <MiyagiWordmark height={16} className="h-[16px] w-auto" />
        </motion.span>
      )}
    </>
  )
}
