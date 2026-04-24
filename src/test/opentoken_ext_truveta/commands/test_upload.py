"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the upload command.
"""

import argparse
from pathlib import Path
from unittest.mock import patch

from opentoken_ext_truveta.auth import AuthError, Credentials
from opentoken_ext_truveta.commands.upload import _upload


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
        file=file_path,
        metadata=metadata,
        domain=domain,
        api_domain=api_domain,
        local_dev=local_dev,
    )


def _creds() -> Credentials:
    return Credentials(access_token="access-token", id_token="id-token")


class TestUploadCommand:
    def test_happy_path_uploads_file_and_metadata(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        metadata_file = tmp_path / "tokenized.metadata.json"
        data_file.write_text("token\nabc")
        metadata_file.write_text(
            '{"payload":{"exchangeId":"ex-1","senderKeyFingerprint":"sender","recipientKeyFingerprint":"recipient","curve":"P-256"}}'
        )

        captured = {}

        def _post(url, files, headers, timeout):
            captured["url"] = url
            captured["keys"] = set(files.keys())
            captured["auth"] = headers.get("Authorization")
            captured["timeout"] = timeout
            return _Response(
                202,
                {
                    "uploadReferenceId": "upload-123",
                    "statusEndpoint": "/v1/upload/upload-123",
                },
            )

        with (
            patch(
                "opentoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.ensure_auth",
                return_value=_creds(),
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.requests.post", side_effect=_post
            ),
            patch(
                "opentoken_ext_truveta.commands.common.read_session_api_url",
                return_value="https://api.truveta.com",
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 0
        assert captured["url"] == "https://api.truveta.com/v1/uploads/x"
        assert captured["keys"] == {"dataFile", "metadataFile"}
        assert captured["auth"] == "Bearer access-token"
        assert captured["timeout"] == 30
        assert "Upload accepted" in capsys.readouterr().out

    def test_missing_credentials_returns_friendly_message(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")

        with (
            patch(
                "opentoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.ensure_auth",
                side_effect=AuthError("No valid cached credentials found."),
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 1
        err = capsys.readouterr().err
        assert "olt truveta login" in err

    def test_file_not_found_returns_error(self, capsys):
        result = _upload(_args("/does/not/exist.csv"))
        assert result == 1
        assert "Input file not found" in capsys.readouterr().err

    def test_server_error_response_returns_failure(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")

        with (
            patch(
                "opentoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.ensure_auth",
                return_value=_creds(),
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.requests.post",
                return_value=_Response(500, {"error": "server exploded"}, text="boom"),
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 1
        assert "Upload failed: 500" in capsys.readouterr().err

    def test_explicit_metadata_override_is_used(self, tmp_path):
        data_file = tmp_path / "tokenized.csv"
        auto_metadata = tmp_path / "tokenized.metadata.json"
        explicit_metadata = tmp_path / "manual.metadata.json"
        data_file.write_text("token\nabc")
        auto_metadata.write_text('{"source":"auto"}')
        explicit_metadata.write_text('{"source":"manual"}')

        captured = {}

        def _post(url, files, headers, timeout):
            metadata_part = files.get("metadataFile")
            captured["metadata_name"] = metadata_part[0] if metadata_part else None
            return _Response(
                202,
                {
                    "uploadReferenceId": "upload-123",
                    "statusEndpoint": "/v1/upload/upload-123",
                },
            )

        with (
            patch(
                "opentoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.ensure_auth",
                return_value=_creds(),
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.requests.post", side_effect=_post
            ),
        ):
            result = _upload(_args(str(data_file), metadata=str(explicit_metadata)))

        assert result == 0
        assert captured["metadata_name"] == Path(explicit_metadata).name

    def test_upload_synthesizes_metadata_from_exchange_config(self, tmp_path):
        data_file = tmp_path / "enc_tokenized.csv"
        data_file.write_text("token\nabc")

        captured = {}

        def _post(url, files, headers, timeout):
            captured["metadata_name"] = files["metadataFile"][0]
            captured["metadata_payload"] = files["metadataFile"][1]
            return _Response(
                202,
                {
                    "uploadReferenceId": "upload-123",
                    "statusEndpoint": "/v1/upload/upload-123",
                },
            )

        args = _args(str(data_file))

        with (
            patch(
                "opentoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "exchangeName": "name",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                    "hashingSecret": "secret",
                },
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.ensure_auth",
                return_value=_creds(),
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(args)

        assert result == 0
        assert captured["metadata_name"] == "enc_tokenized.metadata.json"
        assert '"exchangeId": "x"' in captured["metadata_payload"]
        assert "hashingSecret" not in captured["metadata_payload"]

    def test_upload_uses_session_domain_for_non_login_commands(self, tmp_path):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")

        captured = {}

        def _post(url, files, headers, timeout):
            captured["url"] = url
            return _Response(202, {"uploadReferenceId": "upload-123"})

        args = _args(
            str(data_file),
            domain="http://localhost:8080",
            api_domain="http://override.example",
        )

        with (
            patch(
                "opentoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "opentoken_ext_truveta.commands.upload.ensure_auth",
                return_value=_creds(),
            ) as mock_auth,
            patch(
                "opentoken_ext_truveta.commands.upload.requests.post", side_effect=_post
            ),
            patch(
                "opentoken_ext_truveta.commands.common.read_session_api_url",
                return_value="https://api.dev.truveta-int.com",
            ),
        ):
            result = _upload(args)

        assert result == 0
        mock_auth.assert_called_once_with(
            "https://api.dev.truveta-int.com", cached_only=True
        )
        assert captured["url"] == "https://api.dev.truveta-int.com/v1/uploads/x"

    def test_upload_requires_session_when_not_local_dev(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")

        with patch(
            "opentoken_ext_truveta.commands.common.read_session_api_url",
            return_value=None,
        ):
            result = _upload(_args(str(data_file), domain=None, api_domain=None))

        assert result == 1
        assert "olt truveta login" in capsys.readouterr().err
