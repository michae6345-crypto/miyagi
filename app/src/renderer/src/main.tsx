import '@fontsource-variable/inter'
import './styles.css'
import { StrictMode, useEffect, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import type { Layout } from '../../preload/api'
import { bridge, isElectron } from './bridge'
import { useLesson } from './store'
import { Overlay, useClickThrough } from './overlay/Overlay'
import { Launcher } from './launcher/Launcher'
import { Stage } from './dev/Stage'

/** Electron loads #/overlay and #/launcher. The browser shows the stage (any hash; #/launcher opens it). */
const route = location.hash.replace(/^#\/?/, '') || (isElectron ? 'overlay' : 'stage')

function useEngineFeed(): Layout {
  const [layout, setLayout] = useState<Layout>({ width: innerWidth, height: innerHeight, workArea: { x: 0, y: 0, width: innerWidth, height: innerHeight } })
  useEffect(() => {
    const offs = [
      bridge.onEvent((e) => useLesson.getState().apply(e)),
      bridge.onStatus((c) => useLesson.getState().setConnected(c)),
      bridge.on('layout', (l) => setLayout(l as Layout))
    ]
    bridge.ready()
    return () => offs.forEach((off) => off())
  }, [])
  return layout
}

function ElectronOverlay({ layout }: { layout: Layout }): ReactNode {
  useClickThrough()
  return <Overlay layout={layout} />
}

function App(): ReactNode {
  const layout = useEngineFeed()
  return (
    <MotionConfig reducedMotion="user">
      {isElectron && route === 'overlay' && <ElectronOverlay layout={layout} />}
      {isElectron && route === 'launcher' && <Launcher layout={layout} />}
      {!isElectron && <Stage openLauncher={route === 'launcher'} />}
    </MotionConfig>
  )
}

document.documentElement.dataset.route = isElectron ? route : 'stage'
// Reuse the root if Vite re-runs this module (dependency re-optimization in dev).
const container = document.getElementById('root')! as HTMLElement & { __root?: ReturnType<typeof createRoot> }
container.__root ??= createRoot(container)
container.__root.render(
  <StrictMode>
    <App />
  </StrictMode>
)
