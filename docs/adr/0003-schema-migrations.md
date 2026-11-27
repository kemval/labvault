# ADR 0003 — Versioned schema migrations

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding A5 (no schema evolution); prerequisite for C4

## Context
The schema was created with `CREATE TABLE IF NOT EXISTS`. That can't add or
change columns on an existing database, so any schema fix would only reach
new installs.

## Decision
- The existing `CREATE TABLE` statements in `db.init_db()` are frozen as the
  baseline (version 0).
- Later changes are appended to `db.MIGRATIONS` as Python functions that take
  a connection. A migration's version is its position plus one, recorded in
  SQLite's `PRAGMA user_version`.
- `init_db()` calls `apply_migrations()`, which runs each pending migration in
  its own `BEGIN IMMEDIATE` transaction and re-reads the version under the
  write lock. A failure rolls back that migration and leaves the version
  unchanged. Concurrent startups apply each migration once.
- No migration library. Alembic and similar tools are justified only if we
  move to Postgres (roadmap 5.1). At that point the same ordered list can be
  ported.

## Rules
- Never edit, reorder or delete a released migration. Fix forward with a new
  one.
- Migrations that change data must also write an `audit_trail` entry.
