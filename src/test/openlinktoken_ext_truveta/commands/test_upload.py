"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the upload command.
"""

import argparse
import base64
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq
from openlinktoken.tokens.token import Token
from openlinktoken_ext_truveta.auth import Credentials
from openlinktoken_ext_truveta.commands.common import (
    LOCAL_API_URL,
    AuthenticatedCommandContext,
    SessionResolutionError,
)
from openlinktoken_ext_truveta.commands.upload import (
    _upload,
)
from openlinktoken_ext_truveta.commands.upload_validation import (
    _decrypt_sample_token,
    _validate_zip,
)
from openlinktoken_ext_truveta.commands.upload_validation import (
    validate_file as _validate_schema_and_extract_sample_token,
)
from openlinktoken_ext_truveta.commands.upload_validation import (
    validate_token_encryption as _validate_token_encryption,
)
from openlinktoken_ext_truveta.exchange.config import ExchangeConfigError


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
    domain: str | None = "https://api.truveta.com",
    api_domain: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        input=file_path,
        metadata=metadata,
        domain=domain,
        api_domain=api_domain,
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


def _valid_csv_content() -> str:
    return "RuleId,Token,RecordId\nT1,olt.V1.abc,REC-1\nT2,olt.V1.def,REC-2\n"


def _make_zip(
    tmp_path: Path, data_name: str = "tokenized.csv", metadata: dict | None = None
) -> Path:
    zip_path = tmp_path / "tokens.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(data_name, _valid_csv_content())
        if metadata is not None:
            zf.writestr("tokenized.metadata.json", json.dumps(metadata))
    return zip_path


def _patch_validation(
    sample_token: str | None = None, zip_metadata: dict | None = None
):
    return patch(
        "openlinktoken_ext_truveta.commands.upload.validate_file",
        return_value=(sample_token, zip_metadata, None),
    )


def _patch_token_encryption():
    return patch(
        "openlinktoken_ext_truveta.commands.upload.validate_token_encryption",
        return_value=None,
    )


def _patch_exchange_payload(
    exchange_id: str = "x",
    sender: str = "sender",
    recipient: str = "recipient",
    curve: str = "P-256",
):
    return patch(
        "openlinktoken_ext_truveta.commands.upload.resolve_exchange_payload",
        return_value={
            "exchangeId": exchange_id,
            "senderKeyFingerprint": sender,
            "recipientKeyFingerprint": recipient,
            "curve": curve,
        },
    )


class TestUploadCommand:
    def test_happy_path_uploads_file_and_metadata(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        metadata_file = tmp_path / "tokenized.metadata.json"
        data_file.write_text(_valid_csv_content())
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
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 0
        assert captured["url"] == "https://api.truveta.com/openlink/v1/uploads/x"
        assert captured["keys"] == {"dataFile", "metadataFile"}
        assert captured["auth"] == "Bearer access-token"
        assert captured["timeout"] == 30
        assert "Upload accepted" in capsys.readouterr().out

    def test_missing_credentials_returns_friendly_message(self, tmp_path, capsys):
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text(_valid_csv_content())

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
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
        data_file.write_text(_valid_csv_content())

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
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
        data_file.write_text(_valid_csv_content())
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
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(data_file), metadata=str(explicit_metadata)))

        assert result == 0
        assert captured["metadata_name"] == Path(explicit_metadata).name

    def test_upload_synthesizes_metadata_from_exchange_config(self, tmp_path):
        data_file = tmp_path / "enc_tokenized.csv"
        data_file.write_text(_valid_csv_content())

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
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
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
                "openlinktoken_ext_truveta.commands.upload.requests.post",
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
        data_file.write_text(_valid_csv_content())

        captured = {}

        def _post(url, files, headers, timeout):
            captured["url"] = url
            return _Response(202, {"uploadReferenceId": "upload-123"})

        args = _args(str(data_file), domain="dev.truveta-int.com")

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(
                    domain="dev.truveta-int.com",
                    api_url="https://api.dev.truveta-int.com/openlink",
                    storage_domain="dev.truveta-int.com",
                ),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
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
        data_file.write_text(_valid_csv_content())

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                side_effect=SessionResolutionError(
                    "No login session found. Please run 'olt truveta login' first."
                ),
            ),
        ):
            result = _upload(_args(str(data_file), domain=None, api_domain=None))

        assert result == 1
        assert "olt truveta login" in capsys.readouterr().err

    def test_upload_local_dev_uses_localhost_endpoint_and_timeout(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("OLT_TRV_LOCAL_DEV", "true")
        data_file = tmp_path / "tokenized.csv"
        data_file.write_text(_valid_csv_content())

        captured = {}

        def _post(url, files, headers, timeout):
            captured["url"] = url
            captured["timeout"] = timeout
            return _Response(202, {"uploadReferenceId": "upload-123"})

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(
                    domain="dev.truveta-int.com",
                    api_url=LOCAL_API_URL,
                    storage_domain="localhost-18080",
                ),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 0
        assert captured["url"] == "http://localhost:18080/v1/uploads/x"
        assert captured["timeout"] == 180


class TestSupportedExtensions:
    def test_unsupported_extension_rejected(self, tmp_path, capsys):
        bad_file = tmp_path / "tokens.txt"
        bad_file.write_text("something")
        result = _upload(_args(str(bad_file)))
        assert result == 1
        assert "Unsupported file format" in capsys.readouterr().err

    def test_parquet_extension_accepted(self, tmp_path):
        parquet_file = tmp_path / "tokens.parquet"
        parquet_file.write_bytes(b"PAR1fake")

        captured = {}

        def _post(url, files, headers, timeout):
            captured["name"] = files["dataFile"][0]
            return _Response(202, {"uploadReferenceId": "u-1"})

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(parquet_file)))

        assert result == 0
        assert captured["name"] == "tokens.parquet"

    def test_zip_extension_accepted(self, tmp_path):
        zip_path = _make_zip(tmp_path)
        captured = {}

        def _post(url, files, headers, timeout):
            captured["name"] = files["dataFile"][0]
            return _Response(202, {"uploadReferenceId": "u-1"})

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(zip_path)))

        assert result == 0
        assert captured["name"] == "tokens.zip"


class TestZipUpload:
    def test_zip_uploaded_as_is(self, tmp_path):
        zip_path = _make_zip(tmp_path)
        captured = {}

        def _post(url, files, headers, timeout):
            captured["name"] = files["dataFile"][0]
            return _Response(202, {"uploadReferenceId": "u-1"})

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(zip_path)))

        assert result == 0
        assert captured["name"] == "tokens.zip"

    def test_zip_ignores_metadata_flag_and_warns(self, tmp_path, capsys):
        zip_path = _make_zip(tmp_path)
        stray_metadata = tmp_path / "stray.metadata.json"
        stray_metadata.write_text("{}")

        def _post(url, files, headers, timeout):
            return _Response(202, {"uploadReferenceId": "u-1"})

        with (
            _patch_validation("olt.V1.abc"),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(zip_path), metadata=str(stray_metadata)))

        assert result == 0
        assert "ignored" in capsys.readouterr().err.lower()

    def test_zip_uses_embedded_metadata(self, tmp_path):
        embedded_meta = {"HashingSecretHash": "abc", "TotalRows": 10}
        zip_path = _make_zip(tmp_path, metadata=embedded_meta)

        captured = {}

        def _post(url, files, headers, timeout):
            captured["metadata_content"] = files["metadataFile"][1]
            return _Response(202, {"uploadReferenceId": "u-1"})

        with (
            patch(
                "openlinktoken_ext_truveta.commands.upload.validate_file",
                return_value=("olt.V1.abc", embedded_meta, None),
            ),
            _patch_token_encryption(),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.upload.requests.post",
                side_effect=_post,
            ),
        ):
            result = _upload(_args(str(zip_path)))

        assert result == 0
        assert "HashingSecretHash" in captured["metadata_content"]

    def test_zip_with_no_data_files_fails(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "no data here")
        _, _, error = _validate_zip(zip_path)
        assert error is not None
        assert "no supported data file" in error

    def test_zip_with_multiple_data_files_fails(self, tmp_path):
        zip_path = tmp_path / "multi.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a.csv", _valid_csv_content())
            zf.writestr("b.csv", _valid_csv_content())
        _, _, error = _validate_zip(zip_path)
        assert error is not None
        assert "multiple data files" in error

    def test_zip_bad_file_fails(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"this is not a zip")
        _, _, error = _validate_zip(bad_zip)
        assert error is not None
        assert "not a valid ZIP" in error

    def test_zip_schema_validation_fails_end_to_end(self, tmp_path, capsys):
        zip_path = tmp_path / "bad_schema.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("tokens.csv", "WrongCol1,WrongCol2\na,b\n")

        result = _upload(_args(str(zip_path)))
        assert result == 1
        assert "missing required columns" in capsys.readouterr().err.lower()


class TestSchemaValidation:
    def test_csv_valid_columns_returns_token(self, tmp_path):
        csv_file = tmp_path / "tokens.csv"
        csv_file.write_text(_valid_csv_content())
        token, _, error = _validate_schema_and_extract_sample_token(csv_file)
        assert error is None
        assert token is not None
        assert token.startswith("olt.V1.")

    def test_csv_missing_columns_returns_error(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("RuleId,Token\nT1,olt.V1.abc\n")
        _, _, error = _validate_schema_and_extract_sample_token(bad_csv)
        assert error is not None
        assert "missing required columns" in error.lower()

    def test_csv_all_blank_tokens_returns_none(self, tmp_path):
        blank_csv = tmp_path / "blank.csv"
        blank_csv.write_text(f"RuleId,Token,RecordId\nT1,{Token.BLANK},R1\n")
        token, _, error = _validate_schema_and_extract_sample_token(blank_csv)
        assert error is None
        assert token is None

    def test_schema_validation_rejects_unsupported_extension(self, tmp_path):
        bad_file = tmp_path / "tokens.json"
        bad_file.write_text("{}")
        _, _, error = _validate_schema_and_extract_sample_token(bad_file)
        assert error is not None
        assert "Unsupported file format" in error

    def test_parquet_valid_columns_returns_token(self, tmp_path):
        table = pa.table(
            {"RuleId": ["T1"], "Token": ["olt.V1.abc"], "RecordId": ["R1"]}
        )
        parquet_file = tmp_path / "tokens.parquet"
        pq.write_table(table, parquet_file)
        token, _, error = _validate_schema_and_extract_sample_token(parquet_file)
        assert error is None
        assert token == "olt.V1.abc"

    def test_parquet_missing_columns_returns_error(self, tmp_path):
        table = pa.table({"RuleId": ["T1"], "Token": ["olt.V1.abc"]})
        parquet_file = tmp_path / "missing.parquet"
        pq.write_table(table, parquet_file)
        _, _, error = _validate_schema_and_extract_sample_token(parquet_file)
        assert error is not None

    def test_parquet_all_blank_tokens_returns_none(self, tmp_path):
        table = pa.table({"RuleId": ["T1"], "Token": [Token.BLANK], "RecordId": ["R1"]})
        parquet_file = tmp_path / "blank.parquet"
        pq.write_table(table, parquet_file)
        token, _, error = _validate_schema_and_extract_sample_token(parquet_file)
        assert error is None
        assert token is None


class TestEncryptionValidation:
    def _make_jwe_token(self, key: bytes) -> str:
        import json as _json

        from jwcrypto import jwe, jwk

        key_b64 = base64.urlsafe_b64encode(key).decode().rstrip("=")
        jwk_key = jwk.JWK(kty="oct", k=key_b64)
        plaintext = b'{"ppid":["abc"],"rlid":"T1"}'
        token = jwe.JWE(
            plaintext, _json.dumps({"alg": "dir", "enc": "A256GCM"}), recipient=jwk_key
        )
        return f"olt.V1.{token.serialize(compact=True)}"

    def test_decrypt_sample_token_succeeds_with_correct_key(self):
        key = b"A" * 32
        token = self._make_jwe_token(key)
        assert _decrypt_sample_token(token, key) is None

    def test_decrypt_sample_token_fails_with_wrong_key(self):
        key = b"A" * 32
        wrong_key = b"Z" * 32
        token = self._make_jwe_token(key)
        error = _decrypt_sample_token(token, wrong_key)
        assert error is not None
        assert "not encrypted with the current exchange config" in error

    def test_validate_token_encryption_skips_when_no_token(self):
        _validate_token_encryption(None, "truveta.com")

    def test_validate_token_encryption_skips_non_v1_tokens(self):
        _validate_token_encryption("legacy-token-no-prefix", "truveta.com")

    def test_validate_token_encryption_fails_on_bad_exchange_config(self):
        with patch(
            "openlinktoken_ext_truveta.commands.upload_validation._load_exchange_config",
            side_effect=ExchangeConfigError("no config"),
        ):
            error = _validate_token_encryption("olt.V1.some-token", "truveta.com")
            assert error is not None

    def test_encryption_validation_failure_causes_upload_to_fail(
        self, tmp_path, capsys
    ):
        data_file = tmp_path / "tokens.csv"
        data_file.write_text(_valid_csv_content())

        with (
            _patch_validation("olt.V1.abc"),
            patch(
                "openlinktoken_ext_truveta.commands.upload.validate_token_encryption",
                return_value="Token decryption failed. The file was not encrypted with the current exchange config.",
            ),
            _patch_exchange_payload(),
            patch(
                "openlinktoken_ext_truveta.commands.upload.resolve_authenticated_context",
                return_value=_context(),
            ),
        ):
            result = _upload(_args(str(data_file)))

        assert result == 1
        assert (
            "not encrypted with the current exchange config" in capsys.readouterr().err
        )
