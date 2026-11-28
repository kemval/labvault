# Runbook: monitoring and alerting

This runbook covers roadmap 5.3 (ADR 0025). Each kind of failure reaches the owner through a free channel:

| What goes wrong | Who notices | How you hear |
|---|---|---|
| An error in the app (an export, a page, the FDA import) | LabVault itself (ADR 0021) | **ntfy** push: message, reference, time |
| The site is down, unhealthy, or its HTTPS certificate is invalid | an external uptime monitor, e.g. **UptimeRobot** | email or app, from the monitor |
| Backups stop (Litestream can't reach the bucket) | **Healthchecks.io**, fed by Litestream's heartbeat | email, or ntfy via its integration |
| A dependency gets a known vulnerability | the weekly dependency audit (ADR 0022), Dependabot | GitHub email |
| A deploy fails or isn't healthy | the Container workflow (ADR 0024) | GitHub email |

Free tiers and terms change. Check each service's current plan when you sign up.

## 1. Error alerts on your phone (ntfy)
1. Install the **ntfy** app (Android or iOS) or open https://ntfy.sh in a browser.
2. Make a long, unguessable topic name. Anyone who knows it can read the alerts. The alerts hold no lab data, but keep the name private anyway.
   ```bash
   python3 -c "import secrets; print('labvault-' + secrets.token_urlsafe(18))"
   ```
3. In the app, **subscribe** to that topic on `ntfy.sh`.
4. In `/opt/labvault/.env`, set `LABVAULT_ALERT_URL=https://ntfy.sh/<topic>`, then `docker compose up -d`.
5. Test it:
   ```bash
   docker compose exec labvault python scripts/send_test_alert.py
   ```
   A "test alert" notification should arrive within seconds.

**What an alert says:** for example, *"lab.example.org: error — The PDF report could not be built. Reference: 3f9c1a2b"*. To see the details, search the log for that reference:
```bash
docker compose logs labvault | grep 3f9c1a2b
```

**Limits:** the same message alerts at most once every 10 minutes, and no more than 20 alerts go out an hour. A failing page that re-runs on every click sends one alert, not hundreds. If ntfy can't be reached, the app carries on normally and a line is written to the log.

## 2. Uptime (UptimeRobot, or any HTTP monitor)
1. Create a free account and add a monitor:
   - **Type:** Keyword, or HTTP(s) if keywords aren't available.
   - **URL:** `https://<your-domain>/_stcore/health`.
   - **Keyword:** `ok` (alert when it's missing).
   - **Interval:** 5 minutes.
2. Under **Alert contacts**, add your email. To get these on your phone too, add a webhook to your ntfy topic if the plan allows it.
3. An HTTPS monitor also fails when the certificate is invalid or has expired. Caddy renews certificates on its own, so this catches renewal problems.

Better Stack (formerly Better Uptime) has a comparable free tier, if you prefer it.

## 3. Backups (Healthchecks.io)
1. Create a free account → **Add Check**, with **period 5 minutes** and **grace 15 minutes**.
2. Copy its ping URL (`https://hc-ping.com/<uuid>`) into `/opt/labvault/.env` as `LITESTREAM_HEARTBEAT_URL`, then `docker compose up -d`.
3. Litestream pings that URL every 5 minutes, but only while replication to the bucket is succeeding (`deploy/litestream.yml`). An idle database keeps pinging. If the bucket credentials expire, the bucket fills up or the server dies, the pings stop and Healthchecks.io alerts you.

   Tested 2026-11-28: one last ping can still go out up to 5 minutes after the bucket fails, credited to the last good sync. With a 5-minute period and 15 minutes' grace, expect the alert **within about 25 minutes** of backups failing.
4. Optionally, under **Integrations**, add ntfy and point it at the same topic.

## When an alert arrives
| Alert | First steps |
|---|---|
| App error | `docker compose logs labvault \| grep <reference>`. One-off: note it. Repeating: check the traceback; roll back if a deploy caused it (deployment.md). |
| Site down | `docker compose ps`; `docker compose logs --tail 100 labvault caddy`; `docker compose up -d`. Check the VM itself in the cloud console. |
| Backups stopped | `docker compose logs labvault \| grep -i litestream`. Usually credentials or the bucket. Fix them, then confirm pings resume. Until they do, take a file backup (backup-restore.md). |

Record significant incidents with date, impact, cause and fix. For GxP use, also record them in your deviation process.
