/**
 * Build-time feature flags, shared by main and the renderer.
 *
 * VOICE_ENABLED (Michael, Nov 20): voice is off for now (the computer's own voice read as obnoxious; ElevenLabs may
 * come later). While false: no Voice button or keycap anywhere (lesson panel, shortcut bar, settings, spotlight), the
 * voice shortcut is never registered, nothing is ever spoken, and the app never grants the microphone. The voice code
 * stays in place: flip this to true to bring it all back.
 */
export const VOICE_ENABLED = false

/**
 * LOGIN_ENABLED (Michael, Nov 20): first-run login is on. The first launch goes intro → miyagi login → guided setup →
 * home. "Continue without an account" is always there, and the login never shows on launch again once the learner has
 * signed in or chosen to go on without one. Separate from v2Cloud: the plans, pricing and usage mock stays behind
 * v2Cloud=false. MIYAGI_LOGIN=0 turns it off for one run (main/features/auth.ts).
 */
export const LOGIN_ENABLED = true
