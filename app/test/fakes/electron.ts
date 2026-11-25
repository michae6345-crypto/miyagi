/** The few Electron pieces main features touch, for offline tests. */
export const safeStorage = {
  isEncryptionAvailable: (): boolean => true,
  getSelectedStorageBackend: (): string => 'keychain',
  encryptString: (s: string): Buffer => Buffer.from(`enc:${s}`, 'utf8'),
  decryptString: (b: Buffer): string => {
    const s = b.toString('utf8')
    if (!s.startsWith('enc:')) throw new Error('not encrypted by the fake')
    return s.slice(4)
  }
}

export const powerMonitor = { on: (): void => undefined }

/** Every URL a feature asked the system browser to open; listeners see each one. Nothing really opens. */
export const opened: string[] = []
export const openListeners = new Set<(url: string) => void>()
export const shell = {
  openExternal: async (url: string): Promise<void> => {
    opened.push(url)
    for (const fn of openListeners) fn(url)
  }
}

/**
 * The module-level app (features import it directly). on() records listeners in appListeners; nothing fires them
 * unless a test does.
 */
export const appListeners: [string, (...a: unknown[]) => void][] = []
export const app = {
  isPackaged: false,
  on: (ev: string, fn: (...a: unknown[]) => void): void => void appListeners.push([ev, fn]),
  getLoginItemSettings: (): { wasOpenedAtLogin: boolean } => ({ wasOpenedAtLogin: false }),
  focus: (): void => undefined,
  quit: (): void => undefined
}

/**
 * Every call that would show a macOS privacy prompt or capture the screen (onboarding.ts onboarding:prompt). A launch
 * must leave this empty: prompts come only from a setup button click.
 */
export const promptCalls: string[] = []
export const systemPreferences = {
  isTrustedAccessibilityClient: (prompt: boolean): boolean => {
    promptCalls.push(`accessibility:${prompt}`)
    return false
  },
  getMediaAccessStatus: (kind: string): string => {
    promptCalls.push(`media-status:${kind}`)
    return 'not-determined'
  }
}
export const desktopCapturer = {
  getSources: async (): Promise<unknown[]> => {
    promptCalls.push('capture')
    return []
  }
}

/** Global keys registered and unregistered, in order (index.ts's launcher key through main/gate.ts gateCore). */
export const shortcuts = new Set<string>()
export const globalShortcut = {
  register: (acc: string): boolean => {
    shortcuts.add(acc)
    return true
  },
  unregister: (acc: string): void => void shortcuts.delete(acc),
  isRegistered: (acc: string): boolean => shortcuts.has(acc)
}

type MenuItem = { label?: string; type?: string; click?: () => void }
/** The menu bar item: the last context menu set, as its items. */
export class Menu {
  constructor(public items: MenuItem[]) {}
  static buildFromTemplate(items: MenuItem[]): Menu {
    return new Menu(items)
  }
  popup(): void {}
}
export const trays: Tray[] = []
export class Tray {
  menu?: Menu
  constructor() {
    trays.push(this)
  }
  setToolTip(): void {}
  setContextMenu(m: Menu): void {
    this.menu = m
  }
  on(): void {}
  destroy(): void {}
}
export const nativeImage = {
  createFromDataURL: (): { addRepresentation: () => void } => ({ addRepresentation: () => undefined })
}

/** Only the static helpers features call; there are no real windows. */
export class BrowserWindow {
  static getFocusedWindow(): undefined {
    return undefined
  }
}
