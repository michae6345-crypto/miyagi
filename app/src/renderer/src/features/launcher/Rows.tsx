/**
 * Feature: launcher. The rows of the results list. Every row is ROW_H tall and absolutely placed in
 * its slot, so a skeleton and the result that replaces it crossfade in place (no reflow, no jump).
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { CircleAlert, FileCode2, FileText, Newspaper, SearchX } from 'lucide-react'
import { Thumb } from '../../core/ui/atoms'
import { clock, color, spring } from '../../core/theme'
import type { SearchResult } from './store'
import { thumbnailFor, type YouTubeLink } from './youtube'
import { tint } from './tint'

export const ROW_H = 64

const enter = { opacity: 0, y: 6 }
const shown = { opacity: 1, y: 0 }
const gone = { opacity: 0, transition: { duration: 0.12 } }

type Slot = { slot: number; delay?: number }

function RowShell({ slot, delay = 0, children, onHover, onPick }: Slot & { children: ReactNode; onHover?: () => void; onPick?: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="absolute inset-x-0 flex cursor-pointer items-center gap-[14px] px-[12px] text-left"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={{ ...spring, delay }}
      // Keep the caret in the input: rows are pointer targets, not focus stops.
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onHover}
      onClick={onPick}
    >
      {children}
    </motion.button>
  )
}

function Icon({ kind }: { kind: SearchResult['kind'] }): ReactNode {
  const I = kind === 'notebook' || kind === 'repo' ? FileCode2 : kind === 'paper' ? FileText : Newspaper
  return (
    <span className="grid h-[40px] w-[62px] shrink-0 place-items-center rounded-[8px] text-white/70" style={{ background: tint.icon }}>
      <I size={17} strokeWidth={1.6} />
    </span>
  )
}

function Text({ title, meta }: { title: string; meta: string }): ReactNode {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[15px] font-medium leading-[20px] text-white">{title}</span>
      <span className="block truncate text-[13px] leading-[18px]" style={{ color: color.faint }}>
        {meta}
      </span>
    </span>
  )
}

export function ResultRow({ r, best, ...rest }: Slot & { r: SearchResult; best: boolean; onHover: () => void; onPick: () => void }): ReactNode {
  return (
    <RowShell {...rest}>
      {r.kind === 'video' ? <Thumb w={62} h={40} src={r.thumbnail} /> : <Icon kind={r.kind} />}
      <Text title={r.title} meta={r.meta} />
      <span className="shrink-0 text-[13px]" style={{ color: best ? color.accent : color.faint }}>
        {r.reason}
      </span>
    </RowShell>
  )
}

/** A pasted YouTube link: no search, one row, Enter builds straight from it. */
export function LinkRow({ link, onPick }: { link: YouTubeLink; onPick: () => void }): ReactNode {
  return (
    <RowShell slot={0} onPick={onPick}>
      <Thumb w={62} h={40} src={thumbnailFor(link.videoId)} />
      <Text title="YouTube video" meta={`youtu.be/${link.videoId}${link.start ? ` · from ${clock(link.start)}` : ''}`} />
      <span className="shrink-0 text-[13px]" style={{ color: color.accent }}>
        Build from link
      </span>
    </RowShell>
  )
}

/** Placeholder while results stream in: a soft pulse, staggered per slot. */
export function SkeletonRow({ slot }: { slot: number }): ReactNode {
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[14px] px-[12px]"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={{ opacity: 0 }}
      animate={{ opacity: [0.45, 1, 0.45] }}
      exit={gone}
      transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut', delay: slot * 0.12 }}
    >
      <span className="h-[40px] w-[62px] shrink-0 rounded-[8px]" style={{ background: tint.skeleton }} />
      <span className="flex flex-1 flex-col gap-[8px]">
        <span className="h-[11px] rounded-full" style={{ width: `${54 - slot * 9}%`, background: tint.skeleton }} />
        <span className="h-[9px] rounded-full" style={{ width: `${32 + slot * 5}%`, background: tint.skeleton }} />
      </span>
    </motion.div>
  )
}

/** Empty / error: one quiet row with an icon, a title and a detail line. */
export function MessageRow({ tone, title, detail }: { tone: 'empty' | 'error'; title: string; detail: string }): ReactNode {
  const I = tone === 'error' ? CircleAlert : SearchX
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[14px] px-[12px]"
      style={{ top: 0, height: ROW_H }}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={spring}
    >
      <span className="grid h-[40px] w-[62px] shrink-0 place-items-center rounded-[8px]" style={{ background: tint.icon, color: tone === 'error' ? color.amber : color.label }}>
        <I size={18} strokeWidth={1.6} />
      </span>
      <Text title={title} meta={detail} />
    </motion.div>
  )
}
