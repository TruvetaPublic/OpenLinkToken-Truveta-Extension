"""
Copyright (c) Truveta. All rights reserved.

Exchange endpoint API client for OpenToken exchange negotiation.

Calls the POST /v1/exchange endpoint to negotiate a new exchange.
"""

import base64
import hashlib

import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)


class ExchangeAPIError(Exception):
    """Raised when exchange API calls fail."""


def _pem_to_spki_b64(public_key_pem: str) -> str:
    """Convert a PEM-encoded EC public key to base64-encoded DER SPKI format."""
    key = load_pem_public_key(public_key_pem.encode("utf-8"))
    der = key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("utf-8")


def _resolve_exchange_id(server_data: dict) -> str:
    """Resolve a non-empty exchange identifier from API response fields."""
    exchange_id = str(server_data.get("exchangeId", "")).strip()
    if exchange_id:
        return exchange_id

    # Back-compat: some service deployments omit exchangeId. Derive a stable ID
    # from returned exchange material so downstream package/upload flows can run.
    derivation_material = "|".join(
        [
            str(server_data.get("exchangeName", "")).strip(),
            str(
                server_data.get(
                    "encryptedHashingKey",
                    server_data.get("hashingSecret", ""),
                )
            ).strip(),
            str(
                server_data.get(
                    "truvetaPublicKey",
                    server_data.get("serverPublicKey", ""),
                )
            ).strip(),
        ]
    )
    digest = hashlib.sha256(derivation_material.encode("utf-8")).hexdigest()[:32]
    return f"derived-{digest}"


def call_exchange_endpoint(
    domain_url: str,
    local_public_key_pem: str,
    access_token: str,
) -> dict:
    """
    Call the /v1/exchange endpoint to negotiate a new exchange.

    Makes an authenticated POST request to https://api.<domain>/v1/exchange
    with the local public key, receiving the server's public key and
    encrypted hashing secret in response.

    Inputs:
        domain_url: The Truveta API URL (e.g. "https://api.truveta.com").
        local_public_key_pem: Our generated public key (PEM-encoded).
        access_token: Valid OAuth access token for authentication.

    Returns:
        Parsed JSON response from the endpoint (dict).

    Raises:
        ExchangeAPIError: If the request fails (network error, HTTP error).
        requests.HTTPError: For 4xx/5xx responses (propagated as-is for
                          caller control over error handling).
    """
    url = f"{domain_url.rstrip('/')}/v1/exchange"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    body = {"publicKey": _pem_to_spki_b64(local_public_key_pem)}

    try:
        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        server_data = response.json()
        return {
            "exchangeName": server_data.get("exchangeName", ""),
            "exchangeId": _resolve_exchange_id(server_data),
            "hashingSecret": server_data.get(
                "encryptedHashingKey", server_data.get("hashingSecret", "")
            ),
            "hashingSecretEncoding": server_data.get("hashingSecretEncoding", "base64"),
            "serverPublicKey": server_data.get(
                "truvetaPublicKey", server_data.get("serverPublicKey", "")
            ),
        }
    except requests.HTTPError:
        raise
    except Exception as exc:
        raise ExchangeAPIError(f"Failed to call exchange endpoint at {url}: {exc}")
