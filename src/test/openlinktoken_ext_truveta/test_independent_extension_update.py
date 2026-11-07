import hashlib
from contextlib import nullcontext
import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from openlinktoken_ext_truveta.util.extension_bundles import (
    SUPPORTED_BUNDLE_TARGETS,
)

SMOKE_SCRIPT_PATH = (
    Path(__file__).parents[3] / "scripts" / "smoke_independent_extension_update.py"
)
sys.path.insert(0, str(SMOKE_SCRIPT_PATH.parent))
SMOKE_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "smoke_independent_extension_update", SMOKE_SCRIPT_PATH
)
if SMOKE_SCRIPT_SPEC is None or SMOKE_SCRIPT_SPEC.loader is None:
    raise ImportError(f"Could not load smoke script: {SMOKE_SCRIPT_PATH}")
SMOKE_SCRIPT = importlib.util.module_from_spec(SMOKE_SCRIPT_SPEC)
SMOKE_SCRIPT_SPEC.loader.exec_module(SMOKE_SCRIPT)
main = SMOKE_SCRIPT.main


@pytest.mark.skipif(os.name == "nt", reason="The fake CLI uses a POSIX shebang.")
@pytest.mark.parametrize("local_assets", [False, True])
@pytest.mark.parametrize("fresh_core", [False, True])
@pytest.mark.parametrize("python_abi", ["cp311", "cp312"])
@pytest.mark.parametrize("registry_only", [False, True])
def test_smoke_bootstraps_and_updates_extension_without_core_changes(
    tmp_path, monkeypatch, local_assets, fresh_core, python_abi, registry_only
):
    """Verify the smoke script selects one exact target/ABI bundle."""
    bundle_dir = tmp_path / "dist" / "olt"
    internal_dir = bundle_dir / "_internal"
    internal_dir.mkdir(parents=True)
    for metadata_name in (
        "openlinktoken-2.2.1.dist-info",
        "openlinktoken_cli-2.2.1.dist-info",
        "openlinktoken_core_ai-2.2.1.dist-info",
    ):
        metadata_dir = internal_dir / metadata_name
        metadata_dir.mkdir()
        (metadata_dir / "METADATA").write_text(metadata_name, encoding="utf-8")

    fake_cli = bundle_dir / "olt"
    fake_cli.write_text(
        f"#!{sys.executable}\n"
        "import json, os, shutil, sys\n"
        "from pathlib import Path\n"
        "from urllib.request import urlopen\n"
        "args = sys.argv[1:]\n"
        "registry_path = Path(os.environ['OLT_EXTENSIONS_DIR']) / 'registry.json'\n"
        "if args[:2] == ['extension', 'install']:\n"
        "    manifest_url = args[args.index('--manifest') + 1]\n"
        "    with urlopen(manifest_url) as response:\n"
        "        manifest = json.load(response)\n"
        "    extension = manifest['extension']\n"
        "    with urlopen(extension['update_manifest_url']) as response:\n"
        "        update_manifest = json.load(response)\n"
        "    if update_manifest['latest_version'] != extension['version']:\n"
        "        raise SystemExit('bootstrap update manifest URL is incorrect')\n"
        "    entry = {'version': extension['version'], "
        "'update_manifest_url': extension['update_manifest_url']}\n"
        f"    entry['python_abi'] = '{python_abi}'\n"
        "    entry['bundle_sha256'] = next(b['sha256'] for b in manifest['bundles'] "
        f"if b['target'] == 'linux-x64' and b['python_abi'] == '{python_abi}')\n"
        "    payload = registry_path.parent / 'initial'\n"
        "    payload.mkdir(parents=True)\n"
        "    (payload / 'extension.py').write_text('PAYLOAD = True\\n')\n"
        "    entry['install_location'] = str(payload)\n"
        "    registry_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    registry_path.write_text(json.dumps({'truveta': entry}), encoding='utf-8')\n"
        "elif args[:3] == ['extension', 'update', 'truveta']:\n"
        "    registry = json.loads(registry_path.read_text(encoding='utf-8'))\n"
        "    with urlopen(registry['truveta']['update_manifest_url']) as response:\n"
        "        manifest = json.load(response)\n"
        "    registry['truveta']['version'] = manifest['latest_version']\n"
        f"    if not {registry_only!r}:\n"
        "        payload = registry_path.parent / 'updated'\n"
        "        shutil.copytree(registry['truveta']['install_location'], payload)\n"
        "        registry['truveta']['install_location'] = str(payload)\n"
        "    registry_path.write_text(json.dumps(registry), encoding='utf-8')\n"
        "elif args == ['truveta', 'logout']:\n"
        "    if not registry_path.exists():\n"
        "        registry_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        registry_path.write_text(json.dumps({'truveta': {}}), encoding='utf-8')\n"
        "elif args == ['truveta', '--help']:\n"
        "    pass\n"
        "else:\n"
        "    raise SystemExit(f'unexpected command: {args}')\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    selected_bundle_path = tmp_path / f"linux-x64-{python_abi}.zip"
    bundle_records = []
    for target, python_abis in SUPPORTED_BUNDLE_TARGETS.items():
        for bundle_abi in python_abis:
            bundle_path = tmp_path / f"{target}-{bundle_abi}.zip"
            bundle_path.write_bytes(f"{target}-{bundle_abi}".encode())
            bundle_records.append(
                {
                    "target": target,
                    "python_abi": bundle_abi,
                    "url": (
                        f"https://example.invalid/{bundle_path.name}"
                        if local_assets
                        else bundle_path.as_uri()
                    ),
                    "sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
                }
            )
    update_manifest = {
        "schema_version": 2,
        "latest_version": "1.1.0",
        "minimum_runtime_protocol": 2,
        "bundles": bundle_records,
    }
    update_manifest_path = tmp_path / "openlinktoken-ext-truveta-update.json"
    update_manifest_path.write_text(json.dumps(update_manifest), encoding="utf-8")
    bootstrap_manifest = {
        "schema_version": 2,
        "minimum_runtime_protocol": 2,
        "bundles": bundle_records,
        "extension": {
            "version": "1.1.0",
            "update_manifest_url": (
                "https://example.invalid/openlinktoken-ext-truveta-update.json"
                if local_assets
                else update_manifest_path.as_uri()
            ),
        },
    }
    bootstrap_manifest_path = tmp_path / "openlinktoken-ext-truveta-bootstrap.json"
    bootstrap_manifest_path.write_text(json.dumps(bootstrap_manifest), encoding="utf-8")

    verify_bundle = Mock(wraps=SMOKE_SCRIPT._verify_artifact_digest)
    monkeypatch.setattr(SMOKE_SCRIPT, "_verify_artifact_digest", verify_bundle)
    context = (
        pytest.raises(RuntimeError, match="newly installed payload")
        if fresh_core and registry_only
        else nullcontext()
    )
    with context:
        asset_arguments = (
            ["--local-assets-dir", str(tmp_path)]
            if local_assets
            else ["--manifest-url", bootstrap_manifest_path.as_uri()]
        )
        assert (
            main(
                [
                    "--cli",
                    str(fake_cli),
                    *asset_arguments,
                    "--target",
                    "linux-x64",
                    "--python-abi",
                    python_abi,
                    *(["--fresh-core"] if fresh_core else []),
                ]
            )
            == 0
        )
    assert verify_bundle.call_count == 1
    bundle_url = verify_bundle.call_args.args[0]
    if local_assets:
        assert bundle_url.startswith("https://127.0.0.1:")
        assert bundle_url.endswith(f"/{selected_bundle_path.name}")
    else:
        assert bundle_url == selected_bundle_path.as_uri()


def _write_local_assets(directory: Path, missing_bundle: str | None = None) -> None:
    """Create matching manifests and supported bundle records for local-mode tests."""
    bundle_records = []
    for target, python_abis in SUPPORTED_BUNDLE_TARGETS.items():
        for python_abi in python_abis:
            filename = f"{target}-{python_abi}.zip"
            payload = filename.encode()
            bundle_records.append(
                {
                    "target": target,
                    "python_abi": python_abi,
                    "url": f"https://example.invalid/{filename}",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
            if filename != missing_bundle:
                (directory / filename).write_bytes(payload)

    update_manifest = {
        "schema_version": 2,
        "latest_version": "1.1.0",
        "minimum_runtime_protocol": 2,
        "bundles": bundle_records,
    }
    bootstrap_manifest = {
        "schema_version": 2,
        "minimum_runtime_protocol": 2,
        "bundles": bundle_records,
        "extension": {
            "version": "1.1.0",
            "update_manifest_url": "https://example.invalid/update.json",
        },
    }
    (directory / "openlinktoken-ext-truveta-update.json").write_text(
        json.dumps(update_manifest), encoding="utf-8"
    )
    (directory / "openlinktoken-ext-truveta-bootstrap.json").write_text(
        json.dumps(bootstrap_manifest), encoding="utf-8"
    )


def test_local_assets_mode_requires_bootstrap_manifest(tmp_path, monkeypatch):
    """Local mode reports a missing generated bootstrap manifest."""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    monkeypatch.setattr(SMOKE_SCRIPT, "_core_metadata_hashes", lambda _: {})

    with pytest.raises(
        FileNotFoundError, match="openlinktoken-ext-truveta-bootstrap.json"
    ):
        main(
            [
                "--cli",
                str(tmp_path / "unused"),
                "--local-assets-dir",
                str(assets_dir),
                "--target",
                "linux-x64",
                "--python-abi",
                "cp312",
            ]
        )


def test_local_assets_mode_requires_selected_bundle(tmp_path, monkeypatch):
    """Local mode reports a missing bundle referenced by the manifests."""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    _write_local_assets(assets_dir, missing_bundle="linux-x64-cp312.zip")
    monkeypatch.setattr(SMOKE_SCRIPT, "_core_metadata_hashes", lambda _: {})

    with pytest.raises(FileNotFoundError, match="linux-x64-cp312.zip"):
        main(
            [
                "--cli",
                str(tmp_path / "unused"),
                "--local-assets-dir",
                str(assets_dir),
                "--target",
                "linux-x64",
                "--python-abi",
                "cp312",
            ]
        )


def test_core_metadata_hashes_accepts_setuptools_egg_info(tmp_path):
    """The frozen CLI can contain egg-info rather than dist-info."""
    internal = tmp_path / "_internal"
    for name in ("openlinktoken", "openlinktoken_cli", "openlinktoken_core_ai"):
        directory = internal / f"{name}.egg-info"
        directory.mkdir(parents=True)
        (directory / "PKG-INFO").write_text(f"Name: {name}\nVersion: 2.2.1\n")
    assert len(SMOKE_SCRIPT._core_metadata_hashes(tmp_path / "olt")) == 3
