"""
Copyright (c) Truveta. All rights reserved.

Regression tests for standalone bundle extension discovery.
"""

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
REGISTRY_PATH = REPOSITORY_ROOT / "standalone" / "registry.json"
SPEC_PATH = REPOSITORY_ROOT / "openlinktoken-ext-truveta.spec"


def test_embedded_registry_declares_truveta_extension():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    assert registry["truveta"]["module"] == "openlinktoken_ext_truveta.extension"
    assert registry["truveta"]["class"] == "TruvetaExtension"
    assert registry["truveta"]["command_name"] == "truveta"
    assert registry["truveta"]["source_path"] == ""


def test_spec_embeds_registry_and_runtime_hook():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "standalone" in spec
    assert "registry.json" in spec
    assert "standalone_runtime_hook.py" in spec
    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec
