"""
Copyright (c) Truveta. All rights reserved.

Configure extension discovery for a frozen PyInstaller bundle.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from openlinktoken_cli.extension.extension_registry import ExtensionRegistry


logger = logging.getLogger(__name__)


def _seed_persistent_registry(bundle_root: Path) -> None:
    """Copy the embedded registry into persistent storage on the first launch."""
    embedded_registry = bundle_root / "openlinktoken" / "extensions" / "registry.json"
    persistent_registry = ExtensionRegistry.get_registry_path()

    if persistent_registry.exists():
        return

    try:
        persistent_registry.parent.mkdir(parents=True, exist_ok=True)
        with embedded_registry.open("rb") as source:
            try:
                destination = persistent_registry.open("xb")
            except FileExistsError:
                # A concurrent installer won the exclusive create; never overwrite it.
                return
            with destination:
                destination.write(source.read())
    except OSError as exc:
        logger.warning(
            "Could not seed persistent extension registry at %s: %s",
            persistent_registry,
            exc,
        )


if getattr(sys, "frozen", False):
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _seed_persistent_registry(bundle_root)
