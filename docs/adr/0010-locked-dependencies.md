# ADR 0010: Locked, hash-checked dependencies

- **Status:** Accepted (2026-11-27)
- **Addresses:** audit findings M7 and TD7; roadmap item 2.7.

## Context
`requirements.txt` held only lower bounds (`streamlit>=1.32.0`, …). Every deploy or CI run could resolve different versions, including indirect dependencies, so what was tested was not necessarily what was deployed. The Python version was not pinned either.

## Decision
- **Ranges in `.in` files, locks in `.txt` files.** `requirements.in` and `requirements-dev.in` hold the allowed ranges and are edited by hand. `uv pip compile --universal --generate-hashes --python-version 3.11` produces `requirements.txt` and `requirements-dev.txt`, with every package (indirect ones included) at an exact version and with SHA-256 hashes.
- **Universal, not per-machine.** `pip-compile` resolves only for the machine it runs on. A lock compiled on macOS left out `watchdog`, which Streamlit requires on Linux, so a hash-checked install on Streamlit Cloud or CI would have failed. `--universal` resolves for every platform and Python ≥ 3.11 at once and records environment markers (e.g. `watchdog ; sys_platform != 'darwin'`). One file then serves macOS development, Linux CI and Streamlit Cloud.
- **Tools:** uv only compiles the locks; installing stays plain `pip install --require-hashes -r …`.
  - Streamlit Cloud keeps installing `requirements.txt` with no configuration change.
  - The dev lock is constrained to the runtime lock (`-c requirements.txt`), so tests run on exactly the deployed versions.
- **CI installs with `--require-hashes`.** A `lock-check` job recompiles both locks with uv and fails on any diff, which catches a `.in` edit without a regenerated lock. `pip-audit` checks the exact locked runtime versions.
- **Python:** `.python-version` pins 3.12 for local tools and the CI lint, lock and audit jobs; tests also run on 3.11. Streamlit Community Cloud chooses Python in the app's settings, not from a file, so the deployment must be set to 3.12 there.
- **Updates:** Dependabot (`.github/dependabot.yml`) opens weekly PRs for pip (it regenerates `uv pip compile` locks) and for GitHub Actions. CI must pass before merging.

## Consequences
- Upgrading is a deliberate step: `uv pip compile … --upgrade`, or a Dependabot PR.
- Hashes cover every published file of each pinned release, so the same lock installs on every platform.
