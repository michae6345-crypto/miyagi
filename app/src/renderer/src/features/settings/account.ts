/**
 * Feature: settings. The bring-your-own-key flow, moved out of Settings.tsx unchanged (A4: moved, not rewritten).
 *
 * Keys never come back from main: each row shows `•••• last4`. An empty field = unchanged; Clear marks the key for
 * removal (Undo until Save). Save sends only what changed through `settings:save`; main merges, encrypts (safeStorage)
 * and sends the FULL config.keys. Status per key comes from config.status (useLesson keyStatus). Test re-sends
 * config.keys and waits for config.status (spinner, 3 s → "No answer from miyagi"). Drafts are cleared after Save
 * and dropped with the sheet (the Shell mounts this hook once per open).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { bridge } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { KEY_NAMES, type KeyName, type KeysView, type KeyStatus, type SavePatch } from './keys'
import { nextStatus, useSettings } from './store'

/** Test's spinner shows at least this long, so a fast answer still reads as "checked". */
const MIN_SPIN = 450
export const NO_ANSWER = 'No answer from miyagi'

export type KeyFlow = {
  view?: KeysView
  status?: Partial<KeyStatus>
  drafts: Partial<Record<KeyName, string>>
  cleared: KeyName[]
  saving: boolean
  /** Rows whose new value went out and whose config.status hasn't come back yet. */
  waiting: KeyName[]
  testing: boolean
  note?: string
  dirty: boolean
  /** "Saved to Keychain" for a moment after a Save that went through. */
  saved?: string
  save: () => Promise<void>
  test: () => Promise<void>
  setDraft: (k: KeyName, v: string) => void
  toggleClear: (k: KeyName) => void
  /** After Privacy › Delete: main's new view (no keys). */
  replaceView: (v: KeysView) => void
}

/** `live` false (the sheet is collapsing): Save and Test do nothing. */
export function useKeyFlow(live: boolean): KeyFlow {
  const [view, setView] = useState<KeysView>()
  const [drafts, setDrafts] = useState<Partial<Record<KeyName, string>>>({})
  const [cleared, setCleared] = useState<KeyName[]>([])
  const [saving, setSaving] = useState(false)
  const [waiting, setWaiting] = useState<KeyName[]>([])
  const [testing, setTesting] = useState(false)
  const [note, setNote] = useState<string>()
  const [saved, setSaved] = useState<string>()
  const savedTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(savedTimer.current), [])
  const liveRef = useRef(live)
  liveRef.current = live

  const engineStatus = useLesson((s) => s.keyStatus)
  const status = engineStatus ?? view?.status

  useEffect(() => {
    let on = true
    bridge
      .invoke<KeysView>('settings:get')
      .then((v) => on && setView(v))
      .catch(() => {})
    return () => {
      on = false
    }
  }, [])

  const dirty = KEY_NAMES.some((k) => drafts[k]?.trim()) || cleared.length > 0

  const save = async (): Promise<void> => {
    if (!dirty || saving || !liveRef.current) return
    const patch: SavePatch = {}
    for (const k of KEY_NAMES) {
      const d = drafts[k]?.trim()
      if (d) patch[k] = d
      else if (cleared.includes(k)) patch[k] = null
    }
    const changed = Object.keys(patch) as KeyName[]
    const since = useSettings.getState().statusSeq
    setSaving(true)
    setNote(undefined)
    try {
      const v = await bridge.invoke<KeysView>('settings:save', patch)
      setView(v)
      setDrafts({})
      setCleared([])
      if (v.error) setNote(v.error)
      else {
        setSaved(v.secure ? 'Saved to Keychain' : 'Saved for this run')
        clearTimeout(savedTimer.current)
        savedTimer.current = setTimeout(() => setSaved(undefined), 4000)
      }
    } catch {
      setSaving(false)
      setNote('Couldn’t save')
      return
    }
    setWaiting(changed)
    const answered = await nextStatus(since)
    setWaiting([])
    setSaving(false)
    if (!answered) setNote(NO_ANSWER)
  }

  const test = async (): Promise<void> => {
    if (testing || !liveRef.current) return
    const since = useSettings.getState().statusSeq
    const started = performance.now()
    setTesting(true)
    setNote(undefined)
    bridge.invoke('settings:test').catch(() => {})
    const answered = await nextStatus(since)
    await new Promise((r) => setTimeout(r, Math.max(0, MIN_SPIN - (performance.now() - started))))
    setTesting(false)
    if (!answered) setNote(NO_ANSWER)
  }

  const setDraft = useCallback((k: KeyName, v: string): void => {
    setDrafts((d) => ({ ...d, [k]: v }))
    setSaved(undefined)
    if (v) setCleared((c) => c.filter((x) => x !== k))
  }, [])

  const toggleClear = useCallback((k: KeyName): void => {
    setDrafts((d) => ({ ...d, [k]: '' }))
    setCleared((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]))
  }, [])

  const replaceView = useCallback((v: KeysView): void => {
    setView(v)
    setDrafts({})
    setCleared([])
  }, [])

  return { view, status, drafts, cleared, saving, waiting, testing, note, dirty, saved, save, test, setDraft, toggleClear, replaceView }
}
