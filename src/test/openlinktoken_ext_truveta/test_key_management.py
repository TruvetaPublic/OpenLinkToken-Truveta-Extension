"""
Copyright (c) Truveta. All rights reserved.

Unit tests for key_management.py — delegation to OpenToken core EC utilities,
domain key persistence, and fingerprint behavior.
"""

import base64
import hashlib
import hmac
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    generate_private_key,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from openlinktoken_ext_truveta.exchange.key_management import (
    KeyManagementError,
    _generate_keypair_from_core,
    _load_core_ec_key_utils,
    decrypt_hashing_secret,
    get_key_fingerprint,
    load_or_generate_domain_keys,
)


def _generate_test_keypair_pem() -> tuple[str, str]:
    """Generate a real ECDH P-256 key pair and return (private_pem, public_pem)."""
    private_key = generate_private_key(SECP256R1(), backend=default_backend())
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode("utf-8")
    )
    return private_pem, public_pem


def _encrypt_for_recipient(
    plaintext: str,
    recipient_public_pem: str,
    sender_private_pem: str,
    exchange_id: str,
) -> str:
    """Encrypt plaintext using the same algorithm as the C# server."""
    from cryptography.hazmat.primitives.serialization import (
        load_pem_private_key,
        load_pem_public_key,
    )

    sender_private = load_pem_private_key(
        sender_private_pem.encode("utf-8"), password=None
    )
    recipient_public = load_pem_public_key(recipient_public_pem.encode("utf-8"))

    if not exchange_id:
        raise ValueError("exchange_id is required")

    raw_shared = sender_private.exchange(ECDH(), recipient_public)
    shared_secret = hashlib.sha256(raw_shared).digest()

    salt = exchange_id.encode("utf-8")
    prk = hmac.new(salt, shared_secret, hashlib.sha256).digest()
    info = b"openlink-token-encryption"
    encryption_key = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()

    import secrets as _secrets

    nonce = _secrets.token_bytes(12)
    cipher = Cipher(
        algorithms.AES(encryption_key), modes.GCM(nonce), backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext.encode("utf-8")) + encryptor.finalize()
    tag = encryptor.tag

    payload = nonce + ciphertext + tag
    return base64.b64encode(payload).decode("utf-8")


def _fake_core_utils():
    core = MagicMock()
    core.generate_key_pair.return_value = (
        b"-----BEGIN PRIVATE KEY-----\ncore-private\n-----END PRIVATE KEY-----\n",
        b"-----BEGIN PUBLIC KEY-----\ncore-public\n-----END PUBLIC KEY-----\n",
    )
    core.public_key_fingerprint.return_value = "ABCDEF"
    return core


class TestCoreModuleLoading:
    def test_loads_openlinktoken_core_module(self, monkeypatch):
        fake_core = _fake_core_utils()

        def fake_import(name):
            if name == "openlinktoken.ec_key_utils":
                return fake_core
            raise ModuleNotFoundError(name)

        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management.import_module",
            fake_import,
        )
        loaded = _load_core_ec_key_utils()
        assert loaded is fake_core

    def test_raises_when_no_core_module_available(self, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError("missing")),
        )
        with pytest.raises(KeyManagementError, match="OpenToken core EC key utilities"):
            _load_core_ec_key_utils()


class TestGenerateKeypairFromCore:
    def test_generates_and_decodes_pem_strings(self, monkeypatch):
        fake_core = _fake_core_utils()
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._load_core_ec_key_utils",
            lambda: fake_core,
        )

        private_pem, public_pem = _generate_keypair_from_core()

        fake_core.generate_key_pair.assert_called_once_with("P-256")
        assert isinstance(private_pem, str)
        assert isinstance(public_pem, str)
        assert "BEGIN PRIVATE KEY" in private_pem
        assert "BEGIN PUBLIC KEY" in public_pem


class TestLoadOrGenerateDomainKeys:
    def test_loads_existing_keys_without_regeneration(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        domain_dir = tmp_path / ".openlinktoken" / "truveta" / "test.domain.com"
        domain_dir.mkdir(parents=True)
        (domain_dir / "private_key.pem").write_text("private-existing")
        (domain_dir / "public_key.pem").write_text("public-existing")

        private_pem, public_pem = load_or_generate_domain_keys("test.domain.com")
        assert private_pem == "private-existing"
        assert public_pem == "public-existing"

    def test_generates_and_persists_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        private_pem = (
            "-----BEGIN PRIVATE KEY-----\nnew-private\n-----END PRIVATE KEY-----\n"
        )
        public_pem = (
            "-----BEGIN PUBLIC KEY-----\nnew-public\n-----END PUBLIC KEY-----\n"
        )
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._generate_keypair_from_core",
            lambda: (private_pem, public_pem),
        )

        generated_private, generated_public = load_or_generate_domain_keys(
            "test.domain.com"
        )

        assert generated_private == private_pem
        assert generated_public == public_pem

        domain_dir = tmp_path / ".openlinktoken" / "truveta" / "test.domain.com"
        assert (domain_dir / "private_key.pem").read_text() == private_pem
        assert (domain_dir / "public_key.pem").read_text() == public_pem

    def test_raises_on_write_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._generate_keypair_from_core",
            lambda: ("private", "public"),
        )

        def raise_permission_error(*_args, **_kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "write_text", raise_permission_error)

        with pytest.raises(KeyManagementError, match="Failed to persist keys"):
            load_or_generate_domain_keys("test.domain.com")


class TestDecryptHashingSecret:
    def test_uses_core_decrypt_helper_when_available(self, monkeypatch):
        decrypt_mock = MagicMock(return_value="core-decrypted")
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._load_core_decrypt_hashing_secret",
            lambda: decrypt_mock,
        )

        value = decrypt_hashing_secret("enc", "private", "public", "ex-123")

        assert value == "core-decrypted"
        decrypt_mock.assert_called_once_with("enc", "private", "public")

    def test_falls_back_to_local_when_core_helper_missing(self, monkeypatch):
        local_decrypt_mock = MagicMock(return_value="local-decrypted")
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._load_core_decrypt_hashing_secret",
            lambda: None,
        )
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._decrypt_hashing_secret_local",
            local_decrypt_mock,
        )

        value = decrypt_hashing_secret("enc", "private", "public", "ex-123")

        assert value == "local-decrypted"
        local_decrypt_mock.assert_called_once_with("enc", "private", "public", "ex-123")

    def test_decrypts_ecdh_encrypted_secret(self):
        recipient_private_pem, recipient_public_pem = _generate_test_keypair_pem()
        sender_private_pem, sender_public_pem = _generate_test_keypair_pem()
        plaintext = "Truveta.OpenLink.Token.Hashing.Secret.V1"
        exchange_id = "88f1373e-3ffd-4ec5-8980-4fbf544b61a8"

        encrypted_b64 = _encrypt_for_recipient(
            plaintext,
            recipient_public_pem,
            sender_private_pem,
            exchange_id,
        )
        decrypted = decrypt_hashing_secret(
            encrypted_b64,
            recipient_private_pem,
            sender_public_pem,
            exchange_id,
        )

        assert decrypted == plaintext

    def test_accepts_spki_base64_server_public_key(self):
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        recipient_private_pem, recipient_public_pem = _generate_test_keypair_pem()
        sender_private_pem, sender_public_pem = _generate_test_keypair_pem()
        plaintext = "my-hashing-secret"
        exchange_id = "88f1373e-3ffd-4ec5-8980-4fbf544b61a8"

        sender_public_spki_b64 = base64.b64encode(
            load_pem_public_key(sender_public_pem.encode("utf-8")).public_bytes(
                Encoding.DER, PublicFormat.SubjectPublicKeyInfo
            )
        ).decode("utf-8")

        encrypted_b64 = _encrypt_for_recipient(
            plaintext,
            recipient_public_pem,
            sender_private_pem,
            exchange_id,
        )
        decrypted = decrypt_hashing_secret(
            encrypted_b64,
            recipient_private_pem,
            sender_public_spki_b64,
            exchange_id,
        )

        assert decrypted == plaintext

    def test_decrypts_exchangeid_derived_encrypted_secret(self):
        recipient_private_pem, recipient_public_pem = _generate_test_keypair_pem()
        sender_private_pem, sender_public_pem = _generate_test_keypair_pem()
        plaintext = "Truveta.OpenLink.Token.Hashing.Secret.V1"
        exchange_id = "88f1373e-3ffd-4ec5-8980-4fbf544b61a8"

        encrypted_b64 = _encrypt_for_recipient(
            plaintext,
            recipient_public_pem,
            sender_private_pem,
            exchange_id,
        )
        decrypted = decrypt_hashing_secret(
            encrypted_b64,
            recipient_private_pem,
            sender_public_pem,
            exchange_id,
        )

        assert decrypted == plaintext

    def test_raises_on_tampered_ciphertext(self):
        recipient_private_pem, recipient_public_pem = _generate_test_keypair_pem()
        sender_private_pem, sender_public_pem = _generate_test_keypair_pem()

        exchange_id = "88f1373e-3ffd-4ec5-8980-4fbf544b61a8"
        encrypted_b64 = _encrypt_for_recipient(
            "secret",
            recipient_public_pem,
            sender_private_pem,
            exchange_id,
        )
        encrypted_bytes = bytearray(base64.b64decode(encrypted_b64))
        encrypted_bytes[-1] ^= 0xFF
        tampered_b64 = base64.b64encode(bytes(encrypted_bytes)).decode("utf-8")

        with pytest.raises(
            KeyManagementError, match="Failed to decrypt hashing secret"
        ):
            decrypt_hashing_secret(
                tampered_b64,
                recipient_private_pem,
                sender_public_pem,
                exchange_id,
            )

    def test_raises_on_wrong_private_key(self):
        recipient_private_pem, recipient_public_pem = _generate_test_keypair_pem()
        sender_private_pem, sender_public_pem = _generate_test_keypair_pem()
        wrong_private_pem, _ = _generate_test_keypair_pem()

        exchange_id = "88f1373e-3ffd-4ec5-8980-4fbf544b61a8"
        encrypted_b64 = _encrypt_for_recipient(
            "secret",
            recipient_public_pem,
            sender_private_pem,
            exchange_id,
        )

        with pytest.raises(
            KeyManagementError, match="Failed to decrypt hashing secret"
        ):
            decrypt_hashing_secret(
                encrypted_b64,
                wrong_private_pem,
                sender_public_pem,
                exchange_id,
            )

    def test_raises_on_invalid_private_key(self):
        _, sender_public_pem = _generate_test_keypair_pem()
        exchange_id = "88f1373e-3ffd-4ec5-8980-4fbf544b61a8"

        with pytest.raises(
            KeyManagementError, match="Failed to decrypt hashing secret"
        ):
            decrypt_hashing_secret(
                "dGVzdA==",
                "not-a-valid-pem",
                sender_public_pem,
                exchange_id,
            )

    def test_raises_on_invalid_server_public_key(self):
        recipient_private_pem, _ = _generate_test_keypair_pem()
        exchange_id = "88f1373e-3ffd-4ec5-8980-4fbf544b61a8"

        with pytest.raises(
            KeyManagementError, match="Failed to decrypt hashing secret"
        ):
            decrypt_hashing_secret(
                "dGVzdA==",
                recipient_private_pem,
                "not-a-valid-key",
                exchange_id,
            )

    def test_raises_when_exchange_id_missing(self):
        recipient_private_pem, recipient_public_pem = _generate_test_keypair_pem()
        sender_private_pem, sender_public_pem = _generate_test_keypair_pem()

        encrypted_b64 = _encrypt_for_recipient(
            "secret",
            recipient_public_pem,
            sender_private_pem,
            "88f1373e-3ffd-4ec5-8980-4fbf544b61a8",
        )

        with pytest.raises(KeyManagementError, match="exchange_id is required"):
            decrypt_hashing_secret(
                encrypted_b64, recipient_private_pem, sender_public_pem, ""
            )


class TestGetKeyFingerprint:
    def test_uses_core_fingerprint_and_normalizes_case(self, monkeypatch):
        fake_core = _fake_core_utils()
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._load_core_ec_key_utils",
            lambda: fake_core,
        )

        fingerprint = get_key_fingerprint(
            "-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----"
        )
        fake_core.public_key_fingerprint.assert_called_once_with(
            b"-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----"
        )
        assert fingerprint == "abcdef"

    def test_raises_when_core_fingerprint_fails(self, monkeypatch):
        fake_core = _fake_core_utils()
        fake_core.public_key_fingerprint.side_effect = ValueError("bad key")
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._load_core_ec_key_utils",
            lambda: fake_core,
        )

        with pytest.raises(
            KeyManagementError, match="Failed to calculate key fingerprint"
        ):
            get_key_fingerprint("invalid")

    def test_accepts_spki_base64_public_key(self, monkeypatch):
        fake_core = _fake_core_utils()
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.exchange.key_management._load_core_ec_key_utils",
            lambda: fake_core,
        )

        _, public_pem = _generate_test_keypair_pem()
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        spki_b64 = base64.b64encode(
            load_pem_public_key(public_pem.encode("utf-8")).public_bytes(
                Encoding.DER,
                PublicFormat.SubjectPublicKeyInfo,
            )
        ).decode("utf-8")

        fingerprint = get_key_fingerprint(spki_b64)

        fake_core.public_key_fingerprint.assert_called_once()
        passed_value = fake_core.public_key_fingerprint.call_args[0][0]
        assert isinstance(passed_value, bytes)
        assert passed_value.startswith(b"-----BEGIN PUBLIC KEY-----")
        assert fingerprint == "abcdef"
