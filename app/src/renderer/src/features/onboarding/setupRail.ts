/**
 * Feature: onboarding. What the v4 setup page shows beside and around a guided step (Guided.tsx), pure: no React, no
 * reads, no sends, so test/onboardingV4.test.ts checks it with node --test.
 *
 *   stepRail   the quiet rail's how-to: a label and two or three numbered lines (a name and one line under it), in
 *              miyagi's voice (calm, short, lowercase "miyagi", no em dash, 12 words a line at most). The engine has none.
 *   stepGroup  the live rows a step shows: both macOS grants side by side on either grant step (each with its check
 *              mark, Adrian's ui-next onboard-2), the step's own row otherwise.
 */
import type { Row } from './rows'

export type RailCopy = { title: string; lines: ReadonlyArray<readonly [name: string, line: string]> }

export function stepRail(row: Pick<Row, 'id' | 'action'>): RailCopy | undefined {
  if (row.id === 'screen')
    return {
      title: 'To turn on Screen Recording',
      lines: [
        ['Press Allow', 'System Settings opens.'],
        ['Switch miyagi on', 'Privacy & Security, then Screen Recording.'],
        ['Relaunch miyagi', 'macOS turns it on after a relaunch.']
      ]
    }
  if (row.id === 'accessibility')
    return {
      title: 'To turn on Accessibility',
      lines: [
        ['Open System Settings', 'The button on the left opens it.'],
        ['Switch miyagi on', 'Privacy & Security, then Accessibility.'],
        ['Come back here', 'This turns green by itself.']
      ]
    }
  if (row.id === 'companion')
    return {
      title: 'To connect VS Code',
      lines:
        row.action?.id === 'get-vscode'
          ? [
              ['Get VS Code', 'Install it, then open it once.'],
              ['Come back here', 'miyagi looks for it by itself.']
            ]
          : [
              ['Install in VS Code', 'One click, VS Code opens.'],
              ['Come back here', 'This turns green by itself.']
            ]
    }
  return undefined
}

const GRANTS: ReadonlyArray<Row['id']> = ['screen', 'accessibility']

export function stepGroup<R extends Pick<Row, 'id'>>(row: R, steps: readonly R[]): R[] {
  if (GRANTS.includes(row.id)) return steps.filter((s) => GRANTS.includes(s.id))
  return [row]
}
