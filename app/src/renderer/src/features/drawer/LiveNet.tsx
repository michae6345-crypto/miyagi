/**
 * Feature: drawer. The live network (a `network` diagram with real weights) drawn on glass, compact: scaled to the
 * flyout's width, in glass ink, with its caption. It used to sit in the drawer's panel and float out of it; since
 * Michael's Nov 15 call it shows only in the Diagram flyout (Flyout.tsx), and redraws in place while that is open.
 */
import type { ReactNode } from 'react'
import type { DiagramPayload } from '../diagrams/store'
import { glass } from '../../core/theme'
import { Firing, isFiringNetwork } from '../diagrams/Firing'
import { NeuralNet } from '../diagrams/NeuralNet'
import { SafeDiagram } from '../diagrams/SafeDiagram'

/** The network itself (compact: scaled to the surface's width) and its caption. */
export function NetBody({ d }: { d: DiagramPayload }): ReactNode {
  const data = d.data as Record<string, unknown>
  return (
    <>
      <SafeDiagram resetKey={data}>{isFiringNetwork(data) ? <Firing data={data} compact /> : <NeuralNet data={data} compact />}</SafeDiagram>
      {d.caption && (
        <div className="mt-[6px] line-clamp-2 break-words text-[12.5px] leading-[17px]" style={{ color: glass.label }}>
          {d.caption}
        </div>
      )}
    </>
  )
}
