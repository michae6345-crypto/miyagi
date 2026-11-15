/**
 * The "More" tile (layout 'more'): Back, Skip step and End lesson in a small glass menu above the bar, so the bar
 * itself holds only the options and Check. Opens from the tile, closes on a pick, a second click, Esc (dismiss)
 * or a click elsewhere on the overlay. Small shadow (shadows.pill): the panel shadow would dim the Check tile below.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Ellipsis, type LucideIcon } from 'lucide-react'
import { onUi } from '../../core/bus'
import { glass, shadows, spring } from '../../core/theme'
import { GlassKey, look, Tile } from './Tile'

export type MoreItem = { id: string; label: string; icon: LucideIcon; run: () => void; keycap?: string; title?: string }

export function MoreTile({ items, dip }: { items: MoreItem[]; dip?: boolean }): ReactNode {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const off = onUi('dismiss', () => setOpen(false))
    const down = (e: PointerEvent): void => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    addEventListener('pointerdown', down)
    return () => {
      off()
      removeEventListener('pointerdown', down)
    }
  }, [open])

  return (
    <div ref={ref} className="relative">
      <Tile label="More" icon={Ellipsis} look={look.neutral} lit={open} expanded={open} dip={dip} onClick={() => setOpen((o) => !o)} />
      <AnimatePresence>
        {open && (
          <motion.div
            data-hit
            role="menu"
            className="absolute bottom-[calc(100%+18px)] right-0 w-[200px] rounded-[14px] border p-[6px]"
            style={{ background: glass.bg, borderColor: glass.hairline, boxShadow: shadows.pill, backdropFilter: 'blur(30px) saturate(1.4)', originX: 1, originY: 1 }}
            initial={{ opacity: 0, y: 6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.97 }}
            transition={spring}
          >
            {items.map(({ id, label, icon: Icon, run, keycap, title }) => (
              <button
                key={id}
                role="menuitem"
                title={title}
                className="flex h-[34px] w-full cursor-pointer items-center gap-[10px] rounded-[9px] px-[10px] text-left transition-colors duration-150 hover:bg-[var(--glass-field)]"
                onClick={() => {
                  setOpen(false)
                  run()
                }}
              >
                <Icon size={15} strokeWidth={1.8} style={{ color: glass.label }} />
                <span className="flex-1 text-[13.5px]" style={{ color: glass.text }}>
                  {label}
                </span>
                {keycap && <GlassKey text={keycap} />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
