"""Regression tests for the standalone bundle installers."""

import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).parents[3]
INSTALL_SCRIPT = REPOSITORY_ROOT / "scripts" / "install.ps1"


def test_windows_installer_updates_current_process_path():
    """Make the installed command available in the current PowerShell process."""
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell is required to test the Windows installer.")

    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    path_section = script.split(
        "# PATH update (user scope — no elevation required)", 1
    )[1].split("# Verify", 1)[0]
    install_dir = r"C:\Users\Test\.local\bin"
    powershell = f"""
$ErrorActionPreference = "Stop"
$InstallDir = "{install_dir}"
$env:PATH = "C:\\Windows\\System32"
{path_section}
if (($env:PATH -split ";") -notcontains $InstallDir) {{
    throw "The current process PATH does not contain the install directory."
}}
"""

    result = subprocess.run(
        [pwsh, "-NoProfile", "-Command", powershell],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
