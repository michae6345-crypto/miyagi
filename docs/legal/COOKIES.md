# DRAFT: miyagi.study cookie and storage notice

> **DRAFT. Not legal advice. Not published, not linked from the site.**
> Written from a check of the site source (`miyagi-site` at `b3c867b`) and the live site on 2026-11-21
> (notes: `docs/legal/research_notes/Miyagi legal and privacy risks/site_cookies_check.md`).
> Re-check before publishing: any change to `index.html` can make this wrong.
> The part under "Notes for the team" is not for publication.

Last updated: [TBD]

## The short version

miyagi.study sets no cookies. It has no analytics, no ads and no tracking. If you unlock the downloads, your browser
remembers the code you typed. Some parts of the page load from other companies' servers, and those servers see your
IP address, like any website you visit.

## What the site stores in your browser

| Name | Kind | Why | How long |
| --- | --- | --- | --- |
| `miyagi-code` | localStorage | Remembers the download code you typed, so later clicks download straight away. Only written after you type the right code. | Until you clear this site's data. It is removed if the code stops working. |

That is all. The site reads nothing else from your device.

## Other servers your browser talks to

| Server | Run by | What it sends you | When | What they can see |
| --- | --- | --- | --- | --- |
| miyagi.study | GitHub Pages | The page itself and its fonts | Every visit | Your IP address and browser, which GitHub may log for security ([GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement)) |
| `cdn.jsdelivr.net` | jsDelivr | The code for the 3D bonsai and smooth scrolling | Every visit | Your IP address, browser and the page you came from ([jsDelivr privacy policy](https://www.jsdelivr.com/terms/privacy-policy-jsdelivr-net)) |
| `i.ytimg.com` | Google (YouTube) | Thumbnails of the tutorial shown in "see it work" | Every visit | Your IP address and browser ([Google Privacy Policy](https://policies.google.com/privacy)) |
| `www.youtube.com`, `www.youtube-nocookie.com` | Google (YouTube) | The muted tutorial video inside "see it work" | Only when the story reaches a video part | Your IP address and browser. The player uses YouTube's privacy-enhanced mode, but YouTube may still store data in its own frame ([YouTube privacy-enhanced mode](https://support.google.com/youtube/answer/171780)) |
| `github.com` | GitHub | The download files | Only when you download | What GitHub collects on its own site ([GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement)) |

Fonts are served from miyagi.study itself, not from Google Fonts.

## Your choices

- You can clear or block this site's data in your browser. The site still works; you'll type the download code again.
- Because the site doesn't track you, there is nothing to opt out of. We don't change anything for Do Not Track or
  Global Privacy Control signals, since nothing on the site tracks you across sites to begin with.
- The miyagi app has its own privacy policy: [miyagi.study/privacy](https://miyagi.study/privacy) [TBD: publish].

## Changes

If the site starts storing anything new, we'll update this page and the date at the top.

## Contact

[TBD: privacy contact address, the same one as the privacy policy.]

---

## Notes for the team (not for publication)

Why there is no banner, and what would change that:

- The EU ePrivacy Directive Art. 5(3) and the UK's PECR reg. 6 require consent before storing or reading anything on a
  visitor's device (cookies, localStorage, the lot) unless it is strictly necessary for a service the visitor asked
  for ([Directive 2002/58/EC](https://eur-lex.europa.eu/eli/dir/2002/58/oj/eng), [PECR reg. 6](https://www.legislation.gov.uk/uksi/2003/2426/regulation/6), accessed 2026-11-21).
  `miyagi-code` is written only after the visitor asks to unlock the downloads, so it is the closest thing to a
  "strictly necessary" or user-requested preference item. Low risk, but it is listed above anyway.
- The EDPB reads Art. 5(3) to cover more than cookies, including scripts and pixels that make the browser send
  information to a third party ([EDPB Guidelines 2/2023 on the technical scope of Art. 5(3)](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-22023-technical-scope-art-53-eprivacy-directive_en), accessed 2026-11-21).
  The YouTube embed is the one item on the site that could need consent in the EU/UK: the player stores data in
  its own frame once it loads, even in privacy-enhanced mode.
- A German court fined a site for sending visitors' IP addresses to Google by loading Google Fonts from Google's
  servers (LG München I, 20 Jan 2022, 3 O 17493/20). The same reasoning could reach jsDelivr and `i.ytimg.com`.
  Low likelihood for us, but cheap to fix.

Cheap changes that make the notice shorter and remove the banner question entirely:

1. Self-host `three@0.160.0` and `lenis@1.1.13` instead of loading them from jsDelivr. This also fixes a security
   gap: the imports have no Subresource Integrity hashes, so a changed CDN file would run on our page.
2. Replace the YouTube thumbnails in "see it work" with our own stills (the `walk/*.webp` frames already exist), or
   keep `i.ytimg.com` and leave it listed.
3. Load the YouTube embed only after a click ("play the real video"), or keep the stills only. Then nothing from
   YouTube loads unless the visitor asks for it.
4. Remove `miyagi.study/live/` (public, unlinked, writes `miyagi.prefs` to localStorage), or list it here.
5. Add footer links to this notice and to the privacy policy, and one privacy contact address for both.
