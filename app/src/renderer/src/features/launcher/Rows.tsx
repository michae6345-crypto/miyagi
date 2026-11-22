/**
 * Feature: launcher. The rows of the results list. Every row is ROW_H tall and absolutely placed in
 * its slot, so a skeleton and the result that replaces it crossfade in place (no reflow, no jump).
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { CircleAlert, FileCode2, FileText, FolderGit2, Newspaper, SearchX, Settings } from 'lucide-react'
import { useState } from 'react'
import { MiyagiMark } from '../../core/ui/Mark'
import { StepBar } from '../shell/ui'
import { TOOL_NAME } from '../library/parts'
import { Thumb } from '../../core/ui/atoms'
import { clock, color, fill, font, spring, tone } from '../../core/theme'
import { toolsLabel, type LibraryItem } from './library'
import { navKey } from './keys'
import { HOW_LABEL, NavKey, PRESS } from './parts'
import type { SearchResult } from './store'
import { thumbnailFor, type YouTubeLink } from './youtube'
import { alpha, kindTone } from './tint'
import { ease, fade, prefersReduced, sizeMove, springOut } from '../../core/ui/motion'

/** Fixed, so a row that gains a learner line later never moves its neighbours or the highlight. */
export const ROW_H = 64
/** Home-Launcher's tile: 64×40, radius 8. */
const TILE_W = 64
const TILE_H = 40
/** A "Ready to run" row (Home-LauncherInContext): one line, 44 high. */
export const READY_H = 44

const enter = { opacity: 0, y: 6 }
const shown = { opacity: 1, y: 0 }
const gone = { opacity: 0, transition: fade.out }

type Slot = { slot: number; delay?: number }

function RowShell({ slot, delay = 0, children, onHover, onPick }: Slot & { children: ReactNode; onHover?: () => void; onPick?: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="absolute inset-x-0 flex cursor-pointer items-center gap-[16px] px-[16px] text-left"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={enter}
      animate={shown}
      exit={gone}
      whileTap={PRESS}
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

/** 64×40 (Home-Launcher): the video's thumbnail, or a neutral tile with the source kind's glyph. */
function Tile({ kind, thumbnail }: Pick<SearchResult, 'kind' | 'thumbnail'>): ReactNode {
  if (kind === 'video') return <Thumb w={TILE_W} h={TILE_H} src={thumbnail} />
  const I = kind === 'repo' ? FolderGit2 : kind === 'notebook' ? FileCode2 : kind === 'paper' ? FileText : Newspaper
  const tone = kindTone[kind]
  return (
    <span
      className="grid h-[40px] w-[64px] shrink-0 place-items-center rounded-[8px]"
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
          <motion.span className="shrink-0 whitespace-pre" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={fade.in}>
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
            exit={{ height: 0, opacity: 0, transition: { ...sizeMove(prefersReduced(), springOut), opacity: fade.out } }}
            transition={{ ...sizeMove(prefersReduced()), opacity: fade.in }}
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
        <span className="shrink-0 text-[12.5px] font-medium" style={{ color: tone.pink.fg }}>
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
      <span className="grid h-[40px] w-[64px] shrink-0 place-items-center rounded-[8px]" style={{ background: fill.tile }}>
        <MiyagiMark size={18} />
      </span>
      <Text title={HOW_LABEL.lesson} meta="A lesson built from the internet, no video" />
    </RowShell>
  )
}

/**
 * During a lesson with nothing typed, the only row (highlighted, under "Continue"): back to the lesson where it was.
 * Enter, or a click, closes the launcher into the island, so the lesson is one key away and never restarted by
 * accident. Ending the lesson is not a row (desktop test 3, item 8): it's the quiet two-tap link in the footer (parts
 * EndLink). Home-LauncherInContext: no tile, the lesson's title, where you are, and the ↵ it answers to.
 */
export function ResumeRow({
  lessonTitle,
  where,
  active = true,
  onHover,
  onPick
}: {
  lessonTitle?: string
  where: string
  /** The idle list's active line: it shows the Enter keycap. */
  active?: boolean
  onHover?: () => void
  onPick: () => void
}): ReactNode {
  return (
    <RowShell slot={0} onHover={onHover} onPick={onPick}>
      <Text title={lessonTitle ?? 'The lesson in progress'} meta={where} />
      <EnterCue active={active} />
    </RowShell>
  )
}

/**
 * The idle list's active line shows what Enter does there: the Enter keycap, and on a Continue line the word
 * ("Continue ↵"). It fades in and out as ↑↓ move, so the cue sits on the line Enter runs.
 */
function EnterCue({ active, label }: { active: boolean; label?: string }): ReactNode {
  return (
    <motion.span className="flex shrink-0 items-center gap-[6px]" initial={false} animate={{ opacity: active ? 1 : 0 }} transition={fade.tint} aria-hidden>
      {label && (
        <span className="text-[12px] font-medium" style={{ color: color.text }}>
          {label}
        </span>
      )}
      <NavKey>{navKey('enter')}</NavKey>
    </motion.span>
  )
}

/** Typing a settings word ("sett", "keys", "pref", "appear"…): the one way into Settings from the launcher. */
export function SettingsRow({ onPick }: { onPick: () => void }): ReactNode {
  return (
    <RowShell slot={0} onPick={onPick}>
      <span className="grid h-[40px] w-[64px] shrink-0 place-items-center rounded-[8px]" style={{ background: fill.tile, color: fill.tileGlyph }}>
        <Settings size={16} strokeWidth={1.6} />
      </span>
      <Text title="Settings" meta="Keys and appearance" />
    </RowShell>
  )
}

/** The link preview's height: a 128×72 thumbnail with room around it. */
export const LINK_H = 92

/**
 * A pasted YouTube link (Home-Launcher "From your link"): no search, one clear preview, already the active row (the
 * hover tint) since it is the only thing Enter can do. A 16:9 thumbnail with the start time from the link (?t=), what
 * it is, where it starts, and one line saying what Enter does. When a cached lesson was built from this exact video,
 * the preview says so ("Already a lesson", "Ready instantly") and Enter starts it with library.start: zero model
 * calls, nothing built twice. The thumbnail scales in from 0.96 on the house spring; a thumbnail that can't load (no
 * network) falls back to the neutral generated one, never a broken image.
 */
export function LinkPreview({ link, match, onPick }: { link: YouTubeLink; match?: LibraryItem; onPick: () => void }): ReactNode {
  const tools = toolsLabel(match?.tools)
  const reduce = useReducedMotion()
  const [broken, setBroken] = useState(false)
  const src = broken ? undefined : thumbnailFor(link.videoId)
  const where = `youtu.be/${link.videoId}${link.start ? ` · starts at ${clock(link.start)}` : ''}`
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      data-link-preview={link.videoId}
      className="relative flex w-full cursor-pointer items-center gap-[16px] rounded-[12px] px-[16px] text-left"
      style={{ height: LINK_H, background: fill.highlight }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      whileTap={PRESS}
      transition={{ y: spring, opacity: fade.in }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onPick}
    >
      <motion.span
        className="relative shrink-0"
        initial={reduce ? false : { scale: 0.96 }}
        animate={{ scale: 1 }}
        transition={spring}
      >
        <Thumb w={128} h={72} src={src} time={link.start ? clock(link.start) : undefined} />
        {/* Probe the thumbnail once: if it can't load, show the generated tile instead of a broken image. */}
        {src && <img src={src} alt="" className="hidden" onError={() => setBroken(true)} />}
      </motion.span>
      <span className="min-w-0 flex-1">
        <span className="block text-[12px] leading-[16px]" style={{ color: color.label }}>
          {match ? 'Already a lesson' : 'YouTube video'}
        </span>
        <span className="mt-[2px] block truncate text-[15px] font-medium leading-[20px] text-white">{match ? match.title : where}</span>
        <span className="mt-[2px] block truncate text-[12.5px] leading-[17px]" style={{ color: color.faint }}>
          {match
            ? `${match.steps} steps${tools ? ` in ${tools}` : ''}. Starts right away.`
            : 'Builds a lesson that pauses at each step'}
        </span>
      </span>
      {match && (
        <span
          className="inline-flex h-[24px] shrink-0 items-center rounded-full px-[8px] text-[12px]"
          style={{ boxShadow: `inset 0 0 0 1px ${fill.hairline}`, color: fill.keycapText }}
        >
          Ready instantly
        </span>
      )}
      <NavKey>{navKey('enter')}</NavKey>
    </motion.button>
  )
}

/** Two letters for the tool a cached lesson runs in (Home-Launcher's "Jn" tile). */

/**
 * Home-Launcher "Continue": a cached lesson started on this Mac and not finished. Its tool's tag, the title, where it
 * was left ("Step 3 of 6 · Drop the empty rows") and a white meter. Click to pick it up (library.start). Its own slot
 * range: these rows never share slots with the search rows.
 */
export function LibraryContinueRow({
  item,
  slot,
  active = false,
  onHover,
  onPick
}: {
  item: LibraryItem
  slot: number
  /** The idle list's active line: it shows the Enter keycap. */
  active?: boolean
  onHover: () => void
  onPick: () => void
}): ReactNode {
  const p = item.progress
  return (
    <RowShell slot={slot} onHover={onHover} onPick={onPick}>
      <Text title={item.title} meta={p ? `Step ${p.stepIndex + 1} of ${p.total}${p.stepTitle ? ` · ${p.stepTitle}` : ''}` : `${item.steps} steps`} />
      {p && <StepBar done={p.stepIndex} total={p.total} width={84} />}
      <EnterCue active={active} label="Continue" />
    </RowShell>
  )
}

/**
 * Home-LauncherInContext "Ready to run": a cached lesson, built and never started. One line: the title and its step
 * count. 44 high, in its own slot range (READY_H), apart from the search rows and the Continue rows.
 */
export function ReadyRow({
  item,
  slot,
  hover = false,
  active = false,
  onHover,
  onPick
}: {
  item: LibraryItem
  slot: number
  /** The idle list's active line: it shows the Enter keycap. */
  active?: boolean
  /** Its own hover fill (click-only rows during a lesson); with keys, the list's moving highlight shows it instead. */
  hover?: boolean
  onHover: () => void
  onPick: () => void
}): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      data-ready={item.id}
      className="absolute inset-x-0 flex cursor-pointer items-center gap-[16px] rounded-[12px] px-[16px] text-left"
      style={{ top: slot * READY_H, height: READY_H, backgroundColor: fill.clear }}
      whileHover={hover ? { backgroundColor: fill.highlight } : undefined}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={spring}
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onHover}
      onClick={onPick}
    >
      <span className="min-w-0 flex-1 truncate text-[14px] text-white">{item.title}</span>
      <span className="shrink-0 text-[12px]" style={{ color: color.label }}>
        {[(item.tools ?? []).map((t) => TOOL_NAME[t]).join(', '), item.steps === 1 ? '1 step' : `${item.steps} steps`, item.estMinutes ? `${item.estMinutes} min` : ''].filter(Boolean).join(' · ')}
      </span>
      <EnterCue active={active} />
    </motion.button>
  )
}

/** Placeholder while results stream in: a soft pulse, staggered per slot. */
export function SkeletonRow({ slot }: { slot: number }): ReactNode {
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[16px] px-[16px]"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={{ opacity: 0 }}
      animate={{ opacity: [0.5, 1, 0.5] }}
      exit={gone}
      transition={{ duration: 1.4, repeat: Infinity, ease: ease.inOut, delay: slot * 0.12 }}
    >
      <span className="h-[40px] w-[64px] shrink-0 rounded-[8px]" style={{ background: fill.skeleton }} />
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
      className="absolute inset-x-0 flex items-center gap-[16px] px-[16px]"
      style={{ top: slot * ROW_H, height: ROW_H }}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={spring}
    >
      <span
        className="grid h-[40px] w-[64px] shrink-0 place-items-center rounded-[8px]"
        style={{ background: fill.tile, color: tone === 'error' ? color.text : fill.tileGlyph }}
      >
        <I size={17} strokeWidth={1.6} />
      </span>
      <Text title={title} meta={detail} />
    </motion.div>
  )
}
