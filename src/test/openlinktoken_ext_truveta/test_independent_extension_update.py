import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SMOKE_SCRIPT_PATH = (
    Path(__file__).parents[3] / "scripts" / "smoke_independent_extension_update.py"
)
SMOKE_SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "smoke_independent_extension_update", SMOKE_SCRIPT_PATH
)
if SMOKE_SCRIPT_SPEC is None or SMOKE_SCRIPT_SPEC.loader is None:
    raise ImportError(f"Could not load smoke script: {SMOKE_SCRIPT_PATH}")
SMOKE_SCRIPT = importlib.util.module_from_spec(SMOKE_SCRIPT_SPEC)
SMOKE_SCRIPT_SPEC.loader.exec_module(SMOKE_SCRIPT)
main = SMOKE_SCRIPT.main


@pytest.mark.skipif(os.name == "nt", reason="The fake CLI uses a POSIX shebang.")
def test_smoke_bootstraps_and_updates_extension_without_core_changes(tmp_path):
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
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "from urllib.request import urlopen\n"
        "args = sys.argv[1:]\n"
        "registry_path = Path(os.environ['OLT_EXTENSIONS_DIR']) / 'registry.json'\n"
        "if args[:2] == ['extension', 'install']:\n"
        "    manifest_url = args[args.index('--manifest') + 1]\n"
        "    with urlopen(manifest_url) as response:\n"
        "        manifest = json.load(response)\n"
        "    extension = manifest['extension']\n"
        "    entry = {'version': extension['version'], "
        "'update_manifest_url': extension['update_manifest_url']}\n"
        "    registry_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    registry_path.write_text(json.dumps({'truveta': entry}), encoding='utf-8')\n"
        "elif args[:3] == ['extension', 'update', 'truveta']:\n"
        "    registry = json.loads(registry_path.read_text(encoding='utf-8'))\n"
        "    with urlopen(registry['truveta']['update_manifest_url']) as response:\n"
        "        manifest = json.load(response)\n"
        "    registry['truveta']['version'] = manifest['latest_version']\n"
        "    registry_path.write_text(json.dumps(registry), encoding='utf-8')\n"
        "elif args == ['truveta', 'logout']:\n"
        "    if not registry_path.exists():\n"
        "        registry_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        registry_path.write_text(json.dumps({'truveta': {}}), encoding='utf-8')\n"
        "else:\n"
        "    raise SystemExit(f'unexpected command: {args}')\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    wheel_path = tmp_path / "extension.whl"
    wheel_path.write_bytes(b"synthetic extension wheel")
    wheel_digest = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    update_manifest = {
        "latest_version": "1.1.0",
        "artifacts": [{"url": wheel_path.as_uri(), "sha256": wheel_digest}],
    }
    update_manifest_path = tmp_path / "openlinktoken-ext-truveta-update.json"
    update_manifest_path.write_text(json.dumps(update_manifest), encoding="utf-8")
    bootstrap_manifest = {
        "extension": {
            "version": "1.1.0",
            "update_manifest_url": "https://example.invalid/update.json",
            "artifact_url": wheel_path.as_uri(),
            "sha256": wheel_digest,
        }
    }
    bootstrap_manifest_path = tmp_path / "openlinktoken-ext-truveta-bootstrap.json"
    bootstrap_manifest_path.write_text(json.dumps(bootstrap_manifest), encoding="utf-8")

    assert (
        main(
            [
                "--cli",
                str(fake_cli),
                "--manifest-url",
                bootstrap_manifest_path.as_uri(),
            ]
        )
        == 0
    )
