/**
 * Feature: launcher. The rows of the panel, in the v4 frame's look (Adrian's ui-next mock, Nov 23-24): no boxes, the row
 * radius, hairlines between rows (parts.RowRules), a 14 / 550 name, 13 px meta in the label gray, the mock's 16:9
 * thumbnails, the ink progress bar and the ghost chevron that wakes into the ↵ keycap on the active row.
 *
 * Every row is a fixed height and absolutely placed in its slot, so a skeleton and the result that replaces it crossfade
 * in place (no reflow, no jump) and one highlight can glide between rows.
 *   ROW_H      search rows (a video, "Just teach me", a skeleton, the empty / error row): two lines and room for the
 *              learner line that may arrive later
 *   COVER_H    v4's row with a cover (50): Continue, Plans, Ready to run, the lesson in progress, Settings
 */
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { ChevronRight, CircleAlert, FileCode2, FileText, FolderGit2, Newspaper, SearchX, Settings } from 'lucide-react'
import { useState } from 'react'
import type { PlanState } from '../../../../../../shared/contracts/events'
import { MiyagiMark } from '../../core/ui/Mark'
import { Bar, ProgressRing, Tag } from '../shell/ui'
import { TOOL_NAME } from '../library/parts'
import { artForState } from '../plans/PlanPage'
import { Thumb as ArtThumb } from '../plans/Thumb'
import { Thumb } from '../../core/ui/atoms'
import { clock, color, fill, spring, tone, v4, v4c, v4type } from '../../core/theme'
import { artOfItem } from './art'
import { toolsLabel, type LibraryItem } from './library'
import { navKey } from './keys'
import { HOW_LABEL, NavKey, PRESS } from './parts'
import { planLine } from './plans'
import type { SearchResult } from './store'
import { thumbnailFor, type YouTubeLink } from './youtube'
import { alpha, kindTone } from './tint'
import { ease, fade, prefersReduced, sizeMove, springOut } from '../../core/ui/motion'

/** A search row: a 16:9 tile, two lines and the learner line under them (fixed, so a late learner line moves nothing). */
export const ROW_H = 58
/** v4's row with a cover: Continue, Plans, Ready to run, Settings. */
export const COVER_H = v4.row.cover
/** A search row's tile: 16:9, the v4 row radius. */
const TILE_W = 64
const TILE_H = 36
/** A cover row's thumbnail: the Library's rows (56 × 32). */
const ART_W = 56
const ART_H = 32
/** The progress bar on a Continue or plan row (the mock's Home plan rows). */
const BAR_W = 64
/** Room for the longest count ("12 of 12"). */
const COUNT_W = 50

const enter = { opacity: 0, y: 6 }
const shown = { opacity: 1, y: 0 }
const gone = { opacity: 0, transition: fade.out }

type Slot = { slot: number; delay?: number }

/** One row: a button in its slot, v4's padding and radius. Hover tints come from the list's one highlight. */
function RowShell({ slot, delay = 0, h = ROW_H, children, onHover, onPick, data }: Slot & { h?: number; children: ReactNode; onHover?: () => void; onPick?: () => void; data?: Record<string, string> }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className="absolute inset-x-0 flex cursor-pointer items-center gap-[12px] text-left"
      style={{ top: slot * h, height: h, padding: `0 ${v4.row.padX}px`, borderRadius: v4.radius.row, color: color.text }}
      initial={enter}
      animate={shown}
      exit={gone}
      whileTap={PRESS}
      transition={{ ...spring, delay }}
      // A click keeps the caret in the input; Tab still reaches the row (Launcher's Tab order, Q15) and moves the highlight.
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onHover}
      onFocus={onHover}
      onClick={onPick}
      {...data}
    >
      {children}
    </motion.button>
  )
}

/** A neutral 16:9 tile with a glyph (the lesson row, Settings, the empty / error row): the mock's `.th` on the fill wash. */
function GlyphTile({ children, w = TILE_W, h = TILE_H, glyph = color.label }: { children: ReactNode; w?: number; h?: number; glyph?: string }): ReactNode {
  return (
    <span
      className="grid shrink-0 place-items-center"
      style={{ width: w, height: h, borderRadius: v4.radius.row, background: v4c.fill2, boxShadow: `inset 0 0 0 1px ${v4c.hair}`, color: glyph }}
    >
      {children}
    </span>
  )
}

/** 64×36: the video's thumbnail, or a neutral tile with the source kind's glyph. */
function Tile({ kind, thumbnail }: Pick<SearchResult, 'kind' | 'thumbnail'>): ReactNode {
  if (kind === 'video') return <Thumb w={TILE_W} h={TILE_H} src={thumbnail} />
  const I = kind === 'repo' ? FolderGit2 : kind === 'notebook' ? FileCode2 : kind === 'paper' ? FileText : Newspaper
  const t = kindTone[kind]
  if (!t)
    return (
      <GlyphTile>
        <I size={15} strokeWidth={1.7} />
      </GlyphTile>
    )
  return (
    <span className="grid shrink-0 place-items-center" style={{ width: TILE_W, height: TILE_H, borderRadius: v4.radius.row, background: alpha(t, 0.16), color: t }}>
      <I size={15} strokeWidth={1.7} />
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

/** A row's name and meta: v4's row name (14 / 550 ink) over its meta (13, the label gray). */
function Text({ title, meta, extra, checked = false, warnings }: { title: string; meta: string; extra?: string; checked?: boolean; warnings?: string[] }): ReactNode {
  const quote = warnings?.find((w) => w.trim())?.replace(/\s+/g, ' ').trim()
  const more = (warnings?.length ?? 0) - 1
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate" style={{ ...v4type.row, color: color.text }}>
        {title}
      </span>
      <span className="flex min-w-0" style={{ ...v4type.meta, color: color.label }}>
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

/** The progress bar and its count ("3 of 8"), as on Home's plan rows and the Library's progress column. */
function Progress({ value, count }: { value: number; count: string }): ReactNode {
  return (
    <span className="flex shrink-0 items-center gap-[10px]">
      <Bar value={value} width={BAR_W} label={count} />
      {/* A fixed width, so the bars of rows above each other line up ("3 of 8" over "1 of 10"). */}
      <span className="whitespace-nowrap" style={{ ...v4type.meta, minWidth: COUNT_W, color: color.label }}>
        {count}
      </span>
    </span>
  )
}

export function ResultRow({ r, best, ...rest }: Slot & { r: SearchResult; best: boolean; onHover: () => void; onPick: () => void }): ReactNode {
  return (
    <RowShell {...rest}>
      <Tile kind={r.kind} thumbnail={r.thumbnail} />
      <Text title={r.title} meta={r.meta} extra={metaSegment(r)} checked={r.verified === true} warnings={r.warnings} />
      {best && (
        <span className="shrink-0" style={{ ...v4type.meta, fontWeight: 550, color: tone.pink.fg }}>
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
      <GlyphTile>
        <MiyagiMark size={16} />
      </GlyphTile>
      <Text title={HOW_LABEL.lesson} meta="A lesson built from the internet, no video" />
    </RowShell>
  )
}

/**
 * During a lesson with nothing typed, the only row (highlighted, under "Continue"): back to the lesson where it was.
 * Enter, or a click, closes the launcher into the island, so the lesson is one key away and never restarted by
 * accident. Ending the lesson is not a row (desktop test 3, item 8): it's the quiet two-tap link in the footer (parts
 * EndLink). v4: the lesson-in-progress ring (the sidebar's Recent), the lesson's title, where you are, and the ↵.
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
    <RowShell slot={0} h={COVER_H} onHover={onHover} onPick={onPick} data={{ 'data-resume': '' }}>
      <span className="grid shrink-0 place-items-center" style={{ width: 20 }}>
        <ProgressRing size={16} />
      </span>
      <Text title={lessonTitle ?? 'The lesson in progress'} meta={where} />
      <EnterCue active={active} label="Continue" />
    </RowShell>
  )
}

/**
 * The end of a row that opens something: v4's ghost chevron at rest, the Enter keycap on the idle list's active line
 * (and on a Continue line the word, "Continue ↵"). They crossfade as ↑↓ move, so the cue sits on the line Enter runs.
 */
function EnterCue({ active, label }: { active: boolean; label?: string }): ReactNode {
  return (
    <span className="relative flex shrink-0 items-center justify-end" style={{ minWidth: 20 }} aria-hidden>
      <motion.span className="flex items-center gap-[7px]" initial={false} animate={{ opacity: active ? 1 : 0 }} transition={fade.tint}>
        {label && (
          <span className="text-[12.5px]" style={{ fontWeight: 550, color: color.text }}>
            {label}
          </span>
        )}
        <NavKey>{navKey('enter')}</NavKey>
      </motion.span>
      <motion.span
        className="absolute right-0 top-1/2 flex -translate-y-1/2 items-center"
        style={{ color: v4c.ghost }}
        initial={false}
        animate={{ opacity: active ? 0 : 1 }}
        transition={fade.tint}
      >
        <ChevronRight size={14} strokeWidth={1.8} />
      </motion.span>
    </span>
  )
}

/** Typing a settings word ("sett", "keys", "pref", "appear"…): the one way into Settings from the launcher. */
export function SettingsRow({ onPick }: { onPick: () => void }): ReactNode {
  return (
    <RowShell slot={0} h={COVER_H} onPick={onPick} data={{ 'data-settings-row': '' }}>
      <GlyphTile w={ART_W} h={ART_H}>
        <Settings size={15} strokeWidth={1.7} />
      </GlyphTile>
      <Text title="Settings" meta="Keys and appearance" />
      <EnterCue active />
    </RowShell>
  )
}

/** The link preview's height: a 128×72 thumbnail with room around it. */
export const LINK_H = 92

/**
 * A pasted YouTube link (Home-Launcher "From your link"): no search, one clear preview, already the active row (the
 * selected-row wash) since it is the only thing Enter can do. A 16:9 thumbnail with the start time from the link (?t=),
 * what it is, where it starts, and one line saying what Enter does. When a cached lesson was built from this exact video,
 * the preview says so ("Already a lesson", a "Ready instantly" tag) and Enter starts it with library.start: zero model
 * calls, nothing built twice. The thumbnail scales in from 0.96 on the house spring; a thumbnail that can't load (no
 * network) falls back to the neutral generated one, never a broken image. v4: the mock's home-link preview (thumbnail,
 * a 15 / 600 title, 13 px meta), on the selected-row wash with the control radius.
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
      className="relative flex w-full cursor-pointer items-center gap-[16px] text-left"
      style={{ height: LINK_H, padding: `0 ${v4.row.padX + 4}px 0 ${v4.row.padX + 2}px`, borderRadius: v4.radius.control, background: v4c.active, color: color.text }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      whileTap={PRESS}
      transition={{ y: spring, opacity: fade.in }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onPick}
    >
      <motion.span className="relative shrink-0" initial={reduce ? false : { scale: 0.96 }} animate={{ scale: 1 }} transition={spring}>
        <Thumb w={128} h={72} src={src} time={link.start ? clock(link.start) : undefined} />
        {/* Probe the thumbnail once: if it can't load, show the generated tile instead of a broken image. */}
        {src && <img src={src} alt="" className="hidden" onError={() => setBroken(true)} />}
      </motion.span>
      <span className="min-w-0 flex-1">
        <span className="block" style={{ ...v4type.sec, color: color.label }}>
          {match ? 'Already a lesson' : 'YouTube video'}
        </span>
        <span className="mt-[3px] block truncate" style={{ fontSize: 15, lineHeight: '20px', fontWeight: 600, letterSpacing: '-0.005em', color: color.text }}>
          {match ? match.title : where}
        </span>
        <span className="mt-[2px] block truncate" style={{ ...v4type.meta, color: color.label }}>
          {match ? `${match.steps} steps${tools ? ` in ${tools}` : ''}. Starts right away.` : 'Builds a lesson that pauses at each step'}
        </span>
      </span>
      {match && <Tag tone="out">Ready instantly</Tag>}
      <NavKey>{navKey('enter')}</NavKey>
    </motion.button>
  )
}

/**
 * Home-Launcher "Continue": a cached lesson started on this Mac and not finished, drawn like the Library's In progress
 * row: its picture, the title over where it was left ("Step 3 · Drop the empty rows"), the ink bar with "2 of 6". Click
 * (or ↵ on the active line) to pick it up (library.start). Its own slot range: never shared with the search rows.
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
    <RowShell slot={slot} h={COVER_H} onHover={onHover} onPick={onPick} data={{ 'data-continue': item.id }}>
      <ArtThumb art={artOfItem(item)} w={ART_W} h={ART_H} radius={v4.radius.row} />
      <Text title={item.title} meta={p ? `Step ${p.stepIndex + 1}${p.stepTitle ? ` · ${p.stepTitle}` : ''}` : `${item.steps} steps`} />
      {p && p.total > 0 && <Progress value={p.stepIndex / p.total} count={`${p.stepIndex} of ${p.total}`} />}
      <EnterCue active={active} label="Continue" />
    </RowShell>
  )
}

/**
 * v4 "Plans" (Home's plan rows, Adrian's ui-next mock): one of the learner's plans still going. Its picture (the
 * Library's plan art), the plan's name over "Next · <lesson>", the ink bar with "3 of 8". Click (or ↵ on the active
 * line) starts that next lesson (plans/store startNext).
 */
export function PlanRow({
  plan,
  slot,
  active = false,
  started,
  onHover,
  onPick
}: {
  plan: PlanState
  slot: number
  active?: boolean
  /** The plan has begun: the cue says Continue, else Start. */
  started: boolean
  onHover: () => void
  onPick: () => void
}): ReactNode {
  const line = planLine(plan)
  return (
    <RowShell slot={slot} h={COVER_H} onHover={onHover} onPick={onPick} data={{ 'data-plan': plan.id }}>
      <ArtThumb art={artForState(plan)} w={ART_W} h={ART_H} radius={v4.radius.row} />
      <Text title={plan.title} meta={line.next ? `Next · ${line.next}` : `${plan.total} lessons`} />
      <Progress value={line.value} count={line.count} />
      <EnterCue active={active} label={started ? 'Continue' : 'Start'} />
    </RowShell>
  )
}

/**
 * Home-LauncherInContext "Ready to run": a cached lesson, built and never started, drawn like the Library's Ready row:
 * its picture, the title, and on the right where it runs, its steps and minutes. A cover row in its own slot range
 * (COVER_H), apart from the search rows and the Continue rows.
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
  /** Its own hover wash (click-only rows during a lesson); with keys, the list's moving highlight shows it instead. */
  hover?: boolean
  onHover: () => void
  onPick: () => void
}): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      data-ready={item.id}
      className="absolute inset-x-0 flex cursor-pointer items-center gap-[12px] text-left"
      style={{ top: slot * COVER_H, height: COVER_H, padding: `0 ${v4.row.padX}px`, borderRadius: v4.radius.row, backgroundColor: fill.clear, color: color.text }}
      whileHover={hover ? { backgroundColor: v4c.hover } : undefined}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={spring}
      onMouseDown={(e) => e.preventDefault()}
      onMouseMove={onHover}
      onFocus={onHover}
      onClick={onPick}
    >
      <ArtThumb art={artOfItem(item)} w={ART_W} h={ART_H} radius={v4.radius.row} />
      <span className="min-w-0 flex-1 truncate" style={{ ...v4type.row, color: color.text }}>
        {item.title}
      </span>
      <span className="shrink-0 truncate" style={{ ...v4type.meta, color: color.label }}>
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
      className="absolute inset-x-0 flex items-center gap-[12px]"
      style={{ top: slot * ROW_H, height: ROW_H, padding: `0 ${v4.row.padX}px` }}
      initial={{ opacity: 0 }}
      animate={{ opacity: [0.5, 1, 0.5] }}
      exit={gone}
      transition={{ duration: 1.4, repeat: Infinity, ease: ease.inOut, delay: slot * 0.12 }}
    >
      <span className="shrink-0" style={{ width: TILE_W, height: TILE_H, borderRadius: v4.radius.row, background: v4c.fill2 }} />
      <span className="flex flex-1 flex-col gap-[8px]">
        <span className="h-[10px] rounded-full" style={{ width: `${52 - slot * 9}%`, background: v4c.fill2 }} />
        <span className="h-[8px] rounded-full" style={{ width: `${30 + slot * 6}%`, background: v4c.fill2 }} />
      </span>
    </motion.div>
  )
}

/** Empty / error: one quiet row with an icon, a title and a detail line. */
export function MessageRow({ tone: kind, title, detail, slot = 0 }: { tone: 'empty' | 'error'; title: string; detail: string; slot?: number }): ReactNode {
  const I = kind === 'error' ? CircleAlert : SearchX
  return (
    <motion.div
      className="absolute inset-x-0 flex items-center gap-[12px]"
      style={{ top: slot * ROW_H, height: ROW_H, padding: `0 ${v4.row.padX}px` }}
      initial={enter}
      animate={shown}
      exit={gone}
      transition={spring}
    >
      <GlyphTile glyph={kind === 'error' ? color.text : color.label}>
        <I size={16} strokeWidth={1.7} />
      </GlyphTile>
      <Text title={title} meta={detail} />
    </motion.div>
  )
}
