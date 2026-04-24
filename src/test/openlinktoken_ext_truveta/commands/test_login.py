"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the login command.
"""

import argparse
import base64
import json
import time
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from openlinktoken_ext_truveta.auth import AuthError, Credentials, write_session_api_url
from openlinktoken_ext_truveta.commands.initiate_exchange import _initiate_exchange
from openlinktoken_ext_truveta.commands.login import DEFAULT_DOMAIN_URL, _login

_SERVER_KEY = ec.generate_private_key(ec.SECP256R1())
_SERVER_PUBLIC_SPKI_B64 = base64.b64encode(
    _SERVER_KEY.public_key().public_bytes(
        Encoding.DER,
        PublicFormat.SubjectPublicKeyInfo,
    )
).decode("utf-8")

_LOCAL_KEY = ec.generate_private_key(ec.SECP256R1())
_LOCAL_PRIVATE_PEM = _LOCAL_KEY.private_bytes(
    Encoding.PEM,
    PrivateFormat.PKCS8,
    NoEncryption(),
).decode("utf-8")
_LOCAL_PUBLIC_PEM = (
    _LOCAL_KEY.public_key()
    .public_bytes(
        Encoding.PEM,
        PublicFormat.SubjectPublicKeyInfo,
    )
    .decode("utf-8")
)


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesig"


def _fake_creds(name="Test User", email="test@example.com") -> Credentials:
    id_token = _make_jwt({"name": name, "email": email, "exp": int(time.time()) + 3600})
    return Credentials(access_token="acc_token", id_token=id_token)


def _args(
    domain=DEFAULT_DOMAIN_URL,
    force=False,
    auth_domain=None,
    api_domain=None,
) -> argparse.Namespace:
    return argparse.Namespace(
        domain=domain,
        force=force,
        auth_domain=auth_domain,
        api_domain=api_domain,
    )


def _make_server_response() -> dict:
    """Create a minimal valid server response."""
    return {
        "exchangeName": "test-exchange",
        "exchangeId": "exch-12345",
        "hashingSecret": "encrypted-secret-data",
        "hashingSecretEncoding": "base64",
        "serverPublicKey": _SERVER_PUBLIC_SPKI_B64,
    }


def _sample_keypair() -> tuple[str, str]:
    return (_LOCAL_PRIVATE_PEM, _LOCAL_PUBLIC_PEM)


class TestLoginCommand:
    def test_returns_zero_on_success(self):
        with (
            patch(
                "openlinktoken_ext_truveta.commands.common.read_session_api_url",
                return_value="https://api.test.domain.com",
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {"test": "data"}},
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=Path("/path/to/config"),
            ),
        ):
            assert _initiate_exchange(_args()) == 0

    def test_passes_private_key_to_build_exchange_config(self):
        private_pem, public_pem = _sample_keypair()
        with (
            patch(
                "openlinktoken_ext_truveta.commands.common.read_session_api_url",
                return_value="https://api.truveta.com",
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=(private_pem, public_pem),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {"test": "data"}},
            ) as mock_build,
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=Path("/path/to/config"),
            ),
        ):
            assert _initiate_exchange(_args()) == 0

        mock_build.assert_called_once_with(
            "truveta.com", _make_server_response(), public_pem, private_pem
        )

    def test_prints_welcome_with_name_and_email(self, capsys):
        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {"test": "data"}},
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=Path("/path/to/config"),
            ),
        ):
            _initiate_exchange(_args())

        out = capsys.readouterr().out
        assert "Exchange config written to:" in out

    def test_prints_exchange_config_path_on_success(self, capsys):
        expected_path = Path("/home/user/.openlinktoken/truveta/test.com/exchange.json")
        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {"test": "data"}},
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=expected_path,
            ),
        ):
            _initiate_exchange(_args())

        out = capsys.readouterr().out
        assert str(expected_path) in out
        assert "Exchange config written to:" in out

    def test_prints_welcome_email_only_when_name_equals_email(self, capsys):
        with (
            patch(
                "openlinktoken_ext_truveta.commands.login.ensure_auth",
                return_value=_fake_creds(),
            ),
        ):
            _login(_args())

        out = capsys.readouterr().out
        assert "You've successfully logged in" in out

    def test_returns_one_on_auth_error(self, capsys):
        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            side_effect=AuthError("denied"),
        ):
            result = _login(_args())

        assert result == 1
        assert "denied" in capsys.readouterr().err

    def test_login_can_use_separate_auth_domain(self):
        args = argparse.Namespace(
            domain="http://localhost:8080",
            auth_domain="https://api.dev.truveta-int.com",
            force=False,
        )

        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            return_value=_fake_creds(),
        ) as mock_auth:
            result = _login(args)

        assert result == 0
        mock_auth.assert_called_once_with("https://api.dev.truveta-int.com")

    def test_returns_one_on_key_management_error(self, capsys):
        from openlinktoken_ext_truveta.exchange.key_management import KeyManagementError

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                side_effect=KeyManagementError("key generation failed"),
            ),
        ):
            result = _initiate_exchange(_args())

        assert result == 1
        err = capsys.readouterr().err
        assert "Key management failed" in err
        assert "key generation failed" in err

    def test_returns_one_on_exchange_api_error(self, capsys):
        from openlinktoken_ext_truveta.api.exchange import ExchangeAPIError

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                side_effect=ExchangeAPIError("API call failed"),
            ),
        ):
            result = _initiate_exchange(_args())

        assert result == 1
        err = capsys.readouterr().err
        assert "Exchange endpoint call failed" in err

    def test_returns_one_on_exchange_config_error(self, capsys):
        from openlinktoken_ext_truveta.exchange.config import ExchangeConfigError

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                side_effect=ExchangeConfigError("config building failed"),
            ),
        ):
            result = _initiate_exchange(_args())

        assert result == 1
        err = capsys.readouterr().err
        assert "Exchange config build/write failed" in err

    def test_credentials_cached_even_when_exchange_fails(self, tmp_path, monkeypatch):
        from openlinktoken_ext_truveta.api.exchange import ExchangeAPIError

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        creds = _fake_creds()

        def mock_ensure_auth(url, cached_only=False):
            from openlinktoken_ext_truveta.auth import _extract_domain, _write_cache

            domain = _extract_domain(url)
            _write_cache(domain, creds)
            return creds

        with (
            patch(
                "openlinktoken_ext_truveta.commands.common.read_session_api_url",
                return_value="https://api.test.domain.com",
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                side_effect=mock_ensure_auth,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange._extract_service_domain",
                return_value="test.domain.com",
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                side_effect=ExchangeAPIError("API call failed"),
            ),
        ):
            result = _initiate_exchange(
                argparse.Namespace(force=False, local_dev=False)
            )

        assert result == 1
        credentials_cache = (
            tmp_path
            / ".openlinktoken"
            / "truveta"
            / "test.domain.com"
            / "credentials.json"
        )
        assert credentials_cache.exists()

    def test_force_deletes_cache_before_auth(self, tmp_path, monkeypatch):
        from pathlib import Path as _Path

        monkeypatch.setattr(_Path, "home", lambda: tmp_path)
        cache = (
            tmp_path / ".openlinktoken" / "truveta" / "truveta.com" / "credentials.json"
        )
        cache.parent.mkdir(parents=True)
        cache.write_text('{"access_token": "old", "id_token": "old"}')

        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            return_value=_fake_creds(),
        ):
            _login(_args(force=True))

        assert not cache.exists()

    def test_login_persists_api_domain_in_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            return_value=_fake_creds(),
        ):
            result = _login(_args(domain="https://api.dev.truveta-int.com"))

        assert result == 0
        session_file = tmp_path / ".openlinktoken" / "truveta" / "session.json"
        assert session_file.exists()
        session_data = json.loads(session_file.read_text())
        assert session_data["api_url"] == "https://api.dev.truveta-int.com"

    def test_uses_session_domain_when_args_domain_is_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        write_session_api_url("https://api.truveta-int.com")
        args = argparse.Namespace(domain=None, force=False)

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ) as mock_auth,
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {"test": "data"}},
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=Path("/path/to/config"),
            ),
        ):
            _initiate_exchange(args)

        mock_auth.assert_called_once_with(
            "https://api.truveta-int.com", cached_only=True
        )

    def test_requires_login_session_when_no_session(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        args = argparse.Namespace(force=False, local_dev=False)

        with (
            patch(
                "openlinktoken_ext_truveta.commands.common.read_session_api_url",
                return_value=None,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ) as mock_auth,
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {"test": "data"}},
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=Path("/path/to/config"),
            ),
        ):
            result = _initiate_exchange(args)

        assert result == 1
        mock_auth.assert_not_called()
        assert "olt truveta login" in capsys.readouterr().err

    def test_initiate_exchange_uses_session_domain(self):
        args = argparse.Namespace(force=False, local_dev=False)

        with (
            patch(
                "openlinktoken_ext_truveta.commands.common.read_session_api_url",
                return_value="https://api.dev.truveta-int.com",
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ) as mock_auth,
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ) as mock_exchange,
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {"test": "data"}},
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=Path("/path/to/config"),
            ),
        ):
            result = _initiate_exchange(args)

        assert result == 0
        mock_auth.assert_called_once_with(
            "https://api.dev.truveta-int.com", cached_only=True
        )
        mock_exchange.assert_called_once_with(
            "https://api.dev.truveta-int.com",
            _sample_keypair()[1],
            "acc_token",
        )

    def test_round_trip_exchange_config_load(self, tmp_path, monkeypatch):
        """Test that exchange config written by login can be loaded back."""
        from openlinktoken_ext_truveta.exchange.config import load_exchange_config

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with (
            patch(
                "openlinktoken_ext_truveta.commands.common.read_session_api_url",
                return_value="https://api.test.domain.com",
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=_sample_keypair(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value=_make_server_response(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange._extract_service_domain",
                return_value="test.domain.com",
            ),
            patch(
                "openlinktoken_ext_truveta.exchange.config.decrypt_hashing_secret",
                return_value="decrypted-hashing-secret",
            ),
        ):
            result = _initiate_exchange(
                argparse.Namespace(force=False, local_dev=False)
            )

        assert result == 0

        loaded = load_exchange_config("test.domain.com")
        assert loaded["version"] == 1
        assert "recipients" in loaded

    def test_login_does_not_call_exchange(self):
        with (
            patch(
                "openlinktoken_ext_truveta.commands.login.ensure_auth",
                return_value=_fake_creds(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
            ) as mock_exchange,
        ):
            result = _login(_args())

        assert result == 0
        mock_exchange.assert_not_called()
