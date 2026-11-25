/**
 * Feature: settings. Shortcuts (Set-Shortcuts). Every keycap is live (core/ui/Keycap through core/keys.ts): the
 * platform's own (⌃⌥ on a Mac, Alt on Windows) or, for a rebound shortcut, the learner's own key in the same style.
 *
 * Explain, Hint, Show me and Diagram wear their pastel chip (theme.actionTone, options only); the rest are plain.
 * Watch has no shortcut this push (decision 3). Dismiss is fixed.
 *
 * Click a row, press new keys: the accelerator is validated (common/prefs isAccelerator, never a bare key, no clash with
 * another shortcut or the quit key) and saved to prefs.shortcuts. Main registers it at once (main/shortcutKeys.ts); when
 * another app owns it, main keeps the old key and the row says "Another app uses that key." Esc cancels the recording
 * before it closes the sheet. A rebound row has Reset (back to the default); "Reset all" clears every override.
 */
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import type { ShortcutKind } from '../../../../../main/platform'
import { bridge } from '../../../bridge'
import { savePrefs, usePrefs } from '../../../core/prefs'
import { Keycap } from '../../../core/ui/atoms'
import { actionTone, color, fill, radius2, type2 } from '../../../core/theme'
import { canRecord, stage } from '../env'
import { clashLine, conflictWith, isShortcutKind, record, SHORTCUT_ROWS, withShortcut, type ShortcutRow } from '../shortcuts'
import { Group, PageHeader, TextButton } from '../ui'

const mac = bridge.platform.os === 'mac'

export function Shortcuts(): ReactNode {
  const stored = usePrefs((s) => s.shortcuts)
  const [recording, setRecording] = useState<ShortcutKind | undefined>(canRecord && isShortcutKind(stage.record) ? stage.record : undefined)
  const [problem, setProblem] = useState<string>()
  const any = Object.keys(stored).length > 0

  const start = (k: ShortcutKind): void => {
    setProblem(undefined)
    setRecording(k)
  }
  const cancel = (): void => {
    setProblem(undefined)
    setRecording(undefined)
  }
  const save = async (k: ShortcutKind, value: string): Promise<void> => {
    const clash = conflictWith(value, k, bridge.platform.accelerators, stored, mac)
    if (clash) return setProblem(clashLine(clash))
    // prefs.shortcuts replaces the whole map on prefs:set: send all of it. Main answers with what it kept.
    const saved = await savePrefs({ shortcuts: withShortcut(stored, k, value) })
    if (saved && saved.shortcuts[k] !== value) return setProblem(clashLine('taken'))
    cancel()
  }
  const reset = (k: ShortcutKind): void => {
    cancel()
    void savePrefs({ shortcuts: withShortcut(stored, k, undefined) })
  }
  const resetAll = (): void => {
    cancel()
    void savePrefs({ shortcuts: {} })
  }

  return (
    <>
      <PageHeader
        title="Shortcuts"
        caption={canRecord ? 'Click a shortcut, then press the new keys.' : 'Shortcuts work while miyagi is open, in any app.'}
        right={canRecord && any ? <TextButton label="Reset all" onClick={resetAll} /> : undefined}
      />
      <Group label="Keyboard shortcuts">
        {SHORTCUT_ROWS.map((r) => {
          const kind = isShortcutKind(r.key) ? r.key : undefined
          return (
            <Line
              key={r.key}
              row={r}
              override={kind ? stored[kind] : undefined}
              recording={!!kind && recording === kind}
              problem={kind && recording === kind ? problem : undefined}
              onStart={kind && canRecord && !r.fixed ? () => start(kind) : undefined}
              onReset={kind && canRecord && stored[kind] ? () => reset(kind) : undefined}
              onCancel={cancel}
              onRecorded={(v) => kind && void save(kind, v)}
              onProblem={setProblem}
            />
          )
        })}
      </Group>
      <p className="m-0" style={{ fontSize: type2.xs, color: color.label }}>
        Shortcuts work while miyagi is open, in any app.
      </p>
    </>
  )
}

function Line({
  row,
  override,
  recording,
  problem,
  onStart,
  onReset,
  onCancel,
  onRecorded,
  onProblem
}: {
  row: ShortcutRow
  override?: string
  recording: boolean
  problem?: string
  onStart?: () => void
  onReset?: () => void
  onCancel: () => void
  onRecorded: (accelerator: string) => void
  onProblem: (p: string | undefined) => void
}): ReactNode {
  const box = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (recording) box.current?.focus({ preventScroll: true })
  }, [recording])

  const onKey = (e: KeyboardEvent<HTMLButtonElement>): void => {
    if (!recording) return
    e.preventDefault()
    e.stopPropagation() // never reaches the stage's shortcuts or the sheet's Esc
    if (e.key === 'Escape') return onCancel()
    const r = record(e, mac)
    if (r.kind === 'accelerator') onRecorded(r.value)
    else if (r.kind === 'invalid') onProblem(r.reason)
  }

  const label = row.option ? (
    <span className="inline-flex h-[24px] items-center px-[10px] font-medium" style={{ borderRadius: radius2.round, background: actionTone[row.option], color: color.onPastel, fontSize: type2.xs }}>
      {row.label}
    </span>
  ) : (
    <span className="font-medium" style={{ fontSize: type2.sm, color: color.text }}>
      {row.label}
    </span>
  )

  return (
    <div
      data-shortcut-row={row.key}
      data-override={override ? '' : undefined}
      className="flex min-h-[48px] items-center justify-between gap-[12px] pl-[16px] pr-[8px]"
      style={{ background: recording ? fill.group : undefined }}
    >
      <div className="flex min-w-0 flex-col gap-[2px] py-[6px]">
        {label}
        {recording && problem && (
          <span role="status" style={{ fontSize: type2.xs, color: color.text }}>
            {problem}
          </span>
        )}
      </div>
      {recording ? (
        <div className="flex items-center gap-[8px]">
          <TextButton label="Cancel" onClick={onCancel} />
          <button
            ref={box}
            type="button"
            aria-label={`Recording new shortcut for ${row.label}`}
            className="flex h-[36px] min-w-[144px] items-center justify-between gap-[8px] px-[12px] outline-none"
            style={{ borderRadius: radius2.control, background: fill.segmentTrack, boxShadow: `inset 0 0 0 2px ${color.text}`, color: fill.chipText, fontSize: type2.xs }}
            onKeyDown={onKey}
          >
            Press new keys
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-[4px]">
          {onReset && <TextButton label="Reset" onClick={onReset} />}
          <button
            type="button"
            aria-label={onStart ? `Change shortcut for ${row.label}` : `${row.label} shortcut`}
            disabled={!onStart}
            className="flex h-[36px] min-w-[88px] cursor-pointer items-center justify-end gap-[4px] px-[8px] disabled:cursor-default"
            style={{ borderRadius: radius2.control }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={onStart}
          >
            <Keycap k={row.key} size="md" />
          </button>
        </div>
      )}
    </div>
  )
}
