/**
 * The Dynamic-Island container. ONE black object that morphs between whatever island modes
 * features register (core/registry.ts → islandModes). The highest-priority active mode wins.
 * Width, height and radius animate together on the spring; content crossfades
 * (old out in 80ms, new in after 60ms, rising 4px). The window never resizes.
 *
 * Owner: core. Features add modes; they don't edit this file.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { bridge } from '../bridge'
import { startBuild, useLesson } from './lesson'
import { islandModes } from './registry'
import { color, pill, spring, springOut } from './theme'

export function Island({ top }: { top: number }): ReactNode {
  const [hover, setHover] = useState(false)
  const [landing, setLanding] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const passFlash = useLesson((s) => s.passFlash)

  // Ask every registered mode whether it wants the island. (Stable array → stable hook order.)
  const wanted = islandModes.map((m) => m.useActive(hover))
  const mode = islandModes.find((_, i) => wanted[i])
  const isPill = !mode || mode.width === undefined

  // The launcher just shrank onto our exact pixels: appear at its size, then spring to ours.
  useEffect(
    () =>
      bridge.on('pill:receive', () => {
        startBuild()
        setLanding(true)
        requestAnimationFrame(() => requestAnimationFrame(() => setLanding(false)))
      }),
    []
  )

  // Measure whichever layer is active; the container springs to its size.
  const [active, setActive] = useState<HTMLDivElement | null>(null)
  const bindActive = useCallback((el: HTMLDivElement | null) => {
    if (el) setActive(el)
  }, [])
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 120, h: pill.height })
  useLayoutEffect(() => {
    if (!active) return
    const measure = (): void => {
      const fixed = mode?.width
      setSize({ w: fixed ?? Math.ceil(active.offsetWidth), h: fixed ? Math.ceil(active.offsetHeight) : pill.height })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(active)
    return () => ro.disconnect()
  }, [active, mode])

  const enter = (): void => {
    clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(() => setHover(true), 150)
  }
  const leave = (): void => {
    clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(() => setHover(false), 300)
  }

  if (!mode) return null
  const { Content } = mode

  return (
    <div className="pointer-events-none absolute inset-x-0 flex justify-center" style={{ top }}>
      <motion.div
        data-hit
        className="pointer-events-auto relative overflow-hidden text-white"
        style={{
          background: color.island,
          boxShadow: isPill ? '0 2px 10px rgba(0,0,0,.25)' : '0 24px 60px rgba(0,0,0,.5)',
          transformOrigin: '50% 0%'
        }}
        initial={false}
        animate={{
          width: landing ? pill.landingWidth : size.w,
          height: landing ? pill.height : size.h,
          borderRadius: isPill ? pill.height / 2 : 24
        }}
        transition={landing ? { duration: 0 } : isPill ? springOut : spring}
        onMouseEnter={enter}
        onMouseLeave={leave}
      >
        {/* Step passed: the island flashes green (tint 0 → .25 → 0 over 600ms). */}
        <motion.div
          key={passFlash}
          className="pointer-events-none absolute inset-0"
          style={{ background: color.green }}
          initial={{ opacity: 0 }}
          animate={{ opacity: passFlash ? [0, 0.25, 0] : 0 }}
          transition={{ duration: 0.6, ease: 'easeInOut' }}
        />
        <AnimatePresence initial={false}>
          <motion.div
            key={mode.id}
            ref={bindActive}
            className="absolute left-1/2 top-0"
            style={{ x: '-50%', width: mode.width ?? 'max-content' }}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.2, delay: 0.06, ease: 'easeOut' } }}
            exit={{ opacity: 0, transition: { duration: 0.08 } }}
          >
            <Content />
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  )
}
