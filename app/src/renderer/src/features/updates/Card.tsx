/**
 * Feature: updates. The card that grows out of the island when a newer miyagi is out (never mid-lesson):
 *
 *   offer   "A new miyagi is ready."  What's new (folds open) · Later · Download (the ONE primary)
 *   steps   after Download: how to install (quit, open the download, replace, Open Anyway) · Not now · Quit miyagi
 *
 * No status hue: nothing here passed or failed. The bonsai and the version head the card; Esc means Later.
 */
import { useEffect, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { motion } from 'motion/react'
import { color, copy, fill, font, radius2, spring, surface, type2 } from '../../core/theme'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import { MiyagiMark } from '../../core/ui/Mark'
import { formatSize, type UpdateView } from './manifest'
import { download, later, quitToInstall, setVisible, toggleNotes, useUpdates } from './store'

export const CARD_WIDTH = 400

function Head({ version }: { version: string }): ReactNode {
  return (
    <div className="flex min-h-[22px] items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <MiyagiMark size={18} />
        <span style={{ fontFamily: font.brand, fontSize: type2.md, fontWeight: 500 }}>{copy.name}</span>
        <span className="tabular-nums" style={{ fontFamily: font.mono, fontSize: type2.micro, color: color.label }}>
          {version}
        </span>
      </div>
      <Keycap k="dismiss" />
    </div>
  )
}

function Title({ id, title, body }: { id: string; title: string; body?: string }): ReactNode {
  return (
    <div className="flex flex-col" style={{ gap: 6 }}>
      <h2 id={id} className="m-0" style={{ fontSize: type2.lg, lineHeight: '22px', fontWeight: 600 }}>
        {title}
      </h2>
      {body && (
        <p className="m-0" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
          {body}
        </p>
      )}
    </div>
  )
}

function Caption({ children }: { children: ReactNode }): ReactNode {
  return (
    <p className="m-0" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>
      {children}
    </p>
  )
}

/** "What's new": a neutral disclosure row; the notes fold open under it. */
function Notes({ notes }: { notes: string[] }): ReactNode {
  const open = useUpdates((s) => s.notesOpen)
  if (!notes.length) return null
  return (
    <div className="flex flex-col" style={{ borderRadius: radius2.card, background: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}` }}>
      <button
        type="button"
        data-upd-notes-toggle
        aria-expanded={open}
        className="flex min-h-[40px] cursor-pointer items-center gap-2 text-left"
        style={{ padding: '0 12px', background: 'transparent', border: 'none', color: color.text, fontSize: type2.sm, fontWeight: 500 }}
        onMouseDown={(e) => e.preventDefault()}
        onClick={toggleNotes}
      >
        <motion.span className="flex" animate={{ rotate: open ? 90 : 0 }} transition={spring}>
          <ChevronRight size={14} strokeWidth={2} />
        </motion.span>
        {"What's new"}
      </button>
      {open && (
        <ul data-upd-notes className="m-0 flex list-none flex-col" style={{ padding: '0 12px 12px 34px', gap: 6 }}>
          {notes.map((n) => (
            <li key={n} className="relative" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.label }}>
              <span aria-hidden className="absolute" style={{ left: -12, top: 7, width: 4, height: 4, borderRadius: radius2.round, background: fill.ring }} />
              {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Offer({ view }: { view: UpdateView }): ReactNode {
  const busy = useUpdates((s) => s.busy)
  const failed = useUpdates((s) => s.openFailed)
  const latest = view.latest!
  const size = formatSize(latest.size)
  return (
    <>
      <Head version={latest.version} />
      <Title id="upd-title" title={`A new ${copy.name} is ready.`} body={`You have ${view.current}. Your lessons and progress stay as they are.`} />
      <Notes notes={latest.notes} />
      <div className="flex items-center gap-2">
        {/* Where it comes from and how big it is, one fact per line, so nothing wraps mid-word beside the buttons. */}
        <span data-upd-source className="mr-auto flex min-w-0 flex-col">
          {failed ? (
            <Caption>Could not open your browser. Try again.</Caption>
          ) : (
            <>
              {latest.host && <Caption>From {latest.host}</Caption>}
              {size && <Caption>{size}</Caption>}
            </>
          )}
        </span>
        <QuietButton size="lg" label="Later" disabled={busy === 'download'} onClick={() => void later()} />
        <PrimaryButton size="lg" label="Download" busy={busy === 'download'} onClick={() => void download()} />
      </div>
    </>
  )
}

function stepsFor(view: UpdateView): string[] {
  const file = view.latest?.file
  if (view.os === 'windows')
    return [`Quit ${copy.name}.`, `Run ${file ?? 'the installer'} from your Downloads.`, `Open ${copy.name} again.`]
  return [
    `Quit ${copy.name}.`,
    `Open ${file ?? 'the download'}, then drag ${copy.name} to Applications. Choose Replace.`,
    `Open ${copy.name}. If macOS stops it, choose Open Anyway in Privacy & Security.`
  ]
}

function Steps({ view }: { view: UpdateView }): ReactNode {
  const busy = useUpdates((s) => s.busy)
  return (
    <>
      <Head version={view.latest!.version} />
      <Title id="upd-title" title="Downloading in your browser." body="Three steps once it finishes." />
      <ol data-upd-steps className="m-0 flex list-none flex-col p-0" style={{ gap: 10 }}>
        {stepsFor(view).map((t, i) => (
          <li key={t} className="flex items-start gap-3" style={{ fontSize: type2.sm, lineHeight: '18px', color: color.text }}>
            <span
              aria-hidden
              className="flex shrink-0 items-center justify-center tabular-nums"
              style={{ width: 20, height: 20, marginTop: -1, borderRadius: radius2.round, background: fill.navActive, fontSize: type2.micro, fontWeight: 600, color: color.text }}
            >
              {i + 1}
            </span>
            <span>{t}</span>
          </li>
        ))}
      </ol>
      <div className="flex items-center justify-end gap-2">
        <QuietButton size="lg" label="Not now" disabled={busy === 'quit'} onClick={() => void later()} />
        <PrimaryButton size="lg" label={`Quit ${copy.name}`} busy={busy === 'quit'} onClick={() => void quitToInstall()} />
      </div>
    </>
  )
}

export function UpdateCard(): ReactNode {
  const view = useUpdates((s) => s.view)
  const steps = useUpdates((s) => s.steps)
  useEffect(() => {
    setVisible(true)
    return () => setVisible(false)
  }, [])
  if (!view?.latest) return null
  return (
    <div data-upd-card={steps ? 'steps' : 'offer'} role="dialog" aria-labelledby="upd-title" className="flex flex-col" style={{ padding: 20, gap: 16, color: color.text }}>
      {steps ? <Steps view={view} /> : <Offer view={view} />}
    </div>
  )
}
