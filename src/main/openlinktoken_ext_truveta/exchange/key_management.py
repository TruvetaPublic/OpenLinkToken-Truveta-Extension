"""
Copyright (c) Truveta. All rights reserved.

ECDH P-256 key pair management for OpenToken exchange.

Uses OpenToken core EC key utilities for key generation and fingerprinting,
and persists date-scoped keys under ~/.openlinktoken/.
"""

import base64
import hashlib
import hmac
import inspect
import os
from datetime import date
from importlib import import_module

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import ECDH
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
    load_pem_private_key,
    load_pem_public_key,
)

from openlinktoken_ext_truveta.exchange.constants import PEM_HEADER_PREFIX
from openlinktoken_ext_truveta.paths import (
    private_key_path,
    public_key_path,
)

_NONCE_LENGTH = 12
_TAG_LENGTH = 16
_UTF8_ENCODING = "utf-8"


class KeyManagementError(Exception):
    """Raised when key generation, persistence, or loading fails."""


def _load_core_ec_key_utils():
    """
    Load OpenToken EC key utilities from core modules.

    Inputs:
        None.

    Returns:
        The imported openlinktoken.ec_key_utils module.
    """
    module_name = "openlinktoken.ec_key_utils"
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        raise KeyManagementError(
            "OpenToken core EC key utilities are unavailable. "
            "Expected module: openlinktoken.ec_key_utils"
        ) from exc


def _generate_keypair_from_core() -> tuple[str, str]:
    """
    Generate ECDH P-256 keys using OpenToken core utilities.

    Inputs:
        None.

    Returns:
        A tuple of PEM-encoded private and public keys.
    """
    ec_utils = _load_core_ec_key_utils()
    private_pem, public_pem = ec_utils.generate_key_pair("P-256")

    if isinstance(private_pem, bytes):
        private_pem = private_pem.decode(_UTF8_ENCODING)
    if isinstance(public_pem, bytes):
        public_pem = public_pem.decode(_UTF8_ENCODING)

    return private_pem, public_pem


def load_or_generate_daily_keys(key_date: date | None = None) -> tuple[str, str]:
    """
    Load existing daily keys or generate and persist new ones.

    Inputs:
        key_date: An optional explicit UTC date used to scope key lookup and persistence.

    Returns:
        A tuple of PEM-encoded private and public keys for the resolved day.
    """
    private_key_file = private_key_path(key_date=key_date)
    public_key_file = public_key_path(key_date=key_date)

    if private_key_file.exists() and public_key_file.exists():
        try:
            private_pem = private_key_file.read_text()
            public_pem = public_key_file.read_text()
            return private_pem, public_pem
        except Exception as exc:
            raise KeyManagementError(
                "Failed to read existing daily keys "
                f"from {private_key_file} and {public_key_file}: {exc}"
            )

    try:
        private_pem, public_pem = _generate_keypair_from_core()
    except Exception as exc:
        raise KeyManagementError(f"Failed to generate ECDH P-256 key pair: {exc}")

    try:
        private_key_file.parent.mkdir(parents=True, exist_ok=True)
        private_key_file.write_text(private_pem)
        os.chmod(private_key_file, 0o600)
        public_key_file.write_text(public_pem)
    except Exception as exc:
        raise KeyManagementError(
            "Failed to persist daily keys "
            f"to {private_key_file} and {public_key_file}: {exc}"
        )

    return private_pem, public_pem


def load_or_generate_domain_keys(
    _domain: str, key_date: date | None = None
) -> tuple[str, str]:
    """
    Load or generate the date-scoped exchange keys.

    Inputs:
        _domain: Unused compatibility parameter retained for existing callers.
        key_date: An optional explicit UTC date used to scope key lookup and persistence.

    Returns:
        A tuple of PEM-encoded private and public keys for the resolved day.

    The domain parameter is preserved for compatibility with existing callers,
    but key storage is global per UTC day under ~/.openlinktoken/.
    """
    return load_or_generate_daily_keys(key_date=key_date)


def get_key_fingerprint(public_key_pem: str) -> str:
    """
    Calculate the SHA-256 fingerprint of a public key.

    Inputs:
        public_key_pem: The public key in PEM text or base64 DER/SPKI form.

    Returns:
        The lowercase SHA-256 fingerprint string for the normalized public key.
    """
    try:
        ec_utils = _load_core_ec_key_utils()
        if isinstance(public_key_pem, str) and public_key_pem.strip().startswith(
            PEM_HEADER_PREFIX
        ):
            public_key_bytes = public_key_pem.encode(_UTF8_ENCODING)
        else:
            public_key = _load_public_key_from_pem_or_spki(public_key_pem)
            public_key_bytes = public_key.public_bytes(
                Encoding.PEM,
                PublicFormat.SubjectPublicKeyInfo,
            )
        fingerprint = ec_utils.public_key_fingerprint(public_key_bytes)
        return fingerprint.lower()
    except Exception as exc:
        raise KeyManagementError(f"Failed to calculate key fingerprint: {exc}")


def _load_public_key_from_pem_or_spki(key_data: str):
    """
    Load an EC public key from either PEM or raw DER/SPKI base64 format.

    Inputs:
        key_data: The public key in PEM text or base64 DER/SPKI form.

    Returns:
        The loaded cryptography public key object.
    """
    if key_data.strip().startswith(PEM_HEADER_PREFIX):
        return load_pem_public_key(key_data.encode(_UTF8_ENCODING))
    return load_der_public_key(base64.b64decode(key_data))


def _load_core_decrypt_hashing_secret():
    """
    Load OpenToken's canonical decrypt helper when it exists.

    Inputs:
        None.

    Returns:
        The callable decrypt helper from OpenToken core, or None when unavailable.
    """
    try:
        module = import_module("openlinktoken.ec_key_utils")
    except ModuleNotFoundError:
        return None

    decrypt_helper = getattr(module, "decrypt_hashing_secret", None)
    if callable(decrypt_helper):
        return decrypt_helper

    return None


def _decrypt_hashing_secret_local(
    encrypted_b64: str,
    local_private_key_pem: str,
    server_public_key: str,
    exchange_id: str,
) -> str:
    """
    Local decryption matching the server's HKDF-based key derivation.

    Inputs:
        encrypted_b64: The base64-encoded encrypted hashing secret payload.
        local_private_key_pem: The caller's PEM-encoded private key.
        server_public_key: The server public key in PEM or base64 DER/SPKI form.
        exchange_id: The exchange identifier used as HKDF salt.

    Returns:
        The decrypted hashing secret as a UTF-8 string.

    Server-side derivation (EcdhKeyProvider.EncryptHashingSecret):
      1. sharedSecret = DeriveKeyFromHash(callerPub, SHA256)
                      = SHA-256(ECDH raw X-coordinate)
      2. HKDF-Extract: PRK = HMAC-SHA256(key=exchangeId.bytes, data=sharedSecret)
      3. HKDF-Expand:  key = HMAC-SHA256(key=PRK, data=info || 0x01)
                       where info = b"openlink-token-encryption"
      4. Encrypt: payload = nonce(12) + AES-GCM(key, nonce, plaintext) + tag(16)
    """
    private_key = load_pem_private_key(
        local_private_key_pem.encode(_UTF8_ENCODING), password=None
    )
    peer_public_key = _load_public_key_from_pem_or_spki(server_public_key)

    # Step 1: ECDH + SHA-256 (matches .NET DeriveKeyFromHash with SHA256)
    raw_shared_secret = private_key.exchange(ECDH(), peer_public_key)
    shared_secret = hashlib.sha256(raw_shared_secret).digest()

    if not exchange_id:
        raise KeyManagementError("exchange_id is required to decrypt hashing secret.")

    # Step 2: HKDF-Extract: PRK = HMAC-SHA256(salt=exchangeId, IKM=sharedSecret)
    salt = exchange_id.encode(_UTF8_ENCODING)
    prk = hmac.new(salt, shared_secret, hashlib.sha256).digest()

    # Step 3: HKDF-Expand: key = HMAC-SHA256(PRK, info || 0x01)
    info = b"openlink-token-encryption"
    hmac_data = info + b"\x01"
    encryption_key = hmac.new(prk, hmac_data, hashlib.sha256).digest()

    # Step 4: Decode payload and decrypt AES-GCM
    encrypted_bytes = base64.b64decode(encrypted_b64)
    nonce = encrypted_bytes[:_NONCE_LENGTH]
    ciphertext = encrypted_bytes[_NONCE_LENGTH:-_TAG_LENGTH]
    tag = encrypted_bytes[-_TAG_LENGTH:]

    cipher = Cipher(
        algorithms.AES(encryption_key),
        modes.GCM(nonce, tag),
        backend=default_backend(),
    )
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return plaintext.decode(_UTF8_ENCODING)


def decrypt_hashing_secret(
    encrypted_b64: str,
    local_private_key_pem: str,
    server_public_key: str,
    exchange_id: str,
) -> str:
    """
    Decrypt the ECDH-encrypted hashing secret received from the server.

    Inputs:
        encrypted_b64: The base64-encoded encrypted hashing secret payload.
        local_private_key_pem: The caller's PEM-encoded private key.
        server_public_key: The server public key in PEM or base64 DER/SPKI form.
        exchange_id: The exchange identifier associated with the exchange.

    Returns:
        The decrypted hashing secret as a UTF-8 string.
    """
    try:
        if not exchange_id:
            raise KeyManagementError(
                "exchange_id is required to decrypt hashing secret."
            )

        core_decrypt = _load_core_decrypt_hashing_secret()
        if core_decrypt is not None:
            try:
                signature = inspect.signature(core_decrypt)
                if len(signature.parameters) >= 4:
                    return core_decrypt(
                        encrypted_b64,
                        local_private_key_pem,
                        server_public_key,
                        exchange_id,
                    )

                return core_decrypt(
                    encrypted_b64,
                    local_private_key_pem,
                    server_public_key,
                )
            except (TypeError, ValueError):
                pass
            except Exception:
                # If an installed core helper is older and cannot decrypt the
                # exchangeId-derived payload, fall back to local compatibility.
                pass

        return _decrypt_hashing_secret_local(
            encrypted_b64,
            local_private_key_pem,
            server_public_key,
            exchange_id,
        )
    except KeyManagementError:
        raise
    except Exception as exc:
        raise KeyManagementError(f"Failed to decrypt hashing secret: {exc}")
