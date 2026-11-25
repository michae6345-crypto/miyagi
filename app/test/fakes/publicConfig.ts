/** Test stand-in for src/main/publicConfig.ts: a made-up project, never a real host. */
export const SUPABASE_URL = 'https://fake-project.supabase.test'
export const SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_test'
export const SUPABASE_HOST = new URL(SUPABASE_URL).hostname

export function supabaseConfig(): { url: string; key: string } {
  return { url: SUPABASE_URL, key: SUPABASE_PUBLISHABLE_KEY }
}
