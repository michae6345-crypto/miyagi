/**
 * Building mode: dim the screen and cut a glowing hole around where to work, with a glass caption.
 * The cut-out is ONE animated SVG mask rect: when the target moves it springs to the new spot.
 *
 * Where the rect comes from:
 *   - Browser stage: mapped from line numbers onto the fake desktop (dev/desktop.png).
 *   - Electron: TODO F3 (adrian/spotlight): VS Code window bounds via get-windows + the
 *     vscode-ext line rects. Until then Electron shows the caption only, no dim.
 */
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Volume2 } from 'lucide-react'
import type { SpotlightTarget as SpotlightEvent } from '../store'
import type { Rect } from '../../../main/platform'
import { useLesson } from '../store'
import { color, spring } from '../theme'

/** Line → rect on the 1600×1000 fake desktop (mockup 01: line 1 centers at y=140, 18px per line). */
export function stageRect(sp: SpotlightEvent): Rect {
  const top = (n: number): number => 131 + (n - 1) * 18
  const y = top(sp.startLine) - 9
  return { x: 60, y, width: 690, height: (sp.endLine - sp.startLine + 1) * 18 + 18 }
}

const CAPTION_W = 300

export function Spotlight({ rect, screenW }: { rect?: Rect; screenW: number }): ReactNode {
  const sp = useLesson((s) => s.spotlight)
  const voiceOn = useLesson((s) => s.voiceOn)
  const { index } = useLessonIndex()
  const on = !!sp && !!rect

  const flip = rect ? rect.x + rect.width + 22 + CAPTION_W > screenW - 16 : false
  const capX = rect ? (flip ? rect.x - 22 - CAPTION_W : rect.x + rect.width + 22) : 0
  const capY = rect ? rect.y + 22 : 0

  return (
    <AnimatePresence>
      {on && sp && rect && (
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
                <motion.rect initial={false} animate={{ x: rect.x, y: rect.y, width: rect.width, height: rect.height }} transition={spring} rx={12} fill="#000" />
              </mask>
              <filter id="tut-glow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="6" />
              </filter>
            </defs>
            <rect width="100%" height="100%" fill="rgba(0,0,0,.55)" mask="url(#tut-hole)" />
            {/* Glow ring: pulses once (0.6 → 1 → 0.6 over 1.2s), then stays still. */}
            <motion.g key={`${sp.startLine}-${sp.endLine}`} initial={{ opacity: 0.6 }} animate={{ opacity: [0.6, 1, 0.6] }} transition={{ duration: 1.2 }}>
              <motion.rect initial={false} animate={{ x: rect.x, y: rect.y, width: rect.width, height: rect.height }} transition={spring} rx={12} fill="none" stroke={color.accent} strokeWidth="3" filter="url(#tut-glow)" />
              <motion.rect initial={false} animate={{ x: rect.x, y: rect.y, width: rect.width, height: rect.height }} transition={spring} rx={12} fill="none" stroke="rgba(120,180,255,.9)" strokeWidth="1.2" />
            </motion.g>
          </svg>

          <motion.div
            className="absolute rounded-[18px] border px-[18px] py-[14px]"
            style={{ width: CAPTION_W, background: color.glass, borderColor: color.hairline, boxShadow: '0 20px 60px rgba(0,0,0,.45)', backdropFilter: 'blur(30px) saturate(1.4)' }}
            initial={{ opacity: 0, x: capX + (flip ? 8 : -8), y: capY }}
            animate={{ opacity: 1, x: capX, y: capY }}
            transition={spring}
          >
            <div className="flex items-center gap-[12px]">
              <div className="min-w-0 flex-1">
                <div className="text-[12px] text-white/55">
                  Step {index + 1} · line {sp.endLine}
                </div>
                <div className="mt-[2px] text-[16px] font-semibold leading-[21px]">{sp.caption}</div>
                {sp.code && (
                  <div className="mt-[3px] truncate font-mono text-[13px]" style={{ color: '#6cb2ff' }}>
                    {sp.code}
                  </div>
                )}
              </div>
              <button
                data-hit
                className="pointer-events-auto grid h-[34px] w-[34px] shrink-0 cursor-pointer place-items-center rounded-full"
                style={{ background: voiceOn ? color.accent : 'rgba(10,132,255,.22)', color: voiceOn ? '#fff' : '#6cb2ff' }}
                onClick={() => useLesson.getState().toggleVoice()}
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

function useLessonIndex(): { index: number } {
  const index = useLesson((s) => Math.max(0, s.steps.findIndex((x) => x.id === s.stepId)))
  return { index }
}
