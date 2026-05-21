"""
Copyright (c) Truveta. All rights reserved.

upload command: upload tokenized output data to Truveta for overlap analysis.
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from openlinktoken_ext_truveta.api import upload as upload_api
from openlinktoken_ext_truveta.api.upload import UploadAPIError, call_upload_endpoint
from openlinktoken_ext_truveta.commands.common import (
    AuthenticatedCommandContext,
    SessionResolutionError,
    resolve_authenticated_context,
    resolve_timeout_seconds,
)
from openlinktoken_ext_truveta.commands.upload_validation import (
    SUPPORTED_EXTENSIONS,
    FileExtension,
    validate_file,
    validate_token_encryption,
)
from openlinktoken_ext_truveta.exchange.config import (
    ExchangeConfigError,
    resolve_exchange_payload,
)

# Preserve test monkeypatch compatibility for requests.post patch targets.
requests = upload_api.requests


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
    Raises ExchangeConfigError if any required field is missing.

    Args:
        domain: The Truveta domain used to locate the cached exchange config.

    Returns:
        A dict containing the exchange metadata payload required by the upload endpoint.
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


def _upload(args: argparse.Namespace) -> int:
    """
    Upload tokenized output data and metadata to Truveta for self-serve overlap analysis.

    Steps:
    1. Validate the file extension is supported
    2. Validate schema (required columns: RuleId, Token, RecordId)
    3. Validate a sample token can be decrypted with the current exchange config
    4. Resolve metadata (from ZIP, explicit flag, auto-discovery, or generated)
    5. Authenticate using cached credentials only
    6. Call POST /v1/upload with multipart form data
    7. Return upload result

    For ZIP files: the ZIP is uploaded as-is; its contents are only inspected locally
    for schema and encryption validation. If --metadata is passed with a ZIP, it is
    ignored with a warning.

    Inputs:
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
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS))
        print(
            f"Error: Unsupported file format {suffix!r}. Supported formats: {supported}",
            file=sys.stderr,
        )
        return 1

    is_zip = suffix == FileExtension.ZIP

    if is_zip and metadata_arg:
        print(
            "Warning: --metadata is ignored when uploading a ZIP file. "
            "Include the metadata file inside the ZIP instead.",
            file=sys.stderr,
        )

    # Validate schema and extract a sample token for encryption verification
    sample_token, zip_metadata, schema_error = validate_file(file_path)
    if schema_error:
        print(f"Error: {schema_error}", file=sys.stderr)
        return 1

    # Resolve metadata path for non-ZIP uploads
    metadata_path: Path | None
    if is_zip:
        metadata_path = None
    elif metadata_arg:
        metadata_path = Path(metadata_arg)
        if not metadata_path.exists() or not metadata_path.is_file():
            print(
                f"Error: Metadata file not found: {metadata_arg}",
                file=sys.stderr,
            )
            return 1
    else:
        metadata_path = _discover_metadata_file(file_path)

    try:
        context: AuthenticatedCommandContext = resolve_authenticated_context(args)
    except SessionResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    domain = context.storage_domain

    # Ensure exchange config exists and validate token encryption
    try:
        exchange_metadata = _build_exchange_metadata(domain)
    except ExchangeConfigError as exc:
        print(
            f"Error: Exchange configuration not found. Run 'olt truveta initiate-exchange' first: {exc}",
            file=sys.stderr,
        )
        return 1

    encryption_error = validate_token_encryption(sample_token, domain)
    if encryption_error:
        print(f"Error: {encryption_error}", file=sys.stderr)
        return 1

    # Upload data and metadata as multipart form data
    try:
        with contextlib.ExitStack() as stack:
            data_handle = stack.enter_context(file_path.open("rb"))
            files = {
                "dataFile": (file_path.name, data_handle, "application/octet-stream"),
            }

            if is_zip and zip_metadata is not None:
                metadata_json = json.dumps(zip_metadata)
                files["metadataFile"] = (
                    f"{file_path.stem}.metadata.json",
                    metadata_json,
                    "application/json",
                )
            elif not is_zip and metadata_path is not None:
                metadata_handle = stack.enter_context(metadata_path.open("rb"))
                files["metadataFile"] = (
                    metadata_path.name,
                    metadata_handle,
                    "application/json",
                )
            else:
                metadata_json = json.dumps(exchange_metadata)
                files["metadataFile"] = (
                    f"{file_path.stem}.metadata.json",
                    metadata_json,
                    "application/json",
                )

            payload = call_upload_endpoint(
                context.api_url,
                context.credentials.access_token,
                exchange_metadata["payload"]["exchangeId"],
                files,
                timeout_seconds=resolve_timeout_seconds(args),
            )
        upload_reference_id = payload.get("uploadReferenceId")

        print("✓ Upload accepted.")
        if upload_reference_id:
            print(f"Upload reference ID: {upload_reference_id}")

        return 0

    except FileNotFoundError:
        print("Error: Could not read input or metadata file", file=sys.stderr)
        return 1
    except UploadAPIError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Upload failed with unexpected error: {exc}", file=sys.stderr)
        return 1
