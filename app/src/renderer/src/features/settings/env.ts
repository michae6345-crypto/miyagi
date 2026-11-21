/**
 * Feature: settings. Where the sheet runs and what this build turns on, in one place.
 *
 *   SECTIONS / isSection   the five sidebar sections (core/surfaces SettingsSection), validated (IPC input is untrusted)
 *   stage                  browser-stage params for the scenario shots: ?settings=<section>, ?record=<shortcut>,
 *                          ?confirm=delete. Always empty in Electron.
 *   canRecord              the shortcut recorder: off until live rebinding ships (wave 2); the rows are read-only
 *   v2Cloud                plan card and meter (Set-Account) only with an account; off this push (A9's flag)
 */
import { isElectron } from '../../bridge'
import type { SettingsSection } from '../../core/surfaces'
import { isSection, SECTIONS, type Section } from './keys'

export type { SettingsSection }
export { isSection, SECTIONS }

/** keys.ts's list and core's type must name the same sections. */
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never
const sameSections: Same<Section, SettingsSection> = true
void sameSections

const params = isElectron ? new URLSearchParams() : new URLSearchParams(location.search)
const sectionParam = params.get('settings')

export const stage = {
  /** Open the sheet on this section once the stage is up. */
  section: isSection(sectionParam) ? sectionParam : undefined,
  /** The shortcut row whose recorder starts armed (Set-Shortcuts). */
  record: params.get('record') ?? undefined,
  /** 'delete': Privacy starts on the in-place delete confirm. */
  confirm: params.get('confirm') ?? undefined
} as const

/**
 * The recorder stays off everywhere until live rebinding ships (persona QA: a recorded key that does nothing is a dead
 * end). Flip to `!isElectron` to work on it in the stage.
 */
export const canRecord = false

/** Account and plan (A9, `v2Cloud`): no sign-in, billing or quota this push, so the plan card never shows. */
export const v2Cloud = false
