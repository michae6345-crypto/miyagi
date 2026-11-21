/**
 * Feature: settings. One glossary for the names that drift between surfaces (persona QA, round 3). Settings uses
 * these; onboarding, account and the limit card should import them too (agents/settings.md, Core requests).
 */
/** The bring-your-own-key feature, everywhere: sidebar, heading, account menu, upgrade, pricing. */
export const OWN_KEY = 'Your own key'
/** The VS Code extension that runs cells and reports back. */
export const COMPANION = 'VS Code companion'

/** One description per permission, shared by onboarding, the recovery card and Settings. */
export const PERMISSION_COPY = {
  screen: { label: 'Screen Recording', caption: 'Lets miyagi see which step you are on.' },
  accessibility: { label: 'Accessibility', caption: 'Lets miyagi point at the real button.' },
  companion: { label: COMPANION, caption: 'Lets miyagi run your cells to check your work.' }
} as const
