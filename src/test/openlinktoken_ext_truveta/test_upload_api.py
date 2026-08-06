"""
Copyright (c) Truveta. All rights reserved.

Unit tests for upload API client behavior.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from openlinktoken_ext_truveta.api.upload import (
    UploadAPIError,
    finalize_session,
    initialize_session,
    upload_chunk,
)


def _make_response(status_code: int, json_payload=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = json_payload if json_payload is not None else {}
    return response


class TestInitializeSession:
    def test_returns_max_chunk_size_on_201(self):
        payload = {"maxChunkSizeBytes": 8388608}
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(201, json_payload=payload)

            max_chunk_size = initialize_session(
                "http://localhost:8080", "token", "ex-123"
            )

        assert max_chunk_size == 8388608

    def test_posts_without_a_request_body(self):
        payload = {"maxChunkSizeBytes": 8388608}
        captured = {}
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:

            def capture(url, **kwargs):
                captured["url"] = url
                captured.update(kwargs)
                return _make_response(201, json_payload=payload)

            mock_post.side_effect = capture
            initialize_session("https://api.truveta.com/openlink", "token", "ex-123")

        assert captured["url"] == "https://api.truveta.com/openlink/v1/uploads/ex-123"
        assert "json" not in captured
        assert "data" not in captured
        assert "files" not in captured

    def test_raises_upload_api_error_on_non_201(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(400, text="exchange not found")

            with pytest.raises(UploadAPIError, match="400"):
                initialize_session("http://localhost:8080", "token", "ex-123")

    def test_raises_on_409_already_completed(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(409, text="already completed")

            with pytest.raises(UploadAPIError, match="409"):
                initialize_session("http://localhost:8080", "token", "ex-123")


class TestUploadChunk:
    def test_posts_raw_chunk_with_checksum_header(self):
        chunk_data = b"hello chunk"
        expected_checksum = hashlib.sha256(chunk_data).hexdigest()
        captured = {}

        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:

            def capture(url, **kwargs):
                captured["url"] = url
                captured.update(kwargs)
                return _make_response(200)

            mock_post.side_effect = capture
            upload_chunk("http://localhost:8080", "token", "ex-123", 2, chunk_data)

        assert captured["url"] == "http://localhost:8080/v1/uploads/ex-123/chunks"
        assert captured["params"] == {
            "chunkIndex": "2",
        }
        assert captured["data"] == chunk_data
        assert "files" not in captured
        assert captured["headers"]["Content-Type"] == "application/octet-stream"
        assert captured["headers"]["Chunk-Checksum"] == expected_checksum

    def test_raises_on_checksum_mismatch(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(
                400, text='{"code":"ChunkChecksumMismatch","chunkIndex":0}'
            )

            with pytest.raises(UploadAPIError, match="400"):
                upload_chunk("http://localhost:8080", "token", "ex-123", 0, b"data")

    def test_raises_on_chunk_too_large(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(413, text="chunk too large")

            with pytest.raises(UploadAPIError, match="413"):
                upload_chunk("http://localhost:8080", "token", "ex-123", 0, b"x")


class TestFinalizeSession:
    def test_posts_json_to_complete_on_202(self):
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

        assert captured["url"] == (
            "https://api.truveta.com/openlink/v1/uploads/ex-123/complete"
        )
        assert captured["json"] == {
            "fileName": "data.zip",
            "totalChunkCount": 3,
            "fileChecksum": "a" * 64,
        }

    def test_raises_on_incomplete_session(self):
        with patch("openlinktoken_ext_truveta.api.upload.requests.post") as mock_post:
            mock_post.return_value = _make_response(
                400, text='{"code":"IncompleteUploadSession","missingChunks":[2,3]}'
            )

            with pytest.raises(UploadAPIError, match="400"):
                finalize_session(
                    "http://localhost:8080", "token", "ex-123", "data.zip", 3, "a" * 64
                )
