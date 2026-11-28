"""
Send one test alert to LABVAULT_ALERT_URL and report whether it arrived at
ntfy (roadmap 5.3, ADR 0025). Run it after setting up alerts:

    python scripts/send_test_alert.py                         # on the server: uses its .env
    docker compose exec labvault python scripts/send_test_alert.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alerts  # noqa: E402


def main() -> int:
    if not alerts.alert_url():
        print("LABVAULT_ALERT_URL is not set: alerts are off.", file=sys.stderr)
        return 1
    try:
        alerts.send(f"{alerts.instance_name()}: test alert",
                    "If you can read this, LabVault error alerts reach you.",
                    priority="default", tags="white_check_mark")
    except OSError as e:
        print(f"Not delivered: {e}", file=sys.stderr)
        return 1
    print("Sent. Check the ntfy app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
