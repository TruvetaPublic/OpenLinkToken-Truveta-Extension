"""Regression tests for the standalone bundle installer."""

import os
import shutil
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
INSTALL_SCRIPT = REPOSITORY_ROOT / "scripts" / "install.sh"


def test_installer_extracts_latest_release_tag_with_portable_sed(tmp_path):
    """Extract the version from GitHub's indented release JSON on BSD sed."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    fake_bin.joinpath("curl").write_text(
        """#!/bin/sh
case "$*" in
  *api.github.com*)
    printf '%s\\n' '  "tag_name": "v1.1.0",'
    ;;
  *)
    exit 1
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_bin.joinpath("uname").write_text(
        """#!/bin/sh
case "$1" in
  -s) printf '%s\\n' Linux ;;
  -m) printf '%s\\n' x86_64 ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    real_sed = shutil.which("sed")
    assert real_sed is not None
    fake_bin.joinpath("sed").write_text(
        f"""#!/bin/sh
case "$*" in
  *'v\\\\?'*) cat ;;
  *) exec '{real_sed}' "$@" ;;
esac
""",
        encoding="utf-8",
    )
    for command in ("curl", "uname", "sed"):
        fake_bin.joinpath(command).chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["OLT_INSTALL_DIR"] = str(tmp_path / "install")
    environment.pop("OLT_TRUVETA_VERSION", None)

    result = subprocess.run(
        ["bash", str(INSTALL_SCRIPT)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Installing OLT Truveta v1.1.0 (linux-x64)..." in result.stdout
    assert "invalid release version" not in result.stderr
