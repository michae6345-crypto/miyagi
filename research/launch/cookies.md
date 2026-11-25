# Does miyagi.study need a cookie banner?

Area B (privacy and legal). Not legal advice. Checked 2026-11-21 against the site source (`miyagi-site` at `b3c867b`)
and the live site in a browser.

## Answer: no banner, once one small change ships

The site sets **no cookies**, runs **no analytics, ads or trackers**, and stores one localStorage item that a visitor
asks for. That needs a short notice, not a consent banner, in the US and in the EU/UK.

The one thing that could need consent for EU/UK visitors is the **YouTube player that starts by itself** inside
"see it work". Make it load only after a click (or show our own stills only), and the banner question goes away.
Until then, the risk is low (no regulator targets a free static page with a muted embed), but the fix is a few
lines and cheaper than a banner.

## What the site actually does

| Item | Kind | When | Needs consent? |
| --- | --- | --- | --- |
| `miyagi-code` | localStorage, first party | Only after the visitor types the right download code; remembers it for later downloads (`index.html:510-518`) | No: set because the visitor asked to unlock downloads (closest to "strictly necessary" or a user-requested preference). List it in the notice. |
| Cookies | none | `document.cookie` empty on load and after the whole story | No |
| `cdn.jsdelivr.net` | third-party script (three.js 0.160.0, Lenis 1.1.13) | Every visit | No storage on the device; it is an ordinary request that shows the visitor's IP. Disclose. Self-hosting removes it. |
| `i.ytimg.com` | YouTube thumbnails | Every visit | Same as above: disclose, or use our own stills. |
| `www.youtube.com/iframe_api` + `youtube-nocookie.com` player | third-party embed | Starts automatically when the story reaches a video part (`index.html:893-913`) | **Possibly, in the EU/UK.** The player stores data in its own frame even in privacy-enhanced mode, and the visitor didn't ask to play anything. |
| `miyagi.study/live/` | old app renderer copy, writes `miyagi.prefs` | Public but unlinked | Remove it, or list it. |

Full evidence: [`privacy-legal/sources/site_cookies_check.md`](privacy-legal/sources/site_cookies_check.md).

## Why, by law

- **EU (ePrivacy Directive Art. 5(3)) and UK (PECR reg. 6):** storing or reading anything on a visitor's device,
  cookies or localStorage alike, needs consent unless it is strictly necessary for a service the visitor
  explicitly asked for ([Directive 2002/58/EC](https://eur-lex.europa.eu/eli/dir/2002/58/oj/eng),
  [PECR reg. 6](https://www.legislation.gov.uk/uksi/2003/2426/regulation/6)). `miyagi-code` fits the exemption: it
  is written only after the visitor asks to unlock downloads. The EDPB reads Art. 5(3) broadly, to cover scripts and
  embeds that make the browser store or send information for a third party
  ([EDPB Guidelines 2/2023](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-22023-technical-scope-art-53-eprivacy-directive_en)),
  which is why the auto-starting YouTube player is the item to fix. A Munich court awarded damages for sending a
  visitor's IP address to Google by loading Google Fonts from Google (LG München I, 20 Jan 2022, 3 O 17493/20); the
  same reasoning could reach jsDelivr and `i.ytimg.com`, which is why self-hosting them is on the list below. The UK's
  Data (Use and Access) Act 2025 added more cookie exemptions (in force 2026-02-05), which only makes the UK answer
  easier.
- **US:** no federal or California law requires a cookie banner. CalOPPA requires a posted privacy policy that says
  how the site responds to Do Not Track signals and whether third parties collect data about visitors
  ([Cal. Bus. & Prof. Code § 22575](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=BPC&sectionNum=22575)).
  The CCPA's opt-out and Global Privacy Control duties apply only to "businesses" above its thresholds, which
  miyagi is not, and only to selling or sharing data for ads, which the site doesn't do.
- **Lawsuit wave to stay clear of:** California Invasion of Privacy Act suits target sites with session replay,
  chat widgets and ad pixels. miyagi.study has none, so keep it that way: no analytics or pixels without a fresh
  look at this page.

## To do (owner: Adrian, site repo)

1. Load the YouTube embed only after a click on the stills ("play the real video"), or drop it. **This is the change
   that removes the banner question.**
2. Publish the notice: it is the "The miyagi.study website" section of the suggested privacy policy on #201
   (`web/privacy.md`), so one page covers the app and the site. Link the policy from the footer.
3. Optional but cheap: self-host three.js and Lenis (also closes a security gap: the CDN imports have no integrity
   hashes), and swap the `i.ytimg.com` thumbnails for our own stills.
4. Remove `miyagi.study/live/`.
5. Re-check this page before adding any analytics, form, chat widget or new embed.

The app is a separate question with the same answer: the EDPB counts an app sending locally held data to a server as
"access" under Art. 5(3), but the screenshots and code a learner asks miyagi to check fall under the
strictly-necessary exemption, and opt-in crash and usage sharing already asks first. No banner there either.

Lawyer needed: no.
