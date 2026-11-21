# miyagi.study/download

One self-contained page: `index.html`. No build step, no images, no external requests except an optional call to the GitHub API for the live file size. The logo, wordmark, favicon and Google Sans Flex font are all inlined from `app/brand/`.

## Put it on the site (GitHub Pages)

1. Copy `index.html` to `download/index.html` in the miyagi.study Pages repo. It then lives at `https://miyagi.study/download/`.
2. Optional: copy `app/brand/web/og-image.png` to the site root as `/og-image.png` so link previews show the cover.
3. Link to `/download/` from the home page's download button.

## The config block

Near the top of `index.html`, `window.MIYAGI_DOWNLOAD` is the only thing to edit:

| Field | What it does |
|---|---|
| `version` | Shown as "Version 0.1.0". A version like `1.2.3` in the GitHub release name wins over it. |
| `github.repo` | Where the live size, "Updated" date and SHA-256 come from (`api.github.com/repos/<repo>/releases/tags/<tag>`, no key needed, 60 lookups an hour per visitor). `null` skips the lookup. |
| `mac.file`, `mac.url`, `windows.url` | The download links. They must point at files that exist on the release today, because the page uses them as they are when the GitHub lookup is skipped or fails (shared networks often hit its 60-an-hour limit). Today `mac.file`/`mac.url` are `Miyagi-Mac.zip`, the file on the `mac` release. |
| `mac.fallbackFile` | `null` today. **When you upload `Miyagi-Mac.dmg`:** set `mac.file` and `mac.url` to the .dmg and `fallbackFile` to `"Miyagi-Mac.zip"`. The page then shows the DMG steps, and if a lookup finds no .dmg on the release it links the zip instead. If the lookup finds neither file, the button opens the releases page rather than a broken link. |
| `mac.intelUrl` | `null` today (the build is Apple silicon only). Intel Macs then see a plain note instead of a download that won't open. Set it when an Intel or universal build exists. |
| `mac.needs`, `windows.needs`, `*.chip` | The requirements line. Check `mac.needs` against the Electron version's minimum macOS. |
| `sizeMB` | Shown only when the live lookup is off or fails. |
| `pageUrl` | The link phones copy or share. |
| `remindEndpoint` | `null` = phones get Copy link (and Share where the phone has it). Set it to a form endpoint (Formspree, Buttondown, a Worker) and phones also get an "Email me the link" field; it POSTs `{ "email", "url" }` as JSON. GitHub Pages can't send mail on its own, so the page doesn't promise an email until this is set. |

### Moving downloads to Cloudflare R2 later

Set `mac.url` and `windows.url` to `https://downloads.miyagi.study/...`. Keep `github.repo` if the same files are still on GitHub Releases (for the size and checksum), or set it to `null` and fill `sizeMB`.

## What the page does

- Detects Mac, Windows or phone/tablet (iPads count as tablets) and shows the right button. On a Mac it checks the chip where the browser says (Chrome's client hints, else the WebGL renderer) and only warns about Intel when it's sure; then the big button gives way to a quiet "Download anyway (Apple silicon only)" link. Anything else (Linux, ChromeOS) gets two equal choices, Mac and Windows, with no primary button.
- After a click: "Your download has started", then it scrolls to the three install steps and outlines step 1.
- Install steps for Mac (DMG or zip) and Windows, switchable, each with a small drawing in HTML/CSS/SVG. Step 3 on the Mac has an "Open Privacy & Security" link that opens System Settings.
- What happens next, FAQ (safety with the live SHA-256, screen, cost, models, requirements, uninstall) and a privacy line.
- No cookies, no analytics, no external fonts or scripts.

## Testing

Query parameters, for checking a variant from any computer:

- `?os=mac|windows|phone|other` forces the platform.
- `?chip=intel` or `?chip=arm` forces the Mac chip.
- `?live=0` skips the GitHub lookup (shows exactly what the config says, as visitors see it when the lookup fails).

## Before it goes live, please check

- **Do not publish this page while the shipped build still needs an API key.** Two FAQ answers are only true once the miyagi-cloud proxy from `DISTRIBUTION-PLAN.md` is live and the build uses it: "Our server passes them along and doesn't keep them" (What does it read on my screen?) and "You don't need an account or an API key" (Does it cost money?). Until then, either hold the page or rewrite both answers to match the build.
- The rest of the FAQ matches the build: Claude for lessons and checks, Gemini only to watch videos; the permissions (Screen Recording, Accessibility, and Apple Events to control VS Code).
- `mac.needs` ("macOS 13 or later").
