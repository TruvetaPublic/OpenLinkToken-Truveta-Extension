"""
Copyright (c) Truveta. All rights reserved.

Unit tests for common command domain resolution helpers.
"""

import argparse
from unittest.mock import patch

from openlinktoken_ext_truveta.auth import Credentials
from openlinktoken_ext_truveta.commands.common import (
    DEFAULT_TIMEOUT_SECONDS,
    LOCAL_API_URL,
    LOCAL_DEV_TIMEOUT_SECONDS,
    AuthenticatedCommandContext,
    SessionResolutionError,
    resolve_api_base_url,
    resolve_authenticated_context,
    resolve_domain,
    resolve_timeout_seconds,
)
from openlinktoken_ext_truveta.domain import DEFAULT_DOMAIN


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
    def test_local_api_url_is_openlink_service_port(self):
        assert LOCAL_API_URL == "http://localhost:18080"

    def test_resolve_domain_uses_local_dev_auth_domain(self):
        resolved = resolve_domain(_args(local_dev=True))

        assert resolved == "dev.truveta-int.com"

    def test_resolve_domain_uses_explicit_domain_arg(self):
        resolved = resolve_domain(_args(domain="truveta-int.com"))

        assert resolved == "truveta-int.com"

    def test_resolve_domain_uses_trv_domain_env(self, monkeypatch):
        monkeypatch.setenv("OLT_TRV_DOMAIN", "dev.truveta-int.com")

        resolved = resolve_domain(_args())

        assert resolved == "dev.truveta-int.com"

    def test_resolve_domain_uses_session_domain(self, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.commands.common.read_session_domain",
            lambda: "dev.truveta-int.com",
        )

        resolved = resolve_domain(_args())

        assert resolved == "dev.truveta-int.com"

    def test_resolve_domain_defaults_for_login(self):
        resolved = resolve_domain(_args(), allow_default=True)

        assert resolved == DEFAULT_DOMAIN

    def test_resolve_domain_raises_without_session_for_non_login_command(self):
        with patch(
            "openlinktoken_ext_truveta.commands.common.read_session_domain",
            return_value=None,
        ):
            try:
                resolve_domain(_args())
            except SessionResolutionError as exc:
                assert "No login session found" in str(exc)
            else:
                raise AssertionError("Expected SessionResolutionError")

    def test_resolve_api_base_url_uses_local_dev_url(self):
        resolved = resolve_api_base_url(_args(local_dev=True), "dev.truveta-int.com")

        assert resolved == LOCAL_API_URL

    def test_resolve_api_base_url_derives_hosted_url_from_domain(self):
        resolved = resolve_api_base_url(_args(), "dev.truveta-int.com")

        assert resolved == "https://api.dev.truveta-int.com/openlink"

    def test_resolve_authenticated_context_uses_hosted_domain_and_cached_auth(
        self, monkeypatch
    ):
        expected_credentials = Credentials(access_token="access", id_token="id")
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.commands.common.read_session_domain",
            lambda: "dev.truveta-int.com",
        )
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.commands.common.ensure_auth",
            lambda domain, cached_only: expected_credentials,
        )

        resolved = resolve_authenticated_context(_args())

        assert resolved == AuthenticatedCommandContext(
            domain="dev.truveta-int.com",
            api_url="https://api.dev.truveta-int.com/openlink",
            storage_domain="dev.truveta-int.com",
            credentials=expected_credentials,
        )

    def test_resolve_authenticated_context_uses_local_api_and_dev_auth(
        self, monkeypatch
    ):
        expected_credentials = Credentials(access_token="access", id_token="id")
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.commands.common.ensure_auth",
            lambda domain, cached_only: expected_credentials,
        )

        resolved = resolve_authenticated_context(_args(local_dev=True))

        assert resolved == AuthenticatedCommandContext(
            domain="dev.truveta-int.com",
            api_url="http://localhost:18080",
            storage_domain="localhost-18080",
            credentials=expected_credentials,
        )

    def test_resolve_timeout_seconds_uses_default_in_non_local_dev(self):
        resolved = resolve_timeout_seconds(_args(local_dev=False))

        assert resolved == DEFAULT_TIMEOUT_SECONDS

    def test_resolve_timeout_seconds_uses_local_dev_value_when_enabled(self):
        resolved = resolve_timeout_seconds(_args(local_dev=True))

        assert resolved == LOCAL_DEV_TIMEOUT_SECONDS

    def test_resolve_timeout_seconds_honors_explicit_override(self):
        resolved = resolve_timeout_seconds(_args(local_dev=False), timeout_seconds=90)

        assert resolved == 90
