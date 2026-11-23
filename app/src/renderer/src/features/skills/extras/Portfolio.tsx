/**
 * The portfolio on Progress (mockup skills-07-extras, 4): projects the learner finished, as cards (a picture of their
 * own file when the engine saved one, else the file's name on a quiet well; the project, its track, the date and how
 * many skills it used), then the current goal as a dashed placeholder with the bonsai ("your goal · 5 skills away"),
 * which opens the Skills page. Nothing renders with no finished project and no chosen goal.
 */
import { FileCode2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { bridge } from '../../../bridge'
import { MiyagiMark } from '../../../core/ui/Mark'
import { color, fill, layout, radius2, surface, type2 } from '../../../core/theme'
import { CARD } from '../../shell/ui'
import type { SkillGraph, SkillGraphPortfolioItem } from '../model'
import { goalAway } from './recap'
import { ensureSkillGraph, useSkillGraph } from './store'

const PIC_H = 132

/**
 * The learner's own image. artifact.path is a local path (contract: never a URL), and the renderer's CSP (img-src
 * 'self' data: blob: …) blocks file:// and other web images, so the window shows only data: images. A local path goes
 * through main's `skills:artifact-image` (Core request in agents/skills.md: reads the file, returns a size-capped
 * data: URL). Until main has it, or when it fails, the card keeps the file icon and name.
 */
const IMAGE_CHANNEL = 'skills:artifact-image'
/** A data: URL the card accepts back (about 2 MB of base64). */
const MAX_DATA_URL = 2_800_000
/** An <img> runs no script, so an SVG data image is as safe here as a raster one. */
const isDataImage = (s: unknown): s is string => typeof s === 'string' && s.length <= MAX_DATA_URL && /^data:image\/(png|jpeg|gif|webp|svg\+xml)[;,]/.test(s)
/** Capability: false once main (or the browser stage) said it has no such handler, so the card stops asking. */
let canLoad = true
const loaded = new Map<string, Promise<string | undefined>>()
function loadImage(path: string): Promise<string | undefined> {
  let p = loaded.get(path)
  if (!p) {
    p = bridge.invoke<unknown>(IMAGE_CHANNEL, path).then(
      (r) => (isDataImage(r) ? r : undefined),
      (e: unknown) => {
        if (/no (web )?handler/i.test(String(e))) canLoad = false
        return undefined
      }
    )
    loaded.set(path, p)
  }
  return p
}

/** The picture for an image artifact: a data: image as it is, a local file through main, else undefined. */
function usePicture(path?: string): string | undefined {
  // An absolute path on this Mac; anything else (a URL, a relative name) never loads.
  const local = !!path && path.startsWith('/')
  const [src, setSrc] = useState<string | undefined>(() => (path && isDataImage(path) ? path : undefined))
  useEffect(() => {
    if (!path) return setSrc(undefined)
    if (!local) return setSrc(isDataImage(path) ? path : undefined)
    setSrc(undefined)
    if (!canLoad) return
    let live = true
    void loadImage(path).then((r) => {
      if (live) setSrc(r)
    })
    return () => {
      live = false
    }
  }, [path, local])
  return src
}

const day = (t?: number): string => (t ? new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '')

function Picture({ item }: { item: SkillGraphPortfolioItem }): ReactNode {
  const src = usePicture(item.artifact?.kind === 'image' ? item.artifact.path : undefined)
  const [broken, setBroken] = useState(false)
  const path = item.artifact?.path
  const name = path && !path.startsWith('data:') ? path.split('/').pop() : undefined
  return (
    <div className="relative flex items-center justify-center overflow-hidden" style={{ height: PIC_H, background: surface.well, borderBottom: `1px solid ${fill.hairline}` }}>
      {src && !broken ? (
        <img src={src} alt={item.artifact?.caption ?? `${item.title}, your file`} draggable={false} onError={() => setBroken(true)} className="h-full w-full select-none object-cover" />
      ) : (
        <span className="flex flex-col items-center gap-[6px]" style={{ color: color.label }}>
          <FileCode2 aria-hidden size={22} strokeWidth={1.6} />
          {name && <span style={{ fontSize: type2.xs }}>{name}</span>}
        </span>
      )}
    </div>
  )
}

function ProjectCard({ item, g }: { item: SkillGraphPortfolioItem; g: SkillGraph }): ReactNode {
  const track = item.track ?? g.tracks.find((t) => t.id === g.byId[item.capstoneId]?.track)?.label
  const n = item.skillIds.length
  const meta = [track, day(item.at), n ? `${n} ${n === 1 ? 'skill' : 'skills'}` : ''].filter(Boolean).join(' · ')
  return (
    <li data-portfolio-item={item.capstoneId} className="flex flex-col overflow-hidden" style={{ ...CARD }}>
      <Picture item={item} />
      <div className="flex min-w-0 flex-col gap-[2px]" style={{ padding: '12px 16px 14px' }}>
        <span className="truncate font-semibold" style={{ fontSize: type2.md, color: color.text }}>
          {item.title}
        </span>
        {meta && (
          <span className="truncate" style={{ fontSize: type2.xs, color: color.label, fontVariantNumeric: 'tabular-nums' }}>
            {meta}
          </span>
        )}
      </div>
    </li>
  )
}

function GoalCard({ g, onOpen }: { g: SkillGraph; onOpen?: () => void }): ReactNode {
  const away = goalAway(g)
  const line = ['your goal', away ? `${away} ${away === 1 ? 'skill' : 'skills'} away` : away === 0 ? 'ready to build' : ''].filter(Boolean).join(' · ')
  const body = (
    <>
      <MiyagiMark size={28} />
      <span className="max-w-full truncate font-semibold" style={{ marginTop: 10, fontSize: type2.md, color: color.text }}>
        {g.goal!.label}
      </span>
      <span style={{ fontSize: type2.xs, color: color.label }}>{line}</span>
    </>
  )
  const style = { minHeight: PIC_H + 62, padding: 16, borderRadius: layout.radius.card, border: `1.5px dashed ${fill.trackNextMini}` }
  return (
    <li data-portfolio-goal={g.goal!.id} className="flex">
      {onOpen ? (
        <button type="button" onClick={onOpen} aria-label={`${g.goal!.label}. ${line}. Open Skills.`} className="mg-press relative flex w-full cursor-pointer flex-col items-center justify-center gap-[2px] outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid" style={{ ...style, background: 'transparent', outlineColor: color.text }}>
          {body}
        </button>
      ) : (
        <div className="flex w-full flex-col items-center justify-center gap-[2px]" style={style}>
          {body}
        </div>
      )}
    </li>
  )
}

/** Finished projects and the goal, or nothing. `head`: the page's section header; `onOpenGoal`: opens Skills. */
export function Portfolio({ head, onOpenGoal }: { head?: ReactNode; onOpenGoal?: () => void }): ReactNode {
  const g = useSkillGraph((s) => s.graph)
  useEffect(ensureSkillGraph, [])
  if (!g) return null
  // The goal placeholder only for a project the learner (or the engine) chose, never a track end drawn as one.
  const goal = g.goal && !g.goal.inferred && !g.portfolio.some((p) => p.capstoneId === g.goal!.id) ? g.goal : null
  if (!g.portfolio.length && !goal) return null
  return (
    <section aria-labelledby="prog-portfolio" data-prog-portfolio>
      {head}
      <ul className="m-0 grid list-none p-0" style={{ gap: 16, gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', borderRadius: radius2.card }}>
        {g.portfolio.map((p) => (
          <ProjectCard key={p.capstoneId} item={p} g={g} />
        ))}
        {goal && <GoalCard g={g} onOpen={onOpenGoal} />}
      </ul>
    </section>
  )
}
