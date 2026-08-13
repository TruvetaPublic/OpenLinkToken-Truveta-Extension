"""
Copyright (c) Truveta. All rights reserved.

upload command: upload tokenized output data to Truveta for overlap analysis.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

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
from openlinktoken_ext_truveta.commands import upload_validation

_SUPPORTED_EXTENSIONS = upload_validation.SUPPORTED_EXTENSIONS


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


def _build_exchange_metadata() -> dict[str, Any]:
    """
    Build upload metadata from the cached exchange config.

    Extracts exchange fields required for server-side validation of the encrypt/package flow.

    Returns:
        The upload metadata payload derived from the cached exchange configuration.
    """
    payload = resolve_exchange_payload()

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
) -> Path:
    """
    Package a raw CSV/Parquet data file and required JSON sidecars into a ZIP.

    The CLI always uploads a ZIP regardless of the input format, with metadata and
    exchange configuration embedded as JSON entries.

    Args:
        data_path: Path to the raw CSV or Parquet data file.
        metadata_bytes: Raw JSON bytes to embed as metadata.json inside the ZIP.
        exchange_config_bytes: Raw JSON bytes to embed as exchange-config.json.

    Returns:
        Path to a newly created temporary ZIP file. The caller is responsible for
        deleting it once the upload completes.
    """
    zip_fd, zip_path_str = tempfile.mkstemp(suffix=".zip", prefix="upload-")
    os.close(zip_fd)

    zip_path = Path(zip_path_str)
    # ZIP_STORED (no compression): token data is encrypted/hashed and has near-maximum
    # entropy, so DEFLATE would spend CPU without meaningfully shrinking the payload.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        zf.write(data_path, arcname=data_path.name)
        zf.writestr("metadata.json", metadata_bytes)
        zf.writestr("exchange-config.json", exchange_config_bytes)

    return zip_path


def _package_existing_zip(zip_path: Path, exchange_config_bytes: bytes) -> Path:
    """Copy an existing ZIP and add the required exchange config entry when absent."""
    zip_fd, output_path_str = tempfile.mkstemp(
        suffix=".zip", prefix=f"{zip_path.stem}-"
    )
    os.close(zip_fd)
    output_path = Path(output_path_str)

    with (
        zipfile.ZipFile(zip_path, "r") as source,
        zipfile.ZipFile(output_path, "w", zipfile.ZIP_STORED) as target,
    ):
        names = source.namelist()
        _validate_zip_member_names(names)
        for name in names:
            target.writestr(name, source.read(name))
        if "exchange-config.json" not in names:
            target.writestr("exchange-config.json", exchange_config_bytes)

    return output_path


def _validate_zip_member_names(names: list[str]) -> None:
    """Reject archive members that could escape the logical ZIP root."""
    if len(names) != len(set(names)):
        raise upload_validation.UploadValidationError(
            "ZIP contains duplicate member names"
        )

    for name in names:
        path = PurePosixPath(name)
        if not name or name.startswith("/") or "\\" in name or ".." in path.parts:
            raise upload_validation.UploadValidationError(
                f"ZIP contains unsafe member path: {name!r}"
            )


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

    sample_token, zip_metadata, validation_error = upload_validation.validate_file(
        file_path
    )
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
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

    try:
        exchange_metadata = _build_exchange_metadata()
    except ExchangeConfigError as exc:
        print(
            f"Error: Exchange configuration not found. Run 'olt truveta initiate-exchange' first: {exc}",
            file=sys.stderr,
        )
        return 1

    validation_error = upload_validation.validate_token_encryption(sample_token)
    if validation_error:
        print(f"Error: {validation_error}", file=sys.stderr)
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
    if is_zip:
        metadata_bytes = (
            json.dumps(zip_metadata).encode()
            if zip_metadata is not None
            else json.dumps(exchange_metadata).encode()
        )
        upload_path = _package_existing_zip(
            file_path, exchange_config_file.read_bytes()
        )
        temp_zip_path: Path | None = upload_path
    else:
        metadata_bytes = (
            metadata_path.read_bytes()
            if metadata_path
            else json.dumps(exchange_metadata).encode()
        )
        upload_path = _package_as_zip(
            file_path, metadata_bytes, exchange_config_file.read_bytes()
        )
        temp_zip_path = upload_path

    try:
        file_size = upload_path.stat().st_size
        return _run_upload(
            context=context,
            exchange_id=exchange_id,
            upload_path=upload_path,
            file_size=file_size,
            timeout_secs=timeout_secs,
        )
    finally:
        if temp_zip_path is not None:
            temp_zip_path.unlink(missing_ok=True)


def _run_upload(
    *,
    context: AuthenticatedCommandContext,
    exchange_id: str,
    upload_path: Path,
    file_size: int,
    timeout_secs: int | None,
) -> int:
    """
    Run the 3-step chunked upload flow (initialize, chunk, finalize) for a prepared file.

    Args:
        context: Authenticated command context (API URL, credentials).
        exchange_id: Exchange transaction ID. Also identifies the upload session.
        upload_path: Path to the file to upload (always a ZIP).
        file_size: Size of upload_path in bytes.
        timeout_secs: Optional request timeout override in seconds.

    Returns:
        Exit code (0 on success, 1 on failure).
    """
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
        f"Uploading {upload_path.name} ({file_size / 1_048_576:.1f} MB, {total_chunks} chunk(s))"
    )

    chunk_index = 0
    file_hash = hashlib.sha256()
    try:
        # Step 2: Upload chunks sequentially with progress output.
        with upload_path.open("rb") as f:
            for chunk_index in range(total_chunks):
                chunk_data = f.read(max_chunk_size_bytes)
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
            file_name=upload_path.name,
            total_chunk_count=total_chunks,
            file_checksum=file_hash.hexdigest(),
            timeout_seconds=timeout_secs,
        )
    except UploadAPIError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("\u2713 Upload accepted.")
    return 0
