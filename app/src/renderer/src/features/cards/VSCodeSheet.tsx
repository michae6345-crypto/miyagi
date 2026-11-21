/**
 * v2 (A2): Err-VSCodeSetup. A setup card whose only missing pieces are the editor and its miyagi helper extension
 * becomes this sheet, grown from the pill like every card (352 wide):
 *
 *   [bonsai] miyagi                                    ✕
 *   One thing left before the lesson.
 *   The helper lets miyagi run and check your code.
 *   ┌ (✓) Visual Studio Code       Found in Applications ┐
 *   └ ( ) miyagi helper extension  Not yet installed     ┘
 *   [            Install extension            ]   the one white primary (lg)
 *   No terminal. VS Code reloads once, your files stay open.
 *
 * VS Code itself missing ("VS Code not found"): "miyagi needs VS Code to teach this." with Get VS Code (its download
 * page). VS Code copy only: every editor label goes through copy.editorName, which never names an unsupported editor.
 * The rows' rings carry no hue: a white ring missing, a ring with a white tick present (green stays for passed).
 * Anything else missing (Python, a package), or a missing row with nothing to press (install.method "none"), keeps the
 * regular setup card.
 */
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { color, copy, fill, radius2, status, type2 } from '../../core/theme'
import { CloseButton, PrimaryButtonV2 } from '../../core/ui/atoms'
import { MiyagiMark } from '../../core/ui/Mark'
import { cardAct, engineInstalls, itemDone, useCards, type Install } from './store'
import { copySetupLink, openSetupLink, useRefusedLinks } from '../drawer/store'

type EngineCard = Payload<'card'>
type SetupItem = NonNullable<EngineCard['setup']>['items'][number]

/** The sheet's width (Err-VSCodeSetup). */
export const SHEET_W = 352

/** The helper extension's row: the engine names it by tool id or label (companion / vscode-ext / "helper extension"). */
const HELPER = /companion|vscode[-_ ]?ext|miyagi[-_ ]?helper|helper extension/i
const isHelper = (x: SetupItem): boolean => HELPER.test(x.tool) || HELPER.test(x.label)
/** The editor itself (VS Code), never its helper even when the engine files the helper under kind "editor". */
const isEditor = (x: SetupItem): boolean => x.kind === 'editor' && !isHelper(x)

/** The card actions the sheet itself covers: its install button and its ✕ (Skip). */
const SHEET_ACTIONS = new Set<string>(['install', 'install_all', 'skip_setup'])

/**
 * What the sheet's one button can do for a missing row: open its download page, open it in the browser, or have the
 * engine install it (pip / brew / brew_cask, the same rows the setup card's Install covers). Method "none" (or a
 * download with no url) has nothing to press: sending `install` for it would spin "Installing helper" with no answer.
 */
const canAct = (x: SetupItem): boolean => (x.install.method === 'download' && !!x.install.url) || x.install.method === 'open' || engineInstalls(x)

/**
 * Is this setup card the VS Code sheet? Only the editor and / or its helper are missing, each with something the sheet's
 * button can do (canAct), and the card offers nothing the sheet would drop: no where line, no tutorial files
 * (setup.resources, Download), no action past install / Skip. Anything else keeps the regular setup card (its labels
 * go through copy.editorName too), which never offers Install for a method-"none" row.
 */
export function isEditorSheet(c: EngineCard | undefined, installs: Record<string, Install> = {}): boolean {
  if (!c || c.kind !== 'setup' || !c.setup) return false
  if (c.where || c.setup.resources?.length || !(c.actions ?? []).every((a) => SHEET_ACTIONS.has(a))) return false
  const missing = c.setup.items.filter((x) => x.needed && !itemDone(x, installs))
  return missing.length > 0 && missing.every((x) => (isEditor(x) || isHelper(x)) && canAct(x))
}

/** A label we show: never an unsupported editor's name (copy.editorName). */
const safeLabel = (x: SetupItem): string => {
  const guarded = copy.editorName(x.label)
  if (isEditor(x)) return guarded
  // A helper label that names an unsupported editor (the guard rewrote it): our own name for the helper instead.
  return guarded === x.label.trim() ? x.label : 'miyagi helper extension'
}

/** One row's glyph: a hollow white ring (missing, no hue) or a muted ring with a white tick (there). */
function RowGlyph({ done }: { done: boolean }): ReactNode {
  return (
    <svg aria-hidden width="18" height="18" viewBox="0 0 18 18" className="shrink-0">
      <circle cx="9" cy="9" r="7.2" fill="none" stroke={done ? color.label : status.notYet} strokeWidth="1.6" />
      {done && <path d="M5.4 9.2 L7.8 11.5 L12.6 6.6" fill="none" stroke={color.text} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />}
    </svg>
  )
}

function rowDetail(x: SetupItem, done: boolean, run?: Install): string {
  const refused = done ? undefined : useRefusedLinks.getState().byTool[x.tool]
  if (refused !== undefined) return refused ? `Not on miyagi's list, so not opened: ${refused}` : 'Not a web link, so not opened.'
  if (run?.running) return run.line ?? 'Installing'
  if (run?.error) return run.error
  if (done) return isEditor(x) ? (bridge.platform.os === 'mac' ? 'Found in Applications' : 'Installed') : x.version ? `Version ${x.version}` : 'Installed'
  return isEditor(x) ? 'Not found' : 'Not yet installed'
}

/**
 * The row's button: a download page opens here, an "open" row opens in the browser, and only a row the engine installs
 * (pip / brew / brew_cask) sends `install`. isEditorSheet keeps any other row off the sheet, so nothing here can spin
 * with no answer coming.
 */
function act(x: SetupItem): void {
  // The engine's URL goes to main's setup list, never window.open; a refused one is copied instead (app-harden).
  const refused = useRefusedLinks.getState().byTool[x.tool]
  if (x.install.method === 'download' && refused !== undefined) void copySetupLink(refused)
  else if (x.install.method === 'download' && x.install.url) openSetupLink(x.tool, x.install.url)
  else if (x.install.method === 'open') cardAct('open_in_browser', x.tool)
  else if (engineInstalls(x)) cardAct('install', x.tool)
}

/**
 * The sheet's ✕. When the card lists skip_setup it is the old card's Skip: the engine hears skip_setup (clears its
 * setup card so the Start card may go out, releases the start hold) and the card closes. Otherwise a plain dismiss.
 */
function SheetClose({ skip }: { skip: boolean }): ReactNode {
  if (!skip) return <CloseButton />
  return (
    <button
      className="grid h-[22px] w-[22px] cursor-pointer place-items-center rounded-full text-white/60 hover:text-white"
      style={{ background: fill.key }}
      onClick={() => cardAct('skip_setup')}
      aria-label="Skip setup"
      title="Skip setup"
    >
      <X size={12} strokeWidth={2.2} />
    </button>
  )
}

export function VSCodeSheet({ card }: { card: EngineCard }): ReactNode {
  const installs = useCards((s) => s.installs)
  const refused = useRefusedLinks((s) => s.byTool) // re-render when main refuses a download link (rowDetail, label)
  const items = (card.setup?.items ?? []).filter((x) => x.needed && (isEditor(x) || isHelper(x)))
  const missing = items.filter((x) => !itemDone(x, installs))
  // VS Code first: the helper can't go in without it.
  const editorMissing = missing.find(isEditor)
  const next = editorMissing ?? missing[0]
  const run = next ? installs[next.tool] : undefined
  const busy = !!run?.running
  const title = editorMissing ? 'miyagi needs VS Code to teach this.' : missing.length > 1 ? 'Two things left before the lesson.' : 'One thing left before the lesson.'
  const body = editorMissing ? 'Install it and miyagi picks up on its own.' : 'The helper lets miyagi run and check your code.'
  const label = next && next.install.method === 'download' && refused[next.tool] !== undefined ? 'Copy link' : editorMissing ? 'Get VS Code' : busy ? 'Installing helper' : run?.error ? 'Try again' : 'Install extension'
  return (
    <div data-card="setup" data-sheet="vscode" role="dialog" aria-labelledby="miyagi-vscode-sheet" className="flex flex-col gap-[20px] p-[24px]">
      <div className="flex h-[22px] items-center gap-[8px]">
        <MiyagiMark size={18} />
        <span className="font-medium" style={{ fontSize: type2.md, color: color.text }}>
          {copy.name}
        </span>
        <span className="flex-1" />
        <SheetClose skip={(card.actions ?? []).includes('skip_setup')} />
      </div>
      <div className="flex flex-col gap-[6px]">
        <h2 id="miyagi-vscode-sheet" className="m-0 font-semibold leading-[22px]" style={{ fontSize: type2.lg, color: color.text }}>
          {title}
        </h2>
        <p className="m-0 leading-[18px]" style={{ fontSize: type2.sm, color: color.label }}>
          {body}
        </p>
      </div>
      <ul className="m-0 flex list-none flex-col p-0" style={{ borderRadius: radius2.card, boxShadow: `inset 0 0 0 1px ${fill.hairline}` }}>
        {items.map((x, i) => {
          const r = installs[x.tool]
          const done = itemDone(x, installs)
          return (
            <li
              key={x.tool}
              data-setup-row={x.tool}
              className="flex items-center gap-[12px] px-[16px] py-[12px]"
              style={i < items.length - 1 ? { borderBottom: `1px solid ${fill.hairline}` } : undefined}
            >
              <RowGlyph done={done} />
              <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
                <span className="truncate font-medium" style={{ fontSize: type2.sm, color: color.text }}>
                  {safeLabel(x)}
                </span>
                <span className="line-clamp-2" style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }} title={rowDetail(x, done, r)}>
                  {rowDetail(x, done, r)}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
      {next && (
        <div className="flex flex-col gap-[8px]">
          {/* Busy keeps full strength with the spinner (never look dead); a second press is a no-op (store cardAct). */}
          <PrimaryButtonV2 size="lg" block label={label} busy={busy} onClick={() => act(next)} />
          {!editorMissing && (
            <p className="m-0 text-center leading-[16px]" style={{ fontSize: type2.micro, color: color.label }}>
              No terminal. VS Code reloads once, your files stay open.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
