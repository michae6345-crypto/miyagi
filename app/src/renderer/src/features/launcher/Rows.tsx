/**
 * Feature: launcher. The rows of the results list. Every row is ROW_H tall and absolutely placed in
 * its slot, so a skeleton and the result that replaces it crossfade in place (no reflow, no jump).
 */
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { CircleAlert, CirclePlay, FileCode2, FileText, FolderGit2, Newspaper, SearchX, Settings } from 'lucide-react'
import { MiyagiMark } from '../../core/ui/Mark'
import { Thumb } from '../../core/ui/atoms'
import { brand, clock, color, fill, spring } from '../../core/theme'
import { HOW_LABEL } from './parts'
import type { SearchResult } from './store'
import { thumbnailFor, type YouTubeLink } from './youtube'
import { alpha, kindTone } from './tint'

/** Fixed, so a row that gains a learner line later never moves its neighbours or the highlight. */
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
      className="absolute inset-x-0 flex cursor-pointer items-center gap-[14px] px-[10px] text-left"
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

/** 60×38: the video's thumbnail, or a neutral tile with the source kind's glyph. */
function Tile({ kind, thumbnail }: Pick<SearchResult, 'kind' | 'thumbnail'>): ReactNode {
  if (kind === 'video') return <Thumb w={60} h={38} src={thumbnail} />
  const I = kind === 'repo' ? FolderGit2 : kind === 'notebook' ? FileCode2 : kind === 'paper' ? FileText : Newspaper
  const tone = kindTone[kind]
  return (
    <span
      className="grid h-[38px] w-[60px] shrink-0 place-items-center rounded-[8px]"
      style={tone ? { background: alpha(tone, 0.16), color: tone } : { background: fill.tile, color: fill.tileGlyph }}
    >
      <I size={16} strokeWidth={1.6} />
    </span>
  )
}

/**
 * At most ONE extra meta segment per row (≤12 words of chrome): a non-coding style first (it changes what the lab
 * can check), else the duration of a long video. Nothing for an ordinary coding tutorial.
 */
export function metaSegment(r: SearchResult): string | undefined {
  if (r.style === 'no-code') return 'No-code'
  if (r.style === 'conceptual') return 'Conceptual'
  if (r.long && r.durationLabel) return r.durationLabel
}

function Text({ title, meta, extra, checked = false, warnings }: { title: string; meta: string; extra?: string; checked?: boolean; warnings?: string[] }): ReactNode {
  const quote = warnings?.find((w) => w.trim())?.replace(/\s+/g, ' ').trim()
  const more = (warnings?.length ?? 0) - 1
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[14px] font-medium leading-[18px] text-white">{title}</span>
      <span className="flex min-w-0 text-[12.5px] leading-[17px]" style={{ color: color.faint }}>
        <span className="truncate">{meta}</span>
        {extra && <span className="shrink-0 whitespace-pre">{` · ${extra}`}</span>}
        {/* The engine opened this link itself (oEmbed / HTTP / API). Gray: green only means passed. */}
        {checked && (
          <motion.span className="shrink-0 whitespace-pre" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
            {' · Link checked'}
          </motion.span>
        )}
      </span>
      {/* What other learners said, quoted as-is (the engine's filter can misfire, so never our own verdict). It may
          arrive after the row: the line grows in and the row keeps its slot. */}
      <AnimatePresence initial={false}>
        {quote && (
          <motion.span
            key="learner"
            className="flex min-w-0 overflow-hidden text-[12px] leading-[16px]"
            style={{ color: color.faint }}
            title={warnings?.join('\n\n')}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 16, opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={spring}
          >
            <span className="truncate">A learner said: “{quote}”</span>
            {more > 0 && <span className="shrink-0 whitespace-pre">{` · +${more} more`}</span>}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  )
}

export function ResultRow({ r, best, ...rest }: Slot & { r: SearchResult; best: boolean; onHover: () => void; onPick: () => void }): ReactNode {
  return (
    <RowShell {...rest}>
      <Tile kind={r.kind} thumbnail={r.thumbnail} />
      <Text title={r.title} meta={r.meta} extra={metaSegment(r)} checked={r.verified === true} warnings={r.warnings} />
      {best && (
        <span className="shrink-0 text-[12.5px] font-medium" style={{ color: brand.pastel.pink }}>
          Best
        </span>
      )}
    </RowShell>
  )
}

/**
 * The fixed first row of every search: a text lesson Claude researches from the web for what's typed (learn mode
 * "lesson"), no video. A neutral tile with the bonsai: it's Miyagi's own option, not a source kind.
 * Titled like the chip and the footer (review A18: one name for one action everywhere).
 */
export function LessonRow({ onHover, onPick }: { onHover: () => void; onPick: () => void }): ReactNode {
  return (
    <RowShell slot={0} onHover={onHover} onPick={onPick}>
      <span className="grid h-[38px] w-[60px] shrink-0 place-items-center rounded-[8px]" style={{ background: fill.tile }}>
        <MiyagiMark size={18} />
      </span>
      <Text title={HOW_LABEL.lesson} meta="A lesson built from the internet, no video" />
    </RowShell>
  )
}

/**
 * During a lesson with nothing typed, the only row (highlighted): back to the lesson where it was. Enter, or a click,
 * closes the launcher into the island, so the lesson is one key away and never restarted by accident. Ending the
 * lesson is not a row (desktop test 3, item 8): it's the quiet two-tap link in the footer (parts EndLink).
 */
export function ResumeRow({ lessonTitle, where, onPick }: { lessonTitle?: string; where: string; onPick: () => void }): ReactNode {
  return (
    <RowShell slot={0} onPick={onPick}>
      <span className="grid h-[38px] w-[60px] shrink-0 place-items-center rounded-[8px]" style={{ background: fill.tile, color: fill.tileGlyph }}>
        <CirclePlay size={16} strokeWidth={1.6} />
      </span>
      <Text title={lessonTitle ? `Continue ${lessonTitle}` : 'Continue the lesson'} meta={where} />
    </RowShell>
  )
}

/** Typing a settings word ("sett", "keys", "pref", "appear"…): the one way into Settings from the launcher. */
export function SettingsRow({ onPick }: { onPick: () => void }): ReactNode {
  return (
    <RowShell slot={0} onPick={onPick}>
      <span className="grid h-[38px] w-[60px] shrink-0 place-items-center rounded-[8px]" style={{ background: fill.tile, color: fill.tileGlyph }}>
        <Settings size={16} strokeWidth={1.6} />
      </span>
      <Text title="Settings" meta="Keys and appearance" />
    </RowShell>
  )
}

/** A pasted YouTube link: no search, one row, Enter builds straight from it. */
export function LinkRow({ link, onPick }: { link: YouTubeLink; onPick: () => void }): ReactNode {
  return (
    <RowShell slot={0} onPick={onPick}>
      <Tile kind="video" thumbnail={thumbnailFor(link.videoId)} />
      <Text title="YouTube video" meta={`youtu.be/${link.videoId}${link.start ? ` · from ${clock(link.start)}` : ''}`} />
    </RowShell>
  )
}

/** Placeholder while results stream in: a soft pulse, staggered per slot. */
export function SkeletonRow({ slot }: { slot: number }): ReactNode {
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[14px] px-[10px]"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={{ opacity: 0 }}
      animate={{ opacity: [0.5, 1, 0.5] }}
      exit={gone}
      transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut', delay: slot * 0.12 }}
    >
      <span className="h-[38px] w-[60px] shrink-0 rounded-[8px]" style={{ background: fill.skeleton }} />
      <span className="flex flex-1 flex-col gap-[8px]">
        <span className="h-[10px] rounded-full" style={{ width: `${52 - slot * 9}%`, background: fill.skeleton }} />
        <span className="h-[8px] rounded-full" style={{ width: `${30 + slot * 6}%`, background: fill.skeleton }} />
      </span>
    </motion.div>
  )
}

/** Empty / error: one quiet row with an icon, a title and a detail line. */
export function MessageRow({ tone, title, detail, slot = 0 }: { tone: 'empty' | 'error'; title: string; detail: string; slot?: number }): ReactNode {
  const I = tone === 'error' ? CircleAlert : SearchX
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[14px] px-[10px]"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={spring}
    >
      <span
        className="grid h-[38px] w-[60px] shrink-0 place-items-center rounded-[8px]"
        style={{ background: fill.tile, color: tone === 'error' ? color.text : fill.tileGlyph }}
      >
        <I size={17} strokeWidth={1.6} />
      </span>
      <Text title={title} meta={detail} />
    </motion.div>
  )
}
