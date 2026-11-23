/**
 * Feature: buddy. The color sheet, only in the browser stage with ?buddy=colors (index.tsx). Not an app window.
 * The buddy in every candidate skin (palette.ts SKINS): big on the island's black, and at the size it is on the
 * screen over a dark and a light app. ?char=<kind> shows another character in the same colors. To see one skin
 * doing everything, open ?buddy=point&skin=<name>.
 */
import type { ReactNode } from 'react'
import { brand } from '../../core/theme'
import { Character, CHARACTERS, DEFAULT_CHARACTER, type CharacterKind } from './Character'
import { DEFAULT_SKIN, SKINS, type Skin, type SkinName } from './palette'
import { BODY } from './trip'

const LABEL = { font: '500 12px -apple-system, "Segoe UI", sans-serif', color: '#8F8F88' } as const
const KIND: CharacterKind = (() => {
  const q = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('char') : null
  return CHARACTERS.find((k) => k === q) ?? DEFAULT_CHARACTER
})()

/**
 * Which skins the sheet shows: the first round of nine, or ?set=cream, the cream versions beside the sand it is now.
 */
const SETS: Record<string, { title: string; names: SkinName[] }> = {
  all: { title: 'The buddy: colors to pick from', names: ['mint', 'cream', 'sand', 'butter', 'peach', 'clay', 'pink', 'lilac', 'sky'] },
  cream: { title: 'The buddy: cream, a few ways (sand is what it is now)', names: ['sand', 'cream', 'cream-sand', 'cream-shade', 'ivory', 'cream-sage'] }
}
const SET = SETS[(typeof location !== 'undefined' && new URLSearchParams(location.search).get('set')) || 'all'] ?? SETS.all

/** The same body with other leaves, so the leaves can be picked apart from the body. Shown on `LEAVES_ON`. */
const LEAVES_ON: SkinName = DEFAULT_SKIN
const LEAVES: { name: string; leaf: string }[] = [
  { name: 'paper white (what it has)', leaf: SKINS[LEAVES_ON].leaf },
  { name: 'same as the body', leaf: SKINS[LEAVES_ON].body },
  { name: 'pale mint (kit)', leaf: brand.pastel.mint },
  { name: 'sage (new)', leaf: '#A9D0A6' },
  { name: "the bonsai's green", leaf: brand.pass }
]

function Tile({ name, note, skin }: { name: string; note: string; skin: Skin }): ReactNode {
  return (
    <div data-skin={name} style={{ background: '#000', borderRadius: 16, padding: '14px 16px 12px', display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Character kind={KIND} skin={skin} size={92} />
          <Character kind={KIND} skin={skin} size={92} mood="happy" />
          <Character kind={KIND} skin={skin} size={92} point={-1} look={{ x: -1, y: 0.2 }} />
        </div>
        <div style={{ display: 'grid', gap: 6 }}>
          {(['dark', 'light'] as const).map((tone) => (
            <div key={tone} style={{ background: tone === 'dark' ? '#1E1E1E' : brand.paper, borderRadius: 10, padding: '5px 10px', display: 'flex', gap: 8 }}>
              <Character kind={KIND} skin={skin} size={BODY.size} />
              <Character kind={KIND} skin={skin} size={BODY.size} mood="curious" look={{ x: -0.8, y: 0 }} />
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
        <span style={{ ...LABEL, fontSize: 14, fontWeight: 600, color: '#F4F4F5' }}>{name}</span>
        <span style={LABEL}>{note}</span>
      </div>
    </div>
  )
}

export function ColorStage(): ReactNode {
  return (
    <div data-hit data-theme="dark" data-colors style={{ position: 'absolute', inset: 0, background: '#161615', padding: '22px 26px', overflow: 'hidden', color: '#F4F4F5' }}>
      <div style={{ font: '600 20px -apple-system, "Segoe UI", sans-serif', marginBottom: 2 }}>{SET.title}</div>
      <div style={{ ...LABEL, fontSize: 13, marginBottom: 14 }}>Big on the island&apos;s black, and at real size ({BODY.size} px) over a dark and a light app. Its loop is drawn in the same color.</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {SET.names.map((name) => (
          <Tile key={name} name={name} note={SKINS[name].note} skin={SKINS[name]} />
        ))}
      </div>
      <div data-colors-leaves style={{ marginTop: 16 }}>
        <div style={{ ...LABEL, fontSize: 13, color: '#F4F4F5', marginBottom: 6 }}>its leaves, on {LEAVES_ON}</div>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${LEAVES.length}, 1fr)`, gap: 12 }}>
          {LEAVES.map((l) => (
            <div key={l.name} data-leaf={l.name} style={{ background: '#000', borderRadius: 16, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Character kind={KIND} skin={{ ...SKINS[LEAVES_ON], leaf: l.leaf }} size={64} />
              <Character kind={KIND} skin={{ ...SKINS[LEAVES_ON], leaf: l.leaf }} size={64} mood="listening" />
              <span style={LABEL}>{l.name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
