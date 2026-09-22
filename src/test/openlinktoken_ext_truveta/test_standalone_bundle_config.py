"""
Copyright (c) Truveta. All rights reserved.

Regression tests for standalone bundle extension discovery.
"""

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
REGISTRY_PATH = REPOSITORY_ROOT / "standalone" / "registry.json"
SPEC_PATH = REPOSITORY_ROOT / "openlinktoken-ext-truveta.spec"
RELEASE_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
BUMPVERSION_PATH = REPOSITORY_ROOT / ".bumpversion.cfg"
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
REQUIREMENTS_DEV_PATH = REPOSITORY_ROOT / "requirements-dev.txt"

CORE_SOURCE_REF = "f840e2f509d9ff634dc8a3039a429fa415619492"


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


def test_release_workflow_generates_and_publishes_update_manifests():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")

    build_index = workflow.index("run: uv build")
    manifest_index = workflow.index(
        "python -m openlinktoken_ext_truveta.util.extension_manifests"
    )
    assert build_index < manifest_index
    assert '--version "${VERSION}"' in workflow
    assert (
        '--wheel "dist/openlinktoken_ext_truveta-${VERSION}-py3-none-any.whl"'
        in workflow
    )
    assert "--output-dir release-assets" in workflow

    artifact_start = workflow.index(
        "name: Upload built distributions as workflow artifacts"
    )
    artifact_end = workflow.index("name: Publish to GitHub Releases", artifact_start)
    assert "release-assets/*" in workflow[artifact_start:artifact_end]

    publish_start = workflow.index("name: Publish to GitHub Releases")
    publish_end = workflow.index("  build-standalone:", publish_start)
    assert "release-assets/*" in workflow[publish_start:publish_end]


def test_bumpversion_updates_embedded_registry_version():
    bumpversion = BUMPVERSION_PATH.read_text(encoding="utf-8")

    assert "[bumpversion:file:standalone/registry.json]" in bumpversion
    assert 'search = "version": "{current_version}"' in bumpversion
    assert 'replace = "version": "{new_version}"' in bumpversion


def test_core_source_pins_use_the_immutable_merge_commit():
    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
    requirements_dev = REQUIREMENTS_DEV_PATH.read_text(encoding="utf-8")
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert pyproject.count(f"@{CORE_SOURCE_REF}#subdirectory=") == 4
    assert requirements_dev.count(f"@{CORE_SOURCE_REF}#subdirectory=") == 3
    assert f"OPENLINKTOKEN_SOURCE_REF: {CORE_SOURCE_REF}" in workflow
