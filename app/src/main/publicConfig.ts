/**
 * Public, committed configuration for the main process. Everything here is PUBLIC by design and safe to ship inside
 * the app: a packaged build signs in with no .env.
 *
 *   SUPABASE_URL              the miyagi Supabase project (Auth only for now)
 *   SUPABASE_PUBLISHABLE_KEY  its publishable ("anon") key. Supabase documents it as safe to expose in a client: it
 *                             only names the project, and row-level security decides what it may do.
 *
 * Never put a client secret, a service-role key or any other secret here (or anywhere in the app): Supabase holds the
 * Google client secret, and the app has no use for a service key.
 *
 * Override (another project, a local Supabase): MAIN_VITE_SUPABASE_URL / MAIN_VITE_SUPABASE_ANON_KEY at build time
 * (electron-vite hands MAIN_VITE_* to the main bundle). The same names in the process environment count only for an
 * unpackaged dev run: a shipped app never lets an environment variable (launchctl setenv) send the sign-in or the
 * stored refresh token to another host.
 */
import { app } from 'electron'

export const SUPABASE_URL = 'https://wssdpsdbaqtnfhoyimit.supabase.co'
export const SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_ZWGvj_p4OtGo34Itmh9lOQ_XeGi4F2v'

/** The committed project's host (safeOpen's allowlist entry for Google sign-in's start page). */
export const SUPABASE_HOST = new URL(SUPABASE_URL).hostname

/** The Supabase project this build talks to: a build-time override, a dev-run env override, else the values above. */
export function supabaseConfig(): { url: string; key: string } {
  const env = import.meta.env as Record<string, string | undefined>
  const runtime = !app.isPackaged
  const pick = (name: string, fallback: string): string => (env[name] || (runtime ? process.env[name] : undefined) || fallback).trim()
  return { url: pick('MAIN_VITE_SUPABASE_URL', SUPABASE_URL).replace(/\/+$/, ''), key: pick('MAIN_VITE_SUPABASE_ANON_KEY', SUPABASE_PUBLISHABLE_KEY) }
}
