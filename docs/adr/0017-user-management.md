# ADR 0017: User management

- **Status:** Accepted (2026-11-27)
- **Addresses:** roadmap item 3.6 (C1 follow-up). Adds the admin unlock that ADR 0013 lacked.

## Context
Accounts could only be created on first start: the demo users, or a single admin in secure mode. Nobody could be added, removed, reset or unlocked without editing the database, and a locked account had to wait out its 15 minutes.

## Decision (the product owner chose the reset flow and the open-samples rule)
- **Migration 9** adds two columns to `users`:
  - `active`, default 1: existing accounts stay active;
  - `must_change_password`, default 0: no existing password is forced to change.
- **Accounts are disabled, never deleted.** Results, signatures, investigations and the audit trail refer to them, and the foreign keys already stop deletion of a referenced account.
- **Services, each in one transaction with its audit row:**

  | Service | Audit action | Notes |
  |---|---|---|
  | `create_user` | `USER_CREATED` | |
  | `reset_password` | `PASSWORD_RESET` | also clears any lockout |
  | `unlock_user` | `ACCOUNT_UNLOCKED` | |
  | `set_user_active` | `USER_DISABLED`/`USER_ENABLED` | old and new value |
  | `change_role` | `USER_ROLE_CHANGED` | old and new value |
  | `change_password` | `PASSWORD_CHANGED`/`PASSWORD_CHANGE_FAILED` | a user's own password |

  - Every admin action except creating an account requires a reason.
  - Audit rows never contain a password.
- **Rules (`domain.account_change_error`):**
  - only admins manage accounts;
  - an admin can't manage their own account. The acting admin therefore always stays active, so at least one admin remains;
  - system accounts can't be managed.
- **Passwords:**
  - **Temporary passwords:** an admin-set password, whether at creation or reset, must be changed at the next sign-in. Until then the app shows only the change-password form, so the admin never knows a password that stays in use.
  - **Self-service changes:** users change their own password on **My Account**. The current password is checked with the sign-in lockout policy, so failures count toward the lock.
  - **Rules:** at least 12 characters (`domain.MIN_PASSWORD_LENGTH`, also used for the secure-mode admin), not the username, and different from the current one.
  - **Usernames:** 3–32 characters, lowercase, starting with a letter.
- **Open samples block disabling.** An account with Pending or In Progress samples assigned can't be disabled, and a lab tech with open samples can't become an admin (samples are assigned only to lab techs), until an admin reassigns those samples. The refusal lists them.
- **A disabled account stops working everywhere:**
  - **Sign-in:** it can't sign in, and it sees the same message as a wrong password. The attempt is audited as `LOGIN_FAILED` "Account disabled".
  - **Writes:** `_actor` refuses it for every write. Sample registration and protocol creation now check the actor too.
  - **Assignment:** it leaves the assignee lists, and samples can be assigned only to *active* lab techs.
- **Sessions follow the account.** `app.py` re-reads the signed-in account on each rerun, which is one indexed query.
  - A disabled account is signed out at its next click, audited as `LOGOUT` "account disabled".
  - A role change applies at the next click.

## Consequences
- An admin who forgets their own password needs another admin. If the deployment has a single admin, the only recovery is editing the database. The README Configuration section advises keeping two admins.
- Temporary passwords are handed over outside the app. There is no email, so there are no reset links.
- Admin account actions require a reason but not a password re-entry. Re-authentication for sensitive admin actions could come later.
