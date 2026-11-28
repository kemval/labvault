"""
Start-up checks for the production container (roadmap 5.4, ADR 0026), run by
deploy/start.sh before Litestream and the app start. Exit 1 with the reason
if the deployment must not run:

- demo mode requested in a production build (LABVAULT_BUILD=production);
- a non-demo deployment whose database contains simulated demo data.

It also creates or migrates the schema (ADR 0003), so the health check passes
before the first visitor (ADR 0024).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ConfigError, demo_mode  # noqa: E402
from repo.samples import refuse_simulated_data  # noqa: E402
from repo.schema import init_db  # noqa: E402


def main() -> int:
    try:
        demo = demo_mode()
        init_db()
        if not demo:
            refuse_simulated_data()
    except ConfigError as e:
        print(f"LabVault must not start: {e}", file=sys.stderr)
        return 1
    print(f"Preflight ok ({'demo' if demo else 'secure'} mode).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
