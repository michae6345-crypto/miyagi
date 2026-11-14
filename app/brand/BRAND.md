# Miyagi brand

**Miyagi turns any tutorial into an auto-graded lab.** You ask it what you want to learn, it finds the best tutorial, and the video waits at each step until your own code passes.

Read this before building anything people will see: the overlay app, the VS Code extension, the site, the Devpost page, the slides. If you are a Claude session, the rules in "For Claude sessions" at the bottom are not optional.

## Name

- **Miyagi**, written with a capital M in sentences. The wordmark is lowercase: **miyagi**.
- It is someone you ask: "Ask Miyagi anything." "I asked Miyagi to teach me PINNs." "Hey Miyagi, show me."
- It nods to the teacher in *The Karate Kid* who makes you do the work yourself ("wax on, wax off"). That is the product: the video won't move on until you have done the step.
- Play the movie nod, never a voice. No accent, no broken English, no "Japanese" lettering or props. Miyagi is also a real Japanese family name.

## Lines

| Use | Text |
|---|---|
| One-liner | Turn any tutorial into an auto-graded lab. |
| Launcher placeholder | Ask Miyagi anything |
| Pitch | I asked Miyagi to teach me PINNs. It found the best video, paused it at every step, and wouldn't move on until my code actually worked. |
| Off-track card | Loss is flat at 0.25. Add a β curriculum, then rerun. |
| Passed card | Good. Now the next one. |

**Voice:** calm, short, direct, like a teacher who has seen this mistake a hundred times. Every card readable in two seconds, about 12 words of body at most. At most one Miyagi line per card ("Wax on, wax off." "Again." "Patience."), and not on every card. No exclamation marks, no emoji.

## Logo

The logo is a **bonsai in the informal upright style** (moyogi): an S-shaped trunk with three foliage pads stepping up to a crown, in a shallow pot. It is built on a 100-unit grid. Pads are flat-bottomed clouds of circles, and the trunk is one curve that tapers from base to tip. `brand-kit.html` shows the construction (toggle "Show construction") and lights up each part.

There are three cuts of the same tree. Use the right one for the size:

| Cut | Use at | What it has | Files |
|---|---|---|---|
| **Full** | 140 px and up: hero, splash, Devpost, stickers | Two-tone pads, back pads, roots, bark grain, deadwood, soil and moss, pot with seal and feet | `logo/svg/tree-full.svg` |
| **Icon** | 48 to 140 px: app icon, dock, lockups | Same shapes and two-tone pads, roots; no texture | `logo/svg/tree-icon.svg` |
| **Small** | 16 to 32 px: tabs, menu bar, notch pill | Three pads, thick trunk, plain pot | `logo/svg/tree-small.svg` |

Each has a `-dark` version (white trunk and pot) for dark backgrounds.

**Wordmark:** lowercase `miyagi` in Google Sans Flex 600, tracking −4.5%, with the dot of the first i replaced by a green light (#30D158). The files are outlined, so no font is needed. Use the files; do not retype it.

**Lockups:** tree beside the wordmark (`lockup-horizontal`) or above it (`lockup-stacked`), each in light and dark.

**Clear space:** keep empty space around the logo of at least the height of one foliage pad (about 10% of the tree's size).

**Don't:** add gradients, glows, outlines or shadows to the tree; recolor the pads; rotate or stretch it; put it on a busy photo; use the full cut below 140 px; use a sparkle (✦) icon anywhere. The sparkle in the first launcher mockup is replaced by the small tree.

## Color

| Token | Hex | Meaning |
|---|---|---|
| Pass green | `#30D158` | Passed. The light on the i. The bonsai's pads. Nothing else. |
| Pass deep | `#1F9B45` | Pad undersides and back pads, pressed states |
| Pass text | `#1C8A3C` | Green text on light backgrounds |
| Off-track amber | `#FFB020` | A check failed. Calm: no red, no shaking. |
| Watching gray | `#8E8E93` | The status dot while Miyagi watches |
| Ink | `#141414` | Text, the trunk and pot, buttons on light |
| Paper | `#F6F6F3` | Brand background: site, Devpost, slides |
| Pill | `#000000` | The notch pill, always black |

**Rules:** green only ever means passed. Amber only ever means off track. Buttons are ink (on light) or white (on dark), never green and never blue. No purple, no gradients, no neon.

## Type

- **Google Sans Flex** (`fonts/GoogleSansFlex.woff2`, SIL Open Font License) for the wordmark, headings, covers and slides. Medium 500 or SemiBold 600, tight tracking (−3 to −4.5%).
- **The system font inside the app** (SF Pro on the Mac, Segoe on Windows) so the overlay feels built in. Sizes 13 / 15 / 20 / 28.
- Don't use Inter, Plus Jakarta Sans, Space Grotesk or a handwritten font.

## The app (the overlay)

The overlay should feel like a first-party Apple feature (Spotlight, Dynamic Island), not a chatbot. Michael's frontend handoff is the spec for layout and motion; this kit sets the look:

- Glass follows macOS: dark HUD glass by default, light when the system is light. Tokens in `code/theme.ts` (`hud.dark`, `hud.light`).
- The notch pill is always black, with the small tree on the left and the status dot on the right: gray watching, amber off track, green passed.
- The launcher input shows the small tree where the mockup had a sparkle, with the placeholder "Ask Miyagi anything".
- One spring everywhere: stiffness 420, damping 34, mass 0.9. Radii 14 / 20 / 28.
- No annotations: no hand-drawn notes, arrows or doodles anywhere this weekend.

## Files

```
BRAND.md              this guide
brand-kit.html        interactive reference (open in a browser)
logo/svg, logo/png    tree-{full,icon,small}[-dark], wordmark[-dark], lockup-{horizontal,stacked}[-dark]
app-icon/             icon.png (1024, macOS, for electron-builder), icon.ico (Windows, 16-256),
                      icon-macos-1024[-dark].png, icon-{16..512}.png
web/                  favicon.svg (switches for dark mode), favicon.ico, favicon-{16,32,48}.png,
                      apple-touch-icon.png, og-image.png (1200x630)
social/               cover-1200x630.png, devpost-1500x1000.png, square-1080.png
code/                 theme.ts, tokens.css, tailwind.preset.js, MiyagiMark.tsx
fonts/                GoogleSansFlex.woff2, OFL.txt
```

**Quick setup in the app repo:**

1. Copy `logo/svg/*` to `app/src/assets/brand/`, `code/theme.ts` to `app/src/theme.ts`, `code/MiyagiMark.tsx` to `app/src/components/`.
2. Copy `app-icon/icon.png` and `app-icon/icon.ico` to `app/build/`; electron-builder makes the `.icns` from the PNG.
3. Copy `fonts/GoogleSansFlex.woff2` to `app/src/assets/fonts/` and load it with the `@font-face` in `code/tokens.css`.
4. For a web page: `<link rel="icon" href="/favicon.svg" type="image/svg+xml">`, `<link rel="icon" href="/favicon.ico" sizes="any">`, `<link rel="apple-touch-icon" href="/apple-touch-icon.png">`, and `og-image.png` as the `og:image`.

## For Claude sessions

1. Use the files in this kit. Never redraw the tree, retype the wordmark or pick new colors.
2. Use the cut for the size: `markLevel(px)` in `theme.ts`, or `<MiyagiMark size={n} />`, which picks it for you.
3. Green means passed, amber means off track, gray means watching. Nothing else is green or amber. No red.
4. Buttons: ink on light, white on dark. Never system blue, never green.
5. App text in the system font; brand headings in Google Sans Flex. No Inter.
6. No gradients, glows, sparkles, emoji or hand-drawn annotations.
7. Copy: short, calm, plain. At most about 12 words of body per card, and at most one Miyagi line per card.
