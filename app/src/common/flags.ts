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

/**
 * PTT_ENABLED (Michael, Nov 21): push to talk. Hold the chord (Fn+Control, or Control+Option), say a question, let go:
 * miyagi gets it as an ask. Speech turns into text on this Mac (the miyagi-listen helper, main/features/ptt.ts); miyagi
 * never talks back, so it is separate from VOICE_ENABLED (text to speech), which stays false. Off = no helper is
 * started, no settings row, no island state. The learner can also switch it off in Settings > General (prefs.ptt).
 *
 * Off for launch (Adrian, Nov 21): it asks for Microphone and Input Monitoring, listens to the chord across the whole
 * session, and sends the words to Anthropic, and nothing tells the learner yet (the consent screen, policy and site
 * never mention it; #188 says miyagi never uses the microphone). Launch register R05/R06. Turn it back on once it's
 * disclosed there.
 */
export const PTT_ENABLED = false

/**
 * GEMINI_ENABLED (Adrian, Nov 21, decision D1): Claude only at launch, no Gemini. While false the app names only
 * Anthropic (Claude): the consent screen, Settings > Privacy (the Lesson videos row) and Your own key, where the Gemini
 * key field is hidden. The Gemini code stays in place (config.keys still carries every name, so the engine's
 * set_app_keys keeps working): flip this to true to bring the field and the Google lines back.
 */
export const GEMINI_ENABLED = false
