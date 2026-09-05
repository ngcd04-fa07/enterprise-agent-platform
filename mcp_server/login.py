"""One-time helper: logs in against the real running API and prints the
session/CSRF tokens to configure the MCP server with. Not part of the MCP
server itself — this is the only place a password is ever handled, kept
separate and simple. Run once, then set the printed values as
SESSION_TOKEN/CSRF_TOKEN in whatever launches server.py (see README.md).

Usage:
    python3 login.py --api-base-url http://localhost:8000 --email you@example.com
"""

import argparse
import asyncio
import getpass

import httpx


async def _login(*, api_base_url: str, email: str, password: str) -> None:
    async with httpx.AsyncClient(base_url=api_base_url) as client:
        response = await client.post("/auth/login", json={"email": email, "password": password})
        if response.status_code != 200:
            raise SystemExit(f"Login failed ({response.status_code}): {response.text}")

        session_token = response.cookies.get("session_token")
        csrf_token = response.json()["csrf_token"]
        if not session_token:
            raise SystemExit("Login succeeded but no session_token cookie was returned.")

        print("Login succeeded. Set these when launching server.py:\n")
        print(f"SESSION_TOKEN={session_token}")
        print(f"CSRF_TOKEN={csrf_token}")
        print(
            "\nThese expire the same way a browser session would "
            "(logout, or the session's normal lifetime) — re-run this "
            "script to get fresh ones."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    asyncio.run(_login(api_base_url=args.api_base_url, email=args.email, password=password))


if __name__ == "__main__":
    main()
