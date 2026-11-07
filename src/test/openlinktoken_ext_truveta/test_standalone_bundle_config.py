"""
Copyright (c) Truveta. All rights reserved.

Regression tests for standalone bundle extension discovery.
"""

import json
import re
import runpy
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


REPOSITORY_ROOT = Path(__file__).parents[3]
REGISTRY_PATH = REPOSITORY_ROOT / "standalone" / "registry.json"
SPEC_PATH = REPOSITORY_ROOT / "openlinktoken-ext-truveta.spec"
RELEASE_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
INSTALL_SH_PATH = REPOSITORY_ROOT / "scripts" / "install.sh"
INSTALL_PS1_PATH = REPOSITORY_ROOT / "scripts" / "install.ps1"
BUMPVERSION_PATH = REPOSITORY_ROOT / ".bumpversion.cfg"
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
REQUIREMENTS_DEV_PATH = REPOSITORY_ROOT / "requirements-dev.txt"

DEV_CORE_SOURCE_REF = "develop"
RELEASE_CORE_SOURCE_REF = "main"
CORE_DISTRIBUTIONS = (
    "openlinktoken",
    "openlinktoken-cli",
    "openlinktoken-core-ai",
)


def _job_block(workflow: str, name: str) -> str:
    """Return one top-level job block from the release workflow."""
    marker = f"  {name}:\n"
    start = workflow.index(marker)
    remaining = workflow[start + len(marker) :]
    next_job = re.search(r"^  [A-Za-z][A-Za-z0-9_-]*:\s*$", remaining, re.MULTILINE)
    end = start + len(marker) + next_job.start() if next_job else len(workflow)
    return workflow[start:end]


def test_embedded_registry_declares_truveta_extension():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entry = registry["truveta"]

    assert entry["module"] == "openlinktoken_ext_truveta.extension"
    assert entry["class"] == "TruvetaExtension"
    assert entry["command_name"] == "truveta"
    assert entry["source_path"] is None
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


def test_spec_does_not_collect_ml1_model_payloads():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "collect_ml1_assets" not in spec
    assert "OLT_INFERENCING_ASSETS_SOURCE" not in spec


def test_spec_bundles_core_distribution_metadata():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "copy_metadata" in spec
    assert "copy_metadata(distribution_name)" in spec
    for distribution in CORE_DISTRIBUTIONS:
        assert f'"{distribution}"' in spec


def test_release_workflow_builds_bundles_before_publishing_manifests():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")

    distributions_index = workflow.index("  build-distributions:")
    bundles_index = workflow.index("  build-extension-bundle:")
    assemble_index = workflow.index("  assemble-release-assets:")
    publish_index = workflow.index("  publish-release-assets:")
    standalone_index = workflow.index("  build-standalone:")
    publish_standalone_index = workflow.index("  publish-standalone-assets:")
    assert (
        distributions_index
        < bundles_index
        < assemble_index
        < publish_index
        < standalone_index
        < publish_standalone_index
    )

    assert "needs: [release-info, build-distributions]" in workflow
    assert (
        "needs: [release-info, build-distributions, build-extension-bundle]"
        in _job_block(workflow, "assemble-release-assets")
    )
    assert "needs: [release-info, assemble-release-assets]" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "python -m pip download" in workflow
    assert "--require-hashes" in workflow
    assert "--only-binary=:all:" in workflow
    assert 'if line.strip() != "-e ."' in workflow


def test_manual_release_rebuild_can_override_existing_tag_source():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    manual_rebuild_ref = (
        "ref: ${{ github.event.inputs.source_ref || "
        "(needs.release-info.outputs['release-found'] == 'true' && "
        "needs.release-info.outputs.tag || github.sha) }}"
    )

    assert "      source_ref:" in workflow
    assert workflow.count(manual_rebuild_ref) == 4
    assert '--python-abi "${{ matrix.python_abi }}"' in workflow
    assert 'bundle_args+=(--bundle "$bundle_path")' in workflow
    assert "Expected exactly six platform/ABI bundles" in workflow
    assert '--version "${VERSION}"' in workflow
    assert "--output-dir release-assets" in workflow
    assert "path: release-assets/*" in workflow

    bundle_workflow = _job_block(workflow, "build-extension-bundle")
    assert bundle_workflow.count("python_abi: cp311") == 3
    assert bundle_workflow.count("python_abi: cp312") == 3
    assert 'python-version: "${{ matrix.python_version }}"' in bundle_workflow

    publish_workflow = _job_block(workflow, "publish-release-assets")
    assert "fs.readdirSync('release-assets')" in publish_workflow


def test_standalone_release_smokes_compatible_leaf_command():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    standalone_workflow = _job_block(workflow, "build-standalone")

    assert 'SMOKE_HOME="$(mktemp -d)"' in standalone_workflow
    assert 'HOME="$SMOKE_HOME"' in standalone_workflow
    assert "./dist/olt/olt truveta logout" in standalone_workflow
    assert standalone_workflow.count("smoke_independent_extension_update.py") == 2
    assert standalone_workflow.count("--local-assets-dir release-assets") == 2
    assert "--manifest-url" not in standalone_workflow
    assert standalone_workflow.count('--target "${{ matrix.target }}"') == 2
    assert standalone_workflow.count("--python-abi cp312") == 2


def test_release_prs_and_manual_dry_runs_skip_release_lookup():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    dispatch = workflow.split("  workflow_dispatch:\n", 1)[1].split(
        "  workflow_run:\n", 1
    )[0]

    assert '  pull_request:\n    branches: ["release/**"]' in workflow
    assert "      dry_run:" in dispatch
    assert "        default: false" in dispatch
    assert "        type: boolean" in dispatch
    assert (
        "lookup-release: ${{ github.event_name != 'pull_request' "
        "&& github.event.inputs.dry_run != 'true' }}"
    ) in workflow


def test_release_pr_version_comes_from_pr_checkout():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    release_info = _job_block(workflow, "release-info")
    release_context = (
        REPOSITORY_ROOT / ".github" / "workflows" / "release-context.yml"
    ).read_text(encoding="utf-8")
    release_context_job = _job_block(release_context, "release-info")
    checkout_step, version_steps = release_context_job.split(
        "      - name: Determine version", 1
    )
    version_resolution = version_steps.split("      - name: Resolve GitHub release", 1)[
        0
    ]
    build_distributions = _job_block(workflow, "build-distributions")

    assert (
        "release-tag: ${{ github.event_name == 'release' && "
        "github.event.release.tag_name || github.event.inputs.version && "
        "format('v{0}', github.event.inputs.version) || '' }}"
    ) in release_info
    assert "uses: actions/checkout@v7" in checkout_step
    assert "ref:" not in checkout_step
    assert "else\n            VERSION=$(sed -n" in version_resolution
    assert ".bumpversion.cfg" in version_resolution
    assert "|| github.sha) }}" in build_distributions


def test_release_publishers_are_write_scoped_and_gated():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    publisher_gate = (
        "github.event_name != 'pull_request' "
        "&& github.event.inputs.dry_run != 'true' "
        "&& needs.release-info.outputs['release-found'] == 'true'"
    )

    for job_name in (
        "build-distributions",
        "build-extension-bundle",
        "assemble-release-assets",
        "build-standalone",
    ):
        assert "contents: write" not in _job_block(workflow, job_name)

    for job_name in ("publish-release-assets", "publish-standalone-assets"):
        job = _job_block(workflow, job_name)
        assert "permissions:\n      contents: write" in job
        assert publisher_gate in job


def test_standalone_smoke_uses_release_assets_from_the_same_run():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    assembly = _job_block(workflow, "assemble-release-assets")
    standalone = _job_block(workflow, "build-standalone")

    artifact_name = "openlinktoken-ext-truveta-release-assets-${{ env.TAG }}"
    assert f"name: {artifact_name}" in assembly
    assert f"name: {artifact_name}" in standalone
    assert "needs: [release-info, assemble-release-assets]" in standalone
    assert standalone.count("--local-assets-dir release-assets") == 2


def test_release_workflow_verifies_oci_assets_and_supported_platforms():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    standalone_workflow = workflow[workflow.index("  build-standalone:") :]
    matrix = standalone_workflow.split("      matrix:", 1)[1].split("    env:", 1)[0]

    assert "- os: ubuntu-latest\n            target: linux-x64" in matrix
    assert "- os: macos-15\n            target: macos-arm64" in matrix
    assert "- os: windows-latest\n            target: windows-x64" in matrix
    assert "macos-latest" not in matrix
    assert "intel" not in matrix.lower()
    assert "OLT_ML1_MODEL_TAG: v1" in standalone_workflow
    assert "Install ORAS" in standalone_workflow
    assert "version: 1.3.3" in standalone_workflow
    assert "oras pull" in standalone_workflow
    assert "copy_ml1_assets" in standalone_workflow
    assert "Verify release ZIP omits ML1 assets" in standalone_workflow
    assert "git lfs" not in standalone_workflow.lower()


def test_official_installers_retrieve_and_verify_model_assets_before_install():
    install_sh = INSTALL_SH_PATH.read_text(encoding="utf-8")
    install_ps1 = INSTALL_PS1_PATH.read_text(encoding="utf-8")

    for installer in (install_sh, install_ps1):
        assert "ghcr.io/truvetapublic/openlinktoken-ml1-assets" in installer
        assert "1.3.3" in installer
        assert "OLT_ML1_MODEL_TAG" in installer or "$ModelTag" in installer
        assert "asset-manifest.json" in installer
        assert "model.onnx.data" in installer
        assert "SHA-256" in installer
        assert "unexpected size" in installer.lower()

    assert install_sh.index('install_ml1_assets "$BUNDLE_DIR"') < install_sh.index(
        "INSTALLED_BUNDLE_DIR="
    )
    assert install_ps1.index("Install-Ml1Assets -BundleRoot $ExtractedBundle") < (
        install_ps1.index("Move-Item -LiteralPath $ExtractedBundle")
    )


def test_bumpversion_updates_embedded_registry_version():
    bumpversion = BUMPVERSION_PATH.read_text(encoding="utf-8")

    assert "[bumpversion:file:standalone/registry.json]" in bumpversion
    assert 'search = "version": "{current_version}"' in bumpversion
    assert 'replace = "version": "{new_version}"' in bumpversion


def test_dev_and_release_core_sources_use_expected_branches():
    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
    requirements_dev = REQUIREMENTS_DEV_PATH.read_text(encoding="utf-8")

    assert (
        f"openlinktoken-cli @ git+https://github.com/TruvetaPublic/OpenLinkToken.git"
        f"@{DEV_CORE_SOURCE_REF}#subdirectory=lib/python/openlinktoken-cli"
    ) in pyproject
    assert pyproject.count(f"@{RELEASE_CORE_SOURCE_REF}#subdirectory=") == 3
    assert 'conflicts = [[{ extra = "dev" }, { extra = "release" }]]' in pyproject
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


def _run_spec_with_inventory_writer(tmp_path, inventory_writer):
    """Execute the PyInstaller spec with controlled analysis and inventory output."""
    analysis_results = []

    def fake_analysis(*args, **kwargs):
        data_files = list(kwargs["datas"])
        analysis = types.SimpleNamespace(
            pure=["analysis-module"],
            binaries=["analysis-binary"],
            datas=list(data_files),
            input_datas=data_files,
            scripts=[],
            zipped_data=[],
            zipfiles=[],
        )
        analysis_results.append(analysis)
        return analysis

    fake_hooks = types.ModuleType("PyInstaller.utils.hooks")
    fake_hooks.collect_all = lambda package_name: ([], [], [])
    fake_hooks.collect_submodules = lambda package_name: []
    fake_hooks.copy_metadata = lambda distribution_name: []
    fake_utils = types.ModuleType("PyInstaller.utils")
    fake_utils.hooks = fake_hooks
    fake_pyinstaller = types.ModuleType("PyInstaller")
    fake_pyinstaller.utils = fake_utils
    fake_inventory = types.ModuleType(
        "openlinktoken_cli.extension.core_runtime_inventory"
    )
    fake_inventory.write_core_runtime_inventory = inventory_writer

    original_path = list(sys.path)
    try:
        with patch.dict(
            sys.modules,
            {
                "PyInstaller": fake_pyinstaller,
                "PyInstaller.utils": fake_utils,
                "PyInstaller.utils.hooks": fake_hooks,
                "openlinktoken_cli.extension.core_runtime_inventory": fake_inventory,
            },
        ):
            runpy.run_path(
                str(SPEC_PATH),
                init_globals={
                    "SPECPATH": str(tmp_path),
                    "Analysis": fake_analysis,
                    "PYZ": lambda *args, **kwargs: object(),
                    "EXE": lambda *args, **kwargs: object(),
                    "COLLECT": lambda *args, **kwargs: object(),
                },
            )
    finally:
        sys.path[:] = original_path

    return analysis_results[0]


def test_spec_bundles_core_runtime_inventory(tmp_path):
    inventory_calls = []
    inventory_contents = '{"schema_version": 1, "distributions": {}}\n'

    def write_inventory(analysis_items, output_path):
        inventory_calls.append((list(analysis_items), output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(inventory_contents, encoding="utf-8")

    analysis = _run_spec_with_inventory_writer(tmp_path, write_inventory)
    inventory_path = tmp_path / "build" / "core_runtime_inventory.json"

    assert inventory_calls == [
        (analysis.pure + analysis.binaries + analysis.input_datas, inventory_path)
    ]
    assert (
        "openlinktoken_cli/data/core_runtime_inventory.json",
        str(inventory_path),
        "DATA",
    ) in analysis.datas
    assert inventory_path.read_text(encoding="utf-8") == inventory_contents


def test_spec_propagates_core_inventory_generation_failure(tmp_path):
    def fail_inventory_generation(analysis_items, output_path):
        raise RuntimeError("inventory generation failed")

    with pytest.raises(RuntimeError, match="inventory generation failed"):
        _run_spec_with_inventory_writer(tmp_path, fail_inventory_generation)


def test_windows_standalone_smoke_propagates_python_exit_code():
    workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    windows_smoke = _job_block(workflow, "build-standalone").split(
        "      - name: Smoke test (Windows)", 1
    )[1]
    smoke_script = windows_smoke.split(
        "python scripts\\smoke_independent_extension_update.py `", 1
    )[1].split("          .\\dist\\olt\\olt.exe generate-key-pair", 1)[0]

    assert re.search(
        r"--local-assets-dir release-assets\r?\n"
        r"\s*if \(\$LASTEXITCODE -ne 0\) \{\r?\n"
        r"\s*exit \$LASTEXITCODE\r?\n"
        r"\s*\}",
        smoke_script,
    )
