/**
 * electron-builder afterPack hook for scripts/release-mac.sh (-c.afterPack=scripts/release-after-pack.cjs).
 *
 * electron-builder renames the helper apps ("miyagi Helper (Renderer)") but leaves CFBundleName "Electron Helper ...",
 * which crash reports and some process lists show. ship-mac.sh fixes that after packing and then signs ad hoc; a
 * Developer ID build can't edit the plists after signing, so the release does it here: afterPack runs before the fuses
 * are flipped and before electron-builder signs, so the signature (ad hoc or Developer ID) covers the edited plists.
 */
const { execFileSync } = require('node:child_process')
const { existsSync, readdirSync } = require('node:fs')
const { join } = require('node:path')

const PLISTBUDDY = '/usr/libexec/PlistBuddy'

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return
  const appName = `${context.packager.appInfo.productFilename}.app`
  const frameworks = join(context.appOutDir, appName, 'Contents', 'Frameworks')
  if (!existsSync(frameworks)) throw new Error(`[release] no ${frameworks}`)
  let fixed = 0
  for (const entry of readdirSync(frameworks)) {
    if (!entry.includes('Helper') || !entry.endsWith('.app')) continue
    const plist = join(frameworks, entry, 'Contents', 'Info.plist')
    if (!existsSync(plist)) continue
    let shown = entry.slice(0, -'.app'.length)
    try {
      shown = execFileSync(PLISTBUDDY, ['-c', 'Print :CFBundleDisplayName', plist], { encoding: 'utf8' }).trim() || shown
    } catch {
      // no CFBundleDisplayName: the folder name is what electron-builder shows
    }
    execFileSync(PLISTBUDDY, ['-c', `Set :CFBundleName ${shown}`, plist])
    fixed++
  }
  console.log(`[release] helper CFBundleName set on ${fixed} helper app(s)`)
}
