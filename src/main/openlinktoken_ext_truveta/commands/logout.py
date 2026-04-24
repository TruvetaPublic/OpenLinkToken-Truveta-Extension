"""
Copyright (c) Truveta. All rights reserved.

logout command: clear all cached Truveta credentials from disk.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

from openlinktoken_ext_truveta.auth import _get_client_id, clear_session_file
from openlinktoken_ext_truveta.paths import truveta_root_dir


def _revoke_token(domain: str, access_token: str) -> None:
    """
    Revoke an access token against the Auth0 revocation endpoint.

    Inputs:
        domain: The Truveta domain the token was issued by.
        access_token: The access token to revoke.
    """
    client_id = _get_client_id(domain)
    requests.post(
        f"https://login.{domain}/oauth/revoke",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": client_id,
            "token": access_token,
            "token_type_hint": "access_token",
        },
    )


def _logout(args: argparse.Namespace) -> int:
    """
    Revoke cached access tokens and delete credential files under ~/.openlinktoken/truveta/.

    Inputs:
        args: Parsed CLI arguments.

    Returns:
        Exit code (0 on success, non-zero on failure).
    """
    base_dir: Path = truveta_root_dir()
    deleted = False

    if base_dir.exists():
        for credentials_file in base_dir.rglob("credentials.json"):
            # The path structure is <base_dir>/<domain>/credentials.json
            domain = credentials_file.parent.name
            try:
                data = json.loads(credentials_file.read_text())
                access_token = data.get("access_token")
                if access_token:
                    _revoke_token(domain, access_token)
            except Exception as exc:
                print(
                    f"Warning: could not revoke token for {domain}: {exc}",
                    file=sys.stderr,
                )

            try:
                credentials_file.unlink()
                deleted = True
            except OSError as exc:
                print(
                    f"Warning: could not delete {credentials_file}: {exc}",
                    file=sys.stderr,
                )

    clear_session_file()

    if not deleted:
        print("No credentials found.")
    else:
        print("Logged out. Deleted session information.")

    return 0
