"""
Copyright (c) Truveta. All rights reserved.

Exchange endpoint API client for OpenToken exchange negotiation.
"""

import base64
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)

from openlinktoken_ext_truveta.api.common import resolve_timeout_seconds


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
    if _is_local_dev_url(domain_url):
        return f"{domain_url.rstrip('/')}/v1/exchange"

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


def _resolve_exchange_id(server_data: dict) -> str:
    """
    Resolve a non-empty exchange identifier from API response fields.

    Inputs:
        server_data: The parsed JSON payload returned by the exchange endpoint.

    Returns:
        The non-empty exchange identifier string extracted from the payload.
    """
    exchange_id = str(server_data.get("exchangeId", "")).strip()
    if exchange_id:
        return exchange_id

    raise ExchangeAPIError("Exchange response must include a non-empty exchangeId.")


def call_exchange_endpoint(
    domain_url: str,
    local_public_key_pem: str,
    access_token: str,
    timeout_seconds: int | None = None,
) -> dict:
    """
    Call the exchange endpoint to negotiate a new exchange.

    Hosted environments use ``/openlink/v1/exchange``. Local development
    targets (for example ``http://localhost:18080``) use ``/v1/exchange``
    directly. The endpoint returns the server's public key and encrypted
    hashing secret.

    Inputs:
        domain_url: The Truveta API URL, including the /openlink suffix for hosted environments.
        local_public_key_pem: Our generated public key (PEM-encoded).
        access_token: Valid OAuth access token for authentication.
        timeout_seconds: Optional request timeout override in seconds.

    Returns:
        Parsed JSON response from the endpoint.

    Raises:
        ExchangeAPIError: If the request fails (network error, HTTP error).
        requests.HTTPError: For 4xx/5xx responses (propagated as-is for
                          caller control over error handling).
    """
    url = _resolve_exchange_url(domain_url)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    body = {"publicKey": _pem_to_spki_b64(local_public_key_pem)}
    request_timeout = resolve_timeout_seconds(timeout_seconds)

    try:
        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=request_timeout,
        )
        response.raise_for_status()
        server_data = response.json()

        num_rotations = server_data.get("numRotations")
        bin_width = server_data.get("binWidth")
        dimension_bias = server_data.get("dimensionBias")
        encrypted_rotation_iv = server_data.get("encryptedRotationIv")

        normalized: dict = {
            "exchangeName": server_data.get("exchangeName", ""),
            "exchangeId": _resolve_exchange_id(server_data),
            "hashingSecret": server_data.get(
                "encryptedHashingKey", server_data.get("hashingSecret", "")
            ),
            "hashingSecretEncoding": server_data.get("hashingSecretEncoding", "base64"),
            "serverPublicKey": server_data.get(
                "truvetaPublicKey", server_data.get("serverPublicKey", "")
            ),
            "rotationCount": num_rotations if num_rotations is not None else 30,
            "binWidth": bin_width if bin_width is not None else 0.05,
            "dimensionBias": dimension_bias if dimension_bias is not None else [],
        }
        if encrypted_rotation_iv:
            normalized["encryptedRotationIv"] = encrypted_rotation_iv
        return normalized
    except requests.HTTPError:
        raise
    except Exception as exc:
        raise ExchangeAPIError(f"Failed to call exchange endpoint at {url}: {exc}")
