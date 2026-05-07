"""
Copyright (c) Truveta. All rights reserved.

Exchange config management for Open Link Token exchange.

Builds, persists, and loads JWE-compatible exchange config JSON files
that are compatible with Open Link Token initiate-exchange output.
"""

import base64
import json
import math
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
    load_pem_public_key,
)

from openlinktoken_ext_truveta.exchange.constants import (
    BIN_WIDTH_KEY,
    DEFAULT_BIN_WIDTH,
    DEFAULT_ROTATION_COUNT,
    DIMENSION_BIAS_KEY,
    EC_KEY_TYPE,
    ENCRYPTED_ROTATION_IV_KEY,
    EXCHANGE_ID_KEY,
    EXCHANGE_NAME_KEY,
    HASHING_SECRET_KEY,
    JWE_RECIPIENT_ALG,
    KID_SHA256_PREFIX,
    OPENLINKTOKEN_CURVE_BY_CRYPTOGRAPHY_CURVE,
    OPENLINKTOKEN_EXCHANGE_CONFIG_MODULE,
    OPENLINKTOKEN_EXCHANGE_JWE_MODULE,
    P256_CURVE,
    PEM_HEADER_PREFIX,
    REQUIRED_SERVER_RESPONSE_FIELDS,
    ROTATION_COUNT_KEY,
    ROTATION_IV_ENCODING_KEY,
    ROTATION_IV_ENCODING_VALUE,
    ROTATION_IV_KEY,
    SERVER_PUBLIC_KEY_KEY,
)
from openlinktoken_ext_truveta.exchange.key_management import (
    KeyManagementError,
    decrypt_hashing_secret,
)
from openlinktoken_ext_truveta.paths import private_key_path


class ExchangeConfigError(Exception):
    """Raised when exchange config operations fail."""


def _decode_hashing_secret(secret: Any) -> bytes:
    """
    Decode a decrypted hashing secret into raw key bytes.

    The secret is always a base64url-encoded string (unpadded) produced by
    the Truveta provisioning pipeline.

    Inputs:
        secret: The decrypted hashing secret as bytes or str.

    Returns:
        The raw key bytes decoded from the base64url value.
    """
    if isinstance(secret, bytes):
        secret_text = secret.decode("utf-8")
    elif isinstance(secret, str):
        secret_text = secret
    else:
        raise ExchangeConfigError(
            "Decrypted hashing secret must be bytes or string. "
            f"Received type: {type(secret).__name__}"
        )

    try:
        padding = "=" * (-len(secret_text) % 4)
        return base64.urlsafe_b64decode(secret_text + padding)
    except Exception as exc:
        raise ExchangeConfigError(
            f"Failed to decode base64url hashing secret: {exc}"
        ) from exc


def _validate_exchange_envelope_shape(config: dict[str, Any]) -> None:
    """
    Validate that config matches OpenLinkToken JWE envelope schema.

    Inputs:
        config: The exchange envelope object to validate.

    Returns:
        None. The function raises when the envelope does not match the expected schema.
    """
    required_fields = ["version", "protected", "iv", "ciphertext", "tag", "recipients"]
    missing = [field for field in required_fields if field not in config]
    if missing:
        raise ExchangeConfigError(
            "Invalid exchange envelope: missing required fields "
            + ", ".join(repr(field) for field in missing)
        )

    if config.get("version") != 1:
        raise ExchangeConfigError(
            f"Invalid exchange envelope: expected version=1, got {config.get('version')!r}"
        )

    recipients = config.get("recipients")
    if not isinstance(recipients, list) or len(recipients) != 2:
        raise ExchangeConfigError(
            "Invalid exchange envelope: recipients must be a list with exactly 2 entries"
        )

    for index, recipient in enumerate(recipients):
        if not isinstance(recipient, dict):
            raise ExchangeConfigError(
                f"Invalid exchange envelope: recipient[{index}] must be an object"
            )
        if not isinstance(recipient.get("encrypted_key"), str):
            raise ExchangeConfigError(
                "Invalid exchange envelope: "
                f"recipient[{index}].encrypted_key must be a string"
            )

        header = recipient.get("header")
        if not isinstance(header, dict):
            raise ExchangeConfigError(
                "Invalid exchange envelope: "
                f"recipient[{index}].header must be an object"
            )

        if header.get("alg") != JWE_RECIPIENT_ALG:
            raise ExchangeConfigError(
                "Invalid exchange envelope: "
                f"recipient[{index}].header.alg must equal '{JWE_RECIPIENT_ALG}'"
            )

        kid = header.get("kid")
        if not isinstance(kid, str) or not kid.startswith(KID_SHA256_PREFIX):
            raise ExchangeConfigError(
                "Invalid exchange envelope: "
                f"recipient[{index}].header.kid must start with '{KID_SHA256_PREFIX}'"
            )

        epk = header.get("epk")
        if not isinstance(epk, dict):
            raise ExchangeConfigError(
                "Invalid exchange envelope: "
                f"recipient[{index}].header.epk must be an object"
            )

        if epk.get("kty") != EC_KEY_TYPE or epk.get("crv") != P256_CURVE:
            raise ExchangeConfigError(
                "Invalid exchange envelope: "
                "recipient[{index}].header.epk must contain "
                f"kty={EC_KEY_TYPE} and crv={P256_CURVE}"
            )

        if not isinstance(epk.get("x"), str) or not isinstance(epk.get("y"), str):
            raise ExchangeConfigError(
                "Invalid exchange envelope: "
                f"recipient[{index}].header.epk.x and epk.y must be strings"
            )


def _validate_exchange_extension_fields(config: dict[str, Any]) -> None:
    """
    Validate optional rotation and quantization extension fields in the exchange config.

    Inputs:
        config: The exchange config dict potentially containing extension fields.

    Returns:
        None. Raises when any extension field fails type or constraint validation.
    """
    rotation_count = config.get(ROTATION_COUNT_KEY)
    if rotation_count is not None:
        if not isinstance(rotation_count, int) or rotation_count < 0:
            raise ExchangeConfigError(
                f"rotationCount must be a non-negative integer, got {rotation_count!r}"
            )

    bin_width = config.get(BIN_WIDTH_KEY)
    if bin_width is not None:
        if (
            not isinstance(bin_width, (int, float))
            or not math.isfinite(bin_width)
            or bin_width <= 0
        ):
            raise ExchangeConfigError(
                f"binWidth must be a positive finite number, got {bin_width!r}"
            )

    dimension_bias = config.get(DIMENSION_BIAS_KEY)
    if dimension_bias is not None and not isinstance(dimension_bias, list):
        raise ExchangeConfigError(
            f"dimensionBias must be a list, got {type(dimension_bias).__name__}"
        )


def _load_build_exchange_envelope():
    """
    Load OpenLinkToken's JWE exchange envelope builder.

    Inputs:
        None.

    Returns:
        The callable build_exchange_envelope helper provided by OpenLinkToken core.
    """
    try:
        module = import_module(OPENLINKTOKEN_EXCHANGE_JWE_MODULE)
    except ModuleNotFoundError as exc:
        raise ExchangeConfigError(
            "OpenLinkToken exchange envelope utilities are unavailable. "
            f"Expected module: {OPENLINKTOKEN_EXCHANGE_JWE_MODULE}"
        ) from exc

    builder = getattr(module, "build_exchange_envelope", None)
    if callable(builder):
        return builder

    raise ExchangeConfigError(
        "OpenLinkToken exchange envelope utilities are unavailable. "
        f"Expected module: {OPENLINKTOKEN_EXCHANGE_JWE_MODULE}"
    )


def _load_resolve_exchange_inputs():
    """
    Load OpenLinkToken's exchange-config resolver.

    Inputs:
        None.

    Returns:
        The callable resolve_exchange_config_inputs helper from OpenLinkToken core.
    """
    try:
        module = import_module(OPENLINKTOKEN_EXCHANGE_CONFIG_MODULE)
    except ModuleNotFoundError as exc:
        raise ExchangeConfigError(
            "OpenLinkToken exchange config utilities are unavailable. "
            f"Expected module: {OPENLINKTOKEN_EXCHANGE_CONFIG_MODULE}"
        ) from exc

    resolver = getattr(module, "resolve_exchange_config_inputs", None)
    if callable(resolver):
        return resolver

    raise ExchangeConfigError(
        "OpenLinkToken exchange config utilities are unavailable. "
        f"Expected module: {OPENLINKTOKEN_EXCHANGE_CONFIG_MODULE}"
    )


def _to_public_key_pem(public_key_data: str) -> str:
    """
    Normalize a public key value to PEM format.

    Inputs:
        public_key_data: The server public key in PEM text or base64 DER/SPKI form.

    Returns:
        The equivalent public key encoded as PEM text.
    """
    if public_key_data.strip().startswith(PEM_HEADER_PREFIX):
        return public_key_data

    try:
        public_key = load_der_public_key(base64.b64decode(public_key_data))
        return public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")
    except Exception as exc:
        raise ExchangeConfigError(f"Failed to normalize server public key: {exc}")


def _derive_curve_from_public_key(public_key_data: str) -> str:
    """
    Derive OpenLinkToken curve name from the server's public key.

    Inputs:
        public_key_data: The server public key in PEM text or base64 DER/SPKI form.

    Returns:
        The OpenLinkToken curve name corresponding to the public key.
    """
    try:
        if public_key_data.strip().startswith(PEM_HEADER_PREFIX):
            public_key = load_pem_public_key(public_key_data.encode("utf-8"))
        else:
            public_key = load_der_public_key(base64.b64decode(public_key_data))
    except Exception as exc:
        raise ExchangeConfigError(
            f"Failed to load server public key for curve derivation: {exc}"
        )

    if not isinstance(public_key, EllipticCurvePublicKey):
        raise ExchangeConfigError(
            "Server public key must be an elliptic curve key for exchange config generation."
        )

    curve_name = OPENLINKTOKEN_CURVE_BY_CRYPTOGRAPHY_CURVE.get(public_key.curve.name)
    if curve_name is None:
        raise ExchangeConfigError(
            f"Unsupported server public key curve: {public_key.curve.name!r}"
        )

    return curve_name


def build_exchange_config(
    domain: str,
    server_response: dict[str, Any],
    local_public_key_pem: str,
    local_private_key_pem: str,
) -> dict[str, Any]:
    """
    Build a core-compatible JWE exchange config from server response and local keys.

    Inputs:
        domain: The Truveta domain the exchange configuration is associated with.
        server_response: The parsed exchange API response containing exchange metadata.
        local_public_key_pem: The caller's PEM-encoded public key.
        local_private_key_pem: The caller's PEM-encoded private key used to decrypt the secret.

    Returns:
        The validated exchange configuration envelope ready for persistence or upload use.
    """
    required_fields = REQUIRED_SERVER_RESPONSE_FIELDS
    for field in required_fields:
        if field not in server_response:
            raise ExchangeConfigError(
                f"Missing required field in server response: {field!r}"
            )

    try:
        exchange_name = server_response[EXCHANGE_NAME_KEY]
        exchange_id = server_response[EXCHANGE_ID_KEY]
        server_public_key = server_response[SERVER_PUBLIC_KEY_KEY]
        server_public_key_pem = _to_public_key_pem(server_public_key)
        curve = _derive_curve_from_public_key(server_public_key)

        try:
            hashing_secret = decrypt_hashing_secret(
                server_response[HASHING_SECRET_KEY],
                local_private_key_pem,
                server_public_key,
                exchange_id,
            )
        except KeyManagementError as exc:
            raise ExchangeConfigError(f"Failed to decrypt hashing secret: {exc}")

        build_exchange_envelope = _load_build_exchange_envelope()
        config = build_exchange_envelope(
            exchange_name=exchange_name,
            hashing_secret=_decode_hashing_secret(hashing_secret),
            sender_public_pem=local_public_key_pem.encode("utf-8"),
            recipient_public_pem=server_public_key_pem.encode("utf-8"),
            curve=curve,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            exchange_id=exchange_id,
        )
        _validate_exchange_envelope_shape(config)

        encrypted_rotation_iv = server_response.get(ENCRYPTED_ROTATION_IV_KEY)
        if encrypted_rotation_iv:
            try:
                decrypted_iv_str = decrypt_hashing_secret(
                    encrypted_rotation_iv,
                    local_private_key_pem,
                    server_public_key,
                    exchange_id,
                )
            except KeyManagementError as exc:
                raise ExchangeConfigError(f"Failed to decrypt rotation IV: {exc}")
            raw_iv = base64.b64decode(decrypted_iv_str)
            config[ROTATION_IV_KEY] = (
                base64.urlsafe_b64encode(raw_iv).rstrip(b"=").decode("ascii")
            )
            config[ROTATION_IV_ENCODING_KEY] = ROTATION_IV_ENCODING_VALUE

        rotation_count = server_response.get(ROTATION_COUNT_KEY)
        bin_width = server_response.get(BIN_WIDTH_KEY)
        dimension_bias = server_response.get(DIMENSION_BIAS_KEY)
        config[ROTATION_COUNT_KEY] = (
            rotation_count if rotation_count is not None else DEFAULT_ROTATION_COUNT
        )
        config[BIN_WIDTH_KEY] = (
            bin_width if bin_width is not None else DEFAULT_BIN_WIDTH
        )
        config[DIMENSION_BIAS_KEY] = (
            dimension_bias if dimension_bias is not None else []
        )

        _validate_exchange_extension_fields(config)
        return config

    except ExchangeConfigError:
        raise
    except Exception as exc:
        raise ExchangeConfigError(f"Failed to build exchange config: {exc}")


def write_exchange_config(domain: str, config: dict[str, Any]) -> Path:
    """
    Persist an exchange config to the current directory as openlinktoken-<YYYY-MM-DD>.exchange.json.

    Inputs:
        domain: The Truveta domain associated with the exchange configuration.
        config: The validated exchange configuration envelope to persist.

    Returns:
        The filesystem path to the written exchange configuration file.
    """
    try:
        _validate_exchange_envelope_shape(config)
        date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        config_path = Path.cwd() / f"openlinktoken-{date_stamp}.exchange.json"
        config_path.write_text(json.dumps(config, indent=2))
        return config_path
    except Exception as exc:
        raise ExchangeConfigError(
            f"Failed to write exchange config for domain {domain!r}: {exc}"
        )


def load_exchange_config(domain: str) -> dict[str, Any]:
    """
    Load an exchange config from the current directory only.

    Inputs:
        domain: The Truveta domain associated with the expected exchange configuration.

    Returns:
        The parsed exchange configuration JSON object for the current UTC date.
    """
    try:
        cwd_configs = sorted(Path.cwd().glob("openlinktoken-*.exchange.json"))
        if not cwd_configs:
            raise ExchangeConfigError("Exchange config not found in current directory")

        today_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_config = Path.cwd() / f"openlinktoken-{today_stamp}.exchange.json"

        if today_config.exists():
            return json.loads(today_config.read_text())

        raise ExchangeConfigError(
            f"Exchange config for today's date ({today_stamp}) not found in current directory; "
            f"place the config file at openlinktoken-{today_stamp}.exchange.json"
        )
    except ExchangeConfigError:
        raise
    except Exception as exc:
        raise ExchangeConfigError(
            f"Failed to load exchange config for domain {domain!r}: {exc}"
        )


def resolve_exchange_payload(domain: str) -> dict[str, Any]:
    """
    Resolve a decrypted exchange payload from a JWE config.

    Inputs:
        domain: The Truveta domain associated with the exchange configuration to resolve.

    Returns:
        The decrypted exchange payload JSON object produced by OpenLinkToken core.
    """
    config = load_exchange_config(domain)

    private_key_path_value = private_key_path()
    if not private_key_path_value.exists():
        raise ExchangeConfigError(f"Private key not found at {private_key_path_value}")

    try:
        resolve_exchange_config_inputs = _load_resolve_exchange_inputs()
        resolved = resolve_exchange_config_inputs(
            exchange_config_value=config,
            private_key_value=private_key_path_value.read_text(encoding="utf-8"),
        )
        payload = getattr(resolved, "payload", None)
        if not isinstance(payload, dict):
            raise ExchangeConfigError("Resolved exchange payload is not a JSON object.")
        return payload
    except ExchangeConfigError:
        raise
    except Exception as exc:
        raise ExchangeConfigError(
            f"Failed to resolve exchange payload for domain {domain!r}: {exc}"
        )
