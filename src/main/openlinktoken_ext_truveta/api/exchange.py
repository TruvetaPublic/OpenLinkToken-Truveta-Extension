"""
Copyright (c) Truveta. All rights reserved.

Exchange endpoint API client for OpenToken exchange negotiation.
"""

import asyncio
import base64
import logging
from urllib.parse import urlparse

import httpx

from openlinktoken_ext_truveta.openlink_token_service_client.client import (
    OpenLinkTokenServiceClient,
)
from openlinktoken_ext_truveta.openlink_token_service_client.types import (
    ExchangeRequest,
    ExchangeResponse,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)

from openlinktoken_ext_truveta.api.common import (
    format_api_error,
    probe_for_http_status,
    resolve_timeout_seconds,
    ssl_drop_message,
)

# httpx logs every request/response at INFO by default; suppress to keep CLI output clean.
logging.getLogger("httpx").setLevel(logging.WARNING)


class ExchangeAPIError(Exception):
    """Raised when exchange API calls fail."""


def _is_local_dev_url(domain_url: str) -> bool:
    """
    Return True when the target URL points at the local dev token service.

    Inputs:
        domain_url: The candidate API URL being inspected.

    Returns:
        True when the URL targets localhost-style development endpoints.
    """
    hostname = (urlparse(domain_url).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _resolve_exchange_url(domain_url: str) -> str:
    """
    Resolve the exchange URL for local dev and hosted environments.

    Inputs:
        domain_url: The normalized base API URL for the current target environment.

    Returns:
        The fully qualified exchange endpoint URL for hosted or local-dev calls.
    """
    return f"{domain_url.rstrip('/')}/v1/exchange"


def _pem_to_spki_b64(public_key_pem: str) -> str:
    """
    Convert a PEM-encoded EC public key to base64-encoded DER SPKI format.

    Inputs:
        public_key_pem: The PEM-encoded public key to normalize.

    Returns:
        The base64-encoded DER SubjectPublicKeyInfo representation.
    """
    key = load_pem_public_key(public_key_pem.encode("utf-8"))
    der = key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("utf-8")


def _normalize_response(response: ExchangeResponse) -> dict:
    result: dict = {
        "exchangeName": "",
        "exchangeId": response.exchange_id,
        "hashingSecret": response.encrypted_hashing_key,
        "serverPublicKey": response.truveta_public_key,
        "rotationCount": response.num_rotations,
        "binWidth": response.bin_width,
        "dimensionBias": response.dimension_bias or [],
    }
    if response.encrypted_rotation_iv:
        result["encryptedRotationIv"] = response.encrypted_rotation_iv
    return result


async def _call_exchange_async(
    base_url: str,
    public_key_pem: str,
    access_token: str,
    timeout: float | None,
    verify_ssl: bool,
) -> ExchangeResponse:
    """
    Make an async HTTP call to the exchange endpoint.

    Inputs:
        base_url: Base URL of the OpenLink Token service (trailing slash stripped).
        public_key_pem: PEM-encoded public key to send in the exchange request.
        access_token: Bearer token for authentication.
        timeout: Request timeout in seconds, or None for no timeout.
        verify_ssl: Whether to verify the server's SSL certificate.

    Returns:
        Parsed ExchangeResponse from the service.
    """
    request = ExchangeRequest(public_key=_pem_to_spki_b64(public_key_pem))
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {access_token}"},
        verify=verify_ssl,
        timeout=timeout,
    ) as client:
        olt_client = OpenLinkTokenServiceClient(base_url, client)
        return await olt_client.exchange_exchange("1", request)


def call_exchange_endpoint(
    domain_url: str,
    local_public_key_pem: str,
    access_token: str,
    timeout_seconds: int | None = None,
) -> dict:
    """
    Call the exchange endpoint to negotiate a new exchange.

    Inputs:
        domain_url: The Truveta API URL, including the /openlink suffix for hosted environments.
        local_public_key_pem: Our generated public key (PEM-encoded).
        access_token: Valid OAuth access token for authentication.
        timeout_seconds: Optional request timeout override in seconds.

    Returns:
        Parsed and normalized response from the endpoint.

    Raises:
        ExchangeAPIError: If the request fails (network error, HTTP error).
        httpx.HTTPStatusError: For 4xx/5xx responses (propagated as-is for
                              caller control over error handling).
    """
    base_url = domain_url.rstrip("/")
    url = _resolve_exchange_url(domain_url)
    request_timeout = resolve_timeout_seconds(timeout_seconds)
    verify_ssl = not _is_local_dev_url(domain_url)

    try:
        response = asyncio.run(
            _call_exchange_async(
                base_url,
                local_public_key_pem,
                access_token,
                request_timeout,
                verify_ssl,
            )
        )
        return _normalize_response(response)
    except httpx.HTTPStatusError:
        raise
    except httpx.ConnectError as exc:
        probe_detail = probe_for_http_status(
            url,
            access_token,
            request_timeout,
            probe_json={},
        )
        raise ExchangeAPIError(
            format_api_error(
                url,
                ssl_drop_message(
                    probe_detail,
                    generic_hint=(
                        "Server dropped the connection during exchange negotiation. "
                        "Try again or check your network connectivity."
                    ),
                ),
                operation="Exchange",
            )
        ) from exc
    except Exception as exc:
        raise ExchangeAPIError(f"Failed to call exchange endpoint at {url}: {exc}")
