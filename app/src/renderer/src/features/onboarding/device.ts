/**
 * Feature: onboarding. The words that change between a Mac and a Windows PC, in one place, so setup, the login and
 * You're ready read the same on both (Adrian, Nov 21: "consistent for windows and mac, not just mac").
 *
 *   Mac      "this Mac", System Settings, Terminal; setup asks for Screen Recording and Accessibility
 *   Windows  "this PC", no permission steps (Windows has no such grants to ask for), PowerShell
 *
 * The OS comes from bridge.platform (main/platform.ts; the stage takes ?os=win). Pure helpers over that one value.
 */
import { bridge } from '../../bridge'

export type Os = 'mac' | 'win'

export const osNow = (): Os => (bridge.platform?.os === 'win' ? 'win' : 'mac')

/** "this Mac" / "this PC": every place setup names the computer. */
export const thisDevice = (os: Os = osNow()): string => (os === 'win' ? 'this PC' : 'this Mac')

/** Where an engine started by hand runs: macOS Terminal, Windows PowerShell. */
export const shellName = (os: Os = osNow()): string => (os === 'win' ? 'PowerShell' : 'Terminal')

/** Screen Recording and Accessibility are macOS grants. Windows has nothing to ask for, so those steps don't exist there. */
export const needsGrants = (os: Os = osNow()): boolean => os === 'mac'
