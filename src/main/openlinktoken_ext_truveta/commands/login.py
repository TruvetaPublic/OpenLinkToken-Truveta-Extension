"""
Copyright (c) Truveta. All rights reserved.

login command: authenticate with Truveta services via OAuth 2.0 Device Code Flow.
"""

import argparse
import sys

from openlinktoken_ext_truveta.auth import (
    DEFAULT_DOMAIN_URL,
    AuthError,
    Credentials,
    _cache_path,
    _extract_domain,
    decode_jwt_payload,
    ensure_auth,
    write_session_api_url,
)
from openlinktoken_ext_truveta.commands.common import resolve_api_url, resolve_auth_url

__all__ = ["DEFAULT_DOMAIN_URL", "_login"]


def _authenticate(
    args: argparse.Namespace,
) -> tuple[str, Credentials] | tuple[None, None]:
    auth_url = resolve_auth_url(args)
    force = getattr(args, "force", False)

    try:
        if force:
            domain = _extract_domain(auth_url)
            cache_file = _cache_path(domain)
            if cache_file.exists():
                cache_file.unlink()

        credentials: Credentials = ensure_auth(auth_url)

        payload = decode_jwt_payload(credentials.id_token)
        name = payload.get("name") or payload.get("email") or "unknown"
        email = payload.get("email", "")

        if email and name != email:
            print(f"You've successfully logged in, {name} ({email})!")
        else:
            print(f"You've successfully logged in, {name}!")

        return auth_url, credentials
    except AuthError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        return None, None


def _login(args: argparse.Namespace) -> int:
    """
    Authenticate with Truveta services.

    This command only performs authentication and credential caching.
    For exchange configuration setup, use the ``initiate-exchange`` subcommand.

    Inputs:
        args: Parsed CLI arguments containing --domain and --force flags.

    Returns:
        Exit code (0 on success, 1 on failure).
    """
    api_url = resolve_api_url(args)
    auth_url, _credentials = _authenticate(args)
    if not auth_url:
        return 1

    try:
        write_session_api_url(api_url)
    except AuthError as exc:
        print(f"Failed to persist login session: {exc}", file=sys.stderr)
        return 1

    return 0
