/**
 * Feature: drawer. The live network, in the drawer's right-hand panel (Michael, Sun 1:55 AM: the demo is "build a
 * neural network"). When the engine pushes a `network` diagram with real weights for the current step (the forward
 * pass starting, a training run, the stuck-loss off-track), it shows here, under the header, and redraws in place as
 * new ones arrive: never as a card over the code. In train mode the epoch and loss sit right under it.
 *
 * It stays out of the scrolling list so it's on screen while the learner types, and it folds to one row with its
 * chevron. "Full size" is the same as ⌃⌥D: the island's full diagram.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import { ChevronDown, Maximize2 } from 'lucide-react'
import { emitUi } from '../../core/bus'
import { glass, spring } from '../../core/theme'
import { NeuralNet } from '../diagrams/NeuralNet'
import { useLiveNetwork } from '../diagrams/store'
import { titleOf } from '../diagrams/Tabs'

export function LiveNetSection(): ReactNode {
  const d = useLiveNetwork()
  const [folded, setFolded] = useState(false)
  if (!d) return null
  const data = d.data as Record<string, unknown>
  const mode = (data.mode as string) ?? 'forward'
  const title = titleOf(d)
  return (
    <div data-part="drawer-live-net" className="shrink-0 border-b px-[18px] pb-[10px]" style={{ borderColor: glass.rule }}>
      <div className="flex items-center gap-[8px] py-[6px]">
        <button
          type="button"
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-[6px] text-left text-[12px] font-semibold leading-[16px]"
          style={{ color: glass.label }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => setFolded((f) => !f)}
          aria-expanded={!folded}
        >
          <motion.span animate={{ rotate: folded ? -90 : 0 }} transition={spring} className="grid shrink-0 place-items-center">
            <ChevronDown size={13} strokeWidth={2.2} />
          </motion.span>
          <span className="truncate">{title || 'Network'}</span>
          <span className="shrink-0 font-normal" style={{ color: glass.faint }}>
            {mode === 'train' ? 'training' : mode === 'backward' ? 'backprop' : 'forward pass'}
          </span>
        </button>
        <button
          type="button"
          className="grid h-[22px] w-[22px] shrink-0 cursor-pointer place-items-center rounded-full"
          style={{ background: glass.key, color: glass.keyText }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => emitUi('shortcut', 'diagram')}
          aria-label="Full size"
          title="Full size"
        >
          <Maximize2 size={11} strokeWidth={2.2} />
        </button>
      </div>
      <AnimatePresence initial={false}>
        {!folded && (
          <motion.div
            key="net"
            className="overflow-hidden"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={spring}
          >
            <NeuralNet data={data} compact />
            {d.caption && (
              <div className="mt-[6px] line-clamp-2 text-[12.5px] leading-[17px]" style={{ color: glass.label }}>
                {d.caption}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
