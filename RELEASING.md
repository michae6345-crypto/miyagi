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

- **The in-app update card** reads the rolling `mac` release on `adrian-erlikhman/miyagi` (`src/main/features/updates.ts`, `manifest.ts`), not `vX.Y.Z` releases. Until that changes, after publishing a release run `gh release upload mac Miyagi-Mac.dmg --clobber --repo adrian-erlikhman/miyagi`. `install.sh --app` downloads `Miyagi-Mac.zip` from that same `mac` release. If the releases move to a public releases repo or to R2, `OFFICIAL_RELEASE_REPO` and the URL allowlist in `manifest.ts` have to move with them.
- **Intel in the update card**: `OFFICIAL_ASSETS.mac` only accepts `Miyagi-Mac.dmg`, so Intel users aren't offered `Miyagi-Mac-x64.dmg` yet.
- **Universal build**: `ship:mac --universal` still bundles the arm64 Python only. That's why the release makes one dmg per arch.
- **Runner label**: if `macos-15-intel` gets retired, set `MAC_X64_RUNNER`, or turn Intel off with `RELEASE_INTEL=false`.
- **Not run yet**: nobody has run this workflow on GitHub so far, and no signed or notarized build has been made, because there's no Apple account yet. Check the first run's logs and try the first dmg on a Mac before you trust it.
