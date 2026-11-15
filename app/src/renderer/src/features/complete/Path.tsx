/**
 * The learning path (direction B): the track's skills as dots on one thin horizontal line, each label under its dot.
 * Mastered = a filled dot, learning (e.g. a step typed by "Do it for me") = a half-filled ring, next = a hollow,
 * fainter ring. The line is brighter through what's been done and faint through what's next. Click or hover a dot:
 * its detail shows as one quiet line under the path, under that dot. Only the main track is drawn (no cross links).
 */
import { motion } from 'motion/react'
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { color, fill } from '../../core/theme'
import type { SkillMap, SkillNode, SkillState } from './types'

/** The dot's box: room for the selection ring, so selecting never shifts the layout. */
const BOX = 20
const C = BOX / 2

function Dot({ state, selected }: { state: SkillState; selected: boolean }): ReactNode {
  return (
    <svg width={BOX} height={BOX} viewBox={`0 0 ${BOX} ${BOX}`} className="block shrink-0" aria-hidden>
      {selected && <circle cx={C} cy={C} r={8.5} fill={color.island} stroke={fill.ring} strokeWidth={1} />}
      {state === 'mastered' && <circle cx={C} cy={C} r={5} fill={color.text} />}
      {state === 'learning' && (
        <>
          <circle cx={C} cy={C} r={4.5} fill={color.island} stroke={color.text} strokeWidth={1.25} />
          <path d={`M${C},${C - 4.5} A4.5,4.5 0 0,0 ${C},${C + 4.5} Z`} fill={color.text} />
        </>
      )}
      {state === 'next' && <circle cx={C} cy={C} r={4.5} fill={color.island} stroke={color.faint} strokeWidth={1.25} />}
    </svg>
  )
}

/** The default selection: where the path goes next (the first skill up next), else the last one. */
const firstNext = (nodes: SkillNode[]): string | undefined => (nodes.find((n) => n.state === 'next') ?? nodes[nodes.length - 1])?.id

const labelColor = (state: SkillState, selected: boolean): string => (selected ? color.text : state === 'next' ? color.faint : color.label)

export function PathView({ map, width }: { map: SkillMap; width: number }): ReactNode {
  const nodes = map.nodes
  const n = nodes.length
  const colW = width / n
  const [sel, setSel] = useState<string | undefined>(() => firstNext(nodes))
  const at = Math.max(0, nodes.findIndex((x) => x.id === sel))
  const node = nodes[at]
  // The line is bright up to the last skill that isn't still ahead.
  let reached = -1
  nodes.forEach((x, i) => {
    if (x.state !== 'next') reached = i
  })
  // Long single words (e.g. "Backpropagation") need a little more than a narrow column: one size down.
  const px = colW >= 96 ? 13 : 12

  // The detail line sits under the selected dot, kept inside the path's width.
  const detailRef = useRef<HTMLSpanElement>(null)
  const [left, setLeft] = useState(0)
  useLayoutEffect(() => {
    const w = detailRef.current?.offsetWidth ?? 0
    const x = colW * (at + 0.5)
    setLeft(Math.max(0, Math.min(width - w, x - w / 2)))
  }, [at, colW, width, node?.detail])

  return (
    <div data-skill-path style={{ width }}>
      <div className="relative">
        {n > 1 && (
          <>
            <motion.div
              className="absolute h-px"
              style={{ top: C - 0.5, left: colW / 2, width: colW * (n - 1), background: fill.trackSoft, transformOrigin: '0 50%' }}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.08 }}
            />
            {reached > 0 && (
              <motion.div
                className="absolute h-px"
                style={{ top: C - 0.5, left: colW / 2, width: colW * reached, background: color.faint, transformOrigin: '0 50%' }}
                initial={{ scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.08 }}
              />
            )}
          </>
        )}
        <div className="relative flex">
          {nodes.map((x, i) => {
            const on = x.id === node?.id
            return (
              <motion.button
                key={x.id}
                type="button"
                data-node={x.id}
                data-state={x.state}
                aria-pressed={on}
                className="flex min-w-0 flex-1 cursor-pointer flex-col items-center outline-none"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.25, delay: 0.1 + i * 0.03 }}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setSel(x.id)}
                onFocus={() => setSel(x.id)}
                onClick={() => setSel(x.id)}
              >
                <Dot state={x.state} selected={on} />
                <span
                  className="mt-[12px] overflow-hidden text-center"
                  style={{
                    fontSize: px,
                    lineHeight: `${px + 4}px`,
                    color: labelColor(x.state, on),
                    maxWidth: `max(calc(100% - 8px), ${px * 7.6}px)`,
                    width: 'max-content',
                    display: '-webkit-box',
                    WebkitBoxOrient: 'vertical',
                    WebkitLineClamp: 3,
                    transition: 'color 120ms'
                  }}
                >
                  {x.label}
                </span>
              </motion.button>
            )
          })}
        </div>
      </div>
      <div className="relative mt-[18px] h-[18px]" data-skill-detail>
        {node?.detail && (
          <motion.span
            key={node.id}
            ref={detailRef}
            className="absolute top-0 whitespace-nowrap text-[13px] leading-[18px]"
            style={{ left, color: color.label }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.16 }}
          >
            {node.detail}
          </motion.span>
        )}
      </div>
    </div>
  )
}
