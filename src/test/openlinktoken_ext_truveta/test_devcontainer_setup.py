import os
import subprocess
from pathlib import Path


def test_ml1_asset_hydration_pulls_once_and_skips_complete_assets(tmp_path):
    """Hydrate ML1 assets beside the installed package and avoid repeat pulls."""
    package_dir = tmp_path / "openlinktoken" / "core" / "ai" / "tokens"
    package_dir.mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$ML1_TEST_PACKAGE_DIR\"\n", encoding="utf-8"
    )
    fake_python.chmod(0o755)

    oras_log = tmp_path / "oras.log"
    fake_oras = fake_bin / "oras"
    fake_oras.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$ORAS_LOG"
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output" ]; then
    output="$2"
    shift
  fi
  shift
done
mkdir -p "$output"
for filename in model.onnx model.onnx.data tokenizer.json asset-manifest.json; do
  printf 'asset\\n' > "$output/$filename"
done
""",
        encoding="utf-8",
    )
    fake_oras.chmod(0o755)

    script_path = (
        Path(__file__).parents[3] / ".devcontainer" / "scripts" / "unified-setup.sh"
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["UV_PROJECT_ENVIRONMENT"] = str(tmp_path / "venv")
    environment["ML1_TEST_PACKAGE_DIR"] = str(package_dir)
    environment["ORAS_LOG"] = str(oras_log)

    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source '{script_path}'; step_hydrate_ml1_assets; step_hydrate_ml1_assets",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    pull_commands = oras_log.read_text(encoding="utf-8").splitlines()
    assert len(pull_commands) == 1
    assert "ghcr.io/truvetapublic/openlinktoken-ml1-assets:v1" in pull_commands[0]
    assert str(package_dir) in pull_commands[0]
    assert all(
        (package_dir / filename).is_file()
        for filename in (
            "model.onnx",
            "model.onnx.data",
            "tokenizer.json",
            "asset-manifest.json",
        )
    )
