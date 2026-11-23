/**
 * Feature: settings. Puts the renderer-side preferences (local.ts) to work. Imported once by index.tsx, so it runs in
 * every window; each effect checks whether this window is an app window:
 *
 *   text size     page zoom on <html> (TEXT_SCALE), app windows only. The notch island, cards and the settings sheet keep
 *                 their measured sizes.
 *   density       <html data-density>; Row (ui.tsx) reads the store itself.
 *   reduce motion <html data-reduce-motion> (styles.css) plus MotionConfig in settings Content.tsx.
 *   start page    the home window opens on it unless it was opened on a page (a ?page= in the stage; window args in
 *                 Electron override it later, LibraryWindow).
 */
import { isElectron } from '../../bridge'
import { setPage } from '../shell/store'
import { TEXT_SCALE, useLocal, type Local } from './local'

const params = typeof location === 'undefined' ? new URLSearchParams() : new URLSearchParams(location.search)
/** An app window (Library, Onboarding, Progress, Account), or the stage showing the library. */
const appWindow = (): boolean => document.documentElement.dataset.kind === 'app' || (!isElectron && params.get('window') === 'library')

function apply(l: Local): void {
  const root = document.documentElement
  root.dataset.density = l.density
  if (l.motion === 'reduce') root.dataset.reduceMotion = ''
  else delete root.dataset.reduceMotion
  const scale = TEXT_SCALE[l.textSize]
  // `zoom` scales layout the way the browser's own zoom does, so every px-sized token follows. In the stage the window is
  // a framed div inside a bigger page, so only the pages scale there (styles.css, data-stage-zoom).
  const zoom = appWindow() && scale !== 1 ? String(scale) : ''
  root.style.setProperty('zoom', isElectron ? zoom : '')
  root.style.setProperty('--mg-text-scale', zoom || '1')
  if (!isElectron && zoom) root.dataset.stageZoom = ''
  else delete root.dataset.stageZoom
}

if (typeof document !== 'undefined') {
  // main.tsx marks an app window (data-kind) after the features load: look once the module graph has finished.
  setTimeout(() => {
    apply(useLocal.getState())
    const start = useLocal.getState().startPage
    if (appWindow() && start !== 'home' && !params.has('page')) setPage(start)
  }, 0)
  useLocal.subscribe(apply)
}
