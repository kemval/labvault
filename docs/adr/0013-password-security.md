# ADR 0013: Password storage, lockout and session timeout

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit finding H6; roadmap item 4.1. A prerequisite for e-signatures (3.3), which re-check the signer's password.

## Context
Passwords were stored as unsalted SHA-256: fast to brute-force, and identical passwords had identical hashes. Any number of guesses was allowed, and a session lasted until the browser tab closed.

## Decision
- **Hashing: salted scrypt from Python's standard library** (`repo/passwords.py`).
  - N=2¹⁴, r=8, p=5 (about 16 MiB and about 140 ms per hash). This is one of OWASP's recommended scrypt settings.
  - Format: `scrypt$n$r$p$salt$hash`, compared in constant time.
  - argon2id would also qualify. It was not chosen because it adds a compiled dependency to the hashed lock files (ADR 0010), while scrypt is already in the standard library.
  - The cost is stored with each hash, so it can be raised later. `needs_rehash` upgrades old hashes at the user's next successful sign-in.
- **Migration 6:**
  - adds `users.failed_logins` and `users.locked_until`;
  - wraps every legacy SHA-256 digest as `scrypt-sha256$…` (scrypt over the old digest), so no fast hash remains on disk even for users who never sign in again. The next sign-in replaces it with a plain scrypt hash.
- **Lockout:** `services.sign_in` runs in one write transaction, so concurrent attempts count correctly.
  - 5 consecutive failures (`domain.MAX_FAILED_LOGINS`) lock the account for 15 minutes and write `ACCOUNT_LOCKED`.
  - While an account is locked, its password isn't checked. Attempts are refused and audited as `LOGIN_FAILED` with "Account locked".
  - A successful sign-in resets the count.
- **No account enumeration:**
  - The login screen shows one message for every failure: a wrong password, an unknown user or a locked account.
  - An unknown username still costs one hash verification, so response time doesn't reveal which accounts exist.
- **Idle timeout:** the first interaction after 30 minutes idle (`domain.SESSION_IDLE_MINUTES`) signs the user out, writes `SESSION_TIMEOUT`, and the login screen explains why. Streamlit only runs on interaction, so that action is refused rather than the page closing by itself.

## Consequences
- Anyone who knows a username can lock that account for up to 15 minutes. This is accepted, and the lock clears itself. An admin can unlock an account early since 3.6 (ADR 0017).
- Tests set a tiny scrypt cost (`conftest.cheap_password_hashing`); the cost stored in each hash keeps verification correct.
- The new auth events are in `SESSION_ACTIONS`, so they appear in the audit trail but not in the dashboard's activity feed.
