"""
Copyright (c) Truveta. All rights reserved.

Pre-upload validation: schema, format, and token encryption checks.
"""

import base64
import csv
import io
import json
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
from jwcrypto import jwe, jwk
from openlinktoken.exchange_config import derive_transport_encryption_key
from openlinktoken.tokens.token import Token
from openlinktoken.tokentransformer.match_token_constants import (
    is_supported_v1_token,
    strip_supported_v1_token_prefix,
)
from openlinktoken_cli.io import FileExtension
from openlinktoken_cli.io.csv.token_csv_reader import TokenCSVReader
from openlinktoken_cli.io.parquet.token_parquet_reader import TokenParquetReader
from openlinktoken_cli.io.token_reader import TokenReader
from openlinktoken_cli.processor.token_constants import TokenConstants

from openlinktoken_ext_truveta.exchange.config import (
    ExchangeConfigError,
    _load_resolve_exchange_inputs,
)
from openlinktoken_ext_truveta.exchange.config import (
    load_exchange_config as _load_exchange_config,
)
from openlinktoken_ext_truveta.paths import private_key_path as _private_key_path

_TOKEN_READER_BY_EXTENSION: dict[str, type[TokenReader]] = {
    FileExtension.CSV: TokenCSVReader,
    FileExtension.PARQUET: TokenParquetReader,
}
SUPPORTED_DATA_EXTENSIONS = frozenset(_TOKEN_READER_BY_EXTENSION)
SUPPORTED_EXTENSIONS = frozenset({*SUPPORTED_DATA_EXTENSIONS, FileExtension.ZIP})


class UploadValidationError(Exception):
    """Raised when the data file fails pre-upload validation."""


def _extract_sample_token(reader: TokenReader) -> str | None:
    """Return the first non-blank Token value from a TokenReader, or None if all tokens are blank."""
    for row in reader:
        token = row.get(TokenConstants.TOKEN, "")
        if token and token != Token.BLANK:
            return token
    return None


def _validate_data_bytes(
    data_bytes: bytes, suffix: str
) -> tuple[str | None, str | None]:
    """
    Validate token data bytes in memory without writing to disk.

    CSV bytes are parsed via csv.DictReader and iterated lazily until the first token is found.
    Parquet bytes use read_schema for column validation and read_row_group to sample one token,
    avoiding loading the full dataset into memory.
    Returns (sample_token, error) where error is None on success.
    """
    required = {TokenConstants.RULE_ID, TokenConstants.TOKEN, TokenConstants.RECORD_ID}
    try:
        if suffix == FileExtension.CSV:
            reader = csv.DictReader(io.StringIO(data_bytes.decode("utf-8")))
            missing = required - set(reader.fieldnames or [])
            if missing:
                return None, f"Missing required columns: {missing}"
            for row in reader:
                token = row.get(TokenConstants.TOKEN, "")
                if token and token != Token.BLANK:
                    return token, None
            return None, None
        else:
            buf = io.BytesIO(data_bytes)
            schema = pq.read_schema(buf)
            missing = required - set(schema.names)
            if missing:
                return None, f"Missing required columns: {missing}"
            # Read only the first row group and only the Token column to avoid
            # loading the full file (which could be hundreds of millions of rows).
            buf.seek(0)
            pf = pq.ParquetFile(buf)
            for rg_index in range(pf.metadata.num_row_groups):
                batch = pf.read_row_group(rg_index, columns=[TokenConstants.TOKEN])
                for val in batch.column(TokenConstants.TOKEN):
                    token = val.as_py()
                    if token and token != Token.BLANK:
                        return token, None
            return None, None
    except (ValueError, IOError) as exc:
        return None, str(exc)


def _validate_zip(zip_path: Path) -> tuple[str | None, dict | None, str | None]:
    """
    Validate the contents of a ZIP and return a sample token and any embedded metadata.

    Expects exactly one CSV or Parquet data file inside the ZIP.
    Returns (sample_token, zip_metadata, error) where error is None on success.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            all_names = zf.namelist()

            data_names = [
                n
                for n in all_names
                if Path(n).suffix.lower() in SUPPORTED_DATA_EXTENSIONS
            ]
            if not data_names:
                return (
                    None,
                    None,
                    f"ZIP contains no supported data file. "
                    f"Expected one file with extension: {', '.join(sorted(SUPPORTED_DATA_EXTENSIONS))}",
                )
            if len(data_names) > 1:
                return (
                    None,
                    None,
                    f"ZIP contains multiple data files: {data_names}. "
                    "Only one CSV or Parquet file is allowed per ZIP.",
                )

            data_name = data_names[0]
            data_suffix = Path(data_name).suffix.lower()

            try:
                data_bytes = zf.read(data_name)
            except RuntimeError:
                return (
                    None,
                    None,
                    "Could not read ZIP entry (password-protected ZIPs are not supported).",
                )

            sample_token, data_error = _validate_data_bytes(data_bytes, data_suffix)
            if data_error:
                return None, None, data_error

            metadata_names = [
                n for n in all_names if Path(n).name.endswith(".metadata.json")
            ]
            zip_metadata: dict | None = None
            if metadata_names:
                try:
                    zip_metadata = json.loads(
                        zf.read(metadata_names[0]).decode("utf-8")
                    )
                except Exception:
                    zip_metadata = None

            return sample_token, zip_metadata, None

    except zipfile.BadZipFile as exc:
        return None, None, f"File is not a valid ZIP archive: {exc}"


def validate_file(
    file_path: Path,
) -> tuple[str | None, dict | None, str | None]:
    """
    Validate that the upload file has the required schema and extract a sample token.

    For ZIP files the inner data file is inspected without extracting it to disk.
    The ZIP itself is what gets uploaded.

    Inputs:
        file_path: Path to the file being uploaded (CSV, Parquet, or ZIP).

    Returns:
        A tuple of (sample_token, zip_metadata, error) where error is None on success.
    """
    suffix = file_path.suffix.lower()

    if suffix == FileExtension.ZIP:
        return _validate_zip(file_path)

    reader_class = _TOKEN_READER_BY_EXTENSION.get(suffix)
    if reader_class is None:
        return None, None, f"Unsupported file format: {suffix!r}"

    try:
        with reader_class(str(file_path)) as reader:
            token = _extract_sample_token(reader)
    except (ValueError, IOError) as exc:
        cause = exc.__cause__ if isinstance(exc.__cause__, ValueError) else exc
        return None, None, str(cause)
    return token, None, None


def _decrypt_sample_token(token: str, transport_key: bytes) -> str | None:
    """
    Attempt to decrypt a token using the given 32-byte AES-GCM transport key.

    Returns None on success, or an error message string on decryption failure.
    """
    jwe_body = strip_supported_v1_token_prefix(token)
    key_b64 = base64.urlsafe_b64encode(transport_key).decode().rstrip("=")
    jwk_key = jwk.JWK(kty="oct", k=key_b64)
    try:
        jwe_token = jwe.JWE()
        jwe_token.deserialize(jwe_body)
        jwe_token.decrypt(jwk_key)
        return None
    except Exception:
        return (
            "Token decryption failed. The file was not encrypted with the current exchange config. "
            "Re-package the data using 'olt package --exchange-config <current-config>'."
        )


def validate_token_encryption(sample_token: str | None) -> str | None:
    """
    Validate that a sample token can be decrypted using the current exchange config.

    Skipped when sample_token is None (all tokens were blank) or when the token
    does not use the V1 JWE format.

    Inputs:
        sample_token: A token value from the data file to test decryption against.

    Returns:
        None on success, or an error message string on failure.
    """
    if not sample_token:
        return None

    if not is_supported_v1_token(sample_token):
        return (
            "Upload requires JWE-packaged tokens (produced by 'olt package'), "
            "but the file contains plain hashed tokens. "
            "Run 'olt package' on the tokenized output before uploading."
        )

    try:
        exchange_config_raw = _load_exchange_config()
        private_key_file = _private_key_path()
        if not private_key_file.exists():
            return f"Private key not found at {private_key_file}"
        resolve_inputs = _load_resolve_exchange_inputs()
        resolved = resolve_inputs(
            exchange_config_value=exchange_config_raw,
            private_key_value=private_key_file.read_bytes(),
        )
        transport_key = derive_transport_encryption_key(resolved)
    except ExchangeConfigError as exc:
        return str(exc)
    except Exception as exc:
        return f"Could not derive transport key from exchange config: {exc}"

    return _decrypt_sample_token(sample_token, transport_key)
