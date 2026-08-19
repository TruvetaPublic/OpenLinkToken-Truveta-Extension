"""
Copyright (c) Truveta. All rights reserved.

upload command: upload tokenized output data to Truveta for overlap analysis.
"""

import argparse
import base64
import csv
import hashlib
import io
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from openlinktoken.tokentransformer.match_token_constants import V1_TOKEN_PREFIX
from openlinktoken_cli.io.file_extension import FileExtension
from openlinktoken_cli.processor.token_constants import TokenConstants

from openlinktoken_ext_truveta.api import upload as upload_api
from openlinktoken_ext_truveta.api.upload import (
    UploadAPIError,
    UploadSessionInfo,
    finalize_session,
    initialize_session,
    upload_chunk,
)
from openlinktoken_ext_truveta.commands.common import (
    AuthenticatedCommandContext,
    SessionResolutionError,
    resolve_authenticated_context,
    resolve_timeout_seconds,
)
from openlinktoken_ext_truveta.exchange.config import (
    ExchangeConfigError,
    resolve_exchange_config_path,
    resolve_exchange_payload,
)

# Preserve test monkeypatch compatibility for requests.post patch targets.
requests = upload_api.requests

_REQUIRED_COLUMNS = {
    TokenConstants.RULE_ID,
    TokenConstants.TOKEN,
    TokenConstants.RECORD_ID,
}
_SUPPORTED_DATA_EXTENSIONS = frozenset({FileExtension.CSV, FileExtension.PARQUET})

_SUPPORTED_EXTENSIONS = frozenset(
    {FileExtension.CSV, FileExtension.PARQUET, FileExtension.ZIP}
)


class UploadValidationError(Exception):
    """Raised when the data file fails pre-upload validation."""


class UploadPackagingError(Exception):
    """Raised when a ZIP for upload cannot be built, e.g. due to memory pressure."""


@dataclass
class PreparedUpload:
    """A ready-to-upload payload: an open, readable stream plus its size and filename."""

    stream: BinaryIO
    size: int
    filename: str

    def close(self) -> None:
        self.stream.close()


def _validate_csv_columns(file_obj: io.IOBase) -> str | None:
    """
    Validate that a CSV stream has the required columns and return one non-blank token value.

    Inputs:
        file_obj: A readable binary or text stream positioned at the start of the CSV.

    Returns:
        The first non-blank Token value found, or None if all tokens are blank.
    """
    text_stream = (
        io.TextIOWrapper(file_obj, encoding="utf-8")
        if isinstance(file_obj, (io.RawIOBase, io.BufferedIOBase))
        else file_obj
    )
    reader = csv.DictReader(text_stream)
    columns = set(reader.fieldnames or [])
    missing = _REQUIRED_COLUMNS - columns
    if missing:
        raise UploadValidationError(
            f"File is missing required columns: {', '.join(sorted(missing))}. "
            f"Expected: {', '.join(sorted(_REQUIRED_COLUMNS))}"
        )
    for row in reader:
        token = row.get("Token", "")
        if token and token != "0" * 64:
            return token
    return None


def _validate_parquet_columns(file_bytes: bytes) -> str | None:
    """
    Validate that a Parquet byte buffer has the required columns and return one non-blank token.

    Inputs:
        file_bytes: The raw bytes of the Parquet file.

    Returns:
        The first non-blank Token value found, or None if all tokens are blank.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise UploadValidationError(
            "pyarrow is required for Parquet validation. Install with: uv pip install pyarrow"
        ) from exc

    try:
        table = pq.read_table(io.BytesIO(file_bytes))
    except Exception as exc:
        raise UploadValidationError(f"Could not read Parquet file: {exc}") from exc

    columns = set(table.column_names)
    missing = _REQUIRED_COLUMNS - columns
    if missing:
        raise UploadValidationError(
            f"File is missing required columns: {', '.join(sorted(missing))}. "
            f"Expected: {', '.join(sorted(_REQUIRED_COLUMNS))}"
        )
    token_col = table.column("Token")
    for val in token_col:
        token = val.as_py()
        if token and token != "0" * 64:
            return token
    return None


def _validate_schema_and_extract_sample_token(
    file_path: Path,
) -> tuple[str | None, dict | None]:
    """
    Validate that the upload file has the required schema and extract a sample token.

    For ZIP files the inner data file is inspected without extracting it to disk.
    The ZIP itself is what gets uploaded.

    Inputs:
        file_path: Path to the file being uploaded (CSV, Parquet, or ZIP).

    Returns:
        A tuple of (sample_token, zip_metadata) where:
        - sample_token is the first non-blank Token value found (or None if all blank).
        - zip_metadata is the parsed metadata dict embedded in the ZIP, or None for non-ZIP uploads.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".zip":
        return _validate_zip(file_path)

    if suffix == ".csv":
        with file_path.open("rb") as f:
            token = _validate_csv_columns(f)
        return token, None

    if suffix == ".parquet":
        token = _validate_parquet_columns(file_path.read_bytes())
        return token, None

    raise UploadValidationError(f"Unsupported file format: {suffix!r}")


def _validate_zip(zip_path: Path) -> tuple[str | None, dict | None]:
    """
    Validate the contents of a ZIP and return a sample token and embedded metadata.

    Expects exactly one CSV or Parquet data file inside the ZIP.

    Inputs:
        zip_path: Path to the ZIP file.

    Returns:
        A tuple of (sample_token, zip_metadata).
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            all_names = zf.namelist()

            data_names = [
                n
                for n in all_names
                if Path(n).suffix.lower() in _SUPPORTED_DATA_EXTENSIONS
            ]
            if not data_names:
                raise UploadValidationError(
                    f"ZIP contains no supported data file. "
                    f"Expected one file with extension: {', '.join(sorted(_SUPPORTED_DATA_EXTENSIONS))}"
                )
            if len(data_names) > 1:
                raise UploadValidationError(
                    f"ZIP contains multiple data files: {data_names}. "
                    "Only one CSV or Parquet file is allowed per ZIP."
                )

            data_name = data_names[0]
            data_suffix = Path(data_name).suffix.lower()

            try:
                data_bytes = zf.read(data_name)
            except RuntimeError as exc:
                raise UploadValidationError(
                    "Could not read ZIP entry (password-protected ZIPs are not supported)."
                ) from exc

            if data_suffix == ".csv":
                sample_token = _validate_csv_columns(io.BytesIO(data_bytes))
            else:
                sample_token = _validate_parquet_columns(data_bytes)

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

            return sample_token, zip_metadata

    except zipfile.BadZipFile as exc:
        raise UploadValidationError(f"File is not a valid ZIP archive: {exc}") from exc


def _decrypt_sample_token(token: str, transport_key: bytes) -> None:
    """
    Attempt to decrypt a token using the given transport key.

    Inputs:
        token: The raw token string (may include the 'olt.V1.' prefix).
        transport_key: The 32-byte AES-GCM key derived from the exchange config.

    Returns:
        None. Raises UploadValidationError on decryption failure.
    """
    try:
        from jwcrypto import jwe, jwk
    except ImportError as exc:
        raise UploadValidationError(
            "jwcrypto is required for token validation. Install with: uv pip install jwcrypto"
        ) from exc

    jwe_body = (
        token[len(V1_TOKEN_PREFIX) :] if token.startswith(V1_TOKEN_PREFIX) else token
    )
    key_b64 = base64.urlsafe_b64encode(transport_key).decode().rstrip("=")
    jwk_key = jwk.JWK(kty="oct", k=key_b64)
    try:
        jwe_token = jwe.JWE()
        jwe_token.deserialize(jwe_body)
        jwe_token.decrypt(jwk_key)
    except Exception as exc:
        raise UploadValidationError(
            "Token decryption failed. The file was not encrypted with the current exchange config. "
            "Re-package the data using 'olt package --exchange-config <current-config>'."
        ) from exc


def _validate_token_encryption(sample_token: str | None, domain: str) -> None:
    """
    Validate that a sample token can be decrypted using the current exchange config.

    Skipped when sample_token is None (all tokens were blank) or when the token
    does not use the V1 JWE format.

    Inputs:
        sample_token: A token value from the data file to test decryption against.
        domain: The storage domain used to locate the cached exchange config.

    Returns:
        None. Raises UploadValidationError or ExchangeConfigError on failure.
    """
    if not sample_token or not sample_token.startswith(V1_TOKEN_PREFIX):
        return

    try:
        from openlinktoken.exchange_config import derive_transport_encryption_key

        from openlinktoken_ext_truveta.exchange.config import (
            _load_resolve_exchange_inputs,
        )
        from openlinktoken_ext_truveta.exchange.config import (
            load_exchange_config as _load_exchange_config,
        )
        from openlinktoken_ext_truveta.paths import (
            private_key_path as _private_key_path,
        )
    except ImportError as exc:
        raise UploadValidationError(
            f"Required package for token validation is unavailable: {exc}"
        ) from exc

    try:
        exchange_config_raw = _load_exchange_config(domain)
        private_key_file = _private_key_path()
        if not private_key_file.exists():
            raise ExchangeConfigError(f"Private key not found at {private_key_file}")
        resolve_inputs = _load_resolve_exchange_inputs()
        resolved = resolve_inputs(
            exchange_config_value=exchange_config_raw,
            private_key_value=private_key_file.read_bytes(),
        )
        transport_key = derive_transport_encryption_key(resolved)
    except ExchangeConfigError:
        raise
    except Exception as exc:
        raise UploadValidationError(
            f"Could not derive transport key from exchange config: {exc}"
        ) from exc

    _decrypt_sample_token(sample_token, transport_key)


def _discover_metadata_file(data_file: Path) -> Path | None:
    """
    Find metadata file matching <basename>.metadata.json next to the data file.

    Inputs:
        data_file: The tokenized data file path.

    Returns:
        Path to metadata file if present, else None.
    """
    candidate = data_file.with_name(f"{data_file.stem}.metadata.json")
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def _build_exchange_metadata(domain: str) -> dict[str, Any]:
    """
    Build upload metadata from the cached exchange config.

    Extracts exchange fields required for server-side validation of the encrypt/package flow.

    Inputs:
        domain: The storage domain key used to locate the cached exchange config.

    Returns:
        The upload metadata payload derived from the cached exchange configuration.
    """
    payload = resolve_exchange_payload(domain)

    required_fields = [
        "exchangeId",
        "senderKeyFingerprint",
        "recipientKeyFingerprint",
        "curve",
    ]
    for required_field in required_fields:
        if not payload.get(required_field):
            raise ExchangeConfigError(
                f"Exchange config is missing required field {required_field!r}"
            )

    return {
        "payload": {
            "exchangeId": payload["exchangeId"],
            "exchangeName": payload.get("exchangeName"),
            "senderKeyFingerprint": payload["senderKeyFingerprint"],
            "recipientKeyFingerprint": payload["recipientKeyFingerprint"],
            "curve": payload["curve"],
            "createdAt": payload.get("createdAt"),
        }
    }


def _package_as_zip(
    data_path: Path, metadata_bytes: bytes, exchange_config_bytes: bytes
) -> PreparedUpload:
    """
    Package a raw CSV/Parquet data file and required JSON sidecars into an in-memory ZIP.

    The ZIP is built in a BytesIO buffer rather than written to disk, since it is
    immediately re-read for chunked upload and discarded afterward.

    Args:
        data_path: Path to the raw CSV or Parquet data file.
        metadata_bytes: Raw JSON bytes to embed as metadata.json inside the ZIP.
        exchange_config_bytes: Raw JSON bytes to embed as exchange-config.json.

    Returns:
        A PreparedUpload wrapping the in-memory ZIP, positioned at the start.

    Raises:
        UploadPackagingError: The ZIP could not be built.
    """
    buffer = io.BytesIO()
    try:
        # ZIP_STORED (no compression): token data is encrypted/hashed and has near-maximum
        # entropy, so DEFLATE would spend CPU without meaningfully shrinking the payload.
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as zf:
            zf.write(data_path, arcname=data_path.name)
            zf.writestr("metadata.json", metadata_bytes)
            zf.writestr("exchange-config.json", exchange_config_bytes)
    except OSError as exc:
        raise UploadPackagingError(f"Unable to build upload ZIP: {exc}") from exc

    size = buffer.getbuffer().nbytes
    buffer.seek(0)
    return PreparedUpload(stream=buffer, size=size, filename=f"{data_path.stem}.zip")


def _package_existing_zip(
    zip_path: Path, exchange_config_bytes: bytes
) -> PreparedUpload:
    """Prepare an existing ZIP for upload.

    Args:
        zip_path: Path to the user-provided ZIP archive.
        exchange_config_bytes: JSON bytes to add when the archive lacks
            ``exchange-config.json``.

    Returns:
        A PreparedUpload. When the archive already contains exchange-config.json,
        it wraps the original file opened for reading, since no changes are
        needed. Otherwise it wraps an in-memory ZIP built from the source entries
        plus the added entry, avoiding an on-disk copy.

    Raises:
        UploadPackagingError: The augmented ZIP could not be built.
    """
    with zipfile.ZipFile(zip_path, "r") as source:
        names = source.namelist()
        _validate_zip_member_names(names)
        if "exchange-config.json" in names:
            return PreparedUpload(
                stream=zip_path.open("rb"),
                size=zip_path.stat().st_size,
                filename=zip_path.name,
            )

    buffer = io.BytesIO()
    try:
        with (
            zipfile.ZipFile(zip_path, "r") as source,
            zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as target,
        ):
            for name in names:
                target.writestr(name, source.read(name))
            target.writestr("exchange-config.json", exchange_config_bytes)
    except OSError as exc:
        raise UploadPackagingError(f"Unable to build upload ZIP: {exc}") from exc

    size = buffer.getbuffer().nbytes
    buffer.seek(0)
    return PreparedUpload(stream=buffer, size=size, filename=zip_path.name)


def _validate_zip_member_names(names: list[str]) -> None:
    """Reject archive members that could escape the logical ZIP root."""
    if len(names) != len(set(names)):
        raise UploadValidationError("ZIP contains duplicate member names")

    for name in names:
        path = PurePosixPath(name)
        if not name or name.startswith("/") or "\\" in name or ".." in path.parts:
            raise UploadValidationError(f"ZIP contains unsafe member path: {name!r}")


def _upload(args: argparse.Namespace) -> int:
    """
    Upload tokenized output data to Truveta for self-serve overlap analysis.

    Uses the 3-step chunked upload flow:
    1. Initialize session — validates exchange and returns maxChunkSizeBytes. The exchange ID
       itself identifies the upload session for the remaining steps.
    2. Upload chunks — file is split into chunks of maxChunkSizeBytes and sent sequentially.
    3. Finalize session — server reassembles chunks and triggers downstream processing.

    Metadata and exchange config are bundled into the ZIP before initialization.
    Progress is printed to stdout after each chunk.

    Args:
        args: Parsed CLI arguments containing --input and optional --metadata.

    Returns:
        Exit code (0 on success, 1 on failure).
    """
    input_file = getattr(args, "input", None)
    metadata_arg = getattr(args, "metadata", None)

    if not input_file:
        print("Error: --input is required", file=sys.stderr)
        return 1

    file_path = Path(input_file)
    if not file_path.exists():
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
        return 1

    if not file_path.is_file():
        print(f"Error: Input path is not a file: {input_file}", file=sys.stderr)
        return 1

    suffix = file_path.suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(ext.lstrip(".") for ext in _SUPPORTED_EXTENSIONS))
        print(
            f"Error: Unsupported file format {suffix!r}. Supported formats: {supported}",
            file=sys.stderr,
        )
        return 1

    is_zip = suffix == ".zip"

    if is_zip and metadata_arg:
        print(
            "Warning: --metadata is ignored when uploading a ZIP file. "
            "Include the metadata file inside the ZIP instead.",
            file=sys.stderr,
        )

    try:
        sample_token, zip_metadata = _validate_schema_and_extract_sample_token(
            file_path
        )
    except UploadValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    metadata_path: Path | None
    if is_zip:
        metadata_path = None
    elif metadata_arg:
        metadata_path = Path(metadata_arg)
        if not metadata_path.exists() or not metadata_path.is_file():
            print(f"Error: Metadata file not found: {metadata_arg}", file=sys.stderr)
            return 1
    else:
        metadata_path = _discover_metadata_file(file_path)

    try:
        context: AuthenticatedCommandContext = resolve_authenticated_context(args)
    except SessionResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    domain = context.storage_domain

    try:
        exchange_metadata = _build_exchange_metadata(domain)
    except ExchangeConfigError as exc:
        print(
            f"Error: Exchange configuration not found. Run 'olt truveta initiate-exchange' first: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        _validate_token_encryption(sample_token, domain)
    except (UploadValidationError, ExchangeConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    exchange_config_file = resolve_exchange_config_path()
    if not exchange_config_file.exists():
        print(
            f"Error: Exchange config file not found at {exchange_config_file}. "
            "Run 'olt truveta initiate-exchange' to generate it.",
            file=sys.stderr,
        )
        return 1

    exchange_id = exchange_metadata["payload"]["exchangeId"]
    timeout_secs = resolve_timeout_seconds(args)

    # The CLI always uploads a ZIP, regardless of the input format. This keeps
    # metadata resolution and upload chunking on a single code path instead of
    # branching on raw-file vs. ZIP input.
    try:
        if is_zip:
            metadata_bytes = (
                json.dumps(zip_metadata).encode()
                if zip_metadata is not None
                else json.dumps(exchange_metadata).encode()
            )
            prepared_upload = _package_existing_zip(
                file_path, exchange_config_file.read_bytes()
            )
        else:
            metadata_bytes = (
                metadata_path.read_bytes()
                if metadata_path
                else json.dumps(exchange_metadata).encode()
            )
            prepared_upload = _package_as_zip(
                file_path, metadata_bytes, exchange_config_file.read_bytes()
            )
    except UploadPackagingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        return _run_upload(
            context=context,
            exchange_id=exchange_id,
            prepared_upload=prepared_upload,
            timeout_secs=timeout_secs,
        )
    finally:
        prepared_upload.close()


def _run_upload(
    *,
    context: AuthenticatedCommandContext,
    exchange_id: str,
    prepared_upload: PreparedUpload,
    timeout_secs: int | None,
) -> int:
    """
    Run the 3-step chunked upload flow (initialize, chunk, finalize) for a prepared file.

    Args:
        context: Authenticated command context (API URL, credentials).
        exchange_id: Exchange transaction ID. Also identifies the upload session.
        prepared_upload: The ZIP payload to upload, positioned at the start.
        timeout_secs: Optional request timeout override in seconds.

    Returns:
        Exit code (0 on success, 1 on failure).
    """
    file_size = prepared_upload.size
    try:
        # Step 1: Initialize session — validates exchange and returns server-authoritative chunk size.
        session_info = initialize_session(
            api_url=context.api_url,
            access_token=context.credentials.access_token,
            exchange_id=exchange_id,
            timeout_seconds=timeout_secs,
        )
    except UploadAPIError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(
            f"Error: Could not read metadata or exchange config file: {exc}",
            file=sys.stderr,
        )
        return 1

    if isinstance(session_info, UploadSessionInfo):
        max_chunk_size_bytes = session_info.max_chunk_size_bytes
        if file_size > session_info.max_file_size_bytes:
            print(
                f"Error: File size ({file_size} bytes) exceeds maximum "
                f"({session_info.max_file_size_bytes} bytes)",
                file=sys.stderr,
            )
            return 1
    else:
        max_chunk_size_bytes = session_info

    total_chunks = max(
        1, (file_size + max_chunk_size_bytes - 1) // max_chunk_size_bytes
    )

    print(
        f"Uploading {prepared_upload.filename} ({file_size / 1_048_576:.1f} MB, {total_chunks} chunk(s))"
    )

    chunk_index = 0
    file_hash = hashlib.sha256()
    try:
        # Step 2: Upload chunks sequentially with progress output.
        for chunk_index in range(total_chunks):
            chunk_data = prepared_upload.stream.read(max_chunk_size_bytes)
            file_hash.update(chunk_data)
            upload_chunk(
                api_url=context.api_url,
                access_token=context.credentials.access_token,
                exchange_id=exchange_id,
                chunk_index=chunk_index,
                chunk_data=chunk_data,
                timeout_seconds=timeout_secs,
            )
            percent = int((chunk_index + 1) / total_chunks * 100)
            print(f"chunk {chunk_index + 1}/{total_chunks} ({percent}%)")
    except UploadAPIError as exc:
        print(
            f"Upload interrupted at chunk {chunk_index + 1}/{total_chunks}. "
            "Run the upload command again to retry.",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 1

    try:
        # Step 3: Finalize — server verifies completeness and the full-file checksum,
        # assembles the file, and starts processing.
        finalize_session(
            api_url=context.api_url,
            access_token=context.credentials.access_token,
            exchange_id=exchange_id,
            file_name=prepared_upload.filename,
            total_chunk_count=total_chunks,
            file_checksum=file_hash.hexdigest(),
            timeout_seconds=timeout_secs,
        )
    except UploadAPIError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("\u2713 Upload accepted.")
    return 0
