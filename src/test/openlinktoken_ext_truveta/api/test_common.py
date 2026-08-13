"""
Copyright (c) Truveta. All rights reserved.

Unit tests for api/common.py shared helpers.
"""

from unittest.mock import MagicMock, patch

from openlinktoken_ext_truveta.api.common import (
    extract_error_body,
    format_api_error,
    probe_for_http_status,
    ssl_drop_message,
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


class TestExtractErrorBody:
    def test_returns_error_key_from_json(self):
        response = _make_response(400, json_payload={"error": "Bad request"})
        assert extract_error_body(response) == "Bad request"

    def test_falls_back_to_text_when_no_error_key(self):
        response = _make_response(400, json_payload={"message": "Bad"}, text="Bad")
        assert extract_error_body(response) == "Bad"

    def test_falls_back_to_text_when_json_raises(self):
        response = _make_response(
            400, json_side_effect=ValueError("no JSON"), text="raw error"
        )
        assert extract_error_body(response) == "raw error"

    def test_falls_back_to_text_when_json_is_list(self):
        response = _make_response(400, json_payload=["error"], text="raw error")
        assert extract_error_body(response) == "raw error"

    def test_preserves_typed_upload_error_details(self):
        response = _make_response(
            400,
            json_payload={
                "error": "Incomplete upload",
                "code": "IncompleteUploadSession",
                "missingChunks": [2, 3],
            },
        )
        assert extract_error_body(response) == (
            "Incomplete upload (code=IncompleteUploadSession, missingChunks=[2, 3])"
        )


class TestFormatApiError:
    def test_uses_operation_in_message(self):
        msg = format_api_error(
            "https://api.example.com/v1/uploads/ex-1", "timeout", operation="Upload"
        )
        assert (
            msg == "Upload failed for https://api.example.com/v1/uploads/ex-1: timeout"
        )

    def test_defaults_to_api_call_operation(self):
        msg = format_api_error("https://api.example.com/v1/exchange", "SSL error")
        assert (
            msg == "API call failed for https://api.example.com/v1/exchange: SSL error"
        )


class TestProbeForHttpStatus:
    def test_returns_none_when_probe_succeeds_200(self):
        with patch("openlinktoken_ext_truveta.api.common.requests.post") as mock_post:
            mock_post.return_value = _make_response(200)
            result = probe_for_http_status(
                "https://api.example.com/v1/upload", "token", 30
            )
        assert result is None

    def test_returns_none_when_probe_succeeds_202(self):
        with patch("openlinktoken_ext_truveta.api.common.requests.post") as mock_post:
            mock_post.return_value = _make_response(202)
            result = probe_for_http_status(
                "https://api.example.com/v1/upload", "token", 30
            )
        assert result is None

    def test_returns_status_string_when_probe_gets_401(self):
        with patch("openlinktoken_ext_truveta.api.common.requests.post") as mock_post:
            mock_post.return_value = _make_response(401, text="Unauthorized")
            result = probe_for_http_status(
                "https://api.example.com/v1/upload", "token", 30
            )
        assert result is not None
        assert result.startswith("401")

    def test_returns_none_when_probe_itself_raises(self):
        with patch("openlinktoken_ext_truveta.api.common.requests.post") as mock_post:
            mock_post.side_effect = Exception("Connection refused")
            result = probe_for_http_status(
                "https://api.example.com/v1/upload", "token", 30
            )
        assert result is None

    def test_sends_multipart_when_probe_files_provided(self):
        with patch("openlinktoken_ext_truveta.api.common.requests.post") as mock_post:
            mock_post.return_value = _make_response(202)
            probe_for_http_status(
                "https://api.example.com/v1/upload",
                "token",
                30,
                probe_files={
                    "dataFile": ("probe.csv", b"", "application/octet-stream")
                },
            )
        call_kwargs = mock_post.call_args[1]
        assert "files" in call_kwargs

    def test_sends_json_when_probe_json_provided(self):
        with patch("openlinktoken_ext_truveta.api.common.requests.post") as mock_post:
            mock_post.return_value = _make_response(200)
            probe_for_http_status(
                "https://api.example.com/v1/exchange",
                "token",
                30,
                probe_json={},
            )
        call_kwargs = mock_post.call_args[1]
        assert "json" in call_kwargs

    def test_includes_bearer_token_in_headers(self):
        with patch("openlinktoken_ext_truveta.api.common.requests.post") as mock_post:
            mock_post.return_value = _make_response(202)
            probe_for_http_status("https://api.example.com/v1/upload", "my-token", 30)
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer my-token"


class TestSslDropMessage:
    _HINT = "try 'olt truveta initiate-exchange'"

    def test_401_surfaces_auth_error_with_reauth_hint(self):
        msg = ssl_drop_message("401 - Unauthorized", generic_hint=self._HINT)
        assert "Authentication failed" in msg
        assert "olt truveta login" in msg

    def test_403_surfaces_auth_error_with_reauth_hint(self):
        msg = ssl_drop_message("403 - Forbidden", generic_hint=self._HINT)
        assert "Authentication failed" in msg
        assert "olt truveta login" in msg

    def test_409_surfaces_conflict_detail_directly(self):
        msg = ssl_drop_message(
            "409 - An upload has already been completed for this exchange.",
            generic_hint=self._HINT,
        )
        assert "409" in msg
        assert "already been completed" in msg

    def test_400_probe_artifact_falls_back_to_generic_hint(self):
        msg = ssl_drop_message(
            "400 - File is required and cannot be empty",
            generic_hint=self._HINT,
        )
        assert "initiate-exchange" in msg
        assert "400" not in msg

    def test_none_probe_falls_back_to_generic_hint(self):
        msg = ssl_drop_message(None, generic_hint=self._HINT)
        assert "initiate-exchange" in msg

    def test_custom_generic_hint_is_used(self):
        hint = "check your network connectivity"
        msg = ssl_drop_message(None, generic_hint=hint)
        assert hint in msg
