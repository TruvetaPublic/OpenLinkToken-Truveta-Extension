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
    """Extract a useful error message from an API response."""
    try:
        error_json = response.json()
    except Exception:
        return response.text

    if isinstance(error_json, dict):
        return error_json.get("error", response.text)

    return response.text


def call_upload_endpoint(
    api_url: str,
    access_token: str,
    exchange_id: str,
    files: dict[str, Any],
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Call POST /v1/uploads/{exchangeId} and return JSON payload on success."""
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
                f"Upload failed: {response.status_code} - {_extract_error(response)}"
            )

        try:
            return response.json()
        except ValueError:
            return {}
    except UploadAPIError:
        raise
    except requests.RequestException as exc:
        raise UploadAPIError(f"Upload request failed: {exc}")
