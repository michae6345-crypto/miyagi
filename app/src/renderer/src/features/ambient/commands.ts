/**
 * Feature: ambient. The launcher's two commands:
 *
 *   "Set up this project"  typed "set up this project", "install dependencies", "check my environment"… (the whole
 *                          phrase): setup.scan for the folder open in the front editor; the setup card grows out of
 *                          the island. It takes over the rows like the Settings row (placement 'takeover').
 *   "Show me in <App>"     a "how do I …" / "where is …" typed outside a lesson: help.ask {text, app}, then bon points at
 *                          each step. `app` is the app that was in front before the launcher (main's front-app reading;
 *                          the launcher is a non-activating panel, so that is still the learner's app). "how to train a
 *                          neural network" is also how learners ask for a lesson, so this one is one more row above the
 *                          search / lesson rows (placement 'extra'): Enter stays on the lesson, ⌘Enter still teaches,
 *                          and ↑ or Tab picks "Show me" (enterTarget, nextPick).
 * Each is offered only when the engine's hello lists its command (contract gate), never during a lesson.
 */
import { canSend } from '../../core/lesson'
import { useFront } from '../shortcut-bar/front'
import { clip, isHowDoI, isSetupQuery } from './model'
import { askHelp, scanProject } from './store'

export type AmbientCommand = { kind: 'setup' | 'help'; title: string; meta: string; text: string; app?: string }

/** The app to help with: the one in front, when it is a real app (not miyagi itself). */
export function helpApp(): string | undefined {
  const f = useFront.getState()
  return f.known && !f.miyagi && f.name ? f.name : undefined
}

/** The command the typed text asks for, if any. `lesson`: a lesson is loaded (ask mode belongs to it). */
export function ambientCommand(typed: string, lesson: boolean, app = helpApp()): AmbientCommand | undefined {
  const text = typed.trim()
  if (!text || lesson) return undefined
  if (isSetupQuery(text) && canSend('setup.scan'))
    return { kind: 'setup', title: 'Set up this project', meta: 'Find what it needs on this Mac', text }
  if (isHowDoI(text) && canSend('help.ask'))
    return { kind: 'help', title: app ? `Show me in ${clip(app, 24)}` : 'Show me in this app', meta: 'bon points at each step', text, app }
  return undefined
}

/** Run it. False: the engine can't take it now (the launcher keeps the text). */
export function runAmbientCommand(c: AmbientCommand): boolean {
  return c.kind === 'setup' ? scanProject() : askHelp(c.text, c.app)
}

/** 'takeover': the one row instead of the rest (setup). 'extra': one more row over the lesson / search rows (help). */
export function placement(c: AmbientCommand | undefined): 'takeover' | 'extra' | undefined {
  return c ? (c.kind === 'setup' ? 'takeover' : 'extra') : undefined
}

/**
 * What Enter in the launcher's field does while an ambient command is offered. `picked`: the learner moved onto the
 * extra row (↑ / Tab, or the pointer). `mod`: ⌘Enter (Ctrl+Enter), which is always "Just teach me" over an extra row.
 *   'ambient'  run the command      'teach'  ⌘Enter teaches what's typed      'rows'  the search / lesson rows decide
 */
export function enterTarget(c: AmbientCommand | undefined, picked: boolean, mod: boolean): 'ambient' | 'teach' | 'rows' {
  const where = placement(c)
  if (where === 'takeover') return 'ambient'
  if (mod) return 'teach'
  return where === 'extra' && picked ? 'ambient' : 'rows'
}

/**
 * Tab (Shift+Tab back) while the ways are offered: video, lesson, demo, then "Show me" when it is there, wrapping.
 * Returns the way to highlight, or 'ambient' for the extra row.
 */
export function nextPick<H extends string>(hows: readonly H[], how: H, picked: boolean, back: boolean, extra: boolean): H | 'ambient' {
  const stops: (H | 'ambient')[] = extra ? [...hows, 'ambient'] : [...hows]
  const at = stops.indexOf(picked && extra ? 'ambient' : how)
  return stops[(Math.max(0, at) + (back ? stops.length - 1 : 1)) % stops.length]
}
