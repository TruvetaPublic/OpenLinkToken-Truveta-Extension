"""
Copyright (c) Truveta. All rights reserved.

Unit tests for upload API client behavior.
"""

from unittest.mock import MagicMock, patch

from openlinktoken_ext_truveta.api.upload import call_upload_endpoint


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
