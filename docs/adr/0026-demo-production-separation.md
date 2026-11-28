# ADR 0026: Simulated data only on demo instances; a production build that can't run as a demo

- **Status:** Accepted (2026-11-28)
- **Addresses:** roadmap item 5.4 ("no synthetic data in production; production build refuses to run the simulator"); completes audit finding C4.
- **Builds on:** ADR 0001 (demo and secure modes), ADR 0004 (`is_simulated` flag), ADR 0024 (production image).

## Context
The FDA import fetches real recall records but **invents** lot numbers, assignments and every test result. ADR 0004 labels that data as simulated. Even so, a secure (non-demo) instance still:
- **auto-imported** about 100 simulated samples on the first sign-in to an empty database;
- offered admins an **Import FDA Data** button.

A demo database could also be moved into production. ADR 0001 refused it only when it still had demo passwords, not when it held simulated data.

## Decision
- **The simulator is demo-only, enforced in the service layer.**
  - `services.import_fda` raises `ServiceError` unless `demo_mode()`, before contacting openFDA.
  - The UI follows: no button, no first-login auto-import, and no "simulated lab results" line on the login page outside demo mode.
- **No simulated data in a non-demo database.**
  - At start-up, secure mode calls `repo.samples.refuse_simulated_data()`. It raises `ConfigError` if any sample or result has `is_simulated = 1`, and the app shows the reason instead of the sign-in form.
  - There is deliberately no "clean up" tool. Audit rows and signatures are append-only (ADR 0008, ADR 0014), so a demo database can't be made into a clean record. Production starts from a fresh database.
- **Production build:**
  - `LABVAULT_BUILD=production` (set in the Dockerfile) makes `demo_mode()` raise `ConfigError` if demo mode is requested. That misconfiguration stops the app instead of being silently ignored.
  - `scripts/preflight.py`, run by `deploy/start.sh` before Litestream and the app start, applies both refusals and creates the schema. The container then **exits 1 at start** with the reason, so a misconfigured deploy never reports healthy.
- **Empty-state hints** (Dashboard, Test Results) point to Sample Intake outside demo mode, not to the import button. A real-app check found the old wording.
- **The Streamlit Cloud demo** doesn't use the image and keeps `LABVAULT_DEMO_MODE=true`, so nothing changes there.

## Consequences
- A secure instance starts empty. Samples are registered through Sample Intake, and acceptance limits are set by QA (ADR 0012).
- Developers who want demo data locally set `LABVAULT_DEMO_MODE=true`, as before.
- `scripts/dedupe_simulated_results.py` and the `is_simulated` labels stay, for demo instances.
- **Validated:**
  - unit and AppTest tests cover the service refusal (no network call), the secure UI, the start-up refusal of simulated data, the production-build refusal, and all four preflight outcomes;
  - the container smoke test checks that the production image started with `LABVAULT_DEMO_MODE=true` exits 1 with the refusal.
