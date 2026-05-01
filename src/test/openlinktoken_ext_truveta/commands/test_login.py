"""
Copyright (c) Truveta. All rights reserved.

Unit tests for login and initiate-exchange commands.
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
from openlinktoken_ext_truveta.auth import AuthError, Credentials
from openlinktoken_ext_truveta.commands.common import (
    LOCAL_API_URL,
    AuthenticatedCommandContext,
    SessionResolutionError,
)
from openlinktoken_ext_truveta.commands.initiate_exchange import _initiate_exchange
from openlinktoken_ext_truveta.commands.login import _login
from openlinktoken_ext_truveta.domain import DEFAULT_DOMAIN

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


def _fake_creds(
    name: str = "Test User", email: str = "test@example.com"
) -> Credentials:
    id_token = _make_jwt({"name": name, "email": email, "exp": int(time.time()) + 3600})
    return Credentials(access_token="acc_token", id_token=id_token)


def _login_args(
    domain: str | None = DEFAULT_DOMAIN,
    force: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(domain=domain, force=force)


def _exchange_args(local_dev: bool = False) -> argparse.Namespace:
    return argparse.Namespace(local_dev=local_dev)


def _make_server_response() -> dict:
    return {
        "exchangeName": "test-exchange",
        "exchangeId": "exch-12345",
        "hashingSecret": "encrypted-secret-data",
        "hashingSecretEncoding": "utf-8",
        "serverPublicKey": _SERVER_PUBLIC_SPKI_B64,
    }


def _sample_keypair() -> tuple[str, str]:
    return (_LOCAL_PRIVATE_PEM, _LOCAL_PUBLIC_PEM)


class TestLoginCommand:
    def test_returns_zero_and_persists_domain_on_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            return_value=_fake_creds(),
        ):
            result = _login(_login_args(domain="dev.truveta-int.com"))

        assert result == 0
        session_file = tmp_path / ".openlinktoken" / "truveta" / "session.json"
        assert json.loads(session_file.read_text())["domain"] == "dev.truveta-int.com"

    def test_force_deletes_cache_before_auth(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cache = (
            tmp_path / ".openlinktoken" / "truveta" / "truveta.com" / "credentials.json"
        )
        cache.parent.mkdir(parents=True)
        cache.write_text('{"access_token": "old", "id_token": "old"}')

        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            return_value=_fake_creds(),
        ):
            _login(_login_args(force=True))

        assert not cache.exists()

    def test_returns_one_on_auth_error(self, capsys):
        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            side_effect=AuthError("denied"),
        ):
            result = _login(_login_args())

        assert result == 1
        assert "denied" in capsys.readouterr().err


class TestInitiateExchangeCommand:
    def test_returns_zero_on_success(self, capsys):
        context = AuthenticatedCommandContext(
            domain="truveta.com",
            api_url="https://api.truveta.com/openlink",
            storage_domain="truveta.com",
            credentials=_fake_creds(),
        )

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.resolve_authenticated_context",
                return_value=context,
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
            ) as mock_build,
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value=Path("/path/to/config"),
            ) as mock_write,
        ):
            result = _initiate_exchange(_exchange_args())

        assert result == 0
        mock_build.assert_called_once_with(
            "truveta.com",
            _make_server_response(),
            _sample_keypair()[1],
            _sample_keypair()[0],
        )
        mock_write.assert_called_once_with("truveta.com", {"payload": {"test": "data"}})
        assert "Exchange config written to:" in capsys.readouterr().out

    def test_uses_localhost_api_in_local_dev(self):
        context = AuthenticatedCommandContext(
            domain="dev.truveta-int.com",
            api_url=LOCAL_API_URL,
            storage_domain="localhost-18080",
            credentials=_fake_creds(),
        )

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.resolve_authenticated_context",
                return_value=context,
            ),
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
            ) as mock_write,
        ):
            result = _initiate_exchange(_exchange_args(local_dev=True))

        assert result == 0
        mock_exchange.assert_called_once_with(
            LOCAL_API_URL,
            _sample_keypair()[1],
            "acc_token",
            timeout_seconds=180,
        )
        mock_write.assert_called_once_with(
            "localhost-18080", {"payload": {"test": "data"}}
        )

    def test_requires_login_session_when_context_resolution_fails(self, capsys):
        with patch(
            "openlinktoken_ext_truveta.commands.initiate_exchange.resolve_authenticated_context",
            side_effect=SessionResolutionError(
                "No login session found. Please run 'olt truveta login' first."
            ),
        ):
            result = _initiate_exchange(_exchange_args())

        assert result == 1
        assert "olt truveta login" in capsys.readouterr().err

    def test_returns_one_on_key_management_error(self, capsys):
        from openlinktoken_ext_truveta.exchange.key_management import KeyManagementError

        context = AuthenticatedCommandContext(
            domain="truveta.com",
            api_url="https://api.truveta.com/openlink",
            storage_domain="truveta.com",
            credentials=_fake_creds(),
        )

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.resolve_authenticated_context",
                return_value=context,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                side_effect=KeyManagementError("key generation failed"),
            ),
        ):
            result = _initiate_exchange(_exchange_args())

        assert result == 1
        assert "Key management failed" in capsys.readouterr().err
