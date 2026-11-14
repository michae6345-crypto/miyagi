import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import type { TutBridge, UiSignal } from './api'
import type { PlatformInfo } from '../main/platform'

// Main passes the PlatformInfo as a JSON argument (see createWindow in main/index.ts).
const arg = process.argv.find((a) => a.startsWith('--tut-platform='))
const platform = JSON.parse(decodeURIComponent(arg?.slice('--tut-platform='.length) ?? '%7B%7D')) as PlatformInfo

function listen<T>(channel: string, cb: (payload: T) => void): () => void {
  const h = (_e: IpcRendererEvent, payload: T): void => cb(payload)
  ipcRenderer.on(channel, h)
  return () => ipcRenderer.off(channel, h)
}

const bridge: TutBridge = {
  platform,
  onEvent: (cb) => listen('engine:event', cb),
  onStatus: (cb) => listen('engine:status', cb),
  send: (cmd) => ipcRenderer.send('engine:cmd', cmd),
  ready: () => ipcRenderer.send('ui:ready'),
  on: (signal: UiSignal, cb) => listen(`ui:${signal}`, cb),
  emit: (signal: UiSignal, payload) => ipcRenderer.send('ui:emit', signal, payload),
  invoke: (channel, ...args) => ipcRenderer.invoke(`feat:${channel}`, ...args),
  onFeature: (channel, cb) => listen(`feat:${channel}`, cb)
}

contextBridge.exposeInMainWorld('tut', bridge)
