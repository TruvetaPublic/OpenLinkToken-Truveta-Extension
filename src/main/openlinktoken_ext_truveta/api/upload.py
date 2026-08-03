"""
Copyright (c) Truveta. All rights reserved.

Upload endpoint API client for tokenized payload submission.
"""

import hashlib

import requests

from openlinktoken_ext_truveta.api.common import (
    extract_error_body,
    format_api_error,
    resolve_timeout_seconds,
)


class UploadAPIError(Exception):
    """Raised when upload API calls fail."""


def initialize_session(
    api_url: str,
    access_token: str,
    exchange_id: str,
    file_name: str,
    timeout_seconds: int | None = None,
) -> int:
    """
    POST /v1/uploads/{exchangeId} to create a new chunked upload session for this exchange.

    Validates the exchange upfront so the client fails fast before sending any data.
    The exchange ID itself identifies the upload session for all subsequent chunk and
    finalize calls. The server returns the maximum chunk size to use for this session.

    Args:
        api_url: Base API URL including the /openlink path when hosted.
        access_token: OAuth access token for authorization.
        exchange_id: Exchange transaction ID. Also identifies the upload session.
        file_name: Name of the file being uploaded.
        timeout_seconds: Optional request timeout override in seconds.

    Returns:
        max_chunk_size_bytes.

    Raises:
        UploadAPIError: On non-201 response.
    """
    session_url = f"{api_url.rstrip('/')}/v1/uploads/{exchange_id}"
    request_timeout = resolve_timeout_seconds(timeout_seconds)

    try:
        response = requests.post(
            session_url,
            json={"fileName": file_name},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=request_timeout,
        )

        if response.status_code != 201:
            raise UploadAPIError(
                format_api_error(
                    session_url,
                    f"{response.status_code} - {extract_error_body(response)}",
                    operation="Initialize session",
                )
            )

        payload = response.json()
        return payload["maxChunkSizeBytes"]

    except UploadAPIError:
        raise
    except requests.RequestException as exc:
        raise UploadAPIError(
            format_api_error(session_url, str(exc), operation="Initialize session")
        ) from exc


def upload_chunk(
    api_url: str,
    access_token: str,
    exchange_id: str,
    chunk_index: int,
    chunk_data: bytes,
    timeout_seconds: int | None = None,
) -> None:
    """
    POST /v1/uploads/{exchangeId}/chunks to send one chunk.

    Computes a SHA-256 checksum of the chunk bytes and includes it in the request
    so the server can verify data integrity before storing the chunk.

    Args:
        api_url: Base API URL including the /openlink path when hosted.
        access_token: OAuth access token for authorization.
        exchange_id: Exchange transaction ID. Also identifies the upload session.
        chunk_index: 0-based index of this chunk within the session.
        chunk_data: Raw bytes of this chunk.
        timeout_seconds: Optional request timeout override in seconds.

    Raises:
        UploadAPIError: On non-200 response, including checksum mismatch detail.
    """
    chunk_url = f"{api_url.rstrip('/')}/v1/uploads/{exchange_id}/chunks"
    request_timeout = resolve_timeout_seconds(timeout_seconds)
    checksum = hashlib.sha256(chunk_data).hexdigest()

    try:
        response = requests.post(
            chunk_url,
            params={
                "chunkIndex": str(chunk_index),
                "chunkChecksum": checksum,
            },
            data=chunk_data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/octet-stream",
            },
            timeout=request_timeout,
        )

        if response.status_code != 200:
            raise UploadAPIError(
                format_api_error(
                    chunk_url,
                    f"{response.status_code} - {extract_error_body(response)}",
                    operation=f"Upload chunk {chunk_index}",
                )
            )

    except UploadAPIError:
        raise
    except requests.RequestException as exc:
        raise UploadAPIError(
            format_api_error(
                chunk_url, str(exc), operation=f"Upload chunk {chunk_index}"
            )
        ) from exc


def finalize_session(
    api_url: str,
    access_token: str,
    exchange_id: str,
    file_name: str,
    total_chunk_count: int,
    file_checksum: str,
    timeout_seconds: int | None = None,
) -> None:
    """
    POST /v1/uploads/{exchangeId}/complete to finalize the upload.

    Signals the server that all chunks have been sent and provides the original file
    name, total chunk count, and SHA-256 checksum of the complete original file so the
    server can verify completeness and that the reassembled file matches before starting
    downstream processing. The server does not persist any state across the initialize,
    chunk, and finalize calls, so this information must be resent here. Processing only
    starts after this call returns successfully.

    Args:
        api_url: Base API URL including the /openlink path when hosted.
        access_token: OAuth access token for authorization.
        exchange_id: Exchange transaction ID. Also identifies the upload session.
        file_name: Name of the file being uploaded. Must match the name passed to
            initialize_session.
        total_chunk_count: Total number of chunks that were sent. Must match the count
            passed to initialize_session.
        file_checksum: SHA-256 hex digest of the complete original file, computed by the
            client from the same bytes that were chunked.
        timeout_seconds: Optional request timeout override in seconds.

    Raises:
        UploadAPIError: On non-202 response, including checksum mismatch or
            incomplete-session detail.
    """
    finalize_url = f"{api_url.rstrip('/')}/v1/uploads/{exchange_id}/complete"
    request_timeout = resolve_timeout_seconds(timeout_seconds)

    try:
        response = requests.post(
            finalize_url,
            json={
                "fileName": file_name,
                "totalChunkCount": total_chunk_count,
                "fileChecksum": file_checksum,
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=request_timeout,
        )

        if response.status_code != 202:
            raise UploadAPIError(
                format_api_error(
                    finalize_url,
                    f"{response.status_code} - {extract_error_body(response)}",
                    operation="Finalize session",
                )
            )

    except UploadAPIError:
        raise
    except requests.RequestException as exc:
        raise UploadAPIError(
            format_api_error(finalize_url, str(exc), operation="Finalize session")
        ) from exc
