"""
Copyright (c) Truveta. All rights reserved.

Shared filesystem path helpers for the OpenLinkToken Truveta extension.
"""

from datetime import date, datetime, timezone
from pathlib import Path

_SESSION_FILE_NAME = "session.json"
_OPENLINKTOKEN_DIR_NAME = ".openlinktoken"
_KEY_FILE_PREFIX = "openlinktoken"


def openlinktoken_root_dir() -> Path:
    """
    Return the OpenLinkToken root directory (~/.openlinktoken).

    Inputs:
        None.

    Returns:
        The filesystem path to the shared OpenLinkToken home directory.
    """
    return Path.home() / _OPENLINKTOKEN_DIR_NAME


def truveta_root_dir() -> Path:
    """
    Return the extension root directory (~/.openlinktoken/truveta).

    Inputs:
        None.

    Returns:
        The filesystem path to the Truveta extension state directory.
    """
    return openlinktoken_root_dir() / "truveta"


def domain_dir(domain: str) -> Path:
    """
    Return the domain-specific directory under the extension root.

    Inputs:
        domain: The Truveta domain used to scope cached extension state.

    Returns:
        The filesystem path for state stored under the supplied domain.
    """
    return truveta_root_dir() / domain


def credentials_cache_path(domain: str) -> Path:
    """
    Return the credentials cache path for a domain.

    Inputs:
        domain: The Truveta domain whose OAuth credentials are being cached.

    Returns:
        The filesystem path to the credentials.json cache file for the domain.
    """
    return domain_dir(domain) / "credentials.json"


def session_file_path() -> Path:
    """
    Return the login session file path.

    Inputs:
        None.

    Returns:
        The filesystem path to the extension session.json file.
    """
    return truveta_root_dir() / _SESSION_FILE_NAME


def exchange_config_path(domain: str) -> Path:
    """
    Return the exchange configuration file path for a domain.

    Inputs:
        domain: The Truveta domain or storage key for the exchange configuration.

    Returns:
        The filesystem path where the exchange configuration is stored.
    """
    return domain_dir(domain) / "exchange.json"


def _resolve_key_date(key_date: date | None = None) -> date:
    """
    Resolve the UTC date used for date-scoped key filenames.

    Inputs:
        key_date: An optional explicit date override for deterministic key lookup.

    Returns:
        The provided date or the current UTC date when no override is supplied.
    """
    if key_date is not None:
        return key_date

    return datetime.now(timezone.utc).date()


def _dated_key_filename(key_type: str, key_date: date | None = None) -> str:
    """
    Build the date-based key filename for the requested key type.

    Inputs:
        key_type: The key file suffix such as "private" or "public".
        key_date: An optional explicit date override for deterministic filenames.

    Returns:
        The date-scoped filename for the requested key type.
    """
    stamp = _resolve_key_date(key_date).strftime("%Y-%m-%d")
    return f"{_KEY_FILE_PREFIX}-{stamp}.{key_type}.pem"


def private_key_path(key_date: date | None = None) -> Path:
    """
    Return the date-scoped private key path under ~/.openlinktoken.

    Inputs:
        key_date: An optional explicit date override for deterministic key lookup.

    Returns:
        The filesystem path to the private key file for the resolved date.
    """
    return openlinktoken_root_dir() / _dated_key_filename("private", key_date)


def public_key_path(key_date: date | None = None) -> Path:
    """
    Return the date-scoped public key path under ~/.openlinktoken.

    Inputs:
        key_date: An optional explicit date override for deterministic key lookup.

    Returns:
        The filesystem path to the public key file for the resolved date.
    """
    return openlinktoken_root_dir() / _dated_key_filename("public", key_date)
