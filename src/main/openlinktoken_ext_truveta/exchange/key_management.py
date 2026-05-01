"""
Copyright (c) Truveta. All rights reserved.

ECDH P-256 key pair management for OpenToken exchange.

Uses OpenToken core EC key utilities for key generation and fingerprinting,
and persists domain-scoped keys under ~/.openlinktoken/truveta/<domain>/.
"""

import base64
import hashlib
import hmac
import inspect
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
    domain_dir,
    private_key_path,
    public_key_path,
)

_NONCE_LENGTH = 12
_TAG_LENGTH = 16
_UTF8_ENCODING = "utf-8"


class KeyManagementError(Exception):
    """Raised when key generation, persistence, or loading fails."""


def _load_core_ec_key_utils():
    """Load OpenToken EC key utilities from core modules."""
    module_name = "openlinktoken.ec_key_utils"
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        raise KeyManagementError(
            "OpenToken core EC key utilities are unavailable. "
            "Expected module: openlinktoken.ec_key_utils"
        ) from exc


def _generate_keypair_from_core() -> tuple[str, str]:
    """Generate ECDH P-256 keys using OpenToken core utilities."""
    ec_utils = _load_core_ec_key_utils()
    private_pem, public_pem = ec_utils.generate_key_pair("P-256")

    if isinstance(private_pem, bytes):
        private_pem = private_pem.decode(_UTF8_ENCODING)
    if isinstance(public_pem, bytes):
        public_pem = public_pem.decode(_UTF8_ENCODING)

    return private_pem, public_pem


def load_or_generate_domain_keys(domain: str) -> tuple[str, str]:
    """Load existing domain keys or generate and persist new ones."""
    domain_directory = domain_dir(domain)
    private_key_file = private_key_path(domain)
    public_key_file = public_key_path(domain)

    if private_key_file.exists() and public_key_file.exists():
        try:
            private_pem = private_key_file.read_text()
            public_pem = public_key_file.read_text()
            return private_pem, public_pem
        except Exception as exc:
            raise KeyManagementError(
                f"Failed to read existing keys for domain {domain!r}: {exc}"
            )

    try:
        private_pem, public_pem = _generate_keypair_from_core()
    except Exception as exc:
        raise KeyManagementError(f"Failed to generate ECDH P-256 key pair: {exc}")

    try:
        domain_directory.mkdir(parents=True, exist_ok=True)
        private_key_file.write_text(private_pem)
        public_key_file.write_text(public_pem)
    except Exception as exc:
        raise KeyManagementError(f"Failed to persist keys for domain {domain!r}: {exc}")

    return private_pem, public_pem


def get_key_fingerprint(public_key_pem: str) -> str:
    """Calculate the SHA-256 fingerprint of a public key."""
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
    """Load an EC public key from either PEM or raw DER/SPKI base64 format."""
    if key_data.strip().startswith(PEM_HEADER_PREFIX):
        return load_pem_public_key(key_data.encode(_UTF8_ENCODING))
    return load_der_public_key(base64.b64decode(key_data))


def _load_core_decrypt_hashing_secret():
    """Load OpenToken's canonical decrypt helper when it exists."""
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
    """Local decryption matching the server's HKDF-based key derivation.

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
    """Decrypt the ECDH-encrypted hashing secret received from the server."""
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
