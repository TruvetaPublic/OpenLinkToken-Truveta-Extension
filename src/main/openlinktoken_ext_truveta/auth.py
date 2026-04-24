"""
Copyright (c) Truveta. All rights reserved.

OAuth 2.0 Device Code Flow authentication for the Truveta CLI.

Handles device code flow against Auth0, token caching, and building
authenticated headers for Truveta API requests.
"""

import base64
import json
import os
import re
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from openlinktoken_ext_truveta.paths import credentials_cache_path, session_file_path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_URL_PATTERN = re.compile(r"https://api\.([^/]+)")

_CLIENT_IDS: dict[str, str] = {
    "dev.truveta-int.com": "NLEN3QJPPoIPHA6bQ6XUM1qCfDmz5RrO",
    "truveta-int.com": "Ouw9CrFQy8nakVDmgdINXeCZ0iB1laxw",
    "truveta.com": "MV87rfAh0Qy5ExTXZIDKssdgoYUVBIbY",
}

_AUDIENCES: dict[str, str] = {
    "dev.truveta-int.com": "https://api.dev.truveta-int.com/openlink",
    "truveta-int.com": "https://api.truveta-int.com/openlink",
    "truveta.com": "https://api.truveta.com/openlink",
}

DEFAULT_DOMAIN_URL = "https://api.truveta.com"

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Raised when authentication fails or configuration is invalid."""


@dataclass
class Credentials:
    """Holds a pair of OAuth tokens returned by Auth0."""

    access_token: str
    id_token: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_domain(url: str) -> str:
    """
    Extract the domain portion from a Truveta API URL.

    Inputs:
        url: A Truveta API URL in the format https://api.<domain>.

    Returns:
        The domain string (e.g. "dev.truveta-int.com").
    """
    match = _API_URL_PATTERN.match(url)
    if match:
        return match.group(1)

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise AuthError(f"Invalid URL format: {url!r}: {exc}")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise AuthError(f"Invalid URL format: {url!r}. Expected: https://api.<domain>")

    # Accept login hostnames as auth-domain shorthand.
    if host.startswith("login."):
        return host[len("login.") :]

    # Accept full API hostnames even when additional path components are present.
    if host.startswith("api."):
        return host[len("api.") :]

    # Accept bare known domains for convenience in login/auth-domain flows.
    if host in _CLIENT_IDS:
        return host

    raise AuthError(
        f"Invalid URL format: {url!r}. Expected one of: "
        "https://api.<domain>, https://login.<domain>, or <domain>"
    )


def _extract_service_domain(url: str) -> str:
    """Extract a stable local storage key from a Truveta or local service URL."""
    try:
        return _extract_domain(url)
    except AuthError:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AuthError(
                f"Invalid URL format: {url!r}. Expected https://api.<domain> or http(s)://<host>[:port]"
            )

        if parsed.port:
            return f"{parsed.hostname}-{parsed.port}"

        return parsed.hostname


def _get_client_id(domain: str) -> str:
    """
    Return the Auth0 client ID for the given domain.

    Inputs:
        domain: The Truveta domain (e.g. "dev.truveta-int.com").

    Returns:
        The Auth0 client ID string.
    """
    client_id = _CLIENT_IDS.get(domain)
    if not client_id:
        raise AuthError(f"Unknown domain: {domain!r}. No Auth0 client ID configured.")
    return client_id


def _get_audience(domain: str) -> str:
    """
    Return the Auth0 audience for the given domain.

    Inputs:
        domain: The Truveta domain (e.g. "dev.truveta-int.com").

    Returns:
        The Auth0 audience URI string.
    """
    audience = _AUDIENCES.get(domain)
    if not audience:
        raise AuthError(f"Unknown domain: {domain!r}. No Auth0 audience configured.")
    return audience


def _cache_path(domain: str) -> Path:
    """
    Return the path to the credentials cache file for a domain.

    Inputs:
        domain: The Truveta domain (e.g. "dev.truveta-int.com").

    Returns:
        Path to the credentials.json file under ~/.openlinktoken/truveta/<domain>/.
    """
    return credentials_cache_path(domain)


def _session_path() -> Path:
    """
    Return the path to the extension session file.

    Returns:
        Path to session.json under ~/.openlinktoken/truveta/.
    """
    return session_file_path()


def write_session_api_url(api_url: str) -> None:
    """
    Persist the selected API URL and derived service domain for non-login commands.

    Inputs:
        api_url: API URL selected during login.
    """
    normalized_api_url = api_url.strip().rstrip("/")
    if not normalized_api_url:
        raise AuthError("Cannot persist an empty API URL in session.")

    domain = _extract_service_domain(normalized_api_url)
    session_path = _session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "api_url": normalized_api_url,
                "domain": domain,
            }
        )
    )


def read_session_api_url() -> str | None:
    """
    Read the API URL persisted in the extension session file.

    Returns:
        The stored API URL or None when unavailable/invalid.
    """
    session_path = _session_path()
    try:
        session_data = json.loads(session_path.read_text())
    except Exception:
        return None

    api_url = session_data.get("api_url")
    if isinstance(api_url, str) and api_url.strip():
        return api_url.strip().rstrip("/")

    return None


def clear_session_file() -> None:
    """Delete the extension session file when present."""
    _session_path().unlink(missing_ok=True)


def decode_jwt_payload(token: str) -> dict:
    """
    Decode and return the payload section of a JWT without verifying the signature.

    Inputs:
        token: A JWT string with three base64url-encoded segments.

    Returns:
        A dictionary of the decoded payload claims.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError(f"Malformed JWT: expected 3 segments, got {len(parts)}")
    # Re-pad to a valid base64url length before decoding
    payload_b64 = parts[1]
    padding_needed = (4 - len(payload_b64) % 4) % 4
    payload_bytes = base64.urlsafe_b64decode(payload_b64 + "=" * padding_needed)
    return json.loads(payload_bytes)


def _is_token_valid(token: str) -> bool:
    """
    Return True if the token carries a future exp claim with a 5-minute buffer.

    Inputs:
        token: A JWT string to validate.

    Returns:
        True if the token is still valid, False otherwise.
    """
    try:
        payload = decode_jwt_payload(token)
        exp = payload.get("exp")
        if exp is None:
            return False
        return time.time() < exp - 300
    except Exception:
        return False


def _read_cache(domain: str) -> Optional[Credentials]:
    """
    Load cached credentials from disk.

    Deletes the cache file when tokens are found to be expired.

    Inputs:
        domain: The Truveta domain to read credentials for.

    Returns:
        Credentials if valid cached tokens exist, None if missing, malformed, or expired.
    """
    path = _cache_path(domain)
    try:
        data = json.loads(path.read_text())
        access_token = data["access_token"]
        id_token = data["id_token"]
    except Exception:
        return None

    if not _is_token_valid(access_token) or not _is_token_valid(id_token):
        path.unlink(missing_ok=True)
        return None

    return Credentials(access_token=access_token, id_token=id_token)


def _write_cache(domain: str, credentials: Credentials) -> None:
    """
    Persist credentials to disk, creating parent directories as needed.

    Inputs:
        domain: The Truveta domain to cache credentials for.
        credentials: The Credentials object to persist.
    """
    path = _cache_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "access_token": credentials.access_token,
                "id_token": credentials.id_token,
            }
        )
    )


# ---------------------------------------------------------------------------
# Device Code Flow
# ---------------------------------------------------------------------------


def _device_code_flow(
    domain: str,
    client_id: str,
    audience: str,
    suppress_browser: bool = False,
) -> Credentials:
    """
    Execute the OAuth 2.0 Device Code Flow and return the resulting tokens.

    Prints the verification URL to stderr so the user can authenticate in a browser.

    Inputs:
        domain: The Truveta domain to authenticate against.
        client_id: The Auth0 client ID.
        audience: The Auth0 audience URI.
        suppress_browser: If True, skip auto-opening the browser.

    Returns:
        Credentials containing the access and ID tokens.
    """
    auth0_base = f"https://login.{domain}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    # Step 1: request a device code
    response = requests.post(
        f"{auth0_base}/oauth/device/code",
        headers=headers,
        data={
            "client_id": client_id,
            "scope": "openid email profile",
            "audience": audience,
        },
    )
    response.raise_for_status()
    device_data = response.json()

    device_code = device_data["device_code"]
    user_code = device_data["user_code"]
    verification_uri_complete = device_data["verification_uri_complete"]
    expires_in = int(device_data["expires_in"])
    interval = int(device_data["interval"])

    # Step 2: prompt the user
    print(
        f"\nOpen the following URL in your browser to authenticate:\n"
        f"  {verification_uri_complete}\n"
        f"User code: {user_code}",
        file=sys.stderr,
    )

    should_open_browser = (
        not suppress_browser and os.environ.get("TRV_SUPPRESS_LOGIN_OPEN") != "true"
    )
    if should_open_browser:
        try:
            webbrowser.open(verification_uri_complete)
        except Exception:
            pass  # Non-fatal — user can copy the URL manually

    # Step 3: poll until the user authenticates or the code expires
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)

        poll_response = requests.post(
            f"{auth0_base}/oauth/token",
            headers=headers,
            data={
                "client_id": client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
        )
        token_data = poll_response.json()

        if "access_token" in token_data and "id_token" in token_data:
            return Credentials(
                access_token=token_data["access_token"],
                id_token=token_data["id_token"],
            )

        error = token_data.get("error")
        if error == "authorization_pending":
            continue

        if error:
            description = token_data.get("error_description", "")
            raise AuthError(
                f"Authentication failed: {error}"
                + (f" — {description}" if description else "")
            )

    raise AuthError("Device login timed out")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_auth(
    url: str,
    suppress_login_open: bool = False,
    cached_only: bool = False,
) -> Credentials:
    """
    Ensure the user is authenticated and return valid credentials.

    Returns cached credentials if they exist and are not expired; otherwise
    runs the full device code flow, caches the result, and returns it.

    Inputs:
        url: The Truveta API URL to authenticate against.
        suppress_login_open: If True, skip auto-opening the browser during device flow.
        cached_only: If True, do not start device flow when no valid cache exists.

    Returns:
        Valid Credentials containing access and ID tokens.
    """
    domain = _extract_domain(url)
    _get_client_id(domain)  # Validate that the domain is known before doing anything

    cached = _read_cache(domain)
    if cached is not None:
        return cached

    if cached_only:
        raise AuthError(
            "No valid cached credentials found. Run 'olt truveta login' first."
        )

    client_id = _get_client_id(domain)
    audience = _get_audience(domain)
    credentials = _device_code_flow(
        domain, client_id, audience, suppress_browser=suppress_login_open
    )
    _write_cache(domain, credentials)
    return credentials


def get_auth_headers(credentials: Credentials) -> dict[str, str]:
    """
    Return the HTTP headers required for authenticated Truveta API requests.

    Inputs:
        credentials: Valid Credentials containing the access and ID tokens.

    Returns:
        A dictionary of HTTP header name-value pairs.
    """
    return {
        "Authorization": f"Bearer {credentials.access_token}",
        "x-access-token": credentials.access_token,
        "x-truveta-id": credentials.id_token,
        "Content-Type": "application/json",
    }
