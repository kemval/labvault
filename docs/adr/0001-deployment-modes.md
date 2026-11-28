# ADR 0001 — Demo vs. secure deployment modes

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding C1 (hard-coded, publicly displayed default credentials)

## Context
`seed_users()` inserted four accounts with fixed passwords on every start, and
the login and Admin pages printed those passwords. Any deployment, including
the public demo, therefore had a publicly known admin login. Deleted accounts
were also re-created on every restart.

## Decision
1. Two modes, chosen by `LABVAULT_DEMO_MODE`. Only an explicit `true`/`1`/`yes`
   enables demo mode, so a deployment is **secure by default** (fail closed).
2. Settings are read from environment variables first, then `st.secrets`
   (`config.py`).
3. Accounts are seeded **only when the `users` table is empty**.
   - Demo mode seeds `db.DEMO_USERS`, and the UI shows their credentials.
   - Secure mode seeds one `admin` from `LABVAULT_ADMIN_PASSWORD`
     (minimum 12 characters). The app refuses to start if it is not set.
4. In secure mode the app refuses to start if any account still has a
   published demo password. This stops a demo database from being promoted
   to production by accident.
5. No forced password change on first login: the operator chooses the initial
   admin password, so it is not a shared default. User management and
   password changes are roadmap item 3.6.

## Consequences
- The public demo must set `LABVAULT_DEMO_MODE = "true"` in its Streamlit
  Cloud secrets, or it will show a configuration error.
- An existing local `labvault.db` (which contains the demo users) only starts
  in demo mode. Use a fresh database for a secure deployment.
- Password hashing is still unsalted SHA-256 (audit H6, roadmap 4.1), so the
  admin password must not be reused elsewhere. *(Resolved by ADR 0013: salted
  scrypt, lockout and idle timeout.)*
