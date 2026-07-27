"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the upload command.
"""

import argparse
from unittest.mock import patch

import pytest
from openlinktoken_ext_truveta.auth import Credentials
from openlinktoken_ext_truveta.commands.common import (
    AuthenticatedCommandContext,
    SessionResolutionError,
)
from openlinktoken_ext_truveta.commands.upload import _upload


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def _args(
    file_path: str,
    metadata: str | None = None,
    local_dev: bool = False,
    domain: str | None = "https://api.truveta.com",
    api_domain: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        input=file_path,
        metadata=metadata,
        domain=domain,
        api_domain=api_domain,
        local_dev=local_dev,
    )


def _creds() -> Credentials:
    return Credentials(access_token="access-token", id_token="id-token")


def _context(
    *,
    domain: str = "truveta.com",
    api_url: str = "https://api.truveta.com/openlink",
    storage_domain: str = "truveta.com",
) -> AuthenticatedCommandContext:
    return AuthenticatedCommandContext(
        domain=domain,
        api_url=api_url,
        storage_domain=storage_domain,
        credentials=_creds(),
    )


class TestUploadCommand:
    """Tests for the 3-step chunked upload flow."""

    @pytest.fixture(autouse=True)
    def _bypass_file_validation(self, tmp_path_factory):
        """Bypass schema/token validation so tests focus on upload flow."""
        exchange_config = (
            tmp_path_factory.mktemp("exch") / "openlinktoken-default.exchange.json"
        )
        exchange_config.write_bytes(b"{}")
        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload._validate_schema_and_extract_sample_token",
                return_value=(None, None),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload._validate_token_encryption"
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_config_path",
                return_value=exchange_config,
            ),
        ):
            yield

    def _mock_3step(self, init_return=8_388_608):
        """Return a context manager that mocks all three upload API steps."""
        return (
            patch(
                "openlinktoken_ext_truveta.commands.upload.initialize_session",
                return_value=init_return,
            ),
            patch("openlinktoken_ext_truveta.commands.upload.upload_chunk"),
            patch("openlinktoken_ext_truveta.commands.upload.finalize_session"),
        )

    def test_happy_path_completes_3_step_flow(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_bytes(b"token\nabc")

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.initialize_session",
                return_value=8_388_608,
            ),
            patch("openlinktoken_ext_truveta.commands.upload.upload_chunk"),
            patch("openlinktoken_ext_truveta.commands.upload.finalize_session"),
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 0
        out = capsys.readouterr().out
        assert "Upload accepted" in out

    def test_progress_output_printed_per_chunk(self, tmp_path, capsys):
        # 3 chunks: file is 3 * chunk_size bytes so exactly 3 reads produce 3 calls
        chunk_size = 8_388_608
        data_file = tmp_path / "large.parquet"
        data_file.write_bytes(b"x" * (chunk_size * 3))

        upload_chunk_mock = patch(
            "openlinktoken_ext_truveta.commands.upload.upload_chunk"
        )
        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.initialize_session",
                return_value=chunk_size,
            ),
            upload_chunk_mock as mock_chunk,
            patch("openlinktoken_ext_truveta.commands.upload.finalize_session"),
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 0
        assert mock_chunk.call_count == 3
        out = capsys.readouterr().out
        assert "chunk 1/3" in out
        assert "chunk 2/3" in out
        assert "chunk 3/3" in out

    def test_small_file_sends_single_chunk(self, tmp_path):
        data_file = tmp_path / "small.csv"
        data_file.write_bytes(b"token\nabc")  # well below 8MB

        init_mock = patch(
            "openlinktoken_ext_truveta.commands.upload.initialize_session",
            return_value=8_388_608,
        )
        chunk_mock = patch("openlinktoken_ext_truveta.commands.upload.upload_chunk")
        finalize_mock = patch(
            "openlinktoken_ext_truveta.commands.upload.finalize_session"
        )

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            init_mock,
            chunk_mock as mock_chunk,
            finalize_mock,
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 0
        assert mock_chunk.call_count == 1
        call_kwargs = mock_chunk.call_args
        assert call_kwargs.kwargs["chunk_index"] == 0

    def test_uses_max_chunk_size_from_server_response(self, tmp_path):
        # Server returns 4MB chunk size; 10MB file should produce 3 chunks
        server_chunk_size = 4_194_304
        data_file = tmp_path / "data.csv"
        data_file.write_bytes(b"x" * (server_chunk_size * 3 - 1))  # just under 3 * 4MB

        chunk_mock = patch("openlinktoken_ext_truveta.commands.upload.upload_chunk")
        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.initialize_session",
                return_value=server_chunk_size,
            ),
            chunk_mock as mock_chunk,
            patch("openlinktoken_ext_truveta.commands.upload.finalize_session"),
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 0
        assert mock_chunk.call_count == 3

    def test_initialize_failure_exits_before_chunks(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_bytes(b"token\nabc")

        from openlinktoken_ext_truveta.api.upload import UploadAPIError

        chunk_mock = patch("openlinktoken_ext_truveta.commands.upload.upload_chunk")
        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.initialize_session",
                side_effect=UploadAPIError("Exchange not found"),
            ),
            chunk_mock as mock_chunk,
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 1
        assert mock_chunk.call_count == 0
        assert "Exchange not found" in capsys.readouterr().err

    def test_finalize_incomplete_session_error_surfaced(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_bytes(b"token\nabc")

        from openlinktoken_ext_truveta.api.upload import UploadAPIError

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.initialize_session",
                return_value=8_388_608,
            ),
            patch("openlinktoken_ext_truveta.commands.upload.upload_chunk"),
            patch(
                "openlinktoken_ext_truveta.commands.upload.finalize_session",
                side_effect=UploadAPIError(
                    "400 - IncompleteUploadSession, missingChunks: [2]"
                ),
            ),
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 1
        assert "IncompleteUploadSession" in capsys.readouterr().err

    def test_missing_credentials_returns_friendly_message(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_bytes(b"token\nabc")

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                side_effect=SessionResolutionError(
                    "Not logged in. Please, run 'olt truveta login' first."
                ),
            ),
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 1
        assert "olt truveta login" in capsys.readouterr().err

    def test_file_not_found_returns_error(self, capsys):
        rc = _upload(_args("/does/not/exist.csv"))
        assert rc == 1
        assert "Input file not found" in capsys.readouterr().err

    def test_upload_uses_correct_api_url(self, tmp_path):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_bytes(b"token\nabc")
        captured = {}

        def capture_init(api_url, **kwargs):
            captured["api_url"] = api_url
            return 8_388_608

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "ex-1",
                    "senderKeyFingerprint": "s",
                    "recipientKeyFingerprint": "r",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(
                    api_url="https://api.dev.truveta-int.com/openlink"
                ),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.initialize_session",
                side_effect=capture_init,
            ),
            patch("openlinktoken_ext_truveta.commands.upload.upload_chunk"),
            patch("openlinktoken_ext_truveta.commands.upload.finalize_session"),
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 0
        assert captured["api_url"] == "https://api.dev.truveta-int.com/openlink"
