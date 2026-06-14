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
from openlinktoken_ext_truveta.commands.common import (
    AuthenticatedCommandContext,
    SessionResolutionError,
    resolve_authenticated_context,
    resolve_timeout_seconds,
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
from openlinktoken_ext_truveta.paths import (
    private_key_path,
    public_key_path,
)


def _initiate_exchange(args: argparse.Namespace) -> int:
    """
    Authenticate (if needed) and negotiate an initial exchange config.

    Inputs:
        args: Parsed CLI arguments.

    Returns:
        Exit code 0 on success or 1 when authentication, exchange negotiation,
        or config persistence fails.
    """
    try:
        context: AuthenticatedCommandContext = resolve_authenticated_context(args)
    except SessionResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        local_private_pem, local_public_pem = load_or_generate_domain_keys()
    except KeyManagementError as exc:
        print(f"Key management failed: {exc}", file=sys.stderr)
        return 1

    try:
        server_response = call_exchange_endpoint(
            context.api_url,
            local_public_pem,
            context.credentials.access_token,
            timeout_seconds=resolve_timeout_seconds(args),
        )
    except (ExchangeAPIError, Exception) as exc:
        print(f"Exchange endpoint call failed: {exc}", file=sys.stderr)
        return 1

    try:
        config = build_exchange_config(
            server_response, local_public_pem, local_private_pem
        )
        config_path = write_exchange_config(context.storage_domain, config)

        priv_key_path = private_key_path()
        pub_key_path = public_key_path()
        print(f"Private key:     {priv_key_path}")
        print(f"Public key:      {pub_key_path}")
        print(f"Exchange config: {config_path}")
    except ExchangeConfigError as exc:
        print(f"Exchange config build/write failed: {exc}", file=sys.stderr)
        return 1

    return 0
