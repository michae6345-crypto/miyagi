/**
 * Building mode, screen-first: the engine's screen reader (Apple Vision OCR) finds the target on
 * screen and sends `spotlight {rect, caption}` in screen POINTS. We dim everything and cut a glowing,
 * rounded hole at that rect, with a glass caption beside it. Works over any app.
 * The cut-out is ONE animated SVG mask rect: when the target moves it springs to the new spot.
 */
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Volume2 } from 'lucide-react'
import { useLesson, type Rect } from '../../core/lesson'
import { color, spring } from '../../core/theme'
import { toggleVoice, useVoice } from '../voice/store'
import { useSpotlight } from './store'

const CAPTION_W = 300
/** Breathing room around the OCR'd text block. */
const PAD = 8

/** rect: the target in THIS window's coordinates (already offset by the window's screen origin). */
export function Spotlight({ rect, screenW }: { rect?: Rect; screenW: number }): ReactNode {
  const sp = useSpotlight((s) => s.target)
  const voiceOn = useVoice((s) => s.on)
  const index = useLesson((s) => Math.max(0, s.steps.findIndex((x) => x.id === s.stepId)))
  const r = rect && { x: rect.x - PAD, y: rect.y - PAD, w: rect.w + PAD * 2, h: rect.h + PAD * 2 }

  // Caption to the right of the target, top-aligned; flips left at the screen edge.
  const flip = r ? r.x + r.w + 22 + CAPTION_W > screenW - 16 : false
  const capX = r ? (flip ? Math.max(16, r.x - 22 - CAPTION_W) : r.x + r.w + 22) : 0
  const capY = r ? r.y + Math.min(22, r.h / 4) : 0

  return (
    <AnimatePresence>
      {sp && r && (
        <motion.div
          key="dim"
          className="pointer-events-none absolute inset-0"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28 }}
        >
          <svg className="absolute inset-0 h-full w-full">
            <defs>
              <mask id="tut-hole">
                <rect width="100%" height="100%" fill="#fff" />
                <motion.rect initial={false} animate={{ x: r.x, y: r.y, width: r.w, height: r.h }} transition={spring} rx={12} fill="#000" />
              </mask>
              <filter id="tut-glow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="6" />
              </filter>
            </defs>
            <rect width="100%" height="100%" fill="rgba(0,0,0,.55)" mask="url(#tut-hole)" />
            {/* Glow ring: pulses once (0.6 → 1 → 0.6 over 1.2s), then stays still. */}
            <motion.g key={`${rect.x},${rect.y},${rect.w},${rect.h}`} initial={{ opacity: 0.6 }} animate={{ opacity: [0.6, 1, 0.6] }} transition={{ duration: 1.2 }}>
              <motion.rect initial={false} animate={{ x: r.x, y: r.y, width: r.w, height: r.h }} transition={spring} rx={12} fill="none" stroke={color.accent} strokeWidth="3" filter="url(#tut-glow)" />
              <motion.rect initial={false} animate={{ x: r.x, y: r.y, width: r.w, height: r.h }} transition={spring} rx={12} fill="none" stroke="rgba(120,180,255,.9)" strokeWidth="1.2" />
            </motion.g>
          </svg>

          <motion.div
            data-ui
            className="absolute rounded-[18px] border px-[18px] py-[14px]"
            style={{ width: CAPTION_W, background: color.glass, borderColor: color.hairline, boxShadow: '0 20px 60px rgba(0,0,0,.45)', backdropFilter: 'blur(30px) saturate(1.4)' }}
            initial={{ opacity: 0, x: capX + (flip ? 8 : -8), y: capY }}
            animate={{ opacity: 1, x: capX, y: capY }}
            transition={spring}
          >
            <div className="flex items-center gap-[12px]">
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12px] text-white/55">
                  Step {index + 1}
                  {sp.app ? ` · ${sp.app}` : ''}
                </div>
                <div className="mt-[2px] text-[16px] font-semibold leading-[21px]">{sp.caption}</div>
                {(sp.code ?? sp.matched) && (
                  <div className="mt-[3px] truncate font-mono text-[13px]" style={{ color: '#6cb2ff' }}>
                    {sp.code ?? sp.matched}
                  </div>
                )}
              </div>
              <button
                data-hit
                className="pointer-events-auto grid h-[34px] w-[34px] shrink-0 cursor-pointer place-items-center rounded-full"
                style={{ background: voiceOn ? color.accent : 'rgba(10,132,255,.22)', color: voiceOn ? '#fff' : '#6cb2ff' }}
                onClick={toggleVoice}
                aria-label="Voice"
              >
                <Volume2 size={16} />
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
