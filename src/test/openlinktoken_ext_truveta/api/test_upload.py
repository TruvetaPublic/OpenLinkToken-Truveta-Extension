"""
Copyright (c) Truveta. All rights reserved.

Unit tests for upload API client behavior.
"""

from unittest.mock import MagicMock, patch

import pytest
from openlinktoken_ext_truveta.api.upload import (
    UploadAPIError,
    call_upload_endpoint,
)


def _make_response(status_code: int, json_payload=None, json_side_effect=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_side_effect is not None:
        response.json.side_effect = json_side_effect
    else:
        response.json.return_value = json_payload if json_payload is not None else {}
    return response


class TestCallUploadEndpoint:
    def test_returns_payload_when_202_json_present(self):
        payload = {"uploadReferenceId": "u-123"}
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(202, json_payload=payload)

            result = call_upload_endpoint(
                "http://localhost:8080",
                "token",
                "ex-123",
                {"dataFile": ("f.csv", b"x", "application/octet-stream")},
            )

        assert result == payload

    def test_returns_empty_payload_when_202_has_no_json_body(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(
                202,
                json_side_effect=ValueError("No JSON object could be decoded"),
                text="",
            )

            result = call_upload_endpoint(
                "http://localhost:8080",
                "token",
                "ex-123",
                {"dataFile": ("f.csv", b"x", "application/octet-stream")},
            )

        assert result == {}

    def test_ssl_error_triggers_probe_and_uses_ssl_drop_message(self):
        import requests as req

        ssl_error = req.exceptions.SSLError("EOF occurred in violation of protocol")
        probe_response = _make_response(
            400, text="File is required and cannot be empty"
        )

        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.side_effect = [ssl_error, probe_response]

            with pytest.raises(UploadAPIError, match="initiate-exchange"):
                call_upload_endpoint(
                    "https://api.truveta.com/openlink",
                    "token",
                    "ex-123",
                    {"dataFile": ("f.csv", b"x", "application/octet-stream")},
                )

    def test_non_202_error_includes_resolved_upload_url(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(413, text="request too large")

            with pytest.raises(
                UploadAPIError,
                match="https://api.truveta.com/openlink/v1/uploads/ex-123",
            ):
                call_upload_endpoint(
                    "https://api.truveta.com/openlink",
                    "token",
                    "ex-123",
                    {"dataFile": ("f.csv", b"x", "application/octet-stream")},
                )
