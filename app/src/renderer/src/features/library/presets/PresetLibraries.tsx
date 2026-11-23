/**
 * Feature: library / presets. "Start with a pack": curated starter packs on the Lessons page, and a compact row of
 * them on Home. A placeholder download (store.ts): Download plays a short progress and the card reads "Added", with a
 * quiet Remove. Nothing is fetched. Neutral only: monochrome monogram tiles, no brand colors, no hues; the one lifted
 * look is the raised layer cards already use. The topic filter is the same Chip the rest of the library uses.
 */
import { Check, ChevronRight, Download } from 'lucide-react'
import { motion } from 'motion/react'
import { useMemo, type ReactNode } from 'react'
import { color, fill, layer, radius2, surface, type2 } from '../../../core/theme'
import { QuietButton } from '../../../core/ui/buttons'
import { TextAction, caption } from '../../shell/ui'
import { setPage } from '../../shell/store'
import { SectionLabel } from '../layout'
import { Press, Ring, Rise } from '../motion'
import { Chip } from '../parts'
import { useLibrary } from '../store'
import { PACKS, TOPICS, aboutLabel, lessonsLabel, type Pack } from './packs'
import { ADD_MS, addPack, removePack, setTopic, usePresets } from './store'

/** A pack's tile: its letters in ink on the neutral tile fill. Never a logo, never a hue. */
function Tile({ pack, size = 40 }: { pack: Pack; size?: number }): ReactNode {
  const long = pack.mark.length > 2
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center justify-center font-semibold"
      style={{ width: size, height: size, borderRadius: radius2.row, background: fill.tile, color: color.text, boxShadow: `inset 0 0 0 1px ${surface.border}`, fontSize: long ? type2.xs : type2.md, letterSpacing: '-0.2px' }}
    >
      {pack.mark}
    </span>
  )
}

function PackCard({ pack, i }: { pack: Pack; i: number }): ReactNode {
  const added = usePresets((s) => s.added.includes(pack.id))
  const adding = usePresets((s) => s.adding.includes(pack.id))
  const topic = TOPICS.find((t) => t.id === pack.topic)?.label
  return (
    <Rise i={i} data-pack={pack.id} className="relative flex min-w-0 flex-col overflow-hidden" style={{ ...layer.raised, borderRadius: radius2.card, padding: 16, gap: 12 }}>
      <div className="flex items-start gap-[12px]">
        <Tile pack={pack} />
        <div className="flex min-w-0 flex-1 flex-col" style={{ gap: 2 }}>
          <span className="truncate font-semibold" style={{ fontSize: type2.md, lineHeight: '20px', color: color.text }}>
            {pack.name}
          </span>
          <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.faint }}>
            {topic} · {lessonsLabel(pack.lessons)} · {aboutLabel(pack.minutes)}
          </span>
        </div>
      </div>
      <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
        {pack.line}
      </p>
      <div className="mt-auto flex items-center justify-between gap-[8px]" style={{ minHeight: 36 }}>
        {added ? (
          <>
            <span role="status" className="flex items-center gap-[6px]" style={{ fontSize: type2.sm, color: color.text }}>
              <Check aria-hidden size={14} strokeWidth={2} />
              Added
            </span>
            <TextAction onClick={() => removePack(pack.id)}>Remove</TextAction>
          </>
        ) : (
          <Ring>
            <QuietButton label={adding ? 'Adding' : `Download ${pack.short}`} icon={Download} busy={adding} disabled={adding} onClick={() => addPack(pack.id)} />
          </Ring>
        )}
      </div>
      {adding && (
        <motion.span
          aria-hidden
          className="absolute inset-x-0 bottom-0 block"
          style={{ height: 3, background: color.text, originX: 0 }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: ADD_MS / 1000, ease: 'linear' }}
        />
      )}
    </Rise>
  )
}

/** The Lessons page section: header, topic chips, the card grid. Packs you added come first. */
export function PresetLibraries(): ReactNode {
  const topic = usePresets((s) => s.topic)
  const added = usePresets((s) => s.added)
  const query = useLibrary((s) => s.query).trim().toLowerCase()
  const shown = useMemo(() => {
    const list = PACKS.filter((p) => (topic === 'all' || p.topic === topic) && (!query || `${p.name} ${p.short} ${p.line}`.toLowerCase().includes(query)))
    return [...list].sort((a, b) => Number(added.includes(b.id)) - Number(added.includes(a.id)))
  }, [topic, added, query])
  return (
    <section aria-labelledby="lib-packs" data-presets>
      <SectionLabel id="lib-packs" right={<span style={{ fontSize: type2.xs, color: color.faint }}>{added.length ? `${added.length} added` : `${PACKS.length} packs`}</span>}>
        Start with a pack
      </SectionLabel>
      <p className="m-0" style={{ ...caption, marginTop: -4, marginBottom: 16 }}>
        Add a pack to keep its lessons close. Download is a preview for now.
      </p>
      <div role="group" aria-label="Filter packs by topic" className="flex flex-wrap" style={{ gap: 8, marginBottom: 16 }}>
        <Chip label="All" on={topic === 'all'} onClick={() => setTopic('all')} />
        {TOPICS.map((t) => (
          <Chip key={t.id} label={t.label} on={topic === t.id} onClick={() => setTopic(t.id)} />
        ))}
      </div>
      {shown.length === 0 ? (
        <p role="status" className="m-0" style={{ ...caption, fontSize: type2.sm }}>
          No packs match.
        </p>
      ) : (
        <div key={`${topic}|${query}`} className="grid grid-cols-1 @min-[560px]/pane:grid-cols-2" style={{ gap: 12 }}>
          {shown.map((p, n) => (
            <PackCard key={p.id} pack={p} i={n} />
          ))}
        </div>
      )}
    </section>
  )
}

/** Home's compact row: four packs and a link to the rest. Opens the Lessons page, where Download lives. */
const HOME_IDS = ['python', 'cpp', 'pytorch', 'blender']
export function PacksRow(): ReactNode {
  const added = usePresets((s) => s.added)
  const packs = HOME_IDS.map((id) => PACKS.find((p) => p.id === id)).filter((p): p is Pack => !!p)
  return (
    <section aria-labelledby="home-packs" data-home-packs>
      <SectionLabel
        id="home-packs"
        right={
          <span className="flex" style={{ marginRight: -8 }}>
            <TextAction onClick={() => setPage('lessons')}>
              All packs
              <ChevronRight aria-hidden size={16} strokeWidth={1.8} />
            </TextAction>
          </span>
        }
      >
        Packs
      </SectionLabel>
      <ul className="m-0 grid list-none grid-cols-2 p-0 @min-[560px]/pane:grid-cols-4" style={{ gap: 8 }}>
        {packs.map((p, n) => (
          <Rise key={p.id} as="li" i={n}>
            <Press
              onClick={() => {
                setTopic('all')
                setPage('lessons')
              }}
              aria-label={`${p.name}. ${lessonsLabel(p.lessons)}. Open packs.`}
              className="flex w-full flex-col"
              style={{ ...layer.raised, borderRadius: radius2.card, padding: 12, gap: 12 }}
            >
              <span className="relative flex items-center justify-between">
                <Tile pack={p} size={32} />
                {added.includes(p.id) && <Check aria-label="Added" size={14} strokeWidth={2} style={{ color: color.text }} />}
              </span>
              <span className="relative flex min-w-0 flex-col" style={{ gap: 2 }}>
                <span className="truncate font-semibold" style={{ fontSize: type2.sm, color: color.text }}>
                  {p.name}
                </span>
                <span style={{ fontSize: type2.xs, color: color.faint }}>{lessonsLabel(p.lessons)}</span>
              </span>
            </Press>
          </Rise>
        ))}
      </ul>
    </section>
  )
}
