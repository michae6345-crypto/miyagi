import { useLesson } from '../../core/lesson'
import { useDrawer } from '../drawer/store'
import { isSlim } from './slim'

/** Is the bar the slim row right now (slim.ts)? */
export function useSlim(): boolean {
  const open = useDrawer((d) => d.open)
  const text = useLesson((x) => x.lesson?.mode === 'lesson')
  return isSlim(open, text)
}
