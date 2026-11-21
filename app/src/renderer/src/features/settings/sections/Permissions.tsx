/**
 * Feature: settings. Permissions (Set-Permissions): Screen Recording, Accessibility and, when the engine probes it, the
 * VS Code extension. Rows flip live while the section is on show (main polls only then, never prompting).
 *
 *   granted        a white tick and "On" (never green: green only means passed)
 *   denied / not-determined   the white ring and "Not yet", with Turn on: System Settings at that switch
 *   unknown        the gray dashed ring and "Not sure yet" (an engine started in Terminal: macOS asks Terminal)
 *
 * One primary per surface: the first row that needs turning on gets the white button, any other a quiet one. The
 * extension row's fix is the setup checklist (openOnboarding), which installs it.
 */
import { Monitor, MousePointer2, Puzzle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { HealthItem, PermissionKind } from '../../../../../../../shared/contracts/events'
import { openOnboarding } from '../../../core/surfaces'
import { PrimaryButtonV2, QuietButton, StatusGlyph, StatusWord } from '../../../core/ui/atoms'
import { color, type2 } from '../../../core/theme'
import { openPermission, useHealth, usePermissions, type PermissionState } from '../permissions'
import { count, Group, Note, OnWord, PageHeader, Row } from '../ui'

type Item = { id: string; icon: LucideIcon; label: string; caption: string; state: 'on' | 'off' | 'unknown' | 'loading'; fix?: () => void }

const fromPermission = (s: PermissionState | undefined): Item['state'] => (!s ? 'loading' : s === 'granted' ? 'on' : s === 'unknown' ? 'unknown' : 'off')
const fromHealth = (h: HealthItem): Item['state'] => (h.state === 'ok' ? 'on' : h.state === 'unknown' ? 'unknown' : h.state === 'checking' ? 'loading' : 'off')

const PERMS: { kind: PermissionKind; icon: LucideIcon; label: string; caption: string }[] = [
  { kind: 'screen', icon: Monitor, label: 'Screen Recording', caption: 'Lets miyagi see which step you are on.' },
  { kind: 'accessibility', icon: MousePointer2, label: 'Accessibility', caption: 'Lets miyagi point at the real button.' }
]

export function Permissions({ live }: { live: boolean }): ReactNode {
  const perms = usePermissions(live)
  const health = useHealth(live)

  const items: Item[] = PERMS.map((p) => ({ id: p.kind, icon: p.icon, label: p.label, caption: p.caption, state: fromPermission(perms?.[p.kind]), fix: () => openPermission(p.kind) }))
  // Hidden without a probe: only an engine that reports the companion can say whether it's on.
  const companion = health.companion
  if (companion)
    items.push({ id: 'companion', icon: Puzzle, label: 'VS Code extension', caption: 'Lets miyagi run your cells to check work.', state: fromHealth(companion), fix: () => void openOnboarding() })

  const known = items.filter((i) => i.state === 'on' || i.state === 'off')
  const on = known.filter((i) => i.state === 'on').length
  const caption = !perms
    ? 'All in one place.'
    : known.length && on === known.length
      ? 'All in one place. All on.'
      : known.length
        ? `All in one place. ${count(on)} of ${count(known.length).toLowerCase()} are on.`
        : 'All in one place.'
  const firstOff = items.find((i) => i.state === 'off')?.id

  return (
    <>
      <PageHeader title="Permissions" caption={caption} />
      <Group label="Permissions miyagi needs" inset={64}>
        {items.map((i) => (
          <Row
            key={i.id}
            minH={72}
            icon={i.icon}
            label={i.label}
            caption={i.caption}
            right={<Right item={i} primary={i.id === firstOff} />}
          />
        ))}
      </Group>
      {perms?.external ? (
        <Note>Your engine runs in Terminal, so macOS asks Terminal for these.</Note>
      ) : (
        <Note>{companion && fromHealth(companion) === 'off' ? 'Turn on opens System Settings at the right switch. Set up installs the extension.' : 'Turn on opens System Settings at the right switch.'}</Note>
      )}
    </>
  )
}

function Right({ item, primary }: { item: Item; primary: boolean }): ReactNode {
  if (item.state === 'loading') return <StatusGlyph state="checking" size={14} />
  if (item.state === 'on') return <OnWord />
  if (item.state === 'unknown')
    return (
      <span className="flex shrink-0 items-center gap-[8px]">
        <StatusGlyph state="unknown" size={12} />
        <StatusWord state="unknown" />
      </span>
    )
  const label = item.id === 'companion' ? 'Set up' : 'Turn on'
  const Button = primary ? PrimaryButtonV2 : QuietButton
  return (
    <div className="flex shrink-0 items-center gap-[16px]">
      <span className="flex items-center gap-[8px] whitespace-nowrap font-medium" style={{ fontSize: type2.xs, color: color.text }}>
        <StatusGlyph state="notyet" size={12} />
        Not yet
      </span>
      <Button label={label} onClick={() => item.fix?.()} />
    </div>
  )
}
