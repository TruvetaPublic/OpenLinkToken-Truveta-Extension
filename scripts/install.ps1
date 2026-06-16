# install.ps1 — One-line installer for the OLT Truveta CLI distributable.
#
# Usage:
#   irm https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.ps1 | iex
#
# Environment overrides:
#   $env:OLT_TRUVETA_VERSION  — Pin to a specific release (e.g., "1.0.0"). Defaults to latest.
#   $env:OLT_INSTALL_DIR      — Override the install directory.
#                               Defaults to $env:USERPROFILE\.local\bin

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # suppress slow progress bars in Invoke-WebRequest

$Repo = "TruvetaPublic/OpenLinkToken-Truveta-Extension"
$InstallDir = if ($env:OLT_INSTALL_DIR) { $env:OLT_INSTALL_DIR } else { Join-Path $env:USERPROFILE ".local\bin" }
$Version = if ($env:OLT_TRUVETA_VERSION) { $env:OLT_TRUVETA_VERSION } else { $null }

# ---------------------------------------------------------------------------
# Architecture check
# ---------------------------------------------------------------------------
$Arch = $env:PROCESSOR_ARCHITECTURE
if ($Arch -notin @("AMD64", "x86_64")) {
    Write-Error "Unsupported architecture '$Arch'. Only x86_64 (AMD64) is supported."
    exit 1
}

# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------
if (-not $Version) {
    Write-Host "Fetching latest release..."
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -UseBasicParsing
    $Version = $Release.tag_name -replace '^v', ''
}

if (-not $Version) {
    Write-Error "Could not determine the latest release version. Set `$env:OLT_TRUVETA_VERSION to install a specific version."
    exit 1
}

$BinaryName = "olt-truveta-v$Version-windows-x86_64.exe"
$DownloadUrl = "https://github.com/$Repo/releases/download/v$Version/$BinaryName"

# ---------------------------------------------------------------------------
# Download and install
# ---------------------------------------------------------------------------
Write-Host "Installing OLT Truveta v$Version (windows-x86_64)..."

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$DestPath = Join-Path $InstallDir "olt.exe"
$TempPath = Join-Path ([System.IO.Path]::GetTempPath()) "olt-truveta-$Version.exe"

try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempPath -UseBasicParsing
    Move-Item -Path $TempPath -Destination $DestPath -Force
} catch {
    if (Test-Path $TempPath) { Remove-Item $TempPath -Force }
    throw
}

Write-Host "Installed: $DestPath"

# ---------------------------------------------------------------------------
# PATH update (user scope — no elevation required)
# ---------------------------------------------------------------------------
$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$UserPath;$InstallDir", "User")
    Write-Host ""
    Write-Host "  Added $InstallDir to your user PATH."
    Write-Host "  Restart your terminal (or run: `$env:PATH += `";$InstallDir`") for the change to take effect."
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
try {
    & $DestPath --help | Out-Null
    Write-Host "Verification passed."
} catch {
    Write-Warning "Installed but could not run '$DestPath --help': $_"
}

Write-Host "Done. Run 'olt truveta --help' to get started."
