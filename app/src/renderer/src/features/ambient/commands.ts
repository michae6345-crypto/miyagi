/**
 * Feature: ambient. The launcher's two commands (features/launcher shows one row for them, like its Settings row):
 *
 *   "Set up this project"  typed "set up this project", "install dependencies", "check my environment"…: setup.scan
 *                          for the folder open in the front editor; the setup card grows out of the island.
 *   "Show me in <App>"     a "how do I …" / "where is …" typed outside a lesson: help.ask {text, app}, then bon points at
 *                          each step. `app` is the app that was in front before the launcher (main's front-app reading;
 *                          the launcher is a non-activating panel, so that is still the learner's app).
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
