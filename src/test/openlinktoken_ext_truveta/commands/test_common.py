"""
Copyright (c) Truveta. All rights reserved.

Unit tests for common command URL resolution helpers.
"""

import argparse

from openlinktoken_ext_truveta.auth import DEFAULT_DOMAIN_URL
from openlinktoken_ext_truveta.commands.common import (
    DEFAULT_LOCAL_DEV_API_URL,
    resolve_api_url,
    resolve_auth_url,
)


def _args(
    *,
    local_dev: bool = False,
    auth_domain: str | None = None,
    domain: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        local_dev=local_dev,
        auth_domain=auth_domain,
        domain=domain,
    )


class TestCommonResolution:
    def test_default_local_dev_api_url_is_openlink_service_port(self):
        assert DEFAULT_LOCAL_DEV_API_URL == "http://localhost:18080"

    def test_resolve_api_url_uses_domain_arg_for_login(self):
        resolved = resolve_api_url(_args(domain="https://api.example.com"))

        assert resolved == "https://api.example.com"

    def test_resolve_api_url_falls_back_to_default_when_no_domain(self):
        resolved = resolve_api_url(_args())

        assert resolved == DEFAULT_DOMAIN_URL

    def test_resolve_api_url_ignores_trv_api_domain_env(self, monkeypatch):
        monkeypatch.setenv("TRV_API_DOMAIN", "https://should-be-ignored.example.com")

        resolved = resolve_api_url(_args())

        assert resolved == DEFAULT_DOMAIN_URL

    def test_resolve_auth_url_ignores_deprecated_trv_auth_domain_env(self, monkeypatch):
        monkeypatch.setenv("TRV_AUTH_DOMAIN", "https://deprecated.example.com")

        resolved = resolve_auth_url(_args())

        assert resolved == DEFAULT_DOMAIN_URL

    def test_resolve_auth_url_prefers_explicit_auth_domain(self):
        resolved = resolve_auth_url(_args(auth_domain="https://auth.example.com"))

        assert resolved == "https://auth.example.com"
