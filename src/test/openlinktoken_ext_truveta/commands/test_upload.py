"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the upload command.
"""

import argparse
import hashlib
import os
import zipfile
from unittest.mock import patch

import pytest
from openlinktoken_ext_truveta.auth import Credentials
from openlinktoken_ext_truveta.commands.common import (
    AuthenticatedCommandContext,
    SessionResolutionError,
)
from openlinktoken_ext_truveta.commands import upload_validation
from openlinktoken_ext_truveta.commands.upload import (
    _package_as_zip,
    _package_existing_zip,
    _upload,
)


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

    def test_packaged_zip_contains_exchange_config(self, tmp_path):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_bytes(b"token\nabc")

        zip_path = _package_as_zip(
            data_file, b'{"metadata":true}', b'{"exchange":true}'
        )

        try:
            with zipfile.ZipFile(zip_path) as archive:
                assert archive.read("metadata.json") == b'{"metadata":true}'
                assert archive.read("exchange-config.json") == b'{"exchange":true}'
        finally:
            zip_path.unlink(missing_ok=True)

    def test_existing_zip_gets_exchange_config(self, tmp_path):
        source_path = tmp_path / "input.zip"
        with zipfile.ZipFile(source_path, "w") as archive:
            archive.writestr("data.csv", b"token\nabc")
            archive.writestr("metadata.json", b"{}")

        with patch(
            "openlinktoken_ext_truveta.commands.upload.zipfile.ZipFile.read",
            side_effect=AssertionError("existing ZIP members should not be read"),
        ):
            output_path = _package_existing_zip(source_path, b'{"exchange":true}')

        try:
            with zipfile.ZipFile(output_path) as archive:
                assert archive.read("exchange-config.json") == b'{"exchange":true}'
            with zipfile.ZipFile(source_path) as archive:
                assert "exchange-config.json" not in archive.namelist()
        finally:
            output_path.unlink(missing_ok=True)

    def test_complete_existing_zip_is_reused(self, tmp_path):
        source_path = tmp_path / "input.zip"
        with zipfile.ZipFile(source_path, "w") as archive:
            archive.writestr("data.csv", b"token\nabc")
            archive.writestr("exchange-config.json", b'{"exchange":true}')

        with patch(
            "openlinktoken_ext_truveta.commands.upload.tempfile.mkstemp",
            side_effect=AssertionError("complete ZIP should not be copied"),
        ):
            output_path = _package_existing_zip(source_path, b"{}")

        assert output_path == source_path

    def test_existing_zip_cleanup_removes_partial_output(self, tmp_path):
        source_path = tmp_path / "input.zip"
        output_path = tmp_path / "output.zip"
        with zipfile.ZipFile(source_path, "w") as archive:
            archive.writestr("data.csv", b"token\nabc")

        def create_output_file(*args, **kwargs):
            fd = os.open(output_path, os.O_CREAT | os.O_RDWR)
            return fd, str(output_path)

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.tempfile.mkstemp",
                side_effect=create_output_file,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.shutil.copyfile",
                side_effect=OSError("copy failed"),
            ),
            pytest.raises(OSError, match="copy failed"),
        ):
            _package_existing_zip(source_path, b"{}")

        assert not output_path.exists()

    def test_existing_zip_rejects_unsafe_member_path(self, tmp_path):
        source_path = tmp_path / "input.zip"
        with zipfile.ZipFile(source_path, "w") as archive:
            archive.writestr("../data.csv", b"token\nabc")

        with pytest.raises(
            upload_validation.UploadValidationError, match="unsafe member path"
        ):
            _package_existing_zip(source_path, b"{}")

    @pytest.fixture(autouse=True)
    def _bypass_file_validation(self, tmp_path_factory):
        """Bypass schema/token validation so tests focus on upload flow."""
        exchange_config = (
            tmp_path_factory.mktemp("exch") / "openlinktoken-default.exchange.json"
        )
        exchange_config.write_bytes(b"{}")
        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload_validation.validate_file",
                return_value=(None, None, None),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload_validation.validate_token_encryption",
                return_value=None,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_config_path",
                return_value=exchange_config,
            ),
        ):
            yield

    @pytest.mark.parametrize("upload_result", [0, 1])
    def test_reused_input_zip_is_preserved_after_upload(self, tmp_path, upload_result):
        input_zip = tmp_path / "input.zip"
        with zipfile.ZipFile(input_zip, "w") as archive:
            archive.writestr("data.csv", b"token\nabc")
            archive.writestr("exchange-config.json", b'{"exchange":true}')

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
                "openlinktoken_ext_truveta.commands.upload._run_upload",
                return_value=upload_result,
            ),
        ):
            rc = _upload(_args(str(input_zip)))

        assert rc == upload_result
        assert input_zip.exists()

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
        assert "\033[32m\u2713 Upload accepted.\033[0m" in out

    def test_progress_output_printed_per_chunk(self, tmp_path, capsys):
        # 2 * chunk_size + 1 bytes always needs exactly 3 chunks, regardless of the
        # small fixed ZIP container overhead added when packaging the upload.
        chunk_size = 8_388_608
        data_file = tmp_path / "large.parquet"
        data_file.write_bytes(b"x" * (chunk_size * 2 + 1))

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
        # Server returns 4MB chunk size; just over 2 * 4MB always needs 3 chunks,
        # regardless of the small fixed ZIP container overhead added when packaging.
        server_chunk_size = 4_194_304
        data_file = tmp_path / "data.csv"
        data_file.write_bytes(b"x" * (server_chunk_size * 2 + 1))

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

    def test_finalize_receives_checksum_of_uploaded_bytes(self, tmp_path):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_bytes(b"token\nabc" * 1000)

        captured_chunks: list[bytes] = []
        captured_finalize: dict[str, str] = {}

        def capture_chunk(**kwargs):
            captured_chunks.append(kwargs["chunk_data"])

        def capture_finalize(**kwargs):
            captured_finalize["file_checksum"] = kwargs["file_checksum"]

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
            patch(
                "openlinktoken_ext_truveta.commands.upload.upload_chunk",
                side_effect=capture_chunk,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.finalize_session",
                side_effect=capture_finalize,
            ),
        ):
            rc = _upload(_args(str(data_file)))

        assert rc == 0
        expected_checksum = hashlib.sha256(b"".join(captured_chunks)).hexdigest()
        assert captured_finalize["file_checksum"] == expected_checksum

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
