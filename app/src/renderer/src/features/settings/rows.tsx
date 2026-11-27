/**
 * Feature: settings. The settings added to the sheet and the Settings page, as data: one list the panels render and the
 * search reads, so a setting can never be findable without being on its panel (or the other way round).
 *
 * Every control is one of: real (it changes behavior or persists a preference some code reads), read-only (a fact), or
 * `soon` (muted, not pressable, with its default shown). Nothing here does nothing without saying so.
 *
 * Real today: theme (core prefs), text size, density, reduce motion, sidebar, code samples, confirm skip and time left
 * (local.ts, applied by apply.ts or read where used), video speed and volume (the player's own saved record), tips, the start page
 * (apply.ts), sounds and the primary-press tap (features/sound), reminders (features/reminders), export progress,
 * reset tips, check for updates, open-source licenses (LicensesView.tsx), send feedback.
 */
import { ChevronDown } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { setPrefs, usePrefs, type Appearance } from '../../core/prefs'
import { color, fill, radius2, type2 } from '../../core/theme'
import { QuietButton, Toggle } from '../../core/ui/atoms'
import { useDash } from '../dashboard/store'
import { useProgress } from '../progress/store'
import { RemindersGroup } from '../reminders/Settings'
import { reachableInSettings } from '../reminders/store'
import { setSoundMode, setSoundTaps, useSound } from '../sound/settings'
import { resetTips, turnTipsOff, turnTipsOn, useTips } from '../tips/store'
import { checkNow, useUpdates } from '../updates/store'
import { openLicenses } from './licenses'
import { CODE_SIZES, DENSITIES, MOTIONS, START_PAGES, TEXT_SIZES, progressJson, resetLocal, setLocal, useLocal, type Findable } from './local'
import { RATE_OPTIONS, VOLUMES, useVideoPref } from './videoPrefs'
import type { PanelId } from './panels'
import { Badge, Group, Plain, Row, Seg } from './ui'

// Every window loads every feature: this lets the one-time reminders offer show, now that Notifications holds its group.
reachableInSettings()

type Opt = { value: string; label: string; soon?: boolean }
type Pair<T> = () => [T, (v: T) => void]

type Control =
  | { kind: 'segmented'; options: readonly Opt[]; use: Pair<string> }
  | { kind: 'select'; options: readonly Opt[]; use: Pair<string> }
  | { kind: 'toggle'; use: Pair<boolean>; off?: () => boolean }
  | { kind: 'value'; text: string | (() => string) }
  | { kind: 'soon'; text: string }
  | { kind: 'button'; label: string; run: () => string | void; disabled?: () => boolean }
  | { kind: 'link'; label: string; href: string }

export type Setting = Findable & { panel: PanelId; group: string; control: Control }

/** Settings not switchable yet collect in one muted group at the foot of their panel. */
export const COMING = 'Coming soon'
const cap = (s: string): string => s[0].toUpperCase() + s.slice(1)
const opts = (list: readonly string[]): Opt[] => list.map((v) => ({ value: v, label: cap(v) }))

const APPEARANCES: Opt[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' }
]

export const SETTINGS: readonly Setting[] = [
  // ---- General ----
  {
    id: 'start-page',
    panel: 'general',
    group: 'Startup',
    label: 'Start page',
    caption: 'The page the home window opens on.',
    keywords: 'home default open launch library',
    control: { kind: 'select', options: START_PAGES.map((p) => ({ value: p, label: cap(p) })), use: () => [useLocal((s) => s.startPage), (v) => setLocal({ startPage: v as never })] }
  },
  {
    id: 'language',
    panel: 'general',
    group: 'Startup',
    label: 'Language',
    caption: 'Lessons and the app, in English for now.',
    keywords: 'locale translate spanish french german',
    control: {
      kind: 'select',
      options: [{ value: 'en', label: 'English' }, { value: 'es', label: 'Español', soon: true }, { value: 'fr', label: 'Français', soon: true }, { value: 'de', label: 'Deutsch', soon: true }],
      use: () => ['en', () => undefined]
    }
  },
  // ---- Appearance ----
  {
    id: 'theme',
    panel: 'appearance',
    group: 'Look',
    label: 'Theme',
    caption: 'Applies everywhere.',
    keywords: 'dark light system appearance mode',
    control: { kind: 'segmented', options: APPEARANCES, use: () => [usePrefs((s) => s.appearance), (v) => setPrefs({ appearance: v as Appearance })] }
  },
  {
    id: 'text-size',
    panel: 'appearance',
    group: 'Look',
    label: 'Text size',
    caption: 'Scales the home window and its pages.',
    keywords: 'font zoom bigger smaller accessibility',
    control: { kind: 'segmented', options: opts(TEXT_SIZES), use: () => [useLocal((s) => s.textSize), (v) => setLocal({ textSize: v as never })] }
  },
  {
    id: 'density',
    panel: 'appearance',
    group: 'Look',
    label: 'Density',
    caption: 'Compact fits more rows on screen.',
    keywords: 'spacing rows tight comfortable',
    control: { kind: 'segmented', options: opts(DENSITIES), use: () => [useLocal((s) => s.density), (v) => setLocal({ density: v as never })] }
  },
  {
    id: 'reduce-motion',
    panel: 'appearance',
    group: 'Motion',
    label: 'Reduce motion',
    caption: 'Fewer movements. Also follows your Mac’s setting.',
    keywords: 'animation accessibility transitions',
    control: { kind: 'toggle', use: () => [useLocal((s) => s.motion === 'reduce'), (v) => setLocal({ motion: v ? 'reduce' : MOTIONS[0] })] }
  },
  {
    id: 'sidebar-compact',
    panel: 'appearance',
    group: 'Sidebar',
    label: 'Compact sidebar',
    caption: 'Icons only, at any window size.',
    keywords: 'navigation collapse narrow icons',
    control: { kind: 'toggle', use: () => [useLocal((s) => s.sidebarCompact), (v) => setLocal({ sidebarCompact: v })] }
  },
  {
    id: 'sidebar-status',
    panel: 'appearance',
    group: 'Sidebar',
    label: 'Show setup status',
    caption: 'The ready line under the pages.',
    keywords: 'navigation ready health',
    control: { kind: 'toggle', use: () => [useLocal((s) => s.sidebarStatus), (v) => setLocal({ sidebarStatus: v })] }
  },
  // ---- Lessons ----
  {
    id: 'confirm-skip',
    panel: 'lessons',
    group: 'Help',
    label: 'Confirm before skipping a step',
    caption: 'The button asks for a second press.',
    keywords: 'skip step safety',
    control: { kind: 'toggle', use: () => [useLocal((s) => s.confirmSkip), (v) => setLocal({ confirmSkip: v })] }
  },
  {
    id: 'time-left',
    panel: 'lessons',
    group: 'Help',
    label: 'Show time left',
    caption: 'An estimate beside your step count.',
    keywords: 'minutes progress estimate steps panel',
    control: { kind: 'toggle', use: () => [useLocal((s) => s.timeLeft), (v) => setLocal({ timeLeft: v })] }
  },
  {
    id: 'tips',
    panel: 'lessons',
    group: 'Help',
    label: 'Show tips as you learn',
    caption: 'Short first-time hints. Each shows once.',
    keywords: 'coach tour hints onboarding',
    control: { kind: 'toggle', use: () => [useTips((s) => !s.off), (v) => (v ? turnTipsOn() : turnTipsOff())] }
  },
  {
    id: 'speed',
    panel: 'lessons',
    group: 'Video',
    label: 'Playback speed',
    caption: 'Where your next video starts.',
    keywords: 'rate faster slower',
    control: { kind: 'select', options: RATE_OPTIONS.map((r) => ({ value: String(r), label: `${r}x` })), use: () => { const [v, set] = useVideoPref('rate'); return [String(v), (x) => set(Number(x))] } }
  },
  {
    id: 'video-volume',
    panel: 'lessons',
    group: 'Video',
    label: 'Video volume',
    caption: 'Where your next video starts.',
    keywords: 'loud quiet sound audio',
    control: { kind: 'select', options: VOLUMES.map((v) => ({ value: String(v), label: v === 0 ? 'Muted' : `${v}%` })), use: () => { const [v, set] = useVideoPref('volume'); return [String(v), (x) => set(Number(x))] } }
  },
  { id: 'hint-style', panel: 'lessons', group: COMING, label: 'Hint style', caption: 'Start with a nudge, or go straight to an example.', keywords: 'hint show example nudge', control: { kind: 'soon', text: 'Nudge first' } },
  { id: 'auto-advance', panel: 'lessons', group: COMING, label: 'Move on after a passed check', caption: 'The video continues on its own.', keywords: 'auto advance next', control: { kind: 'soon', text: 'Off' } },
  { id: 'pause-video', panel: 'lessons', group: COMING, label: 'Pause the video while you code', caption: 'It waits at each step already.', keywords: 'video player', control: { kind: 'soon', text: 'On' } },
  { id: 'captions', panel: 'lessons', group: COMING, label: 'Captions', caption: 'Show captions when a video has them.', keywords: 'subtitles cc', control: { kind: 'soon', text: 'On' } },
  // ---- Editor ----
  { id: 'default-editor', panel: 'editor', group: 'Editor', label: 'Default editor', caption: 'Lessons open and check your files here.', keywords: 'vscode code', control: { kind: 'value', text: 'VS Code' } },
  {
    id: 'code-size',
    panel: 'editor',
    group: 'Code samples',
    label: 'Code sample size',
    caption: 'Text size inside lesson cards.',
    keywords: 'font monospace',
    control: { kind: 'segmented', options: opts(CODE_SIZES), use: () => [useLocal((s) => s.codeSize), (v) => setLocal({ codeSize: v as never })] }
  },
  {
    id: 'line-numbers',
    panel: 'editor',
    group: 'Code samples',
    label: 'Line numbers',
    caption: 'Number the lines of every sample.',
    keywords: 'gutter',
    control: { kind: 'toggle', use: () => [useLocal((s) => s.lineNumbers), (v) => setLocal({ lineNumbers: v })] }
  },
  {
    id: 'wrap-code',
    panel: 'editor',
    group: 'Code samples',
    label: 'Wrap long lines',
    caption: 'Otherwise a long line scrolls sideways.',
    keywords: 'overflow scroll',
    control: { kind: 'toggle', use: () => [useLocal((s) => s.wrapCode), (v) => setLocal({ wrapCode: v })] }
  },
  // ---- Notifications ----
  { id: 'reminders', panel: 'notifications', group: 'Reminders', label: 'Review reminders', caption: 'A daily nudge at a time you pick, only when something is due.', keywords: 'daily time quiet hours pause notify', control: { kind: 'value', text: '' } },
  { id: 'weekly-recap', panel: 'notifications', group: COMING, label: 'Weekly recap on Monday', caption: 'What you passed last week.', keywords: 'summary email digest', control: { kind: 'soon', text: 'Off' } },
  {
    id: 'sounds',
    panel: 'notifications',
    group: 'Sounds',
    label: 'Sounds',
    caption: 'A soft tick for each step, a chime when a lesson is done.',
    keywords: 'audio chime tick',
    control: { kind: 'segmented', options: [{ value: 'off', label: 'Off' }, { value: 'subtle', label: 'Subtle' }], use: () => [useSound((s) => s.mode), (v) => setSoundMode(v as 'off' | 'subtle')] }
  },
  {
    id: 'sound-taps',
    panel: 'notifications',
    group: 'Sounds',
    label: 'Sound on the main button',
    caption: 'A small click on each primary press.',
    keywords: 'audio tap press',
    control: { kind: 'toggle', use: () => [useSound((s) => s.taps), (v) => setSoundTaps(v)], off: () => useSound((s) => s.mode === 'off') }
  },
  // ---- Storage and data ----
  {
    id: 'export-progress',
    panel: 'storage',
    group: 'Your data',
    label: 'Export my progress',
    caption: 'A JSON file of your skills and finished lessons.',
    keywords: 'download backup json',
    control: { kind: 'button', label: 'Download', run: exportProgress }
  },
  {
    id: 'reset-tips',
    panel: 'storage',
    group: 'Your data',
    label: 'Reset onboarding tips',
    caption: 'Show every first-time tip again.',
    keywords: 'tour help coach',
    control: { kind: 'button', label: 'Reset', run: () => (resetTips(), 'Done') }
  },
  {
    id: 'reset-local',
    panel: 'storage',
    group: 'Your data',
    label: 'Restore default settings',
    caption: 'Text size, density, sidebar and code samples.',
    keywords: 'reset preferences defaults',
    control: { kind: 'button', label: 'Restore', run: () => (resetLocal(), 'Done') }
  },
  { id: 'clear-cache', panel: 'storage', group: COMING, label: 'Lesson cache', caption: 'Clear downloaded lesson files.', keywords: 'clear delete disk space', control: { kind: 'soon', text: 'Clear' } },
  // ---- About ----
  {
    id: 'version',
    panel: 'about',
    group: 'miyagi',
    label: 'Version',
    caption: 'The build you are running.',
    keywords: 'build release',
    control: { kind: 'value', text: () => useUpdates.getState().view?.current ?? '' }
  },
  {
    id: 'updates',
    panel: 'about',
    group: 'miyagi',
    label: 'Check for updates',
    caption: 'miyagi also checks on its own.',
    keywords: 'upgrade new release',
    control: { kind: 'button', label: 'Check now', run: () => void checkNow() }
  },
  {
    id: 'licenses',
    panel: 'about',
    group: 'miyagi',
    label: 'Open-source licenses',
    caption: 'The fonts and code miyagi is built on.',
    keywords: 'legal third party font ofl copyright notices',
    control: { kind: 'button', label: 'View', run: openLicenses }
  },
  {
    id: 'feedback',
    panel: 'about',
    group: 'Say hello',
    label: 'Send feedback',
    caption: 'support@miyagi.study, read by the people who build it.',
    keywords: 'email bug idea contact support',
    control: { kind: 'link', label: 'Write to us', href: 'mailto:support@miyagi.study?subject=miyagi%20feedback' }
  }
]

/** Settings that live in panels rendered by their own components: searchable, no row here. */
export const ELSEWHERE: readonly Findable[] = [
  { id: 'island', panel: 'general', label: 'Island', caption: 'In the notch or below the menu bar.', keywords: 'notch pill place' },
  { id: 'launch-login', panel: 'general', label: 'Launch at login', caption: 'miyagi waits in the pill until you need it.', keywords: 'startup boot' },
  { id: 'push-to-talk', panel: 'general', label: 'Push to talk', caption: 'Hold to ask. Speech stays on this Mac.', keywords: 'voice microphone speak' },
  { id: 'setup', panel: 'general', label: 'Set up miyagi', caption: 'Check permissions and VS Code again.', keywords: 'onboarding tour' },
  { id: 'permissions', panel: 'permissions', label: 'Permissions', caption: 'Accessibility, screen and microphone.', keywords: 'macos accessibility screen recording' },
  { id: 'privacy', panel: 'privacy', label: 'What miyagi sees', caption: 'And what never leaves this Mac.', keywords: 'data crash reports telemetry' },
  { id: 'delete-data', panel: 'privacy', label: 'Delete my data', caption: 'Erase keys and local data.', keywords: 'erase remove' },
  { id: 'api-key', panel: 'account', label: 'Your own key', caption: 'Bring your own Anthropic key.', keywords: 'api anthropic secret' },
  { id: 'keyboard', panel: 'shortcuts', label: 'Keyboard shortcuts', caption: 'The keys that reach miyagi from anywhere.', keywords: 'keys hotkey' }
]

export const FINDABLE: readonly Findable[] = [...SETTINGS, ...ELSEWHERE]

// ---- actions ---------------------------------------------------------------------------------------------------------

/** Nothing to export until the progress or the dashboard has loaded: the row says so instead of writing an empty file. */
function haveProgress(): boolean {
  return !!(useProgress.getState().data ?? useDash.getState().data)
}

function exportProgress(): string {
  if (!haveProgress()) return 'Nothing yet'
  const json = progressJson({ dashboard: useDash.getState().data ?? null, progress: useProgress.getState().data ?? null })
  const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = 'miyagi-progress.json'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return 'Saved'
}

// ---- controls --------------------------------------------------------------------------------------------------------

export function Select({ label, options, value, onChange }: { label: string; options: readonly Opt[]; value: string; onChange: (v: string) => void }): ReactNode {
  return (
    <span className="relative inline-flex shrink-0 items-center">
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mg-press cursor-pointer appearance-none font-medium outline-none"
        style={{ height: 32, minWidth: 132, padding: '0 30px 0 12px', borderRadius: radius2.control, background: fill.segmentTrack, border: `1px solid ${fill.hairline}`, color: color.text, fontSize: type2.xs, fontFamily: 'inherit' }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.soon}>
            {o.soon ? `${o.label} (soon)` : o.label}
          </option>
        ))}
      </select>
      <ChevronDown aria-hidden size={13} strokeWidth={1.8} className="pointer-events-none absolute" style={{ right: 10, color: color.label }} />
    </span>
  )
}

function Soon({ text }: { text: string }): ReactNode {
  return (
    <span className="flex shrink-0 items-center gap-[8px]" style={{ opacity: 0.6 }}>
      <span className="whitespace-nowrap" style={{ fontSize: type2.xs, color: color.label }}>
        {text}
      </span>
      <Badge>Soon</Badge>
    </span>
  )
}

function ButtonControl({ c }: { c: Extract<Control, { kind: 'button' }> }): ReactNode {
  const [note, setNote] = useState<string>()
  return (
    <span className="flex shrink-0 items-center gap-[12px]">
      {note && (
        <span role="status" style={{ fontSize: type2.xs, color: color.label }}>
          {note}
        </span>
      )}
      <QuietButton
        label={c.label}
        disabled={c.disabled?.()}
        onClick={() => {
          const r = c.run()
          if (typeof r === 'string') {
            setNote(r)
            setTimeout(() => setNote(undefined), 2500)
          }
        }}
      />
    </span>
  )
}

/** The control on the right of a setting's row. Hooks run here, one component per row, so the list stays plain data. */
function Control({ s }: { s: Setting }): ReactNode {
  const c = s.control
  switch (c.kind) {
    case 'segmented':
      return <SegmentedControl s={s} c={c} />
    case 'select':
      return <SelectControl s={s} c={c} />
    case 'toggle':
      return <ToggleControl s={s} c={c} />
    case 'value':
      return <ValueControl c={c} />
    case 'soon':
      return <Soon text={c.text} />
    case 'button':
      return <ButtonControl c={c} />
    case 'link':
      return (
        <a className="mg-press inline-flex h-[36px] shrink-0 items-center px-[16px] font-medium" style={{ borderRadius: radius2.row, background: fill.segmentTrack, boxShadow: `inset 0 0 0 1px ${fill.hairline}`, color: color.text, fontSize: type2.sm }} href={c.href}>
          {c.label}
        </a>
      )
  }
}

function SegmentedControl({ s, c }: { s: Setting; c: Extract<Control, { kind: 'segmented' }> }): ReactNode {
  const [v, set] = c.use()
  return <Seg label={s.label} options={c.options} value={v} onChange={set} />
}
function SelectControl({ s, c }: { s: Setting; c: Extract<Control, { kind: 'select' }> }): ReactNode {
  const [v, set] = c.use()
  return <Select label={s.label} options={c.options} value={v} onChange={set} />
}
function ToggleControl({ s, c }: { s: Setting; c: Extract<Control, { kind: 'toggle' }> }): ReactNode {
  const [v, set] = c.use()
  return <Toggle label={s.label} on={v} onChange={set} disabled={c.off?.()} />
}
function ValueControl({ c }: { c: Extract<Control, { kind: 'value' }> }): ReactNode {
  // The version reads the updates view, so it re-renders when it arrives.
  useUpdates((u) => u.view?.current)
  const text = typeof c.text === 'function' ? c.text() : c.text
  return text ? <Badge>{text}</Badge> : null
}

/** A grouped block per `group` of this panel's settings, in list order. */
export function PanelRows({ panel }: { panel: PanelId }): ReactNode {
  const mine = SETTINGS.filter((s) => s.panel === panel)
  const groups = [...new Set(mine.map((s) => s.group))].filter((g) => g !== COMING)
  const coming = mine.filter((s) => s.group === COMING)
  return (
    <>
      {groups.map((g) => {
        const rows = mine.filter((s) => s.group === g)
        // Reminders have their own richer group (time, quiet hours, pause): it takes the place of the plain row.
        if (rows.some((r) => r.id === 'reminders')) {
          return (
            <div key={g} className="flex flex-col gap-[24px]">
              <RemindersGroup />
              {rows.filter((r) => r.id !== 'reminders').length > 0 && (
                <Group label={g}>{rows.filter((r) => r.id !== 'reminders').map((r) => <SettingRow key={r.id} s={r} />)}</Group>
              )}
            </div>
          )
        }
        return (
          <Group key={g} label={g} title={g}>
            {rows.map((r) => (
              <SettingRow key={r.id} s={r} />
            ))}
          </Group>
        )
      })}
      {coming.length > 0 && (
        <Group label={COMING} title={COMING} caption="Not switchable yet. miyagi uses the value shown.">
          {coming.map((r) => (
            <div key={r.id} data-setting={r.id} style={{ opacity: 0.6 }}>
              <Row minH={44} label={r.label} caption={r.caption} right={r.control.kind === 'soon' ? <Plain>{r.control.text}</Plain> : undefined} />
            </div>
          ))}
        </Group>
      )}
    </>
  )
}

/** One setting's row by id (the v4 Settings page composes its groups from these), with the page's own words if given. */
export function SettingRowById({ id, label, caption }: { id: string; label?: string; caption?: string }): ReactNode {
  const s = SETTINGS.find((x) => x.id === id)
  if (!s) return null
  return <SettingRow s={{ ...s, label: label ?? s.label, caption: caption ?? s.caption }} />
}

export function SettingRow({ s, withPanel }: { s: Setting; withPanel?: ReactNode }): ReactNode {
  return (
    <div data-setting={s.id}>
      <Row tight={s.control.kind === 'toggle'} label={s.label} caption={withPanel ?? s.caption} right={<Control s={s} />} />
    </div>
  )
}
