# install.ps1 — One-line installer for the OLT Truveta CLI bundle.
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

$Version = $Version -replace '^v', ''
if ($Version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
    Write-Error "Invalid release version '$Version'."
    exit 1
}

$PackageName = "olt-truveta-$Version-windows-x64"
$ArchiveName = "$PackageName.zip"
$ChecksumName = "$ArchiveName.sha256"
$ArchiveUrl = "https://github.com/$Repo/releases/download/v$Version/$ArchiveName"
$ChecksumUrl = "https://github.com/$Repo/releases/download/v$Version/$ChecksumName"

# ---------------------------------------------------------------------------
# Download and install
# ---------------------------------------------------------------------------
Write-Host "Installing OLT Truveta v$Version (windows-x64)..."

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$ArchivePath = Join-Path $InstallDir $ArchiveName
$ChecksumPath = Join-Path $InstallDir $ChecksumName
$StagingDir = Join-Path $InstallDir ".$PackageName.staging"
$BundleDir = Join-Path $InstallDir $PackageName
$LauncherPath = Join-Path $InstallDir "olt.cmd"
$LegacyPath = Join-Path $InstallDir "olt.exe"

try {
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath -UseBasicParsing
    Invoke-WebRequest -Uri $ChecksumUrl -OutFile $ChecksumPath -UseBasicParsing

    $ChecksumContent = Get-Content -LiteralPath $ChecksumPath -Raw
    if ($ChecksumContent -notmatch '^\s*([0-9A-Fa-f]{64})\s+') {
        throw "Release checksum file is invalid."
    }
    $ExpectedHash = $Matches[1]
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash
    if (-not $ActualHash.Equals($ExpectedHash, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Release archive checksum verification failed."
    }

    if (Test-Path -LiteralPath $StagingDir) {
        Remove-Item -LiteralPath $StagingDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $StagingDir -Force

    $ExtractedBundle = Join-Path $StagingDir $PackageName
    $ExecutablePath = Join-Path $ExtractedBundle "olt.exe"
    $RuntimeDirectory = Join-Path $ExtractedBundle "_internal"
    if (-not (Test-Path -LiteralPath $ExtractedBundle -PathType Container) -or
        -not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $RuntimeDirectory -PathType Container)) {
        throw "Release archive does not contain a complete OLT bundle."
    }

    if (Test-Path -LiteralPath $BundleDir) {
        Remove-Item -LiteralPath $BundleDir -Recurse -Force
    }
    Move-Item -LiteralPath $ExtractedBundle -Destination $BundleDir -Force

    if (Test-Path -LiteralPath $LegacyPath -PathType Leaf) {
        Remove-Item -LiteralPath $LegacyPath -Force
    }
    $LauncherContent = "@echo off`r`n`"%~dp0$PackageName\olt.exe`" %*`r`n"
    [System.IO.File]::WriteAllText(
        $LauncherPath,
        $LauncherContent,
        [System.Text.UTF8Encoding]::new($false)
    )
} finally {
    if (Test-Path -LiteralPath $ArchivePath) { Remove-Item -LiteralPath $ArchivePath -Force }
    if (Test-Path -LiteralPath $ChecksumPath) { Remove-Item -LiteralPath $ChecksumPath -Force }
    if (Test-Path -LiteralPath $StagingDir) { Remove-Item -LiteralPath $StagingDir -Recurse -Force }
}

Write-Host "Installed bundle: $BundleDir"
Write-Host "Command: $LauncherPath"

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
    & $LauncherPath --help | Out-Null
    Write-Host "Verification passed."
} catch {
    Write-Warning "Installed but could not run '$LauncherPath --help': $_"
}

Write-Host "Done. Run 'olt truveta --help' to get started."
