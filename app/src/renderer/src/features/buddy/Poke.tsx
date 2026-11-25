/**
 * Feature: buddy. Tap bon and it plays: a small happy thing, just so the app feels alive (Michael, Nov 24).
 *
 * Each tap plays the next of three, round and round:
 *   hop     it crouches, jumps, lands with a squash
 *   wiggle  it rocks side to side on its feet
 *   twirl   it hops and spins once in the air
 * All three smile (mood happy) and the leaves open. About 0.7 s; a tap while one is playing starts the next one.
 * Transform only, from its feet. With reduced motion nothing moves: it only smiles (buddy.css).
 *
 * A plain button with no chrome, so it is reachable by keyboard too. Never on the flying lesson bon (Companion.tsx):
 * the overlay stays click-through.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Character, type CharacterProps } from './Character'
import { NAME } from './name'

export type Trick = 'hop' | 'wiggle' | 'twirl'
export const TRICKS: Trick[] = ['hop', 'wiggle', 'twirl']
/** How long one trick plays, ms (buddy.css matches it). */
export const TRICK_MS = 720

/** The trick for the nth tap (0-based). */
export const trickFor = (n: number): Trick => TRICKS[((n % TRICKS.length) + TRICKS.length) % TRICKS.length]

export function PokeBon(props: CharacterProps): ReactNode {
  const taps = useRef(0)
  // `run` changes on every tap so the same trick can play twice in a row (the key restarts the animation).
  const [play, setPlay] = useState<{ trick: Trick; run: number } | null>(null)
  useEffect(() => {
    if (!play) return
    const id = setTimeout(() => setPlay(null), TRICK_MS)
    return () => clearTimeout(id)
  }, [play])
  const poke = (): void => {
    const n = taps.current++
    setPlay({ trick: trickFor(n), run: n })
  }
  return (
    <button type="button" className="ch-poke" data-poke-bon aria-label={`Say hi to ${NAME ?? 'bon'}`} onClick={poke}>
      <span key={play?.run ?? 'rest'} className="ch-poke-move" data-trick={play?.trick}>
        <Character {...props} mood={play ? 'happy' : props.mood} />
      </span>
    </button>
  )
}
