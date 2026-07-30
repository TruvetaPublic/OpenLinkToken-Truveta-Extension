"""
Copyright (c) Truveta. All rights reserved.

Unit tests for upload API client behavior.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from openlinktoken_ext_truveta.api.upload import (
    UploadAPIError,
    call_upload_endpoint,
    finalize_session,
    initialize_session,
    upload_chunk,
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


class TestInitializeSession:
    def test_returns_max_chunk_size_on_201(self):
        payload = {
            "expiresAtUtc": "2026-07-21T12:00:00Z",
            "maxChunkSizeBytes": 8388608,
        }
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(201, json_payload=payload)

            max_chunk_size = initialize_session(
                "http://localhost:8080",
                "token",
                "ex-123",
                "data.csv",
                3,
            )

        assert max_chunk_size == 8388608

    def test_posts_to_correct_url(self):
        payload = {"expiresAtUtc": "2026-07-21T12:00:00Z", "maxChunkSizeBytes": 8388608}
        captured = {}
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(201, json_payload=payload)

            def capture(url, **kwargs):
                captured["url"] = url
                return _make_response(201, json_payload=payload)

            mock_post.side_effect = capture
            initialize_session(
                "https://api.truveta.com/openlink", "token", "ex-123", "f.csv", 1
            )

        assert captured["url"] == "https://api.truveta.com/openlink/v1/uploads/ex-123"

    def test_raises_upload_api_error_on_non_201(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(400, text="exchange not found")

            with pytest.raises(UploadAPIError, match="400"):
                initialize_session(
                    "http://localhost:8080", "token", "ex-123", "f.csv", 1
                )

    def test_raises_on_409_already_completed(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(
                409, text="An upload has already been completed for this exchange."
            )

            with pytest.raises(UploadAPIError, match="409"):
                initialize_session(
                    "http://localhost:8080", "token", "ex-123", "f.csv", 1
                )


class TestUploadChunk:
    def test_posts_chunk_with_correct_fields(self):
        chunk_data = b"hello chunk"
        expected_checksum = hashlib.sha256(chunk_data).hexdigest()
        captured = {}

        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:

            def capture(url, **kwargs):
                captured["url"] = url
                captured["data"] = kwargs.get("data", {})
                captured["files"] = kwargs.get("files", {})
                return _make_response(200)

            mock_post.side_effect = capture
            upload_chunk("http://localhost:8080", "token", "ex-123", 2, chunk_data)

        assert captured["url"] == "http://localhost:8080/v1/uploads/ex-123/chunks"
        assert captured["data"]["chunkIndex"] == "2"
        assert captured["data"]["chunkChecksum"] == expected_checksum

    def test_computes_sha256_checksum_of_chunk_bytes(self):
        chunk_data = b"important data"
        expected_checksum = hashlib.sha256(chunk_data).hexdigest()
        captured = {}

        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:

            def capture(url, **kwargs):
                captured["checksum"] = kwargs.get("data", {}).get("chunkChecksum")
                return _make_response(200)

            mock_post.side_effect = capture
            upload_chunk("http://localhost:8080", "token", "ex-123", 0, chunk_data)

        assert captured["checksum"] == expected_checksum

    def test_raises_on_400_checksum_mismatch(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(
                400, text='{"code":"ChunkChecksumMismatch","chunkIndex":0}'
            )

            with pytest.raises(UploadAPIError, match="400"):
                upload_chunk("http://localhost:8080", "token", "ex-123", 0, b"data")

    def test_raises_on_413_chunk_too_large(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(413, text="chunk too large")

            with pytest.raises(UploadAPIError, match="413"):
                upload_chunk("http://localhost:8080", "token", "ex-123", 0, b"x" * 100)


class TestFinalizeSession:
    def test_posts_to_correct_url_and_returns_on_202(self):
        captured = {}
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:

            def capture(url, **kwargs):
                captured["url"] = url
                captured["json"] = kwargs.get("json")
                return _make_response(202)

            mock_post.side_effect = capture
            finalize_session(
                "https://api.truveta.com/openlink",
                "token",
                "ex-123",
                "data.zip",
                3,
                "a" * 64,
            )

        assert (
            captured["url"]
            == "https://api.truveta.com/openlink/v1/uploads/ex-123/complete"
        )
        assert captured["json"] == {
            "fileName": "data.zip",
            "totalChunkCount": 3,
            "fileChecksum": "a" * 64,
        }

    def test_raises_with_missing_chunk_detail_on_incomplete_session(self):
        error_body = '{"code":"IncompleteUploadSession","missingChunks":[2,3]}'
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(400, text=error_body)

            with pytest.raises(UploadAPIError, match="400"):
                finalize_session(
                    "http://localhost:8080", "token", "ex-123", "data.zip", 3, "a" * 64
                )

    def test_raises_on_404_session_not_found(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(404, text="session not found")

            with pytest.raises(UploadAPIError, match="404"):
                finalize_session(
                    "http://localhost:8080", "token", "ex-123", "data.zip", 3, "a" * 64
                )

    def test_raises_on_400_file_checksum_mismatch(self):
        error_body = '{"code":"FileChecksumMismatch"}'
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(400, text=error_body)

            with pytest.raises(UploadAPIError, match="400"):
                finalize_session(
                    "http://localhost:8080", "token", "ex-123", "data.zip", 3, "a" * 64
                )
