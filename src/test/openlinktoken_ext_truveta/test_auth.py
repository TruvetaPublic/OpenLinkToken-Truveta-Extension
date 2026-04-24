"""
Copyright (c) Truveta. All rights reserved.

Unit tests for auth.py — domain extraction, client ID lookup, JWT decoding,
cache read/write, and ensure_auth.
"""

import base64
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from openlinktoken_ext_truveta.auth import (
    AuthError,
    Credentials,
    _cache_path,
    _extract_domain,
    _get_audience,
    _get_client_id,
    _is_token_valid,
    _read_cache,
    _write_cache,
    clear_session_file,
    decode_jwt_payload,
    ensure_auth,
    get_auth_headers,
    read_session_api_url,
    write_session_api_url,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jwt(payload: dict) -> str:
    """Build a fake JWT with the given payload (no real signature)."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesig"


def _future_jwt(**extra) -> str:
    return _make_jwt({"exp": int(time.time()) + 3600, **extra})


def _expired_jwt() -> str:
    return _make_jwt({"exp": int(time.time()) - 10})


# ---------------------------------------------------------------------------
# _extract_domain
# ---------------------------------------------------------------------------


class TestExtractDomain:
    def test_api_url_dev(self):
        assert (
            _extract_domain("https://api.dev.truveta-int.com") == "dev.truveta-int.com"
        )

    def test_api_url_int(self):
        assert _extract_domain("https://api.truveta-int.com") == "truveta-int.com"

    def test_api_url_prod(self):
        assert _extract_domain("https://api.truveta.com") == "truveta.com"

    def test_login_url_dev(self):
        assert (
            _extract_domain("https://login.dev.truveta-int.com")
            == "dev.truveta-int.com"
        )

    def test_plain_domain_url(self):
        assert _extract_domain("https://dev.truveta-int.com") == "dev.truveta-int.com"

    def test_invalid_url_raises(self):
        with pytest.raises(AuthError, match="Invalid URL format"):
            _extract_domain("https://not-a-valid-url.com")


# ---------------------------------------------------------------------------
# _get_client_id
# ---------------------------------------------------------------------------


class TestGetClientId:
    def test_known_domains_return_ids(self):
        assert _get_client_id("truveta.com") == "MV87rfAh0Qy5ExTXZIDKssdgoYUVBIbY"
        assert _get_client_id("truveta-int.com") == "Ouw9CrFQy8nakVDmgdINXeCZ0iB1laxw"
        assert (
            _get_client_id("dev.truveta-int.com") == "NLEN3QJPPoIPHA6bQ6XUM1qCfDmz5RrO"
        )

    def test_unknown_domain_raises(self):
        with pytest.raises(AuthError, match="Unknown domain"):
            _get_client_id("unknown.example.com")


# ---------------------------------------------------------------------------
# _get_audience
# ---------------------------------------------------------------------------


class TestGetAudience:
    def test_dev_domain_returns_audience(self):
        assert (
            _get_audience("dev.truveta-int.com")
            == "https://api.dev.truveta-int.com/openlink"
        )

    def test_unknown_domain_raises(self):
        with pytest.raises(AuthError, match="Unknown domain"):
            _get_audience("unknown.example.com")


# ---------------------------------------------------------------------------
# decode_jwt_payload
# ---------------------------------------------------------------------------


class TestDecodeJwtPayload:
    def test_decodes_payload(self):
        token = _make_jwt({"sub": "user123", "email": "a@b.com"})
        payload = decode_jwt_payload(token)
        assert payload["sub"] == "user123"
        assert payload["email"] == "a@b.com"

    def test_malformed_jwt_raises(self):
        with pytest.raises(AuthError, match="Malformed JWT"):
            decode_jwt_payload("onlytwoparts.here")


# ---------------------------------------------------------------------------
# _is_token_valid
# ---------------------------------------------------------------------------


class TestIsTokenValid:
    def test_future_exp_is_valid(self):
        assert _is_token_valid(_future_jwt()) is True

    def test_expired_token_is_invalid(self):
        assert _is_token_valid(_expired_jwt()) is False

    def test_missing_exp_is_invalid(self):
        assert _is_token_valid(_make_jwt({})) is False

    def test_malformed_token_is_invalid(self):
        assert _is_token_valid("not.a.jwt") is False

    def test_five_minute_buffer_applied(self):
        # Token that expires in 4 minutes (< 300s buffer) should be treated as expired
        near_expiry = _make_jwt({"exp": int(time.time()) + 240})
        assert _is_token_valid(near_expiry) is False


# ---------------------------------------------------------------------------
# _cache_path
# ---------------------------------------------------------------------------


class TestCachePath:
    def test_path_structure(self):
        path = _cache_path("truveta.com")
        assert (
            path
            == Path.home()
            / ".openlinktoken"
            / "truveta"
            / "truveta.com"
            / "credentials.json"
        )


# ---------------------------------------------------------------------------
# _read_cache / _write_cache
# ---------------------------------------------------------------------------


class TestCacheReadWrite:
    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        creds = Credentials(
            access_token=_future_jwt(), id_token=_future_jwt(email="u@t.com")
        )

        _write_cache("truveta.com", creds)
        result = _read_cache("truveta.com")

        assert result is not None
        assert result.access_token == creds.access_token
        assert result.id_token == creds.id_token

    def test_missing_file_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        assert _read_cache("truveta.com") is None

    def test_expired_tokens_delete_cache_and_return_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        creds = Credentials(access_token=_expired_jwt(), id_token=_expired_jwt())
        _write_cache("truveta.com", creds)

        result = _read_cache("truveta.com")

        assert result is None
        assert not _cache_path("truveta.com").exists()

    def test_malformed_json_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        path = (
            tmp_path / ".openlinktoken" / "truveta" / "truveta.com" / "credentials.json"
        )
        path.parent.mkdir(parents=True)
        path.write_text("not json")

        assert _read_cache("truveta.com") is None


class TestSessionReadWrite:
    def test_write_and_read_session_api_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )

        write_session_api_url("https://api.dev.truveta-int.com/")

        assert read_session_api_url() == "https://api.dev.truveta-int.com"

    def test_read_session_api_url_returns_none_when_missing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )

        assert read_session_api_url() is None

    def test_clear_session_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        write_session_api_url("https://api.truveta.com")

        clear_session_file()

        assert read_session_api_url() is None


# ---------------------------------------------------------------------------
# ensure_auth
# ---------------------------------------------------------------------------


class TestEnsureAuth:
    def test_returns_cached_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        creds = Credentials(
            access_token=_future_jwt(), id_token=_future_jwt(email="u@t.com")
        )
        _write_cache("truveta.com", creds)

        result = ensure_auth("https://api.truveta.com")

        assert result.access_token == creds.access_token

    def test_unknown_domain_raises(self):
        with pytest.raises(AuthError, match="Unknown domain"):
            ensure_auth("https://api.unknown.example.com")

    def test_runs_device_flow_when_no_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        fake_creds = Credentials(
            access_token=_future_jwt(), id_token=_future_jwt(email="u@t.com")
        )

        with patch(
            "openlinktoken_ext_truveta.auth._device_code_flow", return_value=fake_creds
        ) as mock_flow:
            result = ensure_auth("https://api.truveta.com")

        mock_flow.assert_called_once()
        assert result.access_token == fake_creds.access_token

    def test_caches_result_of_device_flow(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.auth.Path.home", lambda: tmp_path
        )
        fake_creds = Credentials(
            access_token=_future_jwt(), id_token=_future_jwt(email="u@t.com")
        )

        with patch(
            "openlinktoken_ext_truveta.auth._device_code_flow", return_value=fake_creds
        ):
            ensure_auth("https://api.truveta.com")

        assert _cache_path("truveta.com").exists()


# ---------------------------------------------------------------------------
# get_auth_headers
# ---------------------------------------------------------------------------


class TestGetAuthHeaders:
    def test_headers_contain_required_keys(self):
        creds = Credentials(access_token="acc", id_token="id")
        headers = get_auth_headers(creds)

        assert headers["Authorization"] == "Bearer acc"
        assert headers["x-access-token"] == "acc"
        assert headers["x-truveta-id"] == "id"
        assert headers["Content-Type"] == "application/json"
