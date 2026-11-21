# dmg-art

**Status:** done (pass 1, waiting for review) · **Plan:** A10 · **Port:** 5195 (not used: static page) · **Branch:** `michael/app-dmg-art`

## Goal
The art behind the Finder window of the miyagi disk image (mockup Onb-Install-Dmg): paper, a dashed arrow from the miyagi icon to Applications, "Drag miyagi to Applications" and "Then open it from Applications. No terminal needed."

## Owns
- `app/build/dmg/background.html` (source; `?preview` overlays the icon slots and labels for review only)
- `app/build/dmg/background.png` (640x400) and `background@2x.png` (1280x800), rendered from the source

## Done when (plan A10)
- 640x400 (plus the @2x): yes.
- Paper and ink only: `#F6F6F3` paper, `#141414` ink and ink at alpha (0.64 caption, 0.35 dashes, 0.6 chevron). No green, no pastel, no hue. The two hexes live only in the source's `:root` token block and mirror `brand.paper` / `brand.ink` in `core/theme.ts`.
- No signed footer: the mockup's "Signed and notarized by [ORG NAME] · Version [X.Y]" strip is left out until the build is really signed and notarized.

## What is painted vs what Finder draws
Finder draws the title bar, both icons and their labels on top of the art, so the art paints only paper, the arrow and the two lines of copy. Layout matches the mockup's row (112 icon, 48 gap, 96 arrow, 48 gap, 112 icon, centred):
- miyagi.app icon centre (168, 150), Applications link centre (472, 150), arrow x 272 to 368 at y 150.
- Headline: Google Sans Flex 500, 20 px, tracking -3%, top 262. Caption: system font 13 px, ink 64%, top 294.
- ~90 px of empty paper under the caption, so the art still reads if Finder's title bar eats into the window height.

Deviations from the mockup (brand rules): the mockup's mid-gray folder and traffic-light fills are Finder's, not ours; the footer is omitted; caption ink is the paper token's 64% (mockup 66%).

## Shots
- `agents/shots/dmg-art-background.png`: the @2x art as shipped.
- `agents/shots/dmg-art-preview.png`: `background.html?preview`, icon slots and labels where Finder will put them.

## Core requests
For the wave 2 integrator (`electron-builder.yml`, `scripts/ship-mac.sh`; not edited here):
1. `mac.target` add `dmg`, and a `dmg` block:
   ```yaml
   dmg:
     background: build/dmg/background.png   # electron-builder picks up background@2x.png next to it
     window: { width: 640, height: 400 }
     iconSize: 112
     iconTextSize: 13
     title: miyagi
     contents:
       - { x: 168, y: 150, type: file }
       - { x: 472, y: 150, type: link, path: /Applications }
     artifactName: miyagi-mac.${ext}
   ```
2. If Finder crops the bottom (window height includes the title bar on some macOS versions), raise `window.height` rather than moving the art.
3. Once a Developer ID build is notarized, the footer can come back as a separate pass ("Signed and notarized", version from `package.json`), still paper and ink.

## Notes
- Rendered with a hidden Electron BrowserWindow (CDP `Emulation.setDeviceMetricsOverride` scale 1 and 2, `Page.captureScreenshot`) after `document.fonts.ready` reported Google Sans Flex loaded. Headless Brave hung on this machine; the source comment lists the generic steps.
