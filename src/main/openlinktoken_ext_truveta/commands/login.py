"""
Copyright (c) Truveta. All rights reserved.

Login command: authenticate with Truveta services via OAuth 2.0 Device Code Flow.
"""

import argparse
import sys

from openlinktoken_ext_truveta.auth import (
    AuthError,
    Credentials,
    _cache_path,
    decode_jwt_payload,
    ensure_auth,
)
from openlinktoken_ext_truveta.commands.common import (
    SessionResolutionError,
    resolve_domain,
)
from openlinktoken_ext_truveta.session import write_session_domain


def _authenticate(
    args: argparse.Namespace,
) -> tuple[str, Credentials] | tuple[None, None]:
    """
    Authenticate the user against the resolved Truveta domain.

    Inputs:
        args: Parsed CLI arguments containing --domain and --force flags.

    Returns:
        A tuple of the resolved domain and credentials on success, otherwise
        (None, None) after printing the failure reason.
    """
    try:
        domain = resolve_domain(args, allow_default=True)
    except SessionResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return None, None

    force = getattr(args, "force", False)

    try:
        if force:
            cache_file = _cache_path(domain)
            if cache_file.exists():
                cache_file.unlink()

        credentials = ensure_auth(domain)
        payload = decode_jwt_payload(credentials.id_token)
        name = payload.get("name") or payload.get("email") or "unknown"
        email = payload.get("email", "")

        if email and name != email:
            print(f"You've successfully logged in, {name} ({email})!")
        else:
            print(f"You've successfully logged in, {name}!")

        return domain, credentials
    except AuthError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        return None, None


def _login(args: argparse.Namespace) -> int:
    """
    Authenticate with Truveta services.

    Inputs:
        args: Parsed CLI arguments containing --domain and --force flags.

    Returns:
        Exit code 0 on success or 1 when authentication/session persistence fails.
    """
    domain, _credentials = _authenticate(args)
    if not domain:
        return 1

    try:
        write_session_domain(domain)
    except Exception as exc:
        print(f"Failed to persist login session: {exc}", file=sys.stderr)
        return 1

    return 0
