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
    entry = registry["truveta"]

    assert entry["module"] == "openlinktoken_ext_truveta.extension"
    assert entry["class"] == "TruvetaExtension"
    assert entry["command_name"] == "truveta"
    assert entry["source_path"] == ""
    assert entry["schema_version"] == 1
    assert entry["supported_core"] == ">=2.2.0,<3.0.0"
    assert entry["supported_core_version_range"] == ">=2.2.0,<3.0.0"
    assert entry["core_range"] == ">=2.2.0,<3.0.0"
    assert entry["update_manifest_url"].endswith(
        "/releases/latest/download/openlinktoken-ext-truveta-update.json"
    )
    assert entry["disabled"] is False
    assert entry["error"] is None


def test_spec_embeds_registry_and_runtime_hook():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "standalone" in spec
    assert "registry.json" in spec
    assert "standalone_runtime_hook.py" in spec
    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec


def test_spec_collects_ml1_runtime_dependencies():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert '"onnxruntime"' in spec
    assert '"tokenizers"' in spec
