"""
Copyright (c) Truveta. All rights reserved.

Shared session persistence helpers for the OpenLinkToken Truveta extension.
"""

import json
from typing import Any

from openlinktoken_ext_truveta.domain import DomainError, validate_domain
from openlinktoken_ext_truveta.paths import session_file_path


def read_session_data() -> dict[str, Any]:
    """
    Read the full extension session payload from disk.

    Inputs:
        None.

    Returns:
        The stored session JSON object, or an empty dictionary when the session
        file is missing, malformed, or not a JSON object.
    """
    path = session_file_path()
    try:
        session_data = json.loads(path.read_text())
    except Exception:
        return {}

    if not isinstance(session_data, dict):
        return {}
    return session_data


def update_session_data(values: dict[str, Any]) -> dict[str, Any]:
    """
    Merge additional values into the extension session payload and persist it.

    Inputs:
        values: A JSON-serializable dictionary of session fields to add or update.

    Returns:
        The full merged session payload after it is written to disk.
    """
    session_data = read_session_data()
    session_data.update(values)

    path = session_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session_data))
    return session_data


def write_session_domain(domain: str) -> None:
    """
    Persist the selected Truveta domain in the extension session file.

    Inputs:
        domain: A supported Truveta domain to save as the active session target.

    Returns:
        None. The domain is merged into ~/.openlinktoken/truveta/session.json.
    """
    validated_domain = validate_domain(domain)
    update_session_data({"domain": validated_domain})


def read_session_domain() -> str | None:
    """
    Read the persisted Truveta domain from the extension session file.

    Inputs:
        None.

    Returns:
        The validated session domain when present, otherwise None.
    """
    domain = read_session_data().get("domain")
    if not isinstance(domain, str):
        return None

    try:
        return validate_domain(domain)
    except DomainError:
        return None


def clear_session() -> None:
    """
    Delete the extension session file when present.

    Inputs:
        None.

    Returns:
        None. Missing session files are ignored.
    """
    session_file_path().unlink(missing_ok=True)
