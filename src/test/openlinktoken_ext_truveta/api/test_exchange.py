"""
Copyright (c) Truveta. All rights reserved.

Unit tests for exchange_api.py — API endpoint calls for exchange negotiation.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)
from openlinktoken_ext_truveta.api.exchange import (
    ExchangeAPIError,
    call_exchange_endpoint,
)
from openlinktoken_ext_truveta.openlink_token_service_client.types import (
    ExchangeResponse,
)

_EC_KEY = generate_private_key(SECP256R1())
_PUBLIC_KEY_PEM = (
    _EC_KEY.public_key()
    .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    .decode()
)


def _make_exchange_response(**overrides) -> ExchangeResponse:
    alias_to_field = {
        "exchangeId": "exchange_id",
        "encryptedHashingKey": "encrypted_hashing_key",
        "truvetaPublicKey": "truveta_public_key",
        "encryptedRotationIv": "encrypted_rotation_iv",
        "numRotations": "num_rotations",
        "binWidth": "bin_width",
        "dimensionBias": "dimension_bias",
    }
    defaults = {
        "exchange_id": "ex-123",
        "encrypted_hashing_key": "encrypted-secret",
        "truveta_public_key": "server-spki-b64",
        "encrypted_rotation_iv": "encrypted-iv",
        "num_rotations": None,
        "bin_width": None,
        "dimension_bias": None,
    }
    for key, value in overrides.items():
        defaults[alias_to_field.get(key, key)] = value
    return ExchangeResponse.model_construct(**defaults)


def _make_http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=request, response=response
    )


def _sample_public_key() -> str:
    return _PUBLIC_KEY_PEM


class TestCallExchangeEndpoint:
    def test_successful_call_returns_response(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response(dimensionBias=None)
        expected = {
            "exchangeName": "",
            "exchangeId": "ex-123",
            "hashingSecret": "encrypted-secret",
            "serverPublicKey": "server-spki-b64",
            "rotationCount": 50,
            "binWidth": 0.05,
            "dimensionBias": [],
            "encryptedRotationIv": "encrypted-iv",
        }

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ):
            response = call_exchange_endpoint(
                "https://api.test.com/openlink", public_pem, "test-token"
            )

        assert response == expected

    def test_maps_rotation_fields_when_present(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response(
            exchangeId="ex-456",
            encryptedRotationIv="encrypted-iv-data",
            numRotations=50,
            binWidth=0.1,
            dimensionBias=[0.01, -0.02, 0.03],
        )

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ):
            response = call_exchange_endpoint(
                "https://api.test.com/openlink", public_pem, "test-token"
            )

        assert response["encryptedRotationIv"] == "encrypted-iv-data"
        assert response["rotationCount"] == 50
        assert response["binWidth"] == 0.1
        assert response["dimensionBias"] == [0.01, -0.02, 0.03]

    def test_omits_encrypted_rotation_iv_when_empty(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response(encryptedRotationIv="")

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ):
            response = call_exchange_endpoint(
                "https://api.test.com/openlink", public_pem, "test-token"
            )

        assert response["rotationCount"] == 50
        assert response["binWidth"] == 0.05
        assert response["dimensionBias"] == []
        assert "encryptedRotationIv" not in response

    def test_applies_defaults_for_null_rotation_fields(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response(
            exchangeId="ex-789",
            encryptedHashingKey="encrypted-secret",
            truvetaPublicKey="server-spki-b64",
            numRotations=None,
            binWidth=None,
            dimensionBias=None,
            encryptedRotationIv=None,
        )

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ):
            response = call_exchange_endpoint(
                "https://api.test.com/openlink", public_pem, "test-token"
            )

        assert response["rotationCount"] == 50
        assert response["binWidth"] == 0.05
        assert response["dimensionBias"] == []

    def test_preserves_exchange_id_when_server_provides_one(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response(exchangeId="ex-123")

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ):
            response = call_exchange_endpoint(
                "https://api.test.com/openlink", public_pem, "test-token"
            )

        assert response["exchangeId"] == "ex-123"

    def test_passes_correct_base_url_and_credentials(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ) as mock_async:
            call_exchange_endpoint(
                "https://api.truveta.com/openlink", public_pem, "my-access-token"
            )

        call_args = mock_async.call_args
        assert call_args[0][0] == "https://api.truveta.com/openlink"
        assert call_args[0][2] == "my-access-token"

    def test_strips_trailing_slash_from_base_url(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ) as mock_async:
            call_exchange_endpoint(
                "https://api.truveta.com/openlink/", public_pem, "test-token"
            )

        call_args = mock_async.call_args
        assert call_args[0][0] == "https://api.truveta.com/openlink"

    def test_uses_30_second_timeout_for_non_localhost(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ) as mock_async:
            call_exchange_endpoint(
                "https://api.test.com/openlink", public_pem, "test-token"
            )

        call_args = mock_async.call_args
        assert call_args[0][3] == 30

    def test_uses_custom_timeout_when_provided(self):
        public_pem = _sample_public_key()
        mock_response = _make_exchange_response()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(return_value=mock_response),
        ) as mock_async:
            call_exchange_endpoint(
                "https://api.test.com/openlink",
                public_pem,
                "test-token",
                timeout_seconds=90,
            )

        call_args = mock_async.call_args
        assert call_args[0][3] == 90

    def test_raises_http_error_on_400(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=_make_http_error(400)),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_raises_http_error_on_401(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=_make_http_error(401)),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_raises_http_error_on_403(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=_make_http_error(403)),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_raises_http_error_on_404(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=_make_http_error(404)),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_raises_http_error_on_500(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=_make_http_error(500)),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_raises_http_error_on_502(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=_make_http_error(502)),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_does_not_retry_on_404(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=_make_http_error(404)),
        ) as mock_async:
            with pytest.raises(httpx.HTTPStatusError):
                call_exchange_endpoint(
                    "https://api.truveta.com/openlink", public_pem, "test-token"
                )

        mock_async.assert_called_once()

    def test_raises_exchange_api_error_on_connection_error(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=httpx.ConnectError("Connection failed")),
        ):
            with pytest.raises(ExchangeAPIError, match="Exchange failed for"):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_raises_exchange_api_error_on_timeout(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=httpx.TimeoutException("Request timed out")),
        ):
            with pytest.raises(
                ExchangeAPIError, match="Failed to call exchange endpoint"
            ):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_raises_exchange_api_error_on_generic_exception(self):
        public_pem = _sample_public_key()

        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=RuntimeError("Generic error")),
        ):
            with pytest.raises(
                ExchangeAPIError, match="Failed to call exchange endpoint"
            ):
                call_exchange_endpoint(
                    "https://api.test.com/openlink", public_pem, "test-token"
                )

    def test_ssl_error_with_auth_probe_result_raises_with_auth_hint(self):
        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=httpx.ConnectError("SSL dropped")),
        ):
            with patch(
                "openlinktoken_ext_truveta.api.exchange.probe_for_http_status",
                return_value="401 - Unauthorized",
            ):
                with pytest.raises(ExchangeAPIError, match="Authentication failed"):
                    call_exchange_endpoint(
                        "https://api.truveta.com/openlink",
                        _PUBLIC_KEY_PEM,
                        "test-token",
                    )

    def test_ssl_error_with_no_probe_result_raises_with_generic_hint(self):
        with patch(
            "openlinktoken_ext_truveta.api.exchange._call_exchange_async",
            new=AsyncMock(side_effect=httpx.ConnectError("SSL dropped")),
        ):
            with patch(
                "openlinktoken_ext_truveta.api.exchange.probe_for_http_status",
                return_value=None,
            ):
                with pytest.raises(ExchangeAPIError, match="network connectivity"):
                    call_exchange_endpoint(
                        "https://api.truveta.com/openlink",
                        _PUBLIC_KEY_PEM,
                        "test-token",
                    )
