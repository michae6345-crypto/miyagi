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

export const app = { isPackaged: false }
