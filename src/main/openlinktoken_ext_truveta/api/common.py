"""
Copyright (c) Truveta. All rights reserved.

Shared helpers for OpenLink Token API clients.
"""

import requests

DEFAULT_TIMEOUT_SECONDS = 30


def resolve_timeout_seconds(timeout_seconds: int | None) -> int:
    """
    Resolve request timeout seconds using explicit override or default.

    Inputs:
        timeout_seconds: An optional explicit timeout override in seconds.

    Returns:
        The explicit timeout when supplied, otherwise the API default timeout.
    """
    return timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SECONDS


def extract_error_body(response: requests.Response) -> str:
    """
    Extract a human-readable error message from an API response.

    Inputs:
        response: The HTTP response to extract error detail from.

    Returns:
        A human-readable error string from the JSON "error" field or raw response text.
    """
    try:
        error_json = response.json()
    except Exception:
        return response.text

    if isinstance(error_json, dict):
        return error_json.get("error", response.text)

    return response.text


def format_api_error(url: str, message: str, *, operation: str = "API call") -> str:
    """
    Format an API failure with the resolved endpoint URL for easier diagnosis.

    Inputs:
        url: The fully resolved endpoint URL.
        message: The underlying failure message to surface.
        operation: A label for the operation type (e.g. "Upload", "Exchange").

    Returns:
        A formatted error string that includes the target URL and failure detail.
    """
    return f"{operation} failed for {url}: {message}"


def probe_for_http_status(
    url: str,
    access_token: str,
    timeout: int,
    *,
    probe_files: dict | None = None,
    probe_json: dict | None = None,
) -> str | None:
    """
    Send a minimal authenticated POST to recover the real HTTP status after an SSL drop.

    When the server closes a connection mid-stream, the actual HTTP error response is
    never received. This probe sends a tiny POST to the same endpoint to surface the
    real status code.

    Inputs:
        url: The fully resolved endpoint URL to probe.
        access_token: OAuth access token for authorization.
        timeout: Request timeout in seconds.
        probe_files: Optional multipart file dict to include in the probe POST.
        probe_json: Optional JSON body dict to include in the probe POST.

    Returns:
        A human-readable status string (e.g. "401 - Unauthorized") when the probe
        reveals a server-side rejection, or None when the probe succeeds or fails
        without producing a usable HTTP response.
    """
    try:
        kwargs: dict = {}
        if probe_files is not None:
            kwargs["files"] = probe_files
        if probe_json is not None:
            kwargs["json"] = probe_json
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
            **kwargs,
        )
        if not (200 <= response.status_code < 300):
            return f"{response.status_code} - {extract_error_body(response)}"
    except Exception:
        pass
    return None


def ssl_drop_message(probe_detail: str | None, *, generic_hint: str) -> str:
    """
    Derive a user-facing message from the probe result after an SSL connection drop.

    Authentication errors (401/403) and conflicts (409) are unambiguously caused by
    the request context rather than the probe payload, so those are surfaced directly.
    All other statuses fall back to the provided generic hint.

    Inputs:
        probe_detail: The string returned by probe_for_http_status, or None.
        generic_hint: The fallback message when no specific error is identifiable.

    Returns:
        A human-readable message suitable for raising as an API error detail.
    """
    if probe_detail:
        status_str = probe_detail.split(" - ", 1)[0]
        try:
            status = int(status_str)
        except ValueError:
            status = 0

        if status in (401, 403):
            return (
                f"Authentication failed ({probe_detail}). "
                "Run 'olt truveta login' to re-authenticate."
            )
        if status == 409:
            return probe_detail

    return generic_hint
