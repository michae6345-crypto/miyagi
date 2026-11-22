import './styles.css'
import { StrictMode, useEffect, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import type { Layout } from '../../preload/api'
import { bridge, isElectron } from './bridge'
import { dispatch } from './core/bus'
import { setConnected } from './core/lesson'
import { setNotchInfo } from './core/notchInfo'
import './core/islandDiagReport' // log-only island measurements for main's island.log (overlay route only)
import './core/prefs' // applies the appearance before the first paint
import { getFeatureWindows } from './core/registry' // importing it loads features/* (their stores subscribe on import)
import { Overlay, useClickThrough } from './core/Overlay'
import { Stage } from './dev/Stage'
import { stageNotch } from '../../common/notch'

/**
 * Electron loads index.html#/<route>: 'overlay' (core) or a feature window route ('launcher', …).
 * In a browser (npm run dev:web) every route shows the stage; #/launcher opens the launcher on load.
 */
const route = location.hash.replace(/^#\/?/, '') || (isElectron ? 'overlay' : 'stage')

function useEngineFeed(): Layout {
  const [layout, setLayout] = useState<Layout>({ origin: { x: 0, y: 0 }, width: innerWidth, height: innerHeight, notch: { ...stageNotch('below', innerWidth), hasNotch: false }, workArea: { x: 0, y: 0, width: innerWidth, height: innerHeight } })
  useEffect(() => {
    const offs = [bridge.onEvent(dispatch), bridge.onStatus(setConnected), bridge.on('layout', (l) => {
        // Main re-fits the pill under the menu bar / notch when the displays change: every reader of platform.pillTop follows.
        const next = l as Layout
        setNotchInfo(next.notch)
        if (typeof next.pillTop === 'number') (bridge.platform as { pillTop: number }).pillTop = next.pillTop
        setLayout(next)
      })]
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
  if (!isElectron) return <Stage openLauncher={route === 'launcher'} />
  if (route === 'overlay') return <ElectronOverlay layout={layout} />
  const win = getFeatureWindows().find((w) => w.route === route)
  if (!win) return <div className="p-4 text-red-400">No feature window for route "{route}"</div>
  return <win.Component layout={layout} />
}

document.documentElement.dataset.route = isElectron ? route : 'stage'
// v2 (W0-4): an app window (Onboarding, Library, Progress, Account) is a normal opaque window: styles.css paints its body.
if (isElectron && getFeatureWindows().some((w) => w.route === route && w.kind === 'app')) document.documentElement.dataset.kind = 'app'
// Reuse the root if Vite re-runs this module (dependency re-optimization in dev).
const container = document.getElementById('root')! as HTMLElement & { __root?: ReturnType<typeof createRoot> }
container.__root ??= createRoot(container)
container.__root.render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </StrictMode>
)
