"""
Copyright (c) Truveta. All rights reserved.

Unit tests for exchange_config.py — config building, persistence, and loading.
"""

import base64
import json
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from openlinktoken.exchange_config import resolve_exchange_config_inputs
from openlinktoken_ext_truveta.exchange.config import (
    ExchangeConfigError,
    _load_build_exchange_envelope,
    _load_resolve_exchange_inputs,
    build_exchange_config,
    load_exchange_config,
    resolve_exchange_payload,
    write_exchange_config,
)

_FAKE_PRIVATE_PEM = (
    "-----BEGIN PRIVATE KEY-----\nlocal-private\n-----END PRIVATE KEY-----"
)
_DECRYPTED_SECRET = "decrypted-hashing-secret"


def _generate_keypair() -> tuple[str, str, str]:
    """Generate P-256 keys and return private PEM, public PEM, and public DER b64."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    public_der_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            Encoding.DER,
            PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("utf-8")
    return private_pem, public_pem, public_der_b64


def _make_server_response(server_public_key: str) -> dict:
    """Create a minimal valid server response with an encrypted hashing secret."""
    return {
        "exchangeName": "test-exchange",
        "exchangeId": "exch-12345",
        "hashingSecret": "encrypted-secret-data",
        "hashingSecretEncoding": "base64",
        "serverPublicKey": server_public_key,
    }


def _patch_decrypt(
    return_value: str = _DECRYPTED_SECRET, already_encoded: bool = False
):
    """Patch decrypt_hashing_secret in exchange_config module."""
    patched_value = return_value
    if not already_encoded:
        patched_value = base64.b64encode(return_value.encode("utf-8")).decode("utf-8")

    return patch(
        "openlinktoken_ext_truveta.exchange.config.decrypt_hashing_secret",
        return_value=patched_value,
    )


def _make_valid_exchange_config() -> dict:
    """Build a valid OpenLinkToken-compatible JWE exchange config for write/load tests."""
    local_private_pem, local_public_pem, _ = _generate_keypair()
    _, _, server_public_der_b64 = _generate_keypair()
    server_response = _make_server_response(server_public_der_b64)
    with _patch_decrypt():
        return build_exchange_config(
            "test.domain.com",
            server_response,
            local_public_pem,
            local_private_pem,
        )


class TestBuildExchangeConfig:
    def test_builds_core_compatible_jwe_exchange_config(self):
        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)

        with _patch_decrypt():
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        assert config["version"] == 1
        assert "payload" not in config
        assert isinstance(config.get("protected"), str)
        assert "recipients" in config
        assert "iv" in config
        assert "ciphertext" in config
        assert "tag" in config

        protected_value = config["protected"]
        protected_padded = protected_value + ("=" * (-len(protected_value) % 4))
        protected_header = json.loads(
            base64.urlsafe_b64decode(protected_padded).decode("utf-8")
        )
        assert protected_header["typ"] == "openlinktoken-exchange+jwe"
        assert protected_header["cty"] == "application/openlinktoken-exchange+json"
        assert protected_header["enc"] == "A256GCM"

        recipients = config["recipients"]
        assert isinstance(recipients, list)
        assert len(recipients) == 2
        for recipient in recipients:
            assert isinstance(recipient.get("encrypted_key"), str)
            header = recipient.get("header")
            assert isinstance(header, dict)
            assert header.get("alg") == "ECDH-ES+A256KW"
            assert isinstance(header.get("kid"), str)
            assert header["kid"].startswith("sha256:")
            epk = header.get("epk")
            assert isinstance(epk, dict)
            assert epk.get("kty") == "EC"
            assert epk.get("crv") == "P-256"
            assert isinstance(epk.get("x"), str)
            assert isinstance(epk.get("y"), str)

        resolved = resolve_exchange_config_inputs(
            exchange_config_value=config,
            private_key_value=local_private_pem,
        )
        payload = resolved.payload
        assert payload["exchangeName"] == server_response["exchangeName"]
        assert payload["exchangeId"] == server_response["exchangeId"]
        assert resolved.hashing_secret.decode("utf-8") == _DECRYPTED_SECRET
        assert payload["hashingSecretEncoding"] == "base64url"
        assert payload["senderPublicKey"] == local_public_pem
        assert payload["recipientPublicKey"].startswith("-----BEGIN PUBLIC KEY-----")
        assert payload["curve"] == "P-256"
        assert payload["createdAt"].endswith("Z")

    def test_raises_on_missing_required_field(self):
        _, public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        for field in [
            "exchangeName",
            "exchangeId",
            "hashingSecret",
            "hashingSecretEncoding",
            "serverPublicKey",
        ]:
            server_response = _make_server_response(server_public_der_b64)
            del server_response[field]
            with _patch_decrypt(), pytest.raises(ExchangeConfigError, match=field):
                build_exchange_config(
                    "test.domain.com", server_response, public_pem, _FAKE_PRIVATE_PEM
                )

    def test_raises_when_decryption_fails(self):
        from openlinktoken_ext_truveta.exchange.key_management import KeyManagementError

        _, public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)

        with (
            patch(
                "openlinktoken_ext_truveta.exchange.config.decrypt_hashing_secret",
                side_effect=KeyManagementError("bad key"),
            ),
            pytest.raises(
                ExchangeConfigError, match="Failed to decrypt hashing secret"
            ),
        ):
            build_exchange_config(
                "test.domain.com", server_response, public_pem, _FAKE_PRIVATE_PEM
            )

    def test_decrypt_called_with_correct_arguments(self):
        _, public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)
        mock_decrypt = MagicMock(
            return_value=base64.b64encode(_DECRYPTED_SECRET.encode("utf-8")).decode(
                "utf-8"
            )
        )

        with patch(
            "openlinktoken_ext_truveta.exchange.config.decrypt_hashing_secret",
            mock_decrypt,
        ):
            build_exchange_config(
                "test.domain.com", server_response, public_pem, _FAKE_PRIVATE_PEM
            )

        mock_decrypt.assert_called_once_with(
            server_response["hashingSecret"],
            _FAKE_PRIVATE_PEM,
            server_response["serverPublicKey"],
            server_response["exchangeId"],
        )

    def test_derives_curve_from_server_public_key(self):
        local_private_pem, local_public_pem, _ = _generate_keypair()
        server_private_key = ec.generate_private_key(ec.SECP384R1())
        server_public_der_b64 = base64.b64encode(
            server_private_key.public_key().public_bytes(
                Encoding.DER,
                PublicFormat.SubjectPublicKeyInfo,
            )
        ).decode("utf-8")
        server_response = _make_server_response(server_public_der_b64)

        valid_envelope = {
            "version": 1,
            "protected": "protected",
            "iv": "iv",
            "ciphertext": "ciphertext",
            "tag": "tag",
            "recipients": [
                {
                    "encrypted_key": "key1",
                    "header": {
                        "alg": "ECDH-ES+A256KW",
                        "kid": "sha256:kid1",
                        "epk": {
                            "kty": "EC",
                            "crv": "P-256",
                            "x": "x1",
                            "y": "y1",
                        },
                    },
                },
                {
                    "encrypted_key": "key2",
                    "header": {
                        "alg": "ECDH-ES+A256KW",
                        "kid": "sha256:kid2",
                        "epk": {
                            "kty": "EC",
                            "crv": "P-256",
                            "x": "x2",
                            "y": "y2",
                        },
                    },
                },
            ],
        }
        mock_builder = MagicMock(return_value=valid_envelope)

        with (
            _patch_decrypt(),
            patch(
                "openlinktoken_ext_truveta.exchange.config._load_build_exchange_envelope",
                return_value=mock_builder,
            ),
        ):
            build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        assert mock_builder.call_args.kwargs["curve"] == "P-384"

    def test_decodes_base64_hashing_secret_before_writing_exchange_config(self):
        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)
        decrypted_secret = "YjFLRlBKeUYzdGp1c1BxSXkvUXNrdz09"
        expected_secret_bytes = base64.b64decode(decrypted_secret)

        with _patch_decrypt(return_value=decrypted_secret, already_encoded=True):
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        resolved = resolve_exchange_config_inputs(
            exchange_config_value=config,
            private_key_value=local_private_pem,
        )
        payload = resolved.payload

        assert resolved.hashing_secret == expected_secret_bytes
        assert payload["hashingSecret"] == base64.urlsafe_b64encode(
            expected_secret_bytes
        ).rstrip(b"=").decode("ascii")
        assert payload["hashingSecretEncoding"] == "base64url"

    def test_includes_rotation_count_bin_width_dimension_bias_from_server_response(
        self,
    ):
        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)
        server_response["rotationCount"] = 50
        server_response["binWidth"] = 0.1
        server_response["dimensionBias"] = [0.01, -0.02, 0.03]

        with _patch_decrypt():
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        assert config["rotationCount"] == 50
        assert config["binWidth"] == 0.1
        assert config["dimensionBias"] == [0.01, -0.02, 0.03]

    def test_uses_defaults_for_absent_rotation_count_bin_width_dimension_bias(self):
        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)

        with _patch_decrypt():
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        assert config["rotationCount"] == 30
        assert config["binWidth"] == 0.05
        assert config["dimensionBias"] == []

    def test_decrypts_rotation_iv_and_stores_as_base64url(self):
        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)
        # 16 raw bytes base64-encoded (as the server sends after encryption)
        raw_iv_bytes = bytes(range(16))
        decrypted_iv_b64 = base64.b64encode(raw_iv_bytes).decode("ascii")
        server_response["encryptedRotationIv"] = "some-encrypted-iv-data"
        expected_rotation_iv = (
            base64.urlsafe_b64encode(raw_iv_bytes).rstrip(b"=").decode("ascii")
        )

        hashing_secret_b64 = base64.b64encode(_DECRYPTED_SECRET.encode("utf-8")).decode(
            "utf-8"
        )
        with patch(
            "openlinktoken_ext_truveta.exchange.config.decrypt_hashing_secret",
            side_effect=[hashing_secret_b64, decrypted_iv_b64],
        ):
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        assert config["rotationIv"] == expected_rotation_iv
        assert config["rotationIvEncoding"] == "base64url"

    def test_decrypts_rotation_iv_base64_with_nonurl_chars(self):
        """Prove that base64 chars (+/) are properly converted to base64url (-_)."""
        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)
        # Choose bytes whose base64 encoding contains + and /
        raw_iv_bytes = (
            b"\xfb\xff\xfe\xfb\xff\xfe\xfb\xff\xfe\xfb\xff\xfe\xfb\xff\xfe\xfb"
        )
        assert (
            "+" in base64.b64encode(raw_iv_bytes).decode()
            or "/" in base64.b64encode(raw_iv_bytes).decode()
        )
        decrypted_iv_b64 = base64.b64encode(raw_iv_bytes).decode("ascii")
        server_response["encryptedRotationIv"] = "some-encrypted-iv-data"

        hashing_secret_b64 = base64.b64encode(_DECRYPTED_SECRET.encode("utf-8")).decode(
            "utf-8"
        )
        with patch(
            "openlinktoken_ext_truveta.exchange.config.decrypt_hashing_secret",
            side_effect=[hashing_secret_b64, decrypted_iv_b64],
        ):
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        assert "+" not in config["rotationIv"]
        assert "/" not in config["rotationIv"]
        assert "=" not in config["rotationIv"]
        assert base64.urlsafe_b64decode(config["rotationIv"] + "==") == raw_iv_bytes

    def test_omits_rotation_iv_fields_when_not_in_server_response(self):
        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)

        with _patch_decrypt():
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        assert "rotationIv" not in config
        assert "rotationIvEncoding" not in config

    def test_raises_when_rotation_iv_decryption_fails(self):
        from openlinktoken_ext_truveta.exchange.key_management import KeyManagementError

        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)
        server_response["encryptedRotationIv"] = "some-encrypted-iv-data"

        hashing_secret_b64 = base64.b64encode(_DECRYPTED_SECRET.encode("utf-8")).decode(
            "utf-8"
        )
        with (
            patch(
                "openlinktoken_ext_truveta.exchange.config.decrypt_hashing_secret",
                side_effect=[hashing_secret_b64, KeyManagementError("bad iv key")],
            ),
            pytest.raises(ExchangeConfigError, match="Failed to decrypt rotation IV"),
        ):
            build_exchange_config(
                "test.domain.com", server_response, local_public_pem, local_private_pem
            )


class TestValidateExchangeExtensionFields:
    def test_raises_on_non_positive_rotation_count(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        with pytest.raises(ExchangeConfigError, match="rotationCount"):
            _validate_exchange_extension_fields({"rotationCount": -1})

    def test_raises_on_negative_rotation_count(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        with pytest.raises(ExchangeConfigError, match="rotationCount"):
            _validate_exchange_extension_fields({"rotationCount": -5})

    def test_allows_zero_rotation_count(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        _validate_exchange_extension_fields({"rotationCount": 0})

    def test_raises_on_non_positive_bin_width(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        with pytest.raises(ExchangeConfigError, match="binWidth"):
            _validate_exchange_extension_fields({"binWidth": 0.0})

    def test_raises_on_infinite_bin_width(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        with pytest.raises(ExchangeConfigError, match="binWidth"):
            _validate_exchange_extension_fields({"binWidth": float("inf")})

    def test_raises_when_dimension_bias_not_a_list(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        with pytest.raises(ExchangeConfigError, match="dimensionBias"):
            _validate_exchange_extension_fields({"dimensionBias": "not-a-list"})

    def test_passes_for_valid_extension_fields(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        _validate_exchange_extension_fields(
            {"rotationCount": 30, "binWidth": 0.05, "dimensionBias": [0.01, -0.02]}
        )

    def test_passes_when_extension_fields_absent(self):
        from openlinktoken_ext_truveta.exchange.config import (
            _validate_exchange_extension_fields,
        )

        _validate_exchange_extension_fields({})

    def test_writes_config_to_current_dir_with_openlink_date_name(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)

        config = _make_valid_exchange_config()
        config_path = write_exchange_config("test.domain.com", config)

        assert config_path.parent == tmp_path
        assert re.fullmatch(
            r"openlinktoken-\d{4}-\d{2}-\d{2}\.exchange\.json", config_path.name
        )

    def test_writes_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        config = _make_valid_exchange_config()
        config_path = write_exchange_config("test.domain.com", config)

        written_config = json.loads(config_path.read_text())
        assert written_config == config

    def test_rejects_legacy_payload_only_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ExchangeConfigError, match="Invalid exchange envelope"):
            write_exchange_config("test.domain.com", {"payload": {"test": "data"}})

    def test_raises_on_write_permission_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        config = _make_valid_exchange_config()

        with patch("pathlib.Path.write_text", side_effect=PermissionError("denied")):
            with pytest.raises(
                ExchangeConfigError, match="Failed to write exchange config"
            ):
                write_exchange_config("test.domain.com", config)


class TestLoadExchangeConfig:
    def test_loads_existing_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        config = _make_valid_exchange_config()
        write_exchange_config("test.domain.com", config)

        loaded = load_exchange_config("test.domain.com")
        assert loaded == config

    def test_raises_when_config_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ExchangeConfigError, match="Exchange config not found"):
            load_exchange_config("nonexistent.domain.com")

    def test_raises_on_invalid_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        (tmp_path / "openlinktoken-2026-04-23.exchange.json").write_text(
            "invalid json {"
        )

        with pytest.raises(ExchangeConfigError):
            load_exchange_config("test.domain.com")

    def test_does_not_fallback_to_legacy_home_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with pytest.raises(ExchangeConfigError, match="current directory"):
            load_exchange_config("test.domain.com")

    def test_round_trip_write_and_load(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        _, public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)

        with _patch_decrypt():
            config = build_exchange_config(
                "test.domain.com", server_response, public_pem, _FAKE_PRIVATE_PEM
            )

        write_exchange_config("test.domain.com", config)
        loaded = load_exchange_config("test.domain.com")

        assert loaded == config

    def test_prefers_todays_config_when_multiple_exist(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        today_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        old_config = _make_valid_exchange_config()
        today_config = _make_valid_exchange_config()
        today_config["protected"] = "today-config"

        (tmp_path / "openlinktoken-2020-01-01.exchange.json").write_text(
            json.dumps(old_config)
        )
        (tmp_path / f"openlinktoken-{today_stamp}.exchange.json").write_text(
            json.dumps(today_config)
        )

        loaded = load_exchange_config("test.domain.com")
        assert loaded["protected"] == "today-config"

    def test_raises_when_multiple_configs_exist_without_todays_file(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)

        config_a = _make_valid_exchange_config()
        config_b = _make_valid_exchange_config()

        (tmp_path / "openlinktoken-2026-04-22.exchange.json").write_text(
            json.dumps(config_a)
        )
        (tmp_path / "openlinktoken-2026-04-23.exchange.json").write_text(
            json.dumps(config_b)
        )

        with pytest.raises(
            ExchangeConfigError,
            match="today's date",
        ):
            load_exchange_config("test.domain.com")

    def test_raises_when_single_config_exists_but_not_todays(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)

        config = _make_valid_exchange_config()
        (tmp_path / "openlinktoken-2020-01-01.exchange.json").write_text(
            json.dumps(config)
        )

        with pytest.raises(
            ExchangeConfigError,
            match="today's date",
        ):
            load_exchange_config("test.domain.com")


class TestResolveExchangePayload:
    def test_resolves_jwe_payload_with_daily_private_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        local_private_pem, local_public_pem, _ = _generate_keypair()
        _, _, server_public_der_b64 = _generate_keypair()
        server_response = _make_server_response(server_public_der_b64)
        today_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        with _patch_decrypt():
            config = build_exchange_config(
                "test.domain.com",
                server_response,
                local_public_pem,
                local_private_pem,
            )

        (tmp_path / f"openlinktoken-{today_stamp}.exchange.json").write_text(
            json.dumps(config)
        )
        key_path = (
            tmp_path / ".openlinktoken" / f"openlinktoken-{today_stamp}.private.pem"
        )
        key_path.parent.mkdir(parents=True)
        key_path.write_text(local_private_pem)

        payload = resolve_exchange_payload("test.domain.com")

        assert payload["exchangeId"] == server_response["exchangeId"]


class TestModuleLoaderFallbacks:
    def test_jwe_loader_does_not_fallback_to_opentoken(self):
        calls: list[str] = []

        def _fake_import(module_name: str):
            calls.append(module_name)
            raise ModuleNotFoundError(module_name)

        with (
            patch(
                "openlinktoken_ext_truveta.exchange.config.import_module", _fake_import
            ),
            pytest.raises(ExchangeConfigError, match="exchange envelope utilities"),
        ):
            _load_build_exchange_envelope()

        assert "opentoken.exchange_jwe" not in calls

    def test_exchange_config_loader_does_not_fallback_to_opentoken(self):
        calls: list[str] = []

        def _fake_import(module_name: str):
            calls.append(module_name)
            raise ModuleNotFoundError(module_name)

        with (
            patch(
                "openlinktoken_ext_truveta.exchange.config.import_module", _fake_import
            ),
            pytest.raises(ExchangeConfigError, match="exchange config utilities"),
        ):
            _load_resolve_exchange_inputs()

        assert "opentoken.exchange_config" not in calls
