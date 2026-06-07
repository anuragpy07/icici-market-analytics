#!/usr/bin/env python3
"""refresh_session.py — Renew the ICICI Direct daily session token.

ICICI Direct session tokens expire at midnight IST. This script:
1. Prints the login URL to your terminal.
2. Waits for you to paste the session token from the redirect URL.
3. Updates the ICICI_SESSION_TOKEN in your .env file.

Run this each morning before market open:
    python scripts/refresh_session.py

Or add to cron (adjust path):
    0 8 * * 1-5 cd /path/to/project && python scripts/refresh_session.py
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_settings


def update_env_token(env_path: str, new_token: str) -> None:
    with open(env_path) as f:
        content = f.read()

    pattern = r"^ICICI_SESSION_TOKEN=.*$"
    replacement = f"ICICI_SESSION_TOKEN={new_token}"

    if re.search(pattern, content, re.MULTILINE):
        updated = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        updated = content.rstrip() + f"\n{replacement}\n"

    with open(env_path, "w") as f:
        f.write(updated)

    print(".env updated with new session token.")


def main() -> None:
    settings = get_settings()

    if not settings.ICICI_APP_KEY or not settings.ICICI_SECRET_KEY:
        print("ERROR: ICICI_APP_KEY and ICICI_SECRET_KEY must be set in .env")
        sys.exit(1)

    try:
        from breeze_connect import BreezeConnect  # type: ignore[import]
    except ImportError:
        print("ERROR: breeze-connect not installed. Run: pip install breeze-connect")
        sys.exit(1)

    breeze = BreezeConnect(api_key=settings.ICICI_APP_KEY)
    login_url = f"https://api.icicidirect.com/apiuser/login?api_key={settings.ICICI_APP_KEY}"

    print("=" * 60)
    print("ICICI Direct Session Token Refresh")
    print("=" * 60)
    print(f"\n1. Open this URL in your browser:\n\n   {login_url}\n")
    print("2. Log in with your ICICI Direct credentials.")
    print("3. After redirect, copy the 'apisession' value from the URL.")
    print("\nPaste the session token below and press Enter:")

    token = input("Session token: ").strip()
    if not token:
        print("ERROR: Empty token entered")
        sys.exit(1)

    # Verify the token works
    try:
        breeze.generate_session(api_secret=settings.ICICI_SECRET_KEY, session_token=token)
        print("\n✅ Token verified successfully!")
    except Exception as exc:
        print(f"\n⚠️  Token verification failed: {exc}")
        print("Saving token anyway — it may still work.")

    # Update .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        update_env_token(env_path, token)
    else:
        print(f"\n.env not found at {env_path}")
        print(f"Set manually: ICICI_SESSION_TOKEN={token}")

    print("\nDone. Restart the pipeline to use the new session token.")


if __name__ == "__main__":
    main()
