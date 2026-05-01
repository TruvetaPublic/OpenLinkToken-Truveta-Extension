"""
Copyright (c) Truveta. All rights reserved.

Shared helpers for OpenLink Token API clients.
"""

DEFAULT_TIMEOUT_SECONDS = 30


def resolve_timeout_seconds(timeout_seconds: int | None) -> int:
    """Resolve request timeout seconds using explicit override or default."""
    return timeout_seconds if timeout_seconds is not None else DEFAULT_TIMEOUT_SECONDS
