# Dependency update and vulnerability policy

LabVault's rules for third-party packages (ADR 0010, ADR 0022).

## What is checked, and when

| Check | When | What fails it |
|---|---|---|
| `Dependency audit` workflow (`scripts/audit_deps.py`) | every pull request, every push to `main`, Mondays 06:17 UTC, on demand | any known vulnerability in `requirements.txt` or `requirements-dev.txt`, unless it has a current exception; an expired exception |
| Dependabot alerts | as soon as GitHub learns of an advisory | — (an alert in the Security tab) |
| Dependabot security updates | with each alert that has a fix | — (a fix pull request, which CI tests) |
| Dependabot version updates | weekly | — (update pull requests, which CI tests) |

GitHub emails the repository owner when a scheduled audit fails.

## Rules
1. **Any known vulnerability blocks.** Advisories often have no severity score, so the gate doesn't use one.
2. **Fix by upgrading.**
   - Merge the Dependabot pull request, or raise the range in `requirements.in` and regenerate the locks (see the README, Dependencies).
   - Response times: within 7 days of the alert; within 2 days if the affected code runs in LabVault (for example Streamlit, requests, reportlab or openpyxl on a path the app uses).
3. **Exceptions only when there is no usable fix.**
   - Add a line to `.github/audit-exceptions.txt`: the advisory ID, a review-by date at most 30 days ahead, and why LabVault is not exposed or what limits the risk.
   - A second person reviews the pull request that adds it.
   - On the review-by date the audit fails again: remove the line, or renew it with a new date and reason.
4. **Every update goes through CI.** No direct pushes of lock changes to `main`.
   - Major-version updates also get a manual check of the main flows (sign in, intake, log a result, reports).

## Running the audit locally

```bash
.venv/bin/python scripts/audit_deps.py
```

## Re-running the weekly audit by hand

```bash
gh workflow run "Dependency audit"
```

Or use **Actions → Dependency audit → Run workflow**.
