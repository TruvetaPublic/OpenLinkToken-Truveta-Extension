"""
Copyright (c) Truveta. All rights reserved.

Shared domain validation and URL derivation helpers.
"""

DEFAULT_DOMAIN = "truveta.com"
LOCAL_DOMAIN = "dev.truveta-int.com"

_CLIENT_IDS: dict[str, str] = {
    "dev.truveta-int.com": "NLEN3QJPPoIPHA6bQ6XUM1qCfDmz5RrO",
    "truveta-int.com": "Ouw9CrFQy8nakVDmgdINXeCZ0iB1laxw",
    "truveta.com": "MV87rfAh0Qy5ExTXZIDKssdgoYUVBIbY",
}

VALID_DOMAINS = tuple(_CLIENT_IDS)


class DomainError(ValueError):
    """Raised when a supplied Truveta domain is missing or unsupported."""


def validate_domain(domain: str) -> str:
    """
    Validate and normalize a plain Truveta domain string.

    Inputs:
        domain: A plain Truveta domain such as "truveta.com".

    Returns:
        The normalized domain string when it matches a supported environment.
    """
    normalized_domain = domain.strip().lower().rstrip("/")
    if not normalized_domain:
        raise DomainError("Domain cannot be empty.")
    if "://" in normalized_domain:
        raise DomainError(
            "Domain must be a plain value such as 'truveta.com', not a URL."
        )
    if normalized_domain not in _CLIENT_IDS:
        valid_domains = ", ".join(repr(valid_domain) for valid_domain in VALID_DOMAINS)
        raise DomainError(
            f"Unknown domain: {normalized_domain!r}. Expected one of: {valid_domains}."
        )
    return normalized_domain


def get_login_url(domain: str) -> str:
    """
    Return the Auth0 login URL for a validated Truveta domain.

    Inputs:
        domain: A supported Truveta domain such as "dev.truveta-int.com".

    Returns:
        The Auth0 login URL for the supplied domain.
    """
    return f"https://login.{validate_domain(domain)}"


def get_api_url(domain: str) -> str:
    """
    Return the hosted OpenLink API base URL for a validated Truveta domain.

    Inputs:
        domain: A supported Truveta domain such as "truveta.com".

    Returns:
        The hosted OpenLink API base URL for the supplied domain, including the
        /openlink path suffix.
    """
    return f"https://api.{validate_domain(domain)}/openlink"


def get_audience(domain: str) -> str:
    """
    Return the Auth0 audience URI for a validated Truveta domain.

    Inputs:
        domain: A supported Truveta domain such as "truveta-int.com".

    Returns:
        The Auth0 audience URI used for OAuth device flow requests.
    """
    return get_api_url(domain)


def get_client_id(domain: str) -> str:
    """
    Return the Auth0 client ID for a validated Truveta domain.

    Inputs:
        domain: A supported Truveta domain such as "truveta.com".

    Returns:
        The Auth0 client ID configured for the supplied domain.
    """
    return _CLIENT_IDS[validate_domain(domain)]
