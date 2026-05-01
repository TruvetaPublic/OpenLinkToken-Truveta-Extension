"""
Copyright (c) Truveta. All rights reserved.

Unit tests for common command URL resolution helpers.
"""

import argparse
from unittest.mock import patch

from openlinktoken_ext_truveta.auth import DEFAULT_DOMAIN_URL, get_auth_domain_url
from openlinktoken_ext_truveta.commands.common import (
    DEFAULT_LOCAL_DEV_API_URL,
    DEFAULT_TIMEOUT_SECONDS,
    LOCAL_DEV_TIMEOUT_SECONDS,
    resolve_api_url,
    resolve_auth_url,
    resolve_timeout_seconds,
)


def _args(
    *,
    local_dev: bool = False,
    domain: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        local_dev=local_dev,
        domain=domain,
    )


class TestCommonResolution:
    def test_default_local_dev_api_url_is_openlink_service_port(self):
        assert DEFAULT_LOCAL_DEV_API_URL == "http://localhost:18080"

    def test_resolve_api_url_uses_domain_arg_for_login(self):
        resolved = resolve_api_url(_args(domain="https://api.example.com"))

        assert resolved == "https://api.example.com"

    def test_resolve_api_url_falls_back_to_default_when_no_domain(self):
        with patch(
            "openlinktoken_ext_truveta.commands.common.read_session_auth_url",
            return_value=None,
        ):
            resolved = resolve_api_url(_args())

        assert resolved == DEFAULT_DOMAIN_URL

    def test_resolve_api_url_ignores_trv_api_domain_env(self, monkeypatch):
        monkeypatch.setenv("TRV_API_DOMAIN", "https://should-be-ignored.example.com")

        with patch(
            "openlinktoken_ext_truveta.commands.common.read_session_auth_url",
            return_value=None,
        ):
            resolved = resolve_api_url(_args())

        assert resolved == DEFAULT_DOMAIN_URL

    def test_resolve_api_url_derives_api_domain_from_session_auth_url(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.commands.common.read_session_auth_url",
            lambda: "https://login.dev.truveta-int.com",
        )

        resolved = resolve_api_url(_args())

        assert resolved == "https://api.dev.truveta-int.com"

    def test_resolve_auth_url_ignores_deprecated_trv_auth_domain_env(self, monkeypatch):
        monkeypatch.setenv("TRV_AUTH_DOMAIN", "https://deprecated.example.com")

        with patch(
            "openlinktoken_ext_truveta.commands.common.read_session_auth_url",
            return_value=None,
        ):
            resolved = resolve_auth_url(_args())

        # Should derive auth domain from default API domain, not use env var.
        assert resolved == get_auth_domain_url("truveta.com")

    def test_resolve_auth_url_derives_auth_domain_from_api_domain(self):
        resolved = resolve_auth_url(_args(domain="https://api.example.com"))

        # Should derive the auth domain from the API domain (extract domain and make login URL).
        assert resolved == "https://login.example.com"

    def test_resolve_auth_url_prefers_local_dev_over_session(self, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.commands.common.read_session_auth_url",
            lambda: "https://login.dev.truveta-int.com",
        )

        resolved = resolve_auth_url(_args(local_dev=True))

        # local_dev always takes precedence over any saved session.
        assert resolved == DEFAULT_LOCAL_DEV_API_URL

    def test_resolve_auth_url_uses_stored_session_auth_url(self, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.commands.common.read_session_auth_url",
            lambda: "https://login.dev.truveta-int.com",
        )

        resolved = resolve_auth_url(_args())

        assert resolved == "https://login.dev.truveta-int.com"

    def test_resolve_timeout_seconds_uses_default_in_non_local_dev(self):
        resolved = resolve_timeout_seconds(_args(local_dev=False))

        assert resolved == DEFAULT_TIMEOUT_SECONDS

    def test_resolve_timeout_seconds_uses_local_dev_value_when_enabled(self):
        resolved = resolve_timeout_seconds(_args(local_dev=True))

        assert resolved == LOCAL_DEV_TIMEOUT_SECONDS

    def test_resolve_timeout_seconds_honors_explicit_override(self):
        resolved = resolve_timeout_seconds(_args(local_dev=False), timeout_seconds=90)

        assert resolved == 90
