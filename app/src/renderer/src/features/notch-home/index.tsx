/**
 * Feature: notch-home. In the notch (layout.notch.place 'notch'), hovering the island with no lesson on screen opens a
 * Boring-Notch-size panel grown down from the notch (Michael, Nov 22: "almost as big as boring notch ... show Continue
 * Lesson"). Left: the lesson to pick up (the engine's saved offer, else the most recent unfinished lesson), with one
 * white Continue. Right: ask miyagi, a drop zone for a link (drag a YouTube link onto the notch to build a lesson; with
 * the engine's "link.any", any page: an article, a docs page or a GitHub repo, ANY-LINK.md), and lessons ready to run.
 * Footer: the library, and bon in its own slot. A dropped page first shows its preview card on the left (anylink/Card
 * NotchLinkCard: what it is, about how long, or why miyagi can't teach it) with its own Build lesson; the ✕ puts
 * Continue back. Column widths, spacing and the progress segments come from ./layout.ts (MIC-89).
 * During a lesson the overview card (priority 20) is the hover card; below the menu bar nothing changes.
 */
import { motion } from 'motion/react'
import { useEffect, useState, type DragEvent, type ReactNode } from 'react'
import { create } from 'zustand'
import { ArrowUpRight, Link2, Play } from 'lucide-react'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { useKey } from '../../core/keys'
import { noteLearnMode, useLesson } from '../../core/lesson'
import { notchOf } from '../../core/notchGeometry'
import { useNotchInfo } from '../../core/notchInfo'
import type { PanelKind } from '../../core/islandTone'
import { defineFeature } from '../../core/registry'
import { openLibrary } from '../../core/surfaces'
import { Kbd, PrimaryButton, Thumb } from '../../core/ui/atoms'
import { MiyagiMark } from '../../core/ui/Mark'
import { PokeBon } from '../buddy/Poke'
import { color, copy, fill } from '../../core/theme'
import { librarySections, refreshLibrary, startLibraryLesson, useLibrary, type LibraryItem } from '../launcher/library'
import { parseYouTube, thumbnailFor } from '../launcher/youtube'
import { resumeSaved, usePill } from '../pill/store'
import { NotchLinkCard } from '../anylink/Card'
import { pageAction, parseWebLink } from '../anylink/link'
import { askLink, dropLink, useAnyLink, useLinkAny, usePreview } from '../anylink/store'
import { homeTone } from './tone'
import { HOME, HOME_W, dropLabel, homeColumns, progressSegs } from './layout'

export { HOME_W }

/** The columns' widths (./layout.ts): fixed, so no line in the left half can push past the divider (MIC-89). */
const COLS = homeColumns()

/** Open on hover in the notch, with the engine connected and no lesson step or build on screen. */
function useHomeActive(hover: boolean): boolean {
  const inNotch = useNotchInfo((s) => !!notchOf({ notch: s.notch }))
  const idle = useLesson((s) => s.connected && !s.stepId && !s.building)
  const planning = usePill((s) => s.planning)
  return hover && inNotch && idle && !planning
}

type Pick = { title: string; meta?: string; n?: number; total?: number; thumb?: string; go: () => void }

/** What Continue picks up: the engine's saved lesson first (its resume), else the newest unfinished library lesson. */
function usePick(): Pick | undefined {
  const offer = usePill((s) => s.offer)
  const items = useLibrary((s) => s.items)
  if (offer?.title || offer?.n) {
    const match = items.find((i) => offer.title && i.title === offer.title)
    return {
      title: offer.title ?? 'Your lesson',
      meta: offer.n && offer.total ? `Step ${offer.n} of ${offer.total}` : undefined,
      n: offer.n,
      total: offer.total,
      thumb: thumbOf(match),
      go: resumeSaved
    }
  }
  const cont = librarySections(items).cont[0]
  if (!cont?.progress) return undefined
  return {
    title: cont.title,
    meta: `Step ${cont.progress.stepIndex + 1} of ${cont.progress.total} · ${cont.progress.stepTitle}`,
    n: cont.progress.stepIndex + 1,
    total: cont.progress.total,
    thumb: thumbOf(cont),
    go: () => void startLibraryLesson(cont.id)
  }
}

function thumbOf(item: LibraryItem | undefined): string | undefined {
  const url = item?.source?.kind === 'youtube' ? item.source.url : undefined
  const yt = url ? parseYouTube(url) : null
  return yt ? thumbnailFor(yt.videoId) : undefined
}

/** Thin segments across the left column only: done white, the step you're on gray, the rest a dim track. */
function Progress({ n, total }: { n: number; total: number }): ReactNode {
  return (
    <div data-home-progress className="flex w-full gap-[3px]" aria-hidden>
      {progressSegs(n, total).map((seg, i) => (
        <div key={i} className="h-[3px] min-w-0 flex-1 rounded-full" style={{ background: seg === 'done' ? color.text : seg === 'at' ? color.gray : fill.track }} />
      ))}
    </div>
  )
}

/** The Continue thumbnail: the video's frame, else the bonsai on a tile of the same 16:9 size, so the text always starts at one x. */
function PickThumb({ src }: { src?: string }): ReactNode {
  const { w, h } = HOME.thumb
  return (
    <div data-home-thumb className="shrink-0">
      {src ? (
        <Thumb w={w} h={h} src={src} />
      ) : (
        <div className="flex items-center justify-center rounded-[8px]" style={{ width: w, height: h, background: fill.tile }}>
          <MiyagiMark size={26} />
        </div>
      )}
    </div>
  )
}

function ContinueCard({ pick }: { pick: Pick | undefined }): ReactNode {
  const launcherKey = useKey('launcher') ?? '' // live: the learner's own key when they rebound it
  const resuming = usePill((s) => s.resuming)
  if (!pick)
    return (
      <div className="flex h-full min-w-0 flex-col justify-between gap-[12px]">
        <div className="min-w-0">
          <div className="text-[15px] font-semibold leading-[20px]" style={{ color: color.text }}>
            Learn anything by doing.
          </div>
          <div className="mt-[4px] text-[13px] leading-[18px]" style={{ color: color.label }}>
            Ask for a topic or drop in a link.
          </div>
        </div>
        <div className="flex" data-home-continue>
          <PrimaryButton label="Start a lesson" kbd={launcherKey} onClick={() => bridge.emit('launcher:toggle')} />
        </div>
      </div>
    )
  // Three groups spaced evenly down the column (MIC-89): the title block, the progress, Continue lesson. The title is two
  // lines at most beside the thumbnail and the step line one line under both; each ends in … with its full text as a tooltip.
  return (
    <div className="flex h-full min-w-0 flex-col justify-between gap-[12px]">
      <div className="min-w-0">
        <div className="flex min-w-0 items-start" style={{ gap: HOME.thumbGap }}>
          <PickThumb src={pick.thumb} />
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-medium uppercase leading-[14px] tracking-[.06em]" style={{ color: color.label }}>
              Continue
            </div>
            <div data-home-title title={pick.title} className="mt-[2px] line-clamp-2 break-words text-[14px] font-semibold leading-[18px]" style={{ color: color.text }}>
              {pick.title}
            </div>
          </div>
        </div>
        {pick.meta && (
          <div title={pick.meta} className="mt-[8px] truncate text-[12px] leading-[16px]" style={{ color: color.label }}>
            {pick.meta}
          </div>
        )}
      </div>
      {pick.n && pick.total ? <Progress n={pick.n} total={pick.total} /> : null}
      <div className="flex" data-home-continue>
        <PrimaryButton label={resuming ? 'Opening…' : 'Continue lesson'} icon={Play} disabled={resuming} onClick={pick.go} />
      </div>
    </div>
  )
}

/** A quiet row on the right: neutral chrome, never a pastel. */
function Row({ children, onClick, title, fit = false }: { children: ReactNode; onClick: () => void; title?: string; fit?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      title={title}
      className={`flex ${fit ? 'w-auto' : 'w-full min-w-0'} shrink-0 cursor-pointer items-center gap-[8px] rounded-[8px] px-[8px] text-left text-[13px]`}
      style={{ color: color.text, height: HOME.row }}
      whileHover={{ backgroundColor: fill.chipHover }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {children}
    </motion.button>
  )
}

/**
 * A dropped page's card (left half): link.get answers into it; Build lesson sends learn_url, or "Just teach me" on its
 * title when the page has nothing to practice. Once sent, the building pill takes over (the panel closes on build).
 */
function DroppedLink({ url }: { url: string }): ReactNode {
  const link = parseWebLink(url)
  const preview = usePreview(url)
  const [sent, setSent] = useState(false)
  if (!link) return null
  const go = (): void => {
    const act = pageAction(preview)
    if (act.kind === 'build') {
      noteLearnMode(undefined)
      bridge.send(cmd('learn_url', { url: link.url }))
    } else if (act.kind === 'teach') {
      noteLearnMode('lesson')
      bridge.send(cmd('learn', { query: act.goal, mode: 'lesson' }))
    } else return
    // The card stays (Starting…) until the build begins: the store clears the drop on lesson.building.
    setSent(true)
  }
  return <NotchLinkCard link={link} preview={preview} sent={sent} onGo={go} onClose={() => dropLink(undefined)} />
}

/** How long "Only YouTube links work here" stays after a drop that isn't one. */
const MISS_MS = 2600
/** A drop that wasn't a link miyagi can read is being said (a store, so the panel's tone can read it). */
const useMiss = create<{ miss: boolean }>(() => ({ miss: false }))
const setMiss = (miss: boolean): void => useMiss.setState({ miss })

/** The panel's tone for the island: calm, or 'warning' while it says a link can't be used (./tone.ts). */
function useHomeTone(): PanelKind {
  const dropped = useAnyLink((s) => s.dropped)
  const preview = usePreview(dropped)
  const miss = useMiss((s) => s.miss)
  return homeTone({ dropped, preview, miss })
}

/**
 * Drag a link onto the notch: a YouTube video builds at once; a page (with link.any) shows its preview card first. A
 * click opens the launcher to paste one.
 */
function DropZone(): ReactNode {
  const linkAny = useLinkAny()
  const [over, setOver] = useState(false)
  const [sent, setSent] = useState(false)
  // A drop that isn't a YouTube link says so for a moment, then the zone reads as before (QA Q05).
  const miss = useMiss((s) => s.miss)
  useEffect(() => {
    if (!miss) return
    const t = setTimeout(() => setMiss(false), MISS_MS)
    return () => clearTimeout(t)
  }, [miss])
  // Closing the panel ends the message: it never comes back with the next hover.
  useEffect(() => () => setMiss(false), [])
  const linkOf = (e: DragEvent): string | undefined => {
    const raw = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain')
    const url = raw.split(/\s+/).find((s) => /^https?:\/\//.test(s))
    return url && (parseYouTube(url) || (linkAny && parseWebLink(url))) ? url : undefined
  }
  return (
    <div
      role="button"
      tabIndex={-1}
      data-drop-link
      className="flex w-full min-w-0 shrink-0 cursor-pointer items-center gap-[8px] rounded-[10px] px-[8px] text-[12px]"
      style={{ height: HOME.drop, border: `1px dashed ${over ? color.text : fill.rule}`, color: over ? color.text : color.label, background: over ? fill.chip : 'transparent' }}
      onClick={() => bridge.emit('launcher:toggle')}
      onDragOver={(e) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'copy'
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const url = linkOf(e)
        if (!url) return setMiss(true)
        setMiss(false)
        if (!parseYouTube(url) && askLink(url)) return dropLink(url)
        bridge.send(cmd('learn_url', { url }))
        setSent(true)
      }}
    >
      <Link2 size={14} strokeWidth={1.8} className="shrink-0" />
      <span className="truncate" aria-live="polite">
        {dropLabel({ sent, miss, linkAny })}
      </span>
    </div>
  )
}

function Home(): ReactNode {
  const launcherKey = useKey('launcher') ?? '' // live: the learner's own key when they rebound it
  const pick = usePick()
  const dropped = useAnyLink((s) => s.dropped)
  const items = useLibrary((s) => s.items)
  const ready = librarySections(items, pick?.title).ready.slice(0, HOME.ready)
  // Fresh lessons each time the panel opens (cheap: the engine answers from its cache).
  useEffect(() => refreshLibrary(), [])
  return (
    <div className="flex flex-col" data-notch-home style={{ width: HOME_W, padding: `${HOME.padTop}px ${HOME.padX}px ${HOME.padBottom}px` }}>
      {/* Two fixed columns (./layout.ts, MIC-89), so nothing in the left half can push past the divider. Both stretch to
          one height: at least HOME.minBody and as tall as the right column needs (a fixed 136 squeezed its rows, MIC-83).
          The left half is a one-track grid so its card's h-full still fills it; the track is minmax(0, 1fr), because an
          auto track grew to its widest nowrap line and ran the step line and the progress under the right column.
          Focus order: Continue lesson, ask miyagi, the ready lessons, Library, bon. */}
      <div className="flex items-stretch" style={{ minHeight: HOME.minBody, gap: HOME.gutter }}>
        <div data-home-left className="grid shrink-0" style={{ width: COLS.left, gridTemplateColumns: 'minmax(0, 1fr)' }}>
          {dropped ? <DroppedLink url={dropped} /> : <ContinueCard pick={pick} />}
        </div>
        <div data-home-rule className="shrink-0" style={{ width: HOME.rule, background: fill.rule }} />
        <div data-home-right className="flex min-w-0 shrink-0 flex-col" style={{ width: COLS.right, gap: HOME.rowGap }}>
          <Row onClick={() => bridge.emit('launcher:toggle')} title={copy.ask}>
            <MiyagiMark size={14} />
            <span className="min-w-0 flex-1 truncate">{copy.ask}</span>
            {/* One keycap per action (QA Q06): with no lesson to continue, Start a lesson already shows it. */}
            {pick && <Kbd className="shrink-0">{launcherKey}</Kbd>}
          </Row>
          <DropZone />
          {/* Each title uses the column's full width, then … with the whole name as a tooltip. */}
          {ready.map((r) => (
            <Row key={r.id} onClick={() => void startLibraryLesson(r.id)} title={r.title}>
              <Play size={12} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />
              <span className="min-w-0 flex-1 truncate">{r.title}</span>
            </Row>
          ))}
          <div className="flex-1" style={{ minHeight: HOME.footGap - HOME.rowGap }} />
          {/* The footer shares Continue lesson's bottom line. Library is a link its own width; bon has its own slot at the
              end, clear of it (tap bon and it plays: features/buddy Poke.tsx; Michael, Nov 24). */}
          <div className="flex shrink-0 items-center" style={{ height: HOME.row, gap: HOME.bonGap }}>
            <div data-home-library className="min-w-0">
              <Row onClick={() => void openLibrary()} fit>
                <span style={{ color: color.label }}>Library</span>
                <ArrowUpRight size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />
              </Row>
            </div>
            <div className="flex-1" />
            <div data-home-bon className="flex shrink-0 items-center justify-center" style={{ width: HOME.row, height: HOME.row }}>
              <PokeBon size={HOME.bon} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default defineFeature({
  id: 'notch-home',
  islandModes: [{ id: 'notch-home', priority: 21, width: HOME_W, useActive: useHomeActive, Content: Home, useTone: useHomeTone }]
})
