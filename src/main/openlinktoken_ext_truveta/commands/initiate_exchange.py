"""
Copyright (c) Truveta. All rights reserved.

Dedicated initiate-exchange command implementation.
"""

import argparse
import sys

from openlinktoken_ext_truveta.api.exchange import (
    ExchangeAPIError,
    call_exchange_endpoint,
)
from openlinktoken_ext_truveta.auth import (
    AuthError,
    Credentials,
    _extract_service_domain,
    ensure_auth,
)
from openlinktoken_ext_truveta.commands.common import (
    SessionResolutionError,
    resolve_api_url,
    resolve_auth_url,
)
from openlinktoken_ext_truveta.exchange.config import (
    ExchangeConfigError,
    build_exchange_config,
    write_exchange_config,
)
from openlinktoken_ext_truveta.exchange.key_management import (
    KeyManagementError,
    load_or_generate_domain_keys,
)


def _initiate_exchange(args: argparse.Namespace) -> int:
    """Authenticate (if needed) and negotiate an initial exchange config."""
    try:
        api_url = resolve_api_url(args, session_only=True)
        auth_url = resolve_auth_url(args, session_only=True)
    except SessionResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        credentials: Credentials = ensure_auth(auth_url, cached_only=True)
    except AuthError:
        print(
            "Not logged in. Please, run 'olt truveta login' first.",
            file=sys.stderr,
        )
        return 1

    domain = _extract_service_domain(api_url)

    try:
        local_private_pem, local_public_pem = load_or_generate_domain_keys(domain)
    except KeyManagementError as exc:
        print(f"Key management failed: {exc}", file=sys.stderr)
        return 1

    try:
        server_response = call_exchange_endpoint(
            api_url, local_public_pem, credentials.access_token
        )
    except (ExchangeAPIError, Exception) as exc:
        print(f"Exchange endpoint call failed: {exc}", file=sys.stderr)
        return 1

    try:
        config = build_exchange_config(
            domain, server_response, local_public_pem, local_private_pem
        )
        config_path = write_exchange_config(domain, config)
        print(f"Exchange config written to: {config_path}")
    except ExchangeConfigError as exc:
        print(f"Exchange config build/write failed: {exc}", file=sys.stderr)
        return 1

    return 0
