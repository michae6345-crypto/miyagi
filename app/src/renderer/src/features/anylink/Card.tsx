/**
 * Any link: how a page looks in the app (ANY-LINK.md).
 *
 *   SourceTile    a page's picture: its kind's pastel wash (theme.kindTone: blog for a web page, repo for a GitHub
 *                 repo) with the kind's glyph. Never an image from the site (no favicon, no og:image, no pixel).
 *   LinkCard      the launcher's "From your link" card for a page: kind and site, the title, about how long and where
 *                 it runs, or one calm line on why miyagi can't teach it. The footer's primary says what Enter does
 *                 (link.pageAction); a click on the card does the same.
 *   NotchLinkCard the same answer, compact, for a link dropped on the notch: its own Build lesson button.
 *   SourceLink    "From docs.python.org": the page as a row that opens it in the browser (Library detail, lesson panel).
 *
 * v4 look: Bricolage on v4's ramp, the selected-row wash for the active card, neutral chrome, one primary.
 */
import { motion, useReducedMotion } from 'motion/react'
import { ArrowUpRight, FolderGit2, Globe, X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { LinkPreview } from '../../../../../../shared/contracts/events'
import { PrimaryButton, Spinner } from '../../core/ui/atoms'
import { color, fill, kindTone, radius2, spring, type2, v4, v4c, v4type } from '../../core/theme'
import { fade } from '../../core/ui/motion'
import { TOOL_NAME } from '../library/parts'
import { Tag } from '../shell/ui'
import { NavKey, PRESS } from '../launcher/parts'
import { navKey } from '../launcher/keys'
import { alpha } from '../launcher/tint'
import { KIND_LABEL, lookupLine, minutesText, pageAction, type WebKind, type WebLink } from './link'

export const SOURCE_ICON: Record<WebKind, typeof Globe> = { web: Globe, github: FolderGit2 }
const TONE: Record<WebKind, string> = { web: kindTone.blog, github: kindTone.repo }

/** A page's tile: its kind's 16% pastel wash with the glyph in the pastel (a source kind, never a status). */
export function SourceTile({ kind, w, h, radius = v4.radius.row, glyph }: { kind: WebKind; w: number; h: number; radius?: number; glyph?: number }): ReactNode {
  const I = SOURCE_ICON[kind]
  return (
    <span aria-hidden data-source-tile={kind} className="grid shrink-0 place-items-center" style={{ width: w, height: h, borderRadius: radius, background: alpha(TONE[kind], 0.16), color: TONE[kind] }}>
      <I size={glyph ?? Math.round(Math.min(w, h) * 0.44)} strokeWidth={1.7} />
    </span>
  )
}

/** A page with no title yet (or one that can't be read): where the link goes, "example.org/members/advanced-pandas". */
function shownLink(url: string): string {
  try {
    const u = new URL(url)
    const path = u.pathname.replace(/\/$/, '')
    return `${u.hostname.replace(/^www\./, '')}${path}`
  } catch {
    return url
  }
}

/** "Web page · docs.python.org". */
const kicker = (kind: WebKind, site: string): string => `${KIND_LABEL[kind]} · ${site}`

/** The page's kind as the engine says it (web / github), else the app's guess from the link. */
const kindFrom = (link: WebLink, p?: LinkPreview): WebKind => (p?.kind === 'github' || p?.kind === 'web' ? p.kind : link.kind)

/** "About 10 min · Terminal · by Pallets". */
function metaLine(p: LinkPreview): string {
  const tools = (p.tools ?? []).map((t) => TOOL_NAME[t]).filter(Boolean)
  return [minutesText(p.estMinutes), tools.length ? tools.join(' and ') : undefined, p.author ? `by ${p.author}` : undefined].filter(Boolean).join(' · ')
}

/** What the card's third line says: the reason it can't be read or taught, the minutes, or that it's still reading. */
function useLine(p: LinkPreview | undefined): { text: string; state: 'reading' | 'ok' | 'cannot' } {
  if (p?.error) return { text: lookupLine(p.error), state: 'cannot' }
  if (!p || p.teachable === undefined) return { text: 'Reading the page…', state: 'reading' }
  if (!p.teachable) return { text: `miyagi can’t teach this page. ${p.why ?? 'There’s nothing to do or type.'}`, state: 'cannot' }
  return { text: metaLine(p) || p.why || 'Steps to follow, checked as you go', state: 'ok' }
}

export const LINK_CARD_MIN = 92

/**
 * The launcher's card for a pasted page. Already the active row (the selected-row wash): it is the only thing Enter
 * does. Its third line is the calm verdict; the footer's primary (Build lesson, Start lesson, Just teach me) acts.
 */
export function LinkCard({ link, preview, onPick, teachLabel }: { link: WebLink; preview?: LinkPreview; onPick: () => void; teachLabel: string }): ReactNode {
  const reduce = useReducedMotion()
  const kind = kindFrom(link, preview)
  const site = preview?.site ?? link.site
  const line = useLine(preview)
  const act = pageAction(preview, teachLabel)
  const live = act.kind === 'build' || act.kind === 'teach'
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      data-link-card={kind}
      data-link-state={line.state}
      aria-label={`${preview?.title ?? shownLink(link.url)}. ${line.text}`}
      className="relative flex w-full items-center gap-[16px] text-left"
      style={{ minHeight: LINK_CARD_MIN, padding: `10px ${v4.row.padX + 4}px 10px ${v4.row.padX + 2}px`, borderRadius: v4.radius.control, background: v4c.active, color: color.text, cursor: live ? 'pointer' : 'default' }}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      whileTap={live ? PRESS : undefined}
      transition={{ y: spring, opacity: fade.in }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => live && onPick()}
    >
      <motion.span className="shrink-0" initial={reduce ? false : { scale: 0.96 }} animate={{ scale: 1 }} transition={spring}>
        <SourceTile kind={kind} w={128} h={72} radius={v4.radius.control} glyph={24} />
      </motion.span>
      <span className="min-w-0 flex-1">
        <span className="block truncate" style={{ ...v4type.sec, color: color.label }}>
          {kicker(kind, site)}
        </span>
        <span className="mt-[3px] block truncate" style={{ fontSize: 15, lineHeight: '20px', fontWeight: 600, letterSpacing: '-0.005em', color: color.text }}>
          {preview?.title ?? shownLink(link.url)}
        </span>
        <motion.span
          key={line.state}
          data-link-line
          className="mt-[2px] flex min-w-0 items-start gap-[6px]"
          style={{ ...v4type.meta, color: color.label }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={fade.in}
        >
          {line.state === 'reading' && (
            <span className="pt-[2px]">
              <Spinner size={13} c={color.label} />
            </span>
          )}
          <span className={line.state === 'cannot' ? 'line-clamp-2' : 'truncate'}>{line.text}</span>
        </motion.span>
      </span>
      {act.kind === 'build' && preview?.cached && <Tag tone="out">Ready instantly</Tag>}
      {live && <NavKey>{navKey('enter')}</NavKey>}
    </motion.button>
  )
}

/**
 * The notch's compact card for a dropped page (notch-home's left half, in place of Continue): kind and site, the
 * title on two lines, the verdict line, and its own one primary. `onGo` runs the action; `onClose` puts Continue back.
 */
export function NotchLinkCard({ link, preview, onGo, onClose, sent }: { link: WebLink; preview?: LinkPreview; onGo: () => void; onClose: () => void; sent?: boolean }): ReactNode {
  const kind = kindFrom(link, preview)
  const site = preview?.site ?? link.site
  const line = useLine(preview)
  const act = pageAction(preview)
  return (
    <div data-notch-link={kind} data-link-state={line.state} className="flex h-full flex-col justify-between">
      <div className="flex gap-[12px]">
        <SourceTile kind={kind} w={63} h={63} radius={10} glyph={22} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-[6px]">
            <div className="min-w-0 flex-1 truncate text-[11px] font-medium" style={{ color: color.label }}>
              {kicker(kind, site)}
            </div>
            <button
              type="button"
              aria-label="Not this link"
              className="grid h-[20px] w-[20px] shrink-0 cursor-pointer place-items-center rounded-full"
              style={{ color: color.label, background: fill.chip }}
              onMouseDown={(e) => e.preventDefault()}
              onClick={onClose}
            >
              <X size={11} strokeWidth={2} />
            </button>
          </div>
          <div className="mt-[2px] line-clamp-2 text-[14px] font-semibold leading-[18px]" style={{ color: color.text }}>
            {preview?.title ?? shownLink(link.url)}
          </div>
          <div data-link-line className="mt-[3px] flex items-start gap-[6px] text-[12px] leading-[16px]" style={{ color: color.label }}>
            {line.state === 'reading' && <Spinner size={12} c={color.label} />}
            <span className="line-clamp-2">{line.text}</span>
          </div>
        </div>
      </div>
      <div className="mt-[8px] flex">
        {act.kind === 'build' || act.kind === 'teach' ? (
          <PrimaryButton label={sent ? 'Starting…' : act.label} disabled={sent} onClick={onGo} />
        ) : act.kind === 'wait' ? (
          <PrimaryButton label="Build lesson" disabled onClick={() => undefined} />
        ) : null}
      </div>
    </div>
  )
}

/**
 * The page a lesson was built from, as a row: its tile, "The original page" / "The repo on GitHub", the site (and who
 * wrote it), and the ↗ that says it opens in the browser. `compact`: the lesson panel's narrower row.
 */
export function SourceLink({ kind, url, site, author, heading, onOpen, compact = false }: { kind: WebKind; url: string; site?: string; author?: string; heading?: string; onOpen: (url: string) => void; compact?: boolean }): ReactNode {
  // Compact (the lesson panel, under "From <site>"): the step's part of the page by its heading, else the page.
  const name = heading ? (compact ? heading : `Open “${heading}”`) : kind === 'github' ? 'The repo on GitHub' : 'The original page'
  const where = compact && heading ? 'This step’s part of the page' : [site, author ? `by ${author}` : undefined].filter(Boolean).join(' · ')
  return (
    <button
      type="button"
      data-source-link={kind}
      aria-label={`${name}${site ? ` on ${site}` : ''}, opens in your browser`}
      onClick={() => onOpen(url)}
      className="mg-press flex w-full cursor-pointer items-center text-left outline-offset-2 transition-colors hover:bg-[var(--s-row-hover)] focus-visible:outline-2 focus-visible:outline-solid"
      style={{ gap: compact ? 12 : 16, padding: compact ? 6 : 8, borderRadius: radius2.card, boxShadow: `inset 0 0 0 1px ${v4c.hair2}`, outlineColor: color.text }}
    >
      <SourceTile kind={kind} w={compact ? 40 : 64} h={compact ? 40 : 48} radius={radius2.control} />
      <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
        <span className="truncate" style={{ fontSize: compact ? type2.sm : type2.md, lineHeight: '20px', fontWeight: 550, color: color.text }}>
          {name}
        </span>
        <span className="truncate" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
          {compact ? where || 'Opens in your browser' : where ? `${where} · opens in your browser` : 'Opens in your browser'}
        </span>
      </span>
      <ArrowUpRight aria-hidden size={16} strokeWidth={1.8} className="shrink-0" style={{ color: color.label, marginRight: compact ? 4 : 8 }} />
    </button>
  )
}
