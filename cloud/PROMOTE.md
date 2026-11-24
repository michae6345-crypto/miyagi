# Promote claude/eng-proxy-next to production (claude/eng-proxy)

Production: `claude/eng-proxy` at `d793a7fe`, service miyagi-cloud (`srv-dc0fbemk1f9s738vq2r0`), auto-deploys on push.
Built from `git log --oneline origin/claude/eng-proxy..origin/claude/eng-proxy-next -- cloud/` (2026-11-24).
`d793a7fe` (the key-trim fix) is merged into next, so the push is a **fast-forward**. Only Michael pushes.

## 1. What changes

| PR / lane | Change |
|---|---|
| ratelimit, sec2 (`cf13788d`..`cba57786`) | Per-IP / per-token / admin rate limits, admin lockout, model and body allowlists, reviewed lesson cache, key trim |
| #238 (`fdc15abb`) | Dollar caps per install and user, new-install cap, runtime kill switch, webhook alerts, 32k token cap |
| #241 | `POST /v1/account/delete`, hourly retention prune, networks stored only as keyed hashes |
| #244 | Activation funnel (`/v1/funnel`, `/admin/funnel`) |
| #246 | `REQUIRE_SIGNIN` modes, guest cap, per-user token cap and build cap, validated auto-approve and revoke |
| #250 | Build claim lock (`{"held": true}`) |
| stream (`53c7845a`) | Unbuffered streaming, one keep-alive upstream client |
| #264 | `POST /v1/session` |
| #267 | Region block (off) |
| #269 | Audited client IP, edge-header log, `--no-proxy-headers` |

## 2. What the first start does to the SQLite file (1 GB disk, `/var/data/miyagi.db`)

It runs automatically in `Store.__init__` and then `prune_now()`:
- Adds the new tables and the `tokens.plan` / `tokens.mint_net` columns.
- Moves the old first-writer `lessons` rows into `lesson_candidates` as **pending**, then empties `lessons`.
- Rewrites `tokens.install_id` to the token prefix.
- Hashes any stored network.
- Folds per-install usage and events older than 35 days into daily totals, and deletes old detail rows.

**None of this is reversible** (the lessons move, the install_id rewrite and the prune), so take a copy first.

**Rollback compatibility:** the old code still runs on the migrated file. Every table and column it uses is still there, and it ignores the new ones. It just serves no cached lessons, because `lessons` is now empty.

## 3. Render env (dashboard › miyagi-cloud › Environment)

The service is **not synced from the Blueprint** (its health check path is empty, but `render.yaml` sets one). So `render.yaml` values don't apply on their own. Anything left unset takes the code default.

| Variable | Set to | Default | Stays off? | Why |
|---|---|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | the secret key | unset | — | Without it, account deletes stay `pending` |
| `ADMIN_TOKEN` | keep (32+ chars, 12+ distinct) | — | — | A weak one turns `/admin` off (503) |
| `NET_HASH_KEY` | 32+ random chars, set **before** the deploy | derived from `ADMIN_TOKEN` | — | Network hashes must not change if `ADMIN_TOKEN` is rotated |
| `MINT_NET_RETAIN_DAYS` | leave unset | 0 (kept while the install is anonymous) | — | Needed by the per-network guest cap |
| `REQUIRE_SIGNIN` | `0` | off | yes | The app and engine can't handle `signin_required` yet |
| `REGION_BLOCK` / `COUNTRY_DB_PATH` | `0` / unset | off | yes | No country database on the disk yet |
| `ANON_DAILY_USD` | `0.50` | 0.50 | — | Only applies with `REQUIRE_SIGNIN=build`. **0 means no cap** |
| `LINKED_DAILY_USD` / `LINKED_DAILY_TOKENS` | `3.00` / `20000000` | same | — | Per signed-in user per day |
| `LESSON_AUTO_APPROVE_VALIDATED` | `0` in production | 0 (`render.yaml`: 1) | yes | D11: no shared cache at launch. Turn on after review |
| `LESSON_CLAIM_TTL_S` | `600` | 600 | — | Build lock |
| `TRUSTED_PROXY_HOPS` | `1` until the hop check | 1 | — | See §5 |
| `CLIENT_IP_HEADER` | unset; `cf-connecting-ip` only if the hop check shows it is overwritten | unset | yes | A header the edge passes through would be forgeable |
| `ALERT_WEBHOOK_URL` | Discord or Slack webhook | unset | — | No alerts without it (`ALERTS.md`) |
| `ANTHROPIC_SERVER_TOOLS` | `web_search,web_fetch` (the engine's finder searches the web) | empty | — | New in this release: empty refuses every server tool with 400 |
| `DAILY_USD_CAP` | unset (delete any old low value) | off | yes | A low value stops every learner |

**Settings (by hand, since there is no Blueprint sync):**
- Health Check Path: `/healthz`.
- Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT --no-proxy-headers`.

The start command change isn't urgent (with the default `FORWARDED_ALLOW_IPS` nothing changes), but set it now.

## 4. Order

1. **Snapshot.** Render keeps an automatic daily disk snapshot for 7 days (Disk page). Also take a copy now: service › **Shell**, run `python -c "import sqlite3; s=sqlite3.connect('/var/data/miyagi.db'); d=sqlite3.connect('/var/data/miyagi-pre-promote.db'); s.backup(d); d.close(); print('ok')"`, then `ls -la /var/data`. To keep it off the box too, run `wormhole send /var/data/miyagi-pre-promote.db` there and `wormhole receive` on your Mac.
2. **Env vars and settings** from §3. Saving them restarts the old code, which is harmless.
3. **Push (Michael):**
   ```
   git fetch origin
   git merge-base --is-ancestor origin/claude/eng-proxy origin/claude/eng-proxy-next && echo fast-forward-ok
   git push origin origin/claude/eng-proxy-next:claude/eng-proxy
   ```
   Never use `--force`. If the check doesn't print `fast-forward-ok`, stop.
4. **Watch the deploy** in Events and Logs. A service with a disk has a few seconds of downtime. Look for `miyagi-cloud ... up:` and `pruned old rows:`.

## 5. Live checks (★ = costs money: only with Michael's yes)

- **Health:** `curl -s https://miyagi-cloud.onrender.com/healthz`. Expect `ok`, `db_ok: true`, `commit` = the new SHA, `require_signin: "off"`, `keys_configured.anthropic: true`.
- **Hop check (#269):** restart the service, then right away (before learner traffic takes the "first request") run `curl -s -X POST https://miyagi-cloud.onrender.com/v1/install -H 'Content-Type: application/json' -d '{}' -H 'X-Forwarded-For: 192.0.2.77' -H 'CF-Connecting-IP: 192.0.2.77'`. In the log, look for:
  - `first request: 2 X-Forwarded-For entries ... the chosen entry is a global address`;
  - an `edge client-IP headers:` line with no `EQUALS AN ENTRY THE CLIENT WROTE` on `cf-connecting-ip`.

  Any other count or kind: fix `TRUSTED_PROXY_HOPS` (README, Rate limits) and redo. Free.
- **Session:** `curl -s -X POST .../v1/session -H "Authorization: Bearer $MI" -d "{\"access_token\":\"$JWT\"}" -H 'Content-Type: application/json'`. Use a throwaway install token (`$MI`) and a signed-in Supabase access token (`$JWT`). Expect `linked: true`, `caps`, and `signin_mode: "off"`. Free.
- **Delete:** mint an install (as above), then `curl -s -X POST .../v1/account/delete -H "Authorization: Bearer $MI" -d '{}' -H 'Content-Type: application/json'`. Expect `{"ok":true,"install":true,"account":"none"}`; running it again gives 401. Free.
- **Admin:** `curl -s -H "X-Admin-Token: $ADMIN_TOKEN" .../admin/proxy`, and `POST /admin/alerts/test`. Free.
- **Guest cap without spending (do it on staging, or accept a few minutes):** this briefly gates every guest.
  1. Set `REQUIRE_SIGNIN=build` and `ANON_DAILY_USD=0.0001`. Not 0: 0 turns the cap off.
  2. Send one Haiku call with a fresh guest token. Expect 429 `anon_daily_cap`. The call is refused before anything is sent upstream.
  3. Restore `REQUIRE_SIGNIN=0` and `ANON_DAILY_USD=0.50`.
- ★ **Real model call:** one Haiku call with `max_tokens` 10 (about $0.0001).
- ★ **A guest build reaching the $0.50 cap:** optional.

## 6. Rollback

- **Fast:** Render › Events › the `d793a7fe` deploy › **Rollback**. Auto-deploy keeps the branch at the new commit, so fix forward next. Or reset the branch: `git push --force-with-lease=claude/eng-proxy:<new sha> origin d793a7fe:claude/eng-proxy` (Michael only).
- **What the old code sees:** the migrated DB works as is. Guests keep their tokens, links stay, and usage and deletions done since stay. Lost: cached lessons (now pending candidates the old code doesn't read). The per-network mint limits go back to the old in-memory ones.
- **Restore the snapshot instead** only if the file is damaged or unreadable (`db_ok: false`, startup errors), or the migration went wrong. Restoring undoes everything since the copy, including **account deletions**. Re-run those: `/admin/deletions` won't list them, so check the log for `account delete:` lines.
