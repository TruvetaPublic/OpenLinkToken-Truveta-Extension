"""
Copyright (c) Truveta. All rights reserved.

Shared filesystem path helpers for the OpenLinkToken Truveta extension.
"""

from pathlib import Path

_SESSION_FILE_NAME = "session.json"


def truveta_root_dir() -> Path:
    """Return the extension root directory (~/.openlinktoken/truveta)."""
    return Path.home() / ".openlinktoken" / "truveta"


def domain_dir(domain: str) -> Path:
    """Return the domain-specific directory under the extension root."""
    return truveta_root_dir() / domain


def credentials_cache_path(domain: str) -> Path:
    """Return the credentials cache path for a domain."""
    return domain_dir(domain) / "credentials.json"


def session_file_path() -> Path:
    """Return the login session file path."""
    return truveta_root_dir() / _SESSION_FILE_NAME


def exchange_config_path(domain: str) -> Path:
    """Return the exchange configuration file path for a domain."""
    return domain_dir(domain) / "exchange.json"


def private_key_path(domain: str) -> Path:
    """Return the private key path for a domain."""
    return domain_dir(domain) / "private_key.pem"


def public_key_path(domain: str) -> Path:
    """Return the public key path for a domain."""
    return domain_dir(domain) / "public_key.pem"
