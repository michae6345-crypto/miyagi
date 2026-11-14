/** Feature: voice. Plays `speak` audio while voice is on. No UI of its own (the Voice button lives in the shortcut bar). */
import { useEffect, useRef, type ReactNode } from 'react'
import { defineFeature } from '../../core/registry'
import { useVoice } from './store'

function VoicePlayer(): ReactNode {
  const last = useVoice((s) => s.last)
  const on = useVoice((s) => s.on)
  const audio = useRef<HTMLAudioElement>(undefined)
  useEffect(() => {
    if (!last || !on) return
    audio.current?.pause()
    const a = new Audio(last.url)
    audio.current = a
    useVoice.setState({ speaking: true })
    a.onended = () => useVoice.setState({ speaking: false })
    a.play().catch(() => useVoice.setState({ speaking: false }))
  }, [last, on])
  useEffect(() => {
    if (!on) {
      audio.current?.pause()
      useVoice.setState({ speaking: false })
    }
  }, [on])
  return null
}

export default defineFeature({ id: 'voice', overlayLayers: [{ id: 'voice-player', z: 0, Component: VoicePlayer }] })
