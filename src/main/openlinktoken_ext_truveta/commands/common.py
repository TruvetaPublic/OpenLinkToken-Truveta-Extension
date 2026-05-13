"""
Copyright (c) Truveta. All rights reserved.

Shared command helpers for resolving Truveta domains and API targets.
"""

import argparse
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from openlinktoken_ext_truveta.auth import AuthError, Credentials, ensure_auth
from openlinktoken_ext_truveta.domain import (
    DEFAULT_DOMAIN,
    LOCAL_DOMAIN,
    DomainError,
    get_api_url,
    validate_domain,
)
from openlinktoken_ext_truveta.session import read_session_domain

LOCAL_API_URL = "http://localhost:18080"
DEFAULT_TIMEOUT_SECONDS = 30
LOCAL_DEV_TIMEOUT_SECONDS = 180


class SessionResolutionError(ValueError):
    """Raised when a command requires a login session but none is available."""


@dataclass(frozen=True)
class AuthenticatedCommandContext:
    """Holds resolved session state for commands that require cached auth."""

    domain: str
    api_url: str
    storage_domain: str
    credentials: Credentials


def _is_local_dev() -> bool:
    """
    Return whether the command targets a local development API instance.

    Driven by the ``OLT_TRV_LOCAL_DEV`` environment variable. Set it to any
    truthy value (``1``, ``true``, ``yes``, ``y``, or ``on``) to route calls
    to the local Token Service endpoint instead of the hosted API.

    Returns:
        True when local development routing is enabled, otherwise False.
    """
    env_value = os.environ.get("OLT_TRV_LOCAL_DEV", "")
    return env_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_string_arg(args: argparse.Namespace, name: str) -> str | None:
    """
    Read a non-empty string argument from an argparse namespace.

    Inputs:
        args: Parsed CLI arguments to read from.
        name: The attribute name to resolve on the namespace.

    Returns:
        The string value when present and non-empty, otherwise None.
    """
    value = getattr(args, name, None)
    return value if isinstance(value, str) and value else None


def resolve_domain(
    args: argparse.Namespace,
    *,
    allow_default: bool = False,
) -> str:
    """
    Resolve the Truveta auth domain from args, env, session, or default.

    Inputs:
        args: Parsed CLI arguments that may include --domain.
        allow_default: When True, fall back to the production domain if no other
            source provides a valid domain.

    Returns:
        The validated Truveta domain used for authentication.
    """
    if _is_local_dev():
        return LOCAL_DOMAIN

    try:
        domain_arg = _get_string_arg(args, "domain")
        if domain_arg:
            return validate_domain(domain_arg)

        env_domain = os.environ.get("OLT_TRV_DOMAIN")
        if isinstance(env_domain, str) and env_domain:
            return validate_domain(env_domain)

        session_domain = read_session_domain()
        if session_domain:
            return session_domain
    except DomainError as exc:
        raise SessionResolutionError(str(exc)) from exc

    if allow_default:
        return DEFAULT_DOMAIN

    raise SessionResolutionError(
        "No login session found. Please run 'olt truveta login' first."
    )


def resolve_api_base_url(args: argparse.Namespace, domain: str) -> str:
    """
    Resolve the API base URL for hosted and local-dev command execution.

    Inputs:
        args: Parsed CLI arguments.
        domain: The validated Truveta domain for hosted API routing.

    Returns:
        The localhost API URL when ``OLT_TRV_LOCAL_DEV`` is set, otherwise the
        hosted API base URL.
    """
    if _is_local_dev():
        return LOCAL_API_URL
    return get_api_url(domain)


def _resolve_storage_domain(domain: str, api_url: str) -> str:
    """
    Resolve the storage-key domain used for local and hosted command state.

    Inputs:
        domain: The validated Truveta auth domain.
        api_url: The effective API URL for the current command execution.

    Returns:
        The hosted domain for remote environments or a hostname-port key for
        local development endpoints.
    """
    parsed_url = urlparse(api_url)
    hostname = parsed_url.hostname
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        if parsed_url.port is not None:
            return f"{hostname}-{parsed_url.port}"
        return hostname
    return domain


def resolve_authenticated_context(
    args: argparse.Namespace,
) -> AuthenticatedCommandContext:
    """
    Resolve the shared authenticated context required by session-based commands.

    Inputs:
        args: Parsed CLI arguments that may include --domain.

    Returns:
        An authenticated command context containing the auth domain, effective
        API URL, storage domain key, and cached credentials.
    """
    domain = resolve_domain(args)
    api_url = resolve_api_base_url(args, domain)

    try:
        credentials = ensure_auth(domain, cached_only=True)
    except AuthError as exc:
        raise SessionResolutionError(
            "Not logged in. Please, run 'olt truveta login' first."
        ) from exc

    return AuthenticatedCommandContext(
        domain=domain,
        api_url=api_url,
        storage_domain=_resolve_storage_domain(domain, api_url),
        credentials=credentials,
    )


def resolve_timeout_seconds(
    args: argparse.Namespace,
    timeout_seconds: int | None = None,
) -> int:
    """
    Resolve request timeout from an explicit override or local-dev context.

    Inputs:
        args: Parsed CLI arguments.
        timeout_seconds: Optional explicit timeout override in seconds.

    Returns:
        The effective timeout in seconds for outgoing API requests.
    """
    if timeout_seconds is not None:
        return timeout_seconds

    if _is_local_dev():
        return LOCAL_DEV_TIMEOUT_SECONDS

    return DEFAULT_TIMEOUT_SECONDS
