/**
 * Feature: buddy. The character sheet, only in the browser stage with ?buddy=cast (index.tsx). Not an app window.
 * Each candidate (Character.tsx) in every mood and pose, big on the island's black, and at the size it is on the
 * screen (trip.ts BODY.size) over a dark and a light app, so Adrian can pick one from what it actually looks like.
 */
import type { ReactNode } from 'react'
import { brand } from '../../core/theme'
import { Character, CHARACTERS, type CharacterKind, type CharacterProps } from './Character'
import { PICKS, SKINS } from './palette'
import { BODY } from './trip'

const POSES: { name: string; props: CharacterProps }[] = [
  { name: 'calm', props: {} },
  { name: 'happy', props: { mood: 'happy' } },
  { name: 'curious', props: { mood: 'curious', look: { x: 0.9, y: -0.3 } } },
  { name: 'listening', props: { mood: 'listening' } },
  { name: 'thinking', props: { mood: 'thinking' } },
  { name: 'talking', props: { talking: true } },
  { name: 'pointing', props: { point: -1, look: { x: -1, y: 0.2 } } },
  { name: 'flying', props: { flying: true, look: { x: 0.7, y: 0.5 } } },
  { name: 'sleepy', props: { mood: 'sleepy' } }
]

const NOTE: Record<CharacterKind, string> = {
  sprout: 'sprout · a round creature, a two-leaf sprout on its head (its ears, and its wings)',
  leaf: 'leaf · a leaf with a face; its tip is its pointer',
  dot: 'dot · a droplet of the island: black, a rim in its color, eyes only'
}

const LABEL = { font: '500 12px -apple-system, "Segoe UI", sans-serif', color: '#8F8F88' } as const

export function CastStage(): ReactNode {
  return (
    <div data-hit data-theme="dark" style={{ position: 'absolute', inset: 0, background: '#161615', padding: '22px 26px', overflow: 'hidden', color: '#F4F4F5' }}>
      <div style={{ font: '600 20px -apple-system, "Segoe UI", sans-serif', marginBottom: 2 }}>The buddy: three characters to pick from</div>
      <div style={{ ...LABEL, fontSize: 13, marginBottom: 14 }}>None of them is the bonsai. Same face, moods and motion on each. On the screen it is {BODY.size} px.</div>
      {CHARACTERS.map((kind) => (
        <div key={kind} data-cast={kind} style={{ marginBottom: 14 }}>
          <div style={{ ...LABEL, fontSize: 13, color: '#F4F4F5', marginBottom: 6 }}>{NOTE[kind]}</div>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${POSES.length}, 1fr) 1.5fr 1.5fr`, gap: 8, alignItems: 'stretch' }}>
            {POSES.map((p) => (
              <div key={p.name} style={{ background: '#000', borderRadius: 14, padding: '12px 0 8px', display: 'grid', justifyItems: 'center', gap: 6 }}>
                <Character kind={kind} size={96} {...p.props} />
                <span style={LABEL}>{p.name}</span>
              </div>
            ))}
            {(['dark', 'light'] as const).map((tone) => (
              <div key={tone} style={{ background: tone === 'dark' ? '#1E1E1E' : brand.paper, borderRadius: 14, padding: '12px 10px 8px', display: 'grid', justifyItems: 'center', alignContent: 'space-between', gap: 6 }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <Character kind={kind} size={BODY.size} />
                  <Character kind={kind} size={BODY.size} mood="happy" />
                  <Character kind={kind} size={BODY.size} mood="curious" look={{ x: -0.8, y: 0 }} />
                </div>
                <span style={{ ...LABEL, color: tone === 'dark' ? '#8F8F88' : '#66665F' }}>real size, {tone} app</span>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div data-cast="yours">
        <div style={{ ...LABEL, fontSize: 13, color: '#F4F4F5', marginBottom: 6 }}>make it yours · the learner picks its color at setup (?buddy=pick), and it grows as they learn (a proposal, nothing stores it yet)</div>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${PICKS.length}, 1fr) 0.3fr repeat(3, 1.4fr)`, gap: 8 }}>
          {PICKS.map((tint) => (
            <div key={tint} style={{ background: '#000', borderRadius: 14, padding: '12px 0 8px', display: 'grid', justifyItems: 'center', gap: 6 }}>
              <Character size={72} skin={SKINS[tint]} mood="happy" />
              <span style={LABEL}>{tint}</span>
            </div>
          ))}
          <span />
          {([0, 1, 2] as const).map((grown) => (
            <div key={grown} style={{ background: '#000', borderRadius: 14, padding: '12px 0 8px', display: 'grid', justifyItems: 'center', gap: 6 }}>
              <Character size={72} grown={grown} />
              <span style={LABEL}>{['day one', 'a few lessons in', 'skills mastered'][grown]}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
