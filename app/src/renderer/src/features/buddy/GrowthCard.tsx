/**
 * Feature: buddy. How bon has grown, and what it takes to grow more, so leveling up is never a mystery
 * (Adrian, Nov 23: "leveling up clear... outline what it means").
 *
 *   BonLevel    one line: "Level 3 · Shoot", how many steps to the next level, and a bar
 *   BonLadder   all eight levels side by side, each drawn as it looks, with its name and the steps it takes; the ones
 *               not reached yet are dimmed, the one it is at is marked. Under it, the rule in one sentence.
 * Both read the learner's own count (growth.ts). Settings mounts them (SettingsRows.tsx); a Progress or Home page can
 * mount the same two (brief, Core requests).
 */
import type { ReactNode } from 'react'
import { color, fill, type2 } from '../../core/theme'
import { Character } from './Character'
import { LEVELS, progressOf, useGrowth } from './growth'
import { words } from './name'

const steps = (n: number): string => `${n} ${n === 1 ? 'step' : 'steps'}`

/** What the level line says about the way to the next one. */
export function nextLine(stepsPassed: number): string {
  const p = progressOf(stepsPassed)
  return p.next ? `${steps(p.steps)} passed. ${p.next.left} more to ${p.next.name}.` : `${steps(p.steps)} passed. Fully grown.`
}

export function BonBar({ width = 168 }: { width?: number }): ReactNode {
  const p = progressOf(useGrowth((g) => g.steps))
  return (
    <span
      data-part="bon-bar"
      role="progressbar"
      aria-label={p.next ? `Progress to ${p.next.name}` : 'Fully grown'}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(p.fraction * 100)}
      className="block shrink-0 overflow-hidden"
      style={{ width, height: 6, borderRadius: 3, background: fill.segmentTrack }}
    >
      {/* Neutral, not green: green only means a step passed. */}
      <span className="block h-full" style={{ width: `${Math.max(p.fraction > 0 ? 4 : 0, p.fraction * 100)}%`, borderRadius: 3, background: color.text, transition: 'width 420ms cubic-bezier(0.23, 1, 0.32, 1)' }} />
    </span>
  )
}

/** "Level 3 · Shoot" and what is left. */
export function useLevelWords(): { title: string; caption: string } {
  const stepsPassed = useGrowth((g) => g.steps)
  const p = progressOf(stepsPassed)
  return { title: `Level ${p.level} · ${p.name}`, caption: nextLine(stepsPassed) }
}

export function BonLadder({ size = 40 }: { size?: number }): ReactNode {
  const level = useGrowth((g) => g.level)
  return (
    <div data-part="bon-ladder" className="flex flex-col gap-[14px] px-[16px] pb-[16px] pt-[18px]">
      <ol className="m-0 grid list-none p-0" style={{ gridTemplateColumns: `repeat(${LEVELS.length}, minmax(0, 1fr))`, gap: 4 }} aria-label="Levels">
        {LEVELS.map((l, i) => {
          const n = i + 1
          const reached = n <= level
          const here = n === level
          return (
            <li key={l.name} data-level={n} data-reached={reached || undefined} data-here={here || undefined} aria-current={here ? 'step' : undefined} className="flex flex-col items-center text-center">
              {/* Room above for what grows on its head: the tallest (the tree) stands a fifth of its size over the box. */}
              <span className="flex items-end justify-center" style={{ height: size * 1.24, opacity: reached ? 1 : 0.34 }}>
                <Character size={size} level={n} mood={here ? 'happy' : 'calm'} />
              </span>
              <span className="mt-[8px] whitespace-nowrap" style={{ fontSize: type2.xs, fontWeight: here ? 600 : 500, color: reached ? color.text : color.label }}>
                {l.name}
              </span>
              <span className="whitespace-nowrap tabular-nums" style={{ fontSize: type2.micro, color: color.label }}>
                {l.at === 0 ? 'start' : steps(l.at)}
              </span>
              {/* The one it is at. */}
              <span aria-hidden className="mt-[6px] block" style={{ width: 16, height: 2, borderRadius: 1, background: here ? color.text : 'transparent' }} />
            </li>
          )
        })}
      </ol>
      <span data-part="bon-rule" style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
        {words.growRule}
      </span>
    </div>
  )
}
