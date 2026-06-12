"""
Copyright (c) Truveta. All rights reserved.

Upload endpoint API client for tokenized payload submission.
"""

from typing import Any

import requests

from openlinktoken_ext_truveta.api.common import (
    extract_error_body,
    format_api_error,
    probe_for_http_status,
    resolve_timeout_seconds,
    ssl_drop_message,
)


class UploadAPIError(Exception):
    """Raised when upload API calls fail."""


_UPLOAD_SSL_HINT = (
    "Server dropped the connection while uploading. "
    "The exchange may have expired — try 'olt truveta initiate-exchange'."
)


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
                format_api_error(
                    upload_url,
                    f"{response.status_code} - {extract_error_body(response)}",
                    operation="Upload",
                )
            )

        try:
            return response.json()
        except ValueError:
            return {}
    except UploadAPIError:
        raise
    except requests.exceptions.SSLError as exc:
        probe_detail = probe_for_http_status(
            upload_url,
            access_token,
            request_timeout,
            probe_files={"dataFile": ("probe.csv", b"", "application/octet-stream")},
        )
        raise UploadAPIError(
            format_api_error(
                upload_url,
                ssl_drop_message(probe_detail, generic_hint=_UPLOAD_SSL_HINT),
                operation="Upload",
            )
        ) from exc
    except requests.RequestException as exc:
        raise UploadAPIError(format_api_error(upload_url, str(exc), operation="Upload"))
