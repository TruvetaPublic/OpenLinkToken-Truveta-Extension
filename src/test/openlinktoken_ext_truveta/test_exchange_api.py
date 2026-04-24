"""
Copyright (c) Truveta. All rights reserved.

Unit tests for exchange_api.py — API endpoint calls for exchange negotiation.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from openlinktoken_ext_truveta.api.exchange import (
    ExchangeAPIError,
    call_exchange_endpoint,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_EC_KEY = generate_private_key(SECP256R1())
_PUBLIC_KEY_PEM = (
    _EC_KEY.public_key()
    .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    .decode()
)


def _make_mock_response(status_code: int, json_data: dict | None = None):
    """Create a mock requests response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            f"HTTP {status_code}"
        )
    else:
        response.raise_for_status.return_value = None
    return response


def _sample_public_key(label: str = "test") -> str:
    return _PUBLIC_KEY_PEM


# ---------------------------------------------------------------------------
# call_exchange_endpoint
# ---------------------------------------------------------------------------


class TestCallExchangeEndpoint:
    def test_successful_call_returns_response(self):
        public_pem = _sample_public_key()
        api_response = {
            "encryptedHashingKey": "encrypted-secret",
            "truvetaPublicKey": "server-spki-b64",
        }
        expected_normalized = {
            "exchangeName": "",
            "exchangeId": "derived-acb41b3ccedbcae9b7b05e2a62ebdbfb",
            "hashingSecret": "encrypted-secret",
            "hashingSecretEncoding": "base64",
            "serverPublicKey": "server-spki-b64",
        }

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, api_response)

            response = call_exchange_endpoint(
                "https://api.test.com", public_pem, "test-token"
            )

        assert response == expected_normalized

    def test_preserves_exchange_id_when_server_provides_one(self):
        public_pem = _sample_public_key()
        api_response = {
            "exchangeName": "exchange-a",
            "exchangeId": "ex-123",
            "encryptedHashingKey": "encrypted-secret",
            "truvetaPublicKey": "server-spki-b64",
        }

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, api_response)

            response = call_exchange_endpoint(
                "https://api.test.com", public_pem, "test-token"
            )

        assert response["exchangeId"] == "ex-123"

    def test_post_request_to_correct_url(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, {})

            call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.test.com/v1/exchange"

    def test_includes_bearer_token_in_headers(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, {})

            call_exchange_endpoint(
                "https://api.test.com", public_pem, "my-access-token"
            )

        call_kwargs = mock_post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["Authorization"] == "Bearer my-access-token"

    def test_includes_content_type_json_in_headers(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, {})

            call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

        call_kwargs = mock_post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["Content-Type"] == "application/json"

    def test_sends_public_key_in_request_body(self):
        public_pem = _sample_public_key()

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, {})

            call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

        call_kwargs = mock_post.call_args[1]
        json_body = call_kwargs["json"]
        assert not json_body["publicKey"].startswith("-----")
        import base64 as _b64

        _b64.b64decode(json_body["publicKey"])

    def test_uses_30_second_timeout(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, {})

            call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["timeout"] == 30

    def test_raises_http_error_on_400(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(400)

            with pytest.raises(requests.HTTPError):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_http_error_on_401(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(401)

            with pytest.raises(requests.HTTPError):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_http_error_on_403(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(403)

            with pytest.raises(requests.HTTPError):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_http_error_on_404(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(404)

            with pytest.raises(requests.HTTPError):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_http_error_on_500(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(500)

            with pytest.raises(requests.HTTPError):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_http_error_on_502(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(502)

            with pytest.raises(requests.HTTPError):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_exchange_api_error_on_connection_error(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection failed")

            with pytest.raises(
                ExchangeAPIError, match="Failed to call exchange endpoint"
            ):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_exchange_api_error_on_timeout(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Request timed out")

            with pytest.raises(
                ExchangeAPIError, match="Failed to call exchange endpoint"
            ):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_raises_exchange_api_error_on_request_exception(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("Generic error")

            with pytest.raises(
                ExchangeAPIError, match="Failed to call exchange endpoint"
            ):
                call_exchange_endpoint("https://api.test.com", public_pem, "test-token")

    def test_handles_trailing_slash_in_domain_url(self):
        public_pem = _sample_public_key("sender")

        with patch("openlinktoken_ext_truveta.api.exchange.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200, {})

            call_exchange_endpoint("https://api.test.com/", public_pem, "test-token")

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.test.com/v1/exchange"
