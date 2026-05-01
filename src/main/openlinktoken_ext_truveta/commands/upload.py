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
from openlinktoken_ext_truveta.auth import (
    AuthError,
    Credentials,
    _extract_domain,
    _extract_service_domain,
    ensure_auth,
    get_api_domain_url,
)
from openlinktoken_ext_truveta.commands import common as common_commands
from openlinktoken_ext_truveta.commands.common import (
    SessionResolutionError,
    _is_local_dev,
    resolve_api_url,
    resolve_auth_url,
    resolve_timeout_seconds,
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
    1. Validate data file exists and is readable
    2. Resolve metadata path (explicit flag or auto-discovery)
    3. Ensure exchange config exists for the domain
    4. Authenticate using cached credentials only
    5. Call POST /v1/upload with multipart form data
    6. Return upload result

    Inputs:
        args: Parsed CLI arguments containing --file and optional --metadata.

    Returns:
        Exit code (0 on success, 1 on failure).
    """
    input_file = getattr(args, "file", None)
    metadata_arg = getattr(args, "metadata", None)

    if not input_file:
        print("Error: --file is required", file=sys.stderr)
        return 1

    file_path = Path(input_file)
    if not file_path.exists():
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
        return 1

    if not file_path.is_file():
        print(f"Error: Input path is not a file: {input_file}", file=sys.stderr)
        return 1

    metadata_path: Path | None
    if metadata_arg:
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
        if _is_local_dev(args):
            url = resolve_api_url(args)
            auth_url = resolve_auth_url(args)
        else:
            session_auth_url = common_commands.read_session_auth_url()
            if not session_auth_url:
                raise SessionResolutionError(
                    "No login session found. Please run 'olt truveta login' first."
                )

            auth_url = session_auth_url
            url = get_api_domain_url(_extract_domain(session_auth_url))
    except SessionResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    domain = _extract_service_domain(url)

    # Ensure exchange config exists
    try:
        exchange_metadata = _build_exchange_metadata(domain)
    except ExchangeConfigError as exc:
        print(
            f"Error: Exchange configuration not found. Run 'olt truveta initiate-exchange' first: {exc}",
            file=sys.stderr,
        )
        return 1

    # Authenticate
    try:
        credentials: Credentials = ensure_auth(auth_url, cached_only=True)
    except AuthError as exc:
        print(
            f"Authentication failed: {exc} Please run 'olt truveta login' first.",
            file=sys.stderr,
        )
        return 1

    # Upload data and optional metadata as multipart form data
    try:
        with contextlib.ExitStack() as stack:
            data_handle = stack.enter_context(file_path.open("rb"))
            files = {
                "dataFile": (file_path.name, data_handle, "application/octet-stream"),
            }

            metadata_json = json.dumps(exchange_metadata)

            if metadata_path is not None:
                metadata_handle = stack.enter_context(metadata_path.open("rb"))
                files["metadataFile"] = (
                    metadata_path.name,
                    metadata_handle,
                    "application/json",
                )
            else:
                files["metadataFile"] = (
                    f"{file_path.stem}.metadata.json",
                    metadata_json,
                    "application/json",
                )

            payload = call_upload_endpoint(
                url,
                credentials.access_token,
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
