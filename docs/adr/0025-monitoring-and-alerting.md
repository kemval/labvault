# ADR 0025: Error alerts by ntfy push; external uptime and backup heartbeat monitors

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 5.3 ("uptime and error alerts reach an owner").
- **Builds on:** ADR 0021 (logged errors with a reference), 0022 (weekly audit), 0023 (Litestream), 0024 (container, health check).

## Context
After 4.3, errors were logged as JSON with a reference, but nobody was told about them. A down site, a stopped backup or a failing deploy also went unnoticed unless someone looked.

The owner wanted free services, and chose **ntfy** push notifications for error alerts.

## Decision
- **App errors:**
  - `alerts.AlertHandler` is attached by `logs.configure()` when `LABVAULT_ALERT_URL` is set (an ntfy topic URL; optional `LABVAULT_ALERT_TOKEN` for a protected topic).
  - It turns each ERROR log record into an ntfy push carrying the message, reference, time and instance name (`LABVAULT_DOMAIN`). The **traceback, the user and record data are never sent**; they stay in the server log.
  - Rate limits: the same message once per 10 minutes, at most 20 alerts an hour.
  - It sends from a background thread with a 5 s timeout and swallows delivery failures, writing one line to stderr. Alerting can't slow or break the app, and it can't recurse into logging.
  - `scripts/send_test_alert.py` verifies the channel.
  - No new dependency (stdlib `urllib`).
- **Uptime:** an external HTTP monitor (UptimeRobot or similar) checks `/_stcore/health` over HTTPS every 5 minutes. It has to be external: a monitor inside the VM can't report the VM being down. It also catches certificate problems.
- **Backups:** Litestream's own `heartbeat-url` (`LITESTREAM_HEARTBEAT_URL`, `heartbeat-interval: 5m`) pings a Healthchecks.io check only while replication succeeds. Healthchecks.io alerts when the pings stop. An empty URL disables it.

  Verified with the real image (Litestream 0.5.18):
  - pings arrived about 5 minutes apart while the database was idle;
  - after the bucket was made unreachable and a write had failed to replicate, one more ping went out (within the interval of the last good sync), then none;
  - with the recommended 5-minute period and 15-minute grace, the owner hears within about 25 minutes.
- **Already covered elsewhere:** the weekly audit (ADR 0022) and deploy failures (ADR 0024) alert by GitHub email.
- **Tests:** a conftest fixture removes `LABVAULT_ALERT_URL`, so the test suite can never page the owner.

## Consequences
- An ntfy.sh topic is public to anyone who knows its name. Alerts are designed to hold nothing sensitive, and the runbook asks for a random, private topic. ntfy can be self-hosted, or protected with a token, if that's not enough.
- **Alerts are per process.** Rate-limit state resets when the app restarts, which is acceptable for one container.
- **No metrics or dashboards.** For one lab, alerts on failure are the operational need; dashboards could come later.
