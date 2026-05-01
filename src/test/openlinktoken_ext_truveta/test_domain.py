"""
Copyright (c) Truveta. All rights reserved.

Unit tests for shared domain helpers and session persistence.
"""

from openlinktoken_ext_truveta.domain import (
    DEFAULT_DOMAIN,
    DomainError,
    get_api_url,
    get_audience,
    get_client_id,
    get_login_url,
    validate_domain,
)


class TestValidateDomain:
    def test_known_domain_is_returned(self):
        assert validate_domain("truveta.com") == "truveta.com"

    def test_unknown_domain_raises(self):
        try:
            validate_domain("example.com")
        except DomainError as exc:
            assert "Unknown domain" in str(exc)
        else:
            raise AssertionError("Expected DomainError")


class TestUrlDerivation:
    def test_default_domain_is_truveta_com(self):
        assert DEFAULT_DOMAIN == "truveta.com"

    def test_get_login_url(self):
        assert (
            get_login_url("dev.truveta-int.com") == "https://login.dev.truveta-int.com"
        )

    def test_get_api_url(self):
        assert (
            get_api_url("dev.truveta-int.com")
            == "https://api.dev.truveta-int.com/openlink"
        )

    def test_get_audience(self):
        assert (
            get_audience("dev.truveta-int.com")
            == "https://api.dev.truveta-int.com/openlink"
        )

    def test_get_client_id(self):
        assert get_client_id("truveta.com") == "MV87rfAh0Qy5ExTXZIDKssdgoYUVBIbY"
