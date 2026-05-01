"""
Copyright (c) Truveta. All rights reserved.

Shared command helpers for resolving API and Auth0 environment URLs.
"""

import argparse

from openlinktoken_ext_truveta.auth import (
    DEFAULT_DOMAIN_URL,
    _extract_domain,
    get_api_domain_url,
    get_auth_domain_url,
    read_session_auth_url,
)

DEFAULT_LOCAL_DEV_API_URL = "http://localhost:18080"
DEFAULT_TIMEOUT_SECONDS = 30
LOCAL_DEV_TIMEOUT_SECONDS = 180


class SessionResolutionError(ValueError):
    """Raised when a command requires a login session but none is available."""


def _is_local_dev(args: argparse.Namespace) -> bool:
    return getattr(args, "local_dev", False) is True


def _get_string_arg(args: argparse.Namespace, name: str) -> str | None:
    value = getattr(args, name, None)
    return value if isinstance(value, str) and value else None


def resolve_api_url(args: argparse.Namespace) -> str:
    """Resolve the target API URL from args, saved login context, or defaults."""
    if _is_local_dev(args):
        return DEFAULT_LOCAL_DEV_API_URL

    domain_arg = _get_string_arg(args, "domain")
    if domain_arg:
        return domain_arg

    auth_url = read_session_auth_url()
    if auth_url:
        return get_api_domain_url(_extract_domain(auth_url))

    return DEFAULT_DOMAIN_URL


def resolve_auth_url(args: argparse.Namespace) -> str:
    """Resolve the Auth0 login domain URL from args, saved login context, or defaults."""
    if _is_local_dev(args):
        return DEFAULT_LOCAL_DEV_API_URL

    api_domain = _get_string_arg(args, "domain")
    if api_domain and api_domain.startswith("https://api."):
        domain = api_domain[len("https://api.") :].rstrip("/")
        return get_auth_domain_url(domain)

    if api_domain:
        return api_domain

    saved_auth_url = read_session_auth_url()
    if saved_auth_url:
        return saved_auth_url

    return get_auth_domain_url(_extract_domain(DEFAULT_DOMAIN_URL))


def resolve_timeout_seconds(
    args: argparse.Namespace,
    timeout_seconds: int | None = None,
) -> int:
    """Resolve request timeout from explicit override and local-dev context."""
    if timeout_seconds is not None:
        return timeout_seconds

    if _is_local_dev(args):
        return LOCAL_DEV_TIMEOUT_SECONDS

    return DEFAULT_TIMEOUT_SECONDS
