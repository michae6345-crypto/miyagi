# Releasing miyagi for Mac

`.github/workflows/release.yml` builds and publishes a Mac release. It is a starting point for Adrian, who owns signing, releases and the site. `app/SHIP.md` still covers the local build (`npm run ship:mac`) and the test to run before anyone downloads a build.

## Cut a release

1. Bump `version` in `app/package.json` (for example `0.2.0`) and merge that change.
2. Tag the merged commit and push the tag:
   ```bash
   git tag v0.2.0 && git push origin v0.2.0
   ```
   The tag has to match the version. If it doesn't, the run stops at `plan`. A tag such as `v0.2.0-beta.1` makes a prerelease.
3. The run then does this:
   - **checks**: the app checks from ci.yml (typecheck, build, unit tests, no secret Supabase keys).
   - **build**, once per arch: `app/scripts/release-mac.sh` puts the engine inside the app (`MIYAGI_ENGINE_REF`, default `origin/integration/live`), builds the app, then the dmg, the update zip and `latest-mac.yml`. Apple silicon builds on `macos-latest`. Intel builds on `macos-15-intel`, because the bundled Python has to run on the build Mac to be precompiled.
   - **assemble**: merges the two feeds into one `latest-mac.yml`, writes `SHA256SUMS.txt` and writes the notes. The notes say **unsigned** when the build had no Developer ID.
   - **publish**: sends everything to the target (next section). It is a **draft** by default.
4. Open the draft, run the checks in SHIP.md's "Test before you publish" on the dmg, then press Publish.

You can also run it from the Actions tab: **release › Run workflow**. Choose the target, draft or not, whether to build Intel, and the engine ref. A manual run uses `v<package.json version>` and tags the commit it built. Running it again on the same version replaces that release's files.

To try a build on your own Mac with no publishing, run this in `app/`: `bash scripts/release-mac.sh --arch arm64`. The files land in `app/dist/release/`.

## Ship it to users (the usual setup)

Users get the app from one place: the rolling **`mac`** release on **`adrian-erlikhman/miyagi`**. miyagi.study's download link and the in-app update card both read it, and the update card trusts no other repo (`manifest.ts` `OFFICIAL_RELEASE_REPO`). So for a real release:

1. Set the repo variables `RELEASE_TARGET=github-public` and `RELEASES_REPO=adrian-erlikhman/miyagi`, and add `RELEASES_REPO_TOKEN` (Contents: read and write on that repo only).
2. Put the user-facing changes in `app/RELEASE-NOTES.txt`, one plain line each. The update card shows the first 6 as "What's new". Clear them after the release.
3. Tag and push as above. The `vX.Y.Z` release on `adrian-erlikhman/miyagi` is a draft. Test its dmg (SHIP.md), then run the workflow again by hand (Actions › release › Run workflow, target `github-public`, `draft` off). That publishes `vX.Y.Z` and refreshes the rolling `mac` release with `Miyagi-Mac.dmg`, `Miyagi-Mac.zip` (a copy of the Apple silicon zip) and, when Intel was built, `Miyagi-Mac-x64.dmg`. It is titled `miyagi X.Y.Z` and carries the user-facing notes. Only a non-draft, non-prerelease run does that: a draft or a beta never touches what users download.

Who reads which name:

| Name | Read by |
|---|---|
| `mac/Miyagi-Mac.dmg` | The in-app update card (`OFFICIAL_ASSETS.mac`). The site, once its link is re-sealed to the dmg. Apple silicon. |
| `mac/Miyagi-Mac-x64.dmg` | Intel. Nothing reads it yet: the update card offers it once `OFFICIAL_ASSETS.mac` lists it (see Open points). |
| `mac/Miyagi-Mac.zip` | The site's download link today (sealed, `site-tools` seal script) and `install.sh --app` (on `claude/distribution`). |
| the `mac` release's title and notes | The update card: the version comes from the title (`miyagi X.Y.Z`), "What's new" from the notes' plain lines, the hash from the `sha256:` line. A release with no version in its title or notes gives no offer. |
| `vX.Y.Z/Miyagi-Mac-arm64.zip`, `-x64.zip`, `latest-mac.yml` | electron-updater, once auto-update (#245) is on. Needs signed builds. |

The names, the title and both sets of notes come from one file, `.github/scripts/release-notes.mjs`. The workflow and `ship-mac.sh --publish` both call it, and `app/test/releaseNames.test.ts` checks that a release written this way is one the update card reads. Change a name there and in `manifest.ts` together, or that test fails.

`npm run ship:mac -- --publish` (a hand build on a Mac) uploads the dmg and then sets the same title and notes. Before this it left the old title in place, so the update card found no version and never offered the build. `--x64` builds `Miyagi-Mac-x64.dmg` and a publish uploads only that file.

The update card offers a release only to apps with a lower version, so bump `version` in `app/package.json` for every build you publish. Every line is on `0.1.0` today.

When the first dmg is on `mac`, switch the site: re-seal its Mac link to `.../mac/Miyagi-Mac.dmg` and change the install tip from "unzip" to "open the dmg and drag miyagi to applications". Until then the tip says "unzip", which matches the zip it downloads.

The `github` target (this repo) and `r2` are fine for test builds, but users never see them.

## What a release contains

| File | What it is |
|---|---|
| `Miyagi-Mac.dmg` | Apple silicon. This is the name the site and the in-app update card link to (`manifest.ts` `OFFICIAL_ASSETS`). |
| `Miyagi-Mac-x64.dmg` | Intel. The update card doesn't offer it yet (see Open points). |
| `Miyagi-Mac-arm64.zip`, `Miyagi-Mac-x64.zip` (+ `.blockmap`) | electron-updater's update files. The arch is in the name because electron-updater picks the file by "arm64". |
| `latest-mac.yml` | electron-updater's feed for both arches. |
| `SHA256SUMS.txt` | SHA-256 of every file above. The notes repeat the dmg hashes as `sha256: <hex>` lines. |

## Where it publishes

Use the `target` input, or for tag pushes the repo variable `RELEASE_TARGET`. Pick one:

| Target | What it does | Needs |
|---|---|---|
| `github` (default) | A release on this repo, made with the run's own `GITHUB_TOKEN`. Only this job gets `contents: write`. | nothing |
| `github-public` | A release on a separate **public** repo. Use this if this repo goes private, since a private repo's release files need a login to download. | variable `RELEASES_REPO` (`owner/name`) and secret `RELEASES_REPO_TOKEN` |
| `r2` | Cloudflare R2 through its S3 API: `<prefix>/<tag>/…`. A non-draft also replaces `<prefix>/latest/…`, which is the stable URL for the site and the update feed. | secrets `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, variables `R2_BUCKET`, `R2_PREFIX` (default `mac`) |
| `none` | Builds only. The files stay on the run as the `release-<tag>` artifact for 30 days. | nothing |

Other repo variables (all optional): `RELEASE_DRAFT=false` publishes tag pushes right away. `RELEASE_INTEL=false` skips Intel. `MIYAGI_ENGINE_REF` sets the engine branch. `MAC_ARM64_RUNNER` and `MAC_X64_RUNNER` set the runners. `MIYAGI_UPDATE_FEED_URL` sets the feed URL electron-builder records.

## Secrets to add later (Adrian or Michael, in Settings › Secrets and variables › Actions)

Nobody needs to add anything today. With no signing secrets the build is ad hoc and the release is marked **unsigned**, just like today's `ship:mac`. Add the five signing secrets together. If only some of them exist, the build stops on purpose.

| Secret | Where it comes from |
|---|---|
| `CSC_LINK` | The **Developer ID Application** certificate exported from Keychain Access as a `.p12`, then base64-encoded: `base64 -i DeveloperID.p12 \| pbcopy`. It needs Michael's Apple Developer account ($99/yr). |
| `CSC_KEY_PASSWORD` | The password you chose when you exported the `.p12`. |
| `APPLE_ID` | The Apple ID email of the developer account (used for notarization). |
| `APPLE_APP_SPECIFIC_PASSWORD` | appleid.apple.com › Sign-In and Security › App-Specific Passwords. |
| `APPLE_TEAM_ID` | The 10-character Team ID (developer.apple.com › Membership). It also picks the right certificate from `CSC_LINK`. |
| `RELEASES_REPO_TOKEN` | Only for `github-public`. A fine-grained token with **Contents: read and write** on the public releases repo and nothing else. That repo needs at least one commit (a README). |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Only for `r2`. An R2 API token with Object Read & Write on that one bucket. |

The build and publish jobs run in the GitHub environment **`release`**, which is created on the first run. Put the secrets on that environment rather than on the repo, and add a deployment rule so only `v*` tags and the default branch can use it. If you want, require an approval there too.

Once the five signing secrets exist, `release-mac.sh` does the following:
- signs every binary in the app with the Developer ID and hardened runtime, the bundled Python included, using `app/build/entitlements.mac.plist`;
- notarizes and staples the app;
- signs, notarizes and staples the dmg;
- checks the result with `codesign --verify --deep --strict`, `stapler validate` and `spctl`.

The ad-hoc `codesign --deep -s -` step is skipped for these builds. `ship-mac.sh` and `electron-builder.yml` keep `identity: null` for local builds.

## Security

- The workflow never runs on pull requests: no `pull_request` or `pull_request_target` trigger. Fork code never sees a secret.
- `permissions: {}` at the top level. Every job asks for `contents: read`, except `publish-github`, which gets `contents: write`.
- Secrets are passed as env vars only to the steps that use them. The signing keychain is temporary and is deleted at the end of the job, even when the job fails.
- Actions are pinned to commit SHAs and uv to a version. Nothing is restored from a cache.

## Open points for Adrian

- **The in-app update card** reads the rolling `mac` release on `adrian-erlikhman/miyagi` (`src/main/features/updates.ts`, `manifest.ts`), not `vX.Y.Z` releases. A published `github-public` run now refreshes it (see "Ship it to users"). If the releases move to another repo or to R2, `OFFICIAL_RELEASE_REPO` and the URL allowlist in `manifest.ts` have to move with them.
- **Intel in the update card**: `OFFICIAL_ASSETS.mac` only accepts `Miyagi-Mac.dmg`, so an Intel Mac is offered the Apple silicon dmg, which it can't run. The rolling release now holds `Miyagi-Mac-x64.dmg` when Intel was built; adding that name to `OFFICIAL_ASSETS.mac` is the whole fix (the card already picks the asset that names the Mac's arch). `releaseNames.test.ts` reports the gap and passes either way.
- **`install.sh --app`** (on `claude/distribution`) downloads `mac/Miyagi-Mac.zip` and looks inside it for a folder named exactly `Miyagi.app`. Since the rename the app is `miyagi.app`, so that step likely stops with "no Miyagi.app inside" on any current build (read from the script, not run on a Mac). Either the script accepts `miyagi.app`, or `--app` is retired and `Miyagi-Mac.zip` leaves the rolling release once the site links the dmg.
- **`ci.yml` `mac-build`** still makes a `Miyagi-Mac.zip` artifact with no engine inside on pushes to `main`, under the comment "The Mac download on miyagi.study". Nothing should publish that file any more; drop the job or rename its artifact once this workflow has shipped a release.
- **Universal build**: `ship:mac --universal` still bundles the arm64 Python only. That's why the release makes one dmg per arch.
- **Runner label**: if `macos-15-intel` gets retired, set `MAC_X64_RUNNER`, or turn Intel off with `RELEASE_INTEL=false`.
- **Not run yet**: nobody has run this workflow on GitHub so far, and no signed or notarized build has been made, because there's no Apple account yet. Check the first run's logs and try the first dmg on a Mac before you trust it.
