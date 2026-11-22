/**
 * Feature: notch-home. In the notch (layout.notch.place 'notch'), hovering the island with no lesson on screen opens a
 * Boring-Notch-size panel grown down from the notch (Michael, Nov 22: "almost as big as boring notch ... show Continue
 * Lesson"). Left: the lesson to pick up (the engine's saved offer, else the most recent unfinished lesson), with one
 * white Continue. Right: ask miyagi, a drop zone for a video link (drag a YouTube link onto the notch to build a lesson),
 * and lessons ready to run. Footer: the library.
 * During a lesson the overview card (priority 20) is the hover card; below the menu bar nothing changes.
 */
import { motion } from 'motion/react'
import { useEffect, useState, type DragEvent, type ReactNode } from 'react'
import { ArrowUpRight, Link2, Play } from 'lucide-react'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { notchOf } from '../../core/notchGeometry'
import { useNotchInfo } from '../../core/notchInfo'
import { defineFeature } from '../../core/registry'
import { openLibrary } from '../../core/surfaces'
import { Kbd, PrimaryButton, Thumb } from '../../core/ui/atoms'
import { MiyagiMark } from '../../core/ui/Mark'
import { color, copy, fill } from '../../core/theme'
import { librarySections, refreshLibrary, startLibraryLesson, useLibrary, type LibraryItem } from '../launcher/library'
import { parseYouTube, thumbnailFor } from '../launcher/youtube'
import { resumeSaved, usePill } from '../pill/store'

/** The panel's own width (the island adds its open top radius each side): ~600 wide in all, like Boring Notch's 640. */
export const HOME_W = 560

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

/** Thin segments: done white, the step you're on gray, the rest a dim track. */
function Progress({ n, total }: { n: number; total: number }): ReactNode {
  const segs = Math.min(total, 24)
  const at = Math.round(((n - 1) / total) * segs)
  return (
    <div className="mt-[8px] flex gap-[3px]" aria-hidden>
      {Array.from({ length: segs }, (_, i) => (
        <div key={i} className="h-[3px] flex-1 rounded-full" style={{ background: i < at ? color.text : i === at ? color.gray : fill.track }} />
      ))}
    </div>
  )
}

function ContinueCard({ pick }: { pick: Pick | undefined }): ReactNode {
  const resuming = usePill((s) => s.resuming)
  if (!pick)
    return (
      <div className="flex h-full flex-col justify-between">
        <div>
          <div className="text-[15px] font-semibold" style={{ color: color.text }}>
            Learn anything by doing.
          </div>
          <div className="mt-[4px] text-[13px]" style={{ color: color.label }}>
            Ask for a topic or drop in a video.
          </div>
        </div>
        <div className="flex">
          <PrimaryButton label="Start a lesson" kbd={bridge.platform.keys.launcher} onClick={() => bridge.emit('launcher:toggle')} />
        </div>
      </div>
    )
  return (
    <div className="flex h-full flex-col justify-between">
      <div className="flex gap-[12px]">
        {pick.thumb ? <Thumb w={112} h={63} src={pick.thumb} /> : <div className="flex h-[63px] w-[63px] shrink-0 items-center justify-center rounded-[10px]" style={{ background: fill.tile }}><MiyagiMark size={30} /></div>}
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-medium uppercase tracking-[.06em]" style={{ color: color.label }}>
            Continue
          </div>
          <div className="mt-[2px] line-clamp-2 text-[14px] font-semibold leading-[18px]" style={{ color: color.text }}>
            {pick.title}
          </div>
          {pick.meta && (
            <div className="mt-[2px] truncate text-[12px]" style={{ color: color.label }}>
              {pick.meta}
            </div>
          )}
        </div>
      </div>
      {pick.n && pick.total ? <Progress n={pick.n} total={pick.total} /> : null}
      <div className="mt-[10px] flex">
        <PrimaryButton label={resuming ? 'Opening…' : 'Continue lesson'} icon={Play} disabled={resuming} onClick={pick.go} />
      </div>
    </div>
  )
}

/** A quiet row on the right: neutral chrome, never a pastel. */
function Row({ children, onClick, title }: { children: ReactNode; onClick: () => void; title?: string }): ReactNode {
  return (
    <motion.button
      type="button"
      title={title}
      className="flex h-[30px] w-full cursor-pointer items-center gap-[8px] rounded-[8px] px-[8px] text-left text-[13px]"
      style={{ color: color.text }}
      whileHover={{ backgroundColor: fill.chipHover }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {children}
    </motion.button>
  )
}

/** Drag a video link onto the notch: miyagi builds the lesson from it. A click opens the launcher to paste one. */
function DropZone(): ReactNode {
  const [over, setOver] = useState(false)
  const [sent, setSent] = useState(false)
  const linkOf = (e: DragEvent): string | undefined => {
    const raw = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain')
    const url = raw.split(/\s+/).find((s) => /^https?:\/\//.test(s))
    return url && parseYouTube(url) ? url : undefined
  }
  return (
    <div
      role="button"
      tabIndex={-1}
      data-drop-link
      className="flex h-[44px] cursor-pointer items-center gap-[8px] rounded-[10px] px-[10px] text-[12px]"
      style={{ border: `1px dashed ${over ? color.text : fill.rule}`, color: over ? color.text : color.label, background: over ? fill.chip : 'transparent' }}
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
        if (!url) return
        bridge.send(cmd('learn_url', { url }))
        setSent(true)
      }}
    >
      <Link2 size={14} strokeWidth={1.8} className="shrink-0" />
      <span className="truncate">{sent ? 'Building your lesson…' : 'Drop a YouTube link to learn it'}</span>
    </div>
  )
}

function Home(): ReactNode {
  const pick = usePick()
  const items = useLibrary((s) => s.items)
  const ready = librarySections(items, pick?.title).ready.slice(0, 2)
  // Fresh lessons each time the panel opens (cheap: the engine answers from its cache).
  useEffect(() => refreshLibrary(), [])
  return (
    <div className="flex flex-col px-[18px] pb-[14px] pt-[12px]" data-notch-home style={{ width: HOME_W }}>
      <div className="flex gap-[18px]" style={{ height: 136 }}>
        <div className="min-w-0 flex-1">
          <ContinueCard pick={pick} />
        </div>
        <div className="w-px shrink-0" style={{ background: fill.rule }} />
        <div className="flex w-[200px] shrink-0 flex-col gap-[4px]">
          <Row onClick={() => bridge.emit('launcher:toggle')} title={`${copy.ask}`}>
            <MiyagiMark size={14} />
            <span className="flex-1 truncate">{copy.ask}</span>
            <Kbd>{bridge.platform.keys.launcher}</Kbd>
          </Row>
          <DropZone />
          {ready.map((r) => (
            <Row key={r.id} onClick={() => void startLibraryLesson(r.id)} title={r.title}>
              <Play size={12} strokeWidth={1.8} className="shrink-0" style={{ color: color.label }} />
              <span className="truncate">{r.title}</span>
            </Row>
          ))}
          <div className="flex-1" />
          <Row onClick={() => void openLibrary()}>
            <span className="flex-1" style={{ color: color.label }}>
              Library
            </span>
            <ArrowUpRight size={13} strokeWidth={1.8} style={{ color: color.label }} />
          </Row>
        </div>
      </div>
    </div>
  )
}

export default defineFeature({
  id: 'notch-home',
  islandModes: [{ id: 'notch-home', priority: 21, width: HOME_W, useActive: useHomeActive, Content: Home }]
})
