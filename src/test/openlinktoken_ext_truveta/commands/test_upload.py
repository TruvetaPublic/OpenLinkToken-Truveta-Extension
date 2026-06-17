"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the upload command.
"""

import argparse
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from openlinktoken_ext_truveta.auth import Credentials
from openlinktoken_ext_truveta.commands.common import (
    LOCAL_API_URL,
    AuthenticatedCommandContext,
    SessionResolutionError,
)
from openlinktoken_ext_truveta.commands.upload import (
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


def _patch_validation(sample_token: str):
    return patch(
        "openlinktoken_ext_truveta.commands.upload._validate_schema_and_extract_sample_token",
        return_value=(sample_token, None),
    )


def _patch_token_encryption():
    return patch(
        "openlinktoken_ext_truveta.commands.upload._validate_token_encryption",
        return_value=None,
    )


def _patch_exchange_payload():
    return patch(
        "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
        return_value={
            "exchangeId": "ex-1",
            "hashingSecret": "secret",
            "senderKeyFingerprint": "sender",
            "recipientKeyFingerprint": "recipient",
            "curve": "P-256",
        },
    )


def _make_zip(tmp_path, *, metadata: dict | None = None) -> Path:
    import json as _json

    zip_path = tmp_path / "tokens.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("tokens.csv", _valid_csv_content())
        if metadata is not None:
            zf.writestr("output.metadata.json", _json.dumps(metadata))
    return zip_path


def _valid_csv_content() -> str:
    return "RuleId,Token,RecordId\nT1,olt.V1.abc,R1\n"


class TestUploadCommand:
    @pytest.fixture(autouse=True)
    def _bypass_file_validation(self, tmp_path_factory):
        exchange_config = (
            tmp_path_factory.mktemp("exch") / "openlinktoken-default.exchange.json"
        )
        exchange_config.write_text("{}")
        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload._validate_schema_and_extract_sample_token",
                return_value=(None, None),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload._validate_token_encryption",
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_config_path",
                return_value=exchange_config,
            ),
        ):
            yield

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
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.api.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 0
        assert captured["url"] == "https://api.truveta.com/openlink/v1/uploads/x"
        assert captured["keys"] == {"dataFile", "metadataFile", "exchangeConfigFile"}
        assert captured["auth"] == "Bearer access-token"
        assert captured["timeout"] == 30

        out_lines = capsys.readouterr().out.splitlines()
        assert out_lines[0] == "\x1b[32m✓ Upload accepted.\x1b[0m"
        assert out_lines[1] == "Upload reference ID: upload-123"

    def test_missing_credentials_returns_friendly_message(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
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
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.api.upload.requests.post",
                return_value=_Response(500, {"error": "server exploded"}, text="boom"),
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 1
        assert (
            "Upload failed for https://api.truveta.com/openlink/v1/uploads/x: 500"
            in capsys.readouterr().err
        )

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
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.api.upload.requests.post",
                side_effect=_post,
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
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
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
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.api.upload.requests.post",
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

        args = _args(str(data_file), domain="dev.truveta-int.com")

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(
                    domain="dev.truveta-int.com",
                    api_url="https://api.dev.truveta-int.com/openlink",
                    storage_domain="dev.truveta-int.com",
                ),
            ),
            patch(
                "openlinktoken_ext_truveta.api.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(args)

        assert result == 0
        assert (
            captured["url"] == "https://api.dev.truveta-int.com/openlink/v1/uploads/x"
        )

    def test_upload_requires_session_when_not_local_dev(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")

        with patch(
            "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
            side_effect=SessionResolutionError(
                "No login session found. Please run 'olt truveta login' first."
            ),
        ):
            result = _upload(_args(str(data_file), domain=None, api_domain=None))

        assert result == 1
        assert "olt truveta login" in capsys.readouterr().err

    def test_upload_local_dev_uses_localhost_endpoint_and_timeout(self, tmp_path):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")

        captured = {}

        def _post(url, files, headers, timeout):
            captured["url"] = url
            captured["timeout"] = timeout
            return _Response(202, {"uploadReferenceId": "upload-123"})

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(
                    domain="dev.truveta-int.com",
                    api_url=LOCAL_API_URL,
                    storage_domain="localhost-18080",
                ),
            ),
            patch(
                "openlinktoken_ext_truveta.api.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(data_file), local_dev=True))

        assert result == 0
        assert captured["url"] == "http://localhost:18080/v1/uploads/x"
        assert captured["timeout"] == 180

    def test_upload_includes_exchange_config_file_in_request(self, tmp_path):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")
        exchange_config = tmp_path / "openlinktoken-2026-05-20.exchange.json"
        exchange_config.write_text('{"exchangeId":"x"}')

        captured = {}

        def _post(url, files, headers, timeout):
            captured["keys"] = set(files.keys())
            captured["exchange_config_name"] = files["exchangeConfigFile"][0]
            captured["exchange_config_type"] = files["exchangeConfigFile"][2]
            return _Response(202, {"uploadReferenceId": "upload-123"})

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_config_path",
                return_value=exchange_config,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 0
        assert "exchangeConfigFile" in captured["keys"]
        assert (
            captured["exchange_config_name"] == "openlinktoken-2026-05-20.exchange.json"
        )
        assert captured["exchange_config_type"] == "application/json"

    def test_upload_missing_exchange_config_file_returns_error(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text("token\nabc")
        missing_config = tmp_path / "nonexistent.exchange.json"

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
                return_value={
                    "exchangeId": "x",
                    "senderKeyFingerprint": "sender",
                    "recipientKeyFingerprint": "recipient",
                    "curve": "P-256",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_exchange_config_path",
                return_value=missing_config,
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 1
        err = capsys.readouterr().err
        assert "Exchange config file not found" in err
        assert "olt truveta initiate-exchange" in err
