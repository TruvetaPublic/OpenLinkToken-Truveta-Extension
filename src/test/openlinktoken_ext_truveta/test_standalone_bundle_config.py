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

DEV_CORE_SOURCE_REF = "develop"
RELEASE_CORE_SOURCE_REF = "main"
ASSET_SOURCE_REF = "main"
CORE_DISTRIBUTIONS = (
    "openlinktoken",
    "openlinktoken-cli",
    "openlinktoken-core-ai",
)


def test_embedded_registry_declares_truveta_extension():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = registry["truveta"]

    assert entry["module"] == "openlinktoken_ext_truveta.extension"
    assert entry["class"] == "TruvetaExtension"
    assert entry["command_name"] == "truveta"
    assert entry["source_path"] == ""
    assert entry["schema_version"] == 1
    assert entry["supported_core"] == ">=2.2.1,<3.0.0"
    assert entry["supported_core_version_range"] == ">=2.2.1,<3.0.0"
    assert entry["core_range"] == ">=2.2.1,<3.0.0"
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


def test_spec_bundles_core_distribution_metadata():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "copy_metadata" in spec
    assert "copy_metadata(distribution_name)" in spec
    for distribution in CORE_DISTRIBUTIONS:
        assert f'"{distribution}"' in spec


def test_release_workflow_generates_and_publishes_update_manifests():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")

    build_index = workflow.index("run: uv build")
    manifest_index = workflow.index(
        "python -m openlinktoken_ext_truveta.util.extension_manifests"
    )
    assert build_index < manifest_index
    assert '--version "${VERSION}"' in workflow
    assert "find dist -maxdepth 1 -type f -name '*.whl' -print" in workflow
    assert '--wheel "$wheel_path"' in workflow
    assert "dist/openlinktoken_ext_truveta-${VERSION}-py3-none-any.whl" not in workflow
    assert "--output-dir release-assets" in workflow

    artifact_start = workflow.index(
        "name: Upload built distributions as workflow artifacts"
    )
    artifact_end = workflow.index(
        "name: Upload distributions to GitHub Release", artifact_start
    )
    assert "release-assets/*" in workflow[artifact_start:artifact_end]

    publish_start = workflow.index("name: Upload distributions to GitHub Release")
    publish_end = workflow.index("  build-standalone:", publish_start)
    assert "readdirSync('release-assets')" in workflow[publish_start:publish_end]


def test_standalone_release_smokes_compatible_leaf_command():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'SMOKE_HOME="$(mktemp -d)"' in workflow
    assert 'HOME="$SMOKE_HOME"' in workflow
    assert "./dist/olt/olt truveta logout" in workflow
    assert workflow.count("smoke_independent_extension_update.py") == 2
    assert workflow.count("--manifest-url") == 2


def test_bumpversion_updates_embedded_registry_version():
    bumpversion = BUMPVERSION_PATH.read_text(encoding="utf-8")

    assert "[bumpversion:file:standalone/registry.json]" in bumpversion
    assert 'search = "version": "{current_version}"' in bumpversion
    assert 'replace = "version": "{new_version}"' in bumpversion


def test_dev_and_release_core_sources_use_expected_branches():
    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
    requirements_dev = REQUIREMENTS_DEV_PATH.read_text(encoding="utf-8")
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert (
        f"openlinktoken-cli @ git+https://github.com/TruvetaPublic/OpenLinkToken.git"
        f"@{DEV_CORE_SOURCE_REF}#subdirectory=lib/python/openlinktoken-cli"
    ) in pyproject
    assert pyproject.count(f"@{RELEASE_CORE_SOURCE_REF}#subdirectory=") == 3
    assert 'conflicts = [[{ extra = "dev" }, { extra = "release" }]]' in pyproject
    assert (
        "uv export --frozen --format requirements-txt --extra dev" in requirements_dev
    )
    locked_core_lines = [
        line
        for line in requirements_dev.splitlines()
        if line.startswith(
            (
                "openlinktoken @ ",
                "openlinktoken-cli @ ",
                "openlinktoken-core-ai @ ",
            )
        )
    ]
    locked_core_refs = [
        line.split("@")[-1].split("#", 1)[0] for line in locked_core_lines
    ]
    assert len(locked_core_lines) == 3
    assert len(set(locked_core_refs)) == 1
    assert len(locked_core_refs[0]) == 40
    int(locked_core_refs[0], 16)
    assert f"OPENLINKTOKEN_SOURCE_REF: {ASSET_SOURCE_REF}" in workflow
