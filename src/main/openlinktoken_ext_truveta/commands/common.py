"""
Copyright (c) Truveta. All rights reserved.

Shared command helpers for resolving API and Auth0 environment URLs.
"""

import argparse

from openlinktoken_ext_truveta.auth import DEFAULT_DOMAIN_URL, read_session_api_url

DEFAULT_LOCAL_DEV_API_URL = "http://localhost:18080"


class SessionResolutionError(ValueError):
    """Raised when a command requires a login session but none is available."""


def _get_string_arg(args: argparse.Namespace, name: str) -> str | None:
    value = getattr(args, name, None)
    return value if isinstance(value, str) and value else None


def resolve_api_url(args: argparse.Namespace, *, session_only: bool = False) -> str:
    """Resolve the target API URL from session or command/env inputs."""
    if getattr(args, "local_dev", False):
        return DEFAULT_LOCAL_DEV_API_URL

    if session_only:
        session_url = read_session_api_url()
        if session_url:
            return session_url

        raise SessionResolutionError(
            "No login session found. Please run 'olt truveta login' first."
        )

    return _get_string_arg(args, "domain") or DEFAULT_DOMAIN_URL


def resolve_auth_url(args: argparse.Namespace, *, session_only: bool = False) -> str:
    """Resolve the Auth0 environment URL from session or command/env inputs."""
    if session_only:
        return resolve_api_url(args, session_only=True)

    return _get_string_arg(args, "auth_domain") or resolve_api_url(args)
