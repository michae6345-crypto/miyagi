# Alerts for miyagi-cloud

Service: **miyagi-cloud**, id `srv-dc0fbemk1f9s738vq2r0`, <https://miyagi-cloud.onrender.com>. Four things to set up,
each in a few minutes. Render's menus move from time to time: where a step below names a label you cannot find,
look for the nearest match in the same page, or check in the dashboard (Render's docs: <https://render.com/docs/notifications>
and <https://render.com/docs/health-checks>).

Nothing here needs a deploy, except the env vars in part 4 (saving env vars restarts the service by itself).

## 1. Deploy failures (Render notifications)

Render sends notifications by email and, if connected, to Slack. The default is "failure notifications only", which
covers failed deploys.

1. Open <https://dashboard.render.com>, pick the workspace that owns miyagi-cloud.
2. Workspace **Settings** (left sidebar) › **Notifications**.
3. Under the email section, make sure your address (and Adrian's, if he should get them) is set to receive
   notifications, and the level is **Only failure notifications** (or **All** if you also want successful deploys).
4. Optional, for phones: in the same page, **Connect Slack**, pick the channel both founders watch, and set it to
   failure notifications.
5. Check the per-service setting: open **miyagi-cloud** › **Settings** › scroll to **Notifications**. It should say
   **Use workspace default** (or explicitly failure notifications). If it says **None**, change it.
6. Test: none needed. The next failed build or failed deploy sends one. (To see it once, you can push a commit to a
   staging service that fails `pip install`; never to `claude/eng-proxy`, which deploys production.)

What it does not cover: a deploy that succeeds but serves errors. That is parts 2 and 3.

## 2. Instance down and the health check path

Today the dashboard has no health check path, so Render only knows whether the process is listening on its port.
`render.yaml` already says `healthCheckPath: /healthz`, but the live service was not created from (or synced with)
the Blueprint, so set it by hand:

1. **miyagi-cloud** › **Settings** › **Health Checks** (on some accounts it sits under **Health & Deploy**).
2. **Health Check Path**: `/healthz`. Save.

What that buys:

- Render calls `/healthz` during each deploy and only switches traffic to the new version once it answers 200, so a
  version that crashes on start never replaces the running one (and the deploy fails, which part 1 reports).
- While running, an instance that stops answering `/healthz` is restarted, and Render's failure notifications (part 1)
  include a service that goes down or becomes unhealthy. Check in the dashboard which service events your
  notification level covers; if "unhealthy" or "server failure" is not listed there, use the external monitor below.

`/healthz` answers 200 whenever the process runs (no auth, never rate limited). It does not go red when the database
is unreadable or the proxy is paused: those are in its body (`db_ok`, `paused`), not its status, on purpose, so a
database hiccup does not make Render restart the service in a loop.

**External monitor (recommended, free).** Render cannot tell you it is down if Render itself is the problem. Add an
uptime monitor outside Render (for example UptimeRobot or Better Stack Uptime, both have free tiers):

- URL `https://miyagi-cloud.onrender.com/healthz`, method GET, every 1 to 5 minutes.
- Alert when the status is not 200, or (if the monitor supports a keyword check) when the body does not contain
  `"db_ok":true`. That second check catches a full or broken disk, which the Render health check deliberately does not.
- Send its alerts to the same Slack or Discord channel as part 4.

This is also the "dead-man's switch" the README asks for (R01 step 6, still to do).

## 3. 5xx rate

Render does not offer a built-in "alert me when 5xx passes N%" rule for web services as far as we know: check in the
dashboard under **miyagi-cloud** › **Metrics** whether your plan shows an alert option there. The Metrics page does
show HTTP requests by status code, which is where to look when something feels off.

To get an actual alert on 5xx, send the logs somewhere that alerts on them:

1. Workspace **Settings** › **Log Streams** (Render's name for forwarding logs). Add a destination your log tool gives
   you (Better Stack Logs, Datadog, Papertrail, ... each shows the syslog endpoint and token to paste here).
2. In that tool, make an alert on log lines from miyagi-cloud matching this pattern. Every request writes exactly one
   line, `<time> INFO miyagi.cloud <METHOD> <path> <status> <ms>ms ...`, for example:

       2026-11-22 10:00:00,000 INFO miyagi.cloud POST /v1/anthropic/v1/messages 502 812ms model=claude-haiku-5-5 ...

   Match ` miyagi.cloud ` and a status of 5xx (regex `miyagi\.cloud \S+ \S+ 5\d\d `). Alert when there are more than,
   say, 20 in 5 minutes. The line has the status, not the error kind; an upstream refusal also logs a WARNING line
   `upstream anthropic error <status>: ...` (keys redacted) just before it. Statuses worth knowing before you tune it:
   - `502 upstream_auth_error`: the Anthropic key is wrong or revoked. Every AI call fails. Act at once.
   - `503 upstream_unavailable`: the Anthropic balance or quota ran out (R02's prepaid balance). Act at once.
   - `503 proxy_disabled`: you paused it (`/admin/proxy/pause`) or `PROXY_ENABLED=false`. Expected while paused.
   - `529` / `503 overloaded`: the provider is overloaded. Usually passes on its own.
   - `502 upstream_unreachable`: the provider could not be reached.
3. The log lines never contain a token, a body or an IP address, so forwarding them is safe for the privacy policy's
   "what we keep" (the log tool keeps them for its own retention period; pick a short one).

If you do not want another tool: the upstream-auth and balance cases also show up as a sudden stop in spend, which
the external monitor in part 2 does not catch. A log stream is the only real 5xx alert.

## 4. Spend alerts (built into miyagi-cloud)

The service sends its own alerts to one incoming webhook (Discord or Slack), each at most once per UTC day
(`app.py` `alert()`, README "Alerts"). Nothing is sent until the webhook is set.

1. Make the webhook:
   - Discord: channel › **Edit Channel** › **Integrations** › **Webhooks** › **New Webhook** › **Copy Webhook URL**.
   - Slack: <https://api.slack.com/apps> › **Create New App** › **From scratch** › **Incoming Webhooks** › turn on ›
     **Add New Webhook to Workspace** › pick the channel › copy the URL.
2. Render: **miyagi-cloud** › **Environment** › **Add Environment Variable** (or edit the existing ones) and set:

   | Variable | Value | What it does |
   |---|---|---|
   | `ALERT_WEBHOOK_URL` | the `https://` URL from step 1 | A secret: dashboard only, never in `render.yaml`. Unset or not https: no alerts. |
   | `ALERT_DAILY_USD` | `25` (the default) | `spend_50`, `spend_80`, `spend_100` fire at 50/80/100% of this estimated spend per UTC day, every install together. 0 = off. |
   | `ALERT_TOKEN_DAILY_USD` | `6.00` (the default, 3x `FREE_DAILY_USD`) | `token:<id>` fires when one install spends more than this today. 0 = off. |
   | `GLOBAL_MINTS_WARN_PER_HOUR` | `500` (the default) | `mints_high`: that many new installs in one hour. |
   | `NEW_INSTALLS_PER_DAY` | `500` (the default) | `installs_full` fires when the daily new-install cap is reached. |
   | `DAILY_USD_CAP` | leave unset | Only if you set the global brake: `brake` fires when it is reached. |

   `account_delete_pending` also goes to this webhook, when an account deletion could not delete the Supabase user
   (no `SUPABASE_SERVICE_ROLE_KEY`, or Supabase failed).

   **Save Changes**. Render restarts the service with the new values (a minute or so).
3. Test it reaches both phones:

       curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" https://miyagi-cloud.onrender.com/admin/alerts/test

   Answer `{"alerts": true, "sent": true}` and a message in the channel. `"alerts": false` means the URL is missing or
   not https. `"sent": false` means a test alert already went out today (once per UTC day, like every alert).
4. Check the state any time: `curl -H "X-Admin-Token: $ADMIN_TOKEN" https://miyagi-cloud.onrender.com/admin/proxy`
   shows `alerts`, `alert_daily_usd` and today's new installs; `/admin/usage` shows `usd_today` and `alerts_today`.

These are estimates from the proxy's own price table, not Anthropic's bill. The hard stop stays the Anthropic
prepaid balance with auto-reload off (R02); set the Anthropic console's own usage notification too
(console.anthropic.com › Settings › Billing or Limits: check in the console for the exact label).

## Checklist

- [ ] Part 1: workspace notifications on (failures), service set to workspace default, Slack connected if wanted.
- [ ] Part 2: Health Check Path `/healthz` saved; external uptime monitor on `/healthz`.
- [ ] Part 3: log stream to a log tool, alert on 5xx lines (or decide to go without).
- [ ] Part 4: `ALERT_WEBHOOK_URL` set, `/admin/alerts/test` arrived on both phones.
