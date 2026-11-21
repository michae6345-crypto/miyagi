/**
 * Feature: settings. Privacy › "What miyagi sees" (ROADMAP 5.4): one row per source from facts.ts, each with one calm
 * line and, on the right, "On this Mac" or where it goes. Read only: the switches live in Privacy.tsx. Neutral chrome,
 * no hue on any row (leaving the Mac is not a warning, it is just said plainly).
 */
import { Bug, ChartColumn, CodeXml, Folder, KeyRound, Link, Monitor, Search, Server, SquareCode, UserRound, Video, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Group, Note, Plain, Row } from '../ui'
import { FACTS, KEYS_NO_KEYCHAIN, ROUTE, type FactId } from './facts'

const ICON: Record<FactId, LucideIcon> = {
  screen: Monitor,
  code: CodeXml,
  editor: SquareCode,
  searches: Search,
  videos: Video,
  account: UserRound,
  link: Link,
  cloud: Server,
  keys: KeyRound,
  progress: Folder,
  crash: Bug,
  usage: ChartColumn
}

/** secure: false when this Mac has no secure storage (the keys then live in memory for this run). */
export function Sees({ secure }: { secure?: boolean }): ReactNode {
  return (
    <div className="flex flex-col gap-[8px]">
      <Group label="What miyagi sees" inset={64}>
        {FACTS.map((f) => (
          <Row
            key={f.id}
            minH={64}
            icon={ICON[f.id]}
            label={f.label}
            caption={f.id === 'keys' && secure === false ? KEYS_NO_KEYCHAIN : f.line}
            right={<Plain>{f.where}</Plain>}
          />
        ))}
      </Group>
      <Note>{ROUTE}</Note>
    </div>
  )
}
