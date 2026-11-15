/**
 * Feature: demo. The small Demo button in the corner of the stage.
 *
 * Off: "Demo" reloads the stage into the offline demo (?scenario=demo&clean): the scripted engine, the
 * learner's VS Code, the neural-net lesson. Everything else is the real app, so you can drive it by hand.
 * On: the walkthrough control. → / Space / PageDown (or a clicker) runs the next beat, A toggles autoplay,
 * R starts over. The line under the beat title is what to say.
 */
import { useEffect, type ReactNode } from 'react'
import { ChevronRight, Play, RotateCcw, X } from 'lucide-react'
import { isElectron } from '../../bridge'
import { color, fill, font } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { demoOn } from './store'
import { BEATS, nextBeat, restart, setAuto, useWalk } from './walkthrough'

function go(demo: boolean): void {
  const params = new URLSearchParams(location.search)
  if (demo) {
    params.set('scenario', 'demo')
    params.set('clean', '')
  } else {
    params.delete('scenario')
    params.delete('clean')
  }
  location.search = params.toString().replace(/=(&|$)/g, '$1')
}

const editable = (t: EventTarget | null): boolean => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))

function useKeys(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const typing = editable(e.target)
      const { running } = useWalk.getState()
      // A clicker sends PageDown / →. While a beat types into the launcher, its field has focus: still ours.
      if (e.key === 'PageDown' || (e.key === 'ArrowRight' && (!typing || running)) || (e.key === ' ' && !typing)) {
        e.preventDefault()
        e.stopPropagation()
        void nextBeat()
      } else if (!typing && (e.key === 'a' || e.key === 'A')) setAuto(!useWalk.getState().auto)
      else if (!typing && (e.key === 'r' || e.key === 'R')) restart()
    }
    addEventListener('keydown', onKey, true)
    return () => removeEventListener('keydown', onKey, true)
  }, [])
}

/**
 * Where it sits: clear of the shortcut bar (bottom center), the drawer (right) and the dev HUD (bottom left of the
 * window). Off: a small chip in the menu bar's right half. On: bottom left, over the explorer of the demo desktop.
 */
const chip = 'absolute right-[340px] top-[4px] flex items-center rounded-full text-[12px]'
const panel = 'absolute bottom-[32px] left-[14px] flex rounded-[16px] text-[12px]'
const shellStyle = { background: color.glass, border: `1px solid ${color.hairline}`, color: color.label, fontFamily: font.ui }

function DemoButton(): ReactNode {
  return (
    <button data-hit type="button" className={`${chip} cursor-pointer gap-[6px] px-[10px] py-[3px] hover:text-white`} style={shellStyle} onClick={() => go(true)}>
      <Play size={11} /> Demo
    </button>
  )
}

function Walkthrough(): ReactNode {
  useKeys()
  const { done, running, auto } = useWalk()
  const finished = done >= BEATS.length
  const beat = running ? BEATS[done] : finished ? undefined : BEATS[done]
  const title = finished ? 'Done' : running ? beat!.title : done === 0 ? 'Ready' : `Next: ${beat!.title}`
  const say = finished ? 'R starts over.' : done === 0 && !running ? 'Press → to start.' : beat!.say
  return (
    <div data-hit className={`${panel} flex-col items-stretch gap-[4px] py-[8px] pl-[12px] pr-[8px]`} style={{ ...shellStyle, width: 316 }}>
      <span className="flex items-center gap-[8px]">
      <span className="shrink-0 tabular-nums" style={{ color: color.faint }}>
        {Math.min(done + (running ? 1 : 0), BEATS.length)}/{BEATS.length}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium" style={{ color: color.text }}>
        {title}
      </span>
      <span className="flex shrink-0 items-center gap-[2px]">
        <IconButton label={auto ? 'Autoplay on (A)' : 'Autoplay (A)'} on={auto} onClick={() => setAuto(!auto)}>
          <span className="text-[10.5px] font-semibold tracking-[.04em]">AUTO</span>
        </IconButton>
        <IconButton label="Start over (R)" onClick={restart}>
          <RotateCcw size={12} />
        </IconButton>
        <IconButton label="Leave the demo" onClick={() => go(false)}>
          <X size={12} />
        </IconButton>
        <button
          type="button"
          aria-label="Next beat (→)"
          disabled={running || finished}
          onClick={() => void nextBeat()}
          className="flex h-[28px] w-[28px] cursor-pointer items-center justify-center rounded-full disabled:cursor-default"
          style={{ background: running || finished ? fill.button : color.accent, color: running || finished ? color.label : color.onAccent }}
        >
          {running ? <Spinner size={12} /> : <ChevronRight size={15} />}
        </button>
      </span>
      </span>
      <span className="pr-[6px] text-[11.5px] leading-[15px]">{say}</span>
    </div>
  )
}

function IconButton({ label, on, onClick, children }: { label: string; on?: boolean; onClick: () => void; children: ReactNode }): ReactNode {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-[28px] min-w-[28px] cursor-pointer items-center justify-center rounded-full px-[6px] hover:text-white"
      style={{ background: on ? fill.chipHover : 'transparent', color: on ? color.text : color.label }}
    >
      {children}
    </button>
  )
}

export function Presenter(): ReactNode {
  if (isElectron) return null
  return demoOn ? <Walkthrough /> : <DemoButton />
}
