/**
 * Feature: buddy. Tap bon and it plays: a small happy thing, just so the app feels alive (Michael, Nov 24).
 *
 * Each tap plays the next of three, round and round:
 *   hop     it crouches, jumps, lands with a squash
 *   wiggle  it rocks side to side on its feet
 *   twirl   it hops and spins once in the air
 * All three smile (mood happy). About 0.7 s; a tap while one is playing starts the next one.
 * Transform only, from its feet. With reduced motion nothing moves: it only smiles (buddy.css).
 *
 * A plain button with no chrome, so it is reachable by keyboard too. Never on the flying lesson bon (Companion.tsx):
 * the overlay stays click-through.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Character, type CharacterProps } from './Character'
import { NAME } from './name'
import { TRICK_MS, trickFor, type Trick } from './tricks'

export function PokeBon(props: CharacterProps): ReactNode {
  const taps = useRef(0)
  // `run` changes only on a tap, so a tap restarts the animation (the key) and the end of a trick does not remount bon.
  const [play, setPlay] = useState<{ trick: Trick; run: number; on: boolean }>({ trick: 'hop', run: -1, on: false })
  useEffect(() => {
    if (!play.on) return
    const id = setTimeout(() => setPlay((p) => ({ ...p, on: false })), TRICK_MS)
    return () => clearTimeout(id)
  }, [play.on, play.run])
  const poke = (): void => {
    const n = taps.current++
    setPlay({ trick: trickFor(n), run: n, on: true })
  }
  return (
    <button type="button" className="ch-poke" data-poke-bon aria-label={`Say hi to ${NAME ?? 'bon'}`} onClick={poke}>
      <span key={play.run} className="ch-poke-move" data-trick={play.on ? play.trick : undefined}>
        <Character {...props} mood={play.on ? 'happy' : props.mood} />
      </span>
    </button>
  )
}
