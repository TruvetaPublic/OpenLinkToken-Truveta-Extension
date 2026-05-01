"""
Copyright (c) Truveta. All rights reserved.

Upload endpoint API client for tokenized payload submission.
"""

from typing import Any

import requests

from openlinktoken_ext_truveta.api.common import resolve_timeout_seconds


class UploadAPIError(Exception):
    """Raised when upload API calls fail."""


def _extract_error(response: requests.Response) -> str:
    """
    Extract a useful error message from an API response.

    Inputs:
        response: The HTTP response returned by the upload endpoint.

    Returns:
        A human-readable error string extracted from JSON payloads or raw text.
    """
    try:
        error_json = response.json()
    except Exception:
        return response.text

    if isinstance(error_json, dict):
        return error_json.get("error", response.text)

    return response.text


def _format_upload_error(upload_url: str, message: str) -> str:
    """
    Format upload failures with the resolved target URL for easier diagnosis.

    Inputs:
        upload_url: The fully resolved upload endpoint URL.
        message: The underlying failure message to surface.

    Returns:
        A formatted error string that includes the target URL and failure detail.
    """
    return f"Upload failed for {upload_url}: {message}"


def call_upload_endpoint(
    api_url: str,
    access_token: str,
    exchange_id: str,
    files: dict[str, Any],
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """
    Call POST /v1/uploads/{exchangeId} and return JSON payload on success.

    Inputs:
        api_url: The base API URL for uploads, including the /openlink path when hosted.
        access_token: The OAuth access token used for authorization.
        exchange_id: The exchange identifier for the upload target.
        files: Multipart upload parts for the data and metadata payloads.
        timeout_seconds: An optional request timeout override in seconds.

    Returns:
        The parsed JSON payload returned by the upload endpoint, or an empty
        dictionary when the endpoint responds with no JSON body.
    """
    upload_url = f"{api_url.rstrip('/')}/v1/uploads/{exchange_id}"
    request_timeout = resolve_timeout_seconds(timeout_seconds)

    try:
        response = requests.post(
            upload_url,
            files=files,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=request_timeout,
        )

        if response.status_code != 202:
            raise UploadAPIError(
                _format_upload_error(
                    upload_url,
                    f"{response.status_code} - {_extract_error(response)}",
                )
            )

        try:
            return response.json()
        except ValueError:
            return {}
    except UploadAPIError:
        raise
    except requests.RequestException as exc:
        raise UploadAPIError(_format_upload_error(upload_url, str(exc)))
