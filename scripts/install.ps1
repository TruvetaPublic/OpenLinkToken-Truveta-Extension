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
param(
    [string]$ModelTag = $(if ($env:OLT_ML1_MODEL_TAG) { $env:OLT_ML1_MODEL_TAG } else { "v1" })
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # suppress slow progress bars in Invoke-WebRequest

$Repo = "TruvetaPublic/OpenLinkToken-Truveta-Extension"
$ModelPackage = "ghcr.io/truvetapublic/openlinktoken-ml1-assets"
$OrasVersion = "1.3.3"
$InstallDir = if ($env:OLT_INSTALL_DIR) { $env:OLT_INSTALL_DIR } else { Join-Path $env:USERPROFILE ".local\bin" }
$Version = if ($env:OLT_TRUVETA_VERSION) { $env:OLT_TRUVETA_VERSION } else { $null }

function Install-Ml1Assets {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BundleRoot,

        [Parameter(Mandatory = $true)]
        [string]$TemporaryDirectory
    )

    if ($ModelTag -notmatch '^v[0-9]+$') {
        throw "Invalid ML1 model tag: $ModelTag (expected vN)"
    }

    $OrasArchive = "oras_${OrasVersion}_windows_amd64.zip"
    $OrasChecksum = "30ca213a565a450de33001dae83053db53c221e6674c5233dc3406b686657969"
    $OrasArchivePath = Join-Path $TemporaryDirectory $OrasArchive
    $OrasUrl = "https://github.com/oras-project/oras/releases/download/v$OrasVersion/$OrasArchive"
    Write-Host "Downloading ORAS $OrasVersion..."
    Invoke-WebRequest -Uri $OrasUrl -OutFile $OrasArchivePath -UseBasicParsing
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $OrasArchivePath).Hash -ine $OrasChecksum) {
        throw "SHA-256 verification failed for ORAS $OrasVersion"
    }

    $OrasDirectory = Join-Path $TemporaryDirectory "oras"
    Expand-Archive -LiteralPath $OrasArchivePath -DestinationPath $OrasDirectory
    $Oras = Join-Path $OrasDirectory "oras.exe"
    $ModelAssetsDirectory = Join-Path $TemporaryDirectory "ml1-assets"
    New-Item -ItemType Directory -Path $ModelAssetsDirectory -Force | Out-Null
    Write-Host "Downloading ML1 model assets $ModelTag..."
    & $Oras pull "${ModelPackage}:$ModelTag" --output $ModelAssetsDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to pull ML1 model assets ${ModelPackage}:$ModelTag; ensure the GHCR package is public"
    }

    $RequiredFiles = @("asset-manifest.json", "model.onnx", "model.onnx.data", "tokenizer.json")
    foreach ($FileName in $RequiredFiles) {
        $AssetPath = Join-Path $ModelAssetsDirectory $FileName
        if (-not (Test-Path -LiteralPath $AssetPath -PathType Leaf) -or
            (Get-Item -LiteralPath $AssetPath).Length -eq 0) {
            throw "ML1 OCI artifact is missing $FileName"
        }
    }

    try {
        $Manifest = Get-Content -Raw -LiteralPath (Join-Path $ModelAssetsDirectory "asset-manifest.json") |
            ConvertFrom-Json
    } catch {
        throw "Invalid ML1 asset manifest in OCI artifact: $($_.Exception.Message)"
    }
    if (-not $Manifest.assets) {
        throw "ML1 asset manifest has no assets map"
    }
    foreach ($FileName in @("model.onnx", "model.onnx.data", "tokenizer.json")) {
        $AssetMetadata = $Manifest.assets.PSObject.Properties[$FileName].Value
        if (-not $AssetMetadata -or $AssetMetadata.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
            $AssetMetadata.size -isnot [long] -and $AssetMetadata.size -isnot [int]) {
            throw "Invalid ML1 asset manifest entry for $FileName"
        }
        $AssetPath = Join-Path $ModelAssetsDirectory $FileName
        if ((Get-Item -LiteralPath $AssetPath).Length -ne $AssetMetadata.size) {
            throw "Unexpected size for ML1 asset $FileName"
        }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $AssetPath).Hash -ine $AssetMetadata.sha256) {
            throw "SHA-256 verification failed for $FileName"
        }
    }

    $ModelDirectory = Join-Path $BundleRoot "_internal\openlinktoken\core\ai\tokens"
    New-Item -ItemType Directory -Path $ModelDirectory -Force | Out-Null
    foreach ($FileName in $RequiredFiles) {
        Copy-Item -LiteralPath (Join-Path $ModelAssetsDirectory $FileName) `
            -Destination $ModelDirectory -Force
    }
}

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

if ($ModelTag -notmatch '^v[0-9]+$') {
    throw "Invalid ML1 model tag: $ModelTag (expected vN)"
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
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("olt-truveta-install-" + [Guid]::NewGuid().ToString("N"))
$BundleDir = Join-Path $InstallDir $PackageName
$LauncherPath = Join-Path $InstallDir "olt.cmd"
$LegacyPath = Join-Path $InstallDir "olt.exe"

try {
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
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

    Install-Ml1Assets -BundleRoot $ExtractedBundle -TemporaryDirectory $TempDir

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
    if (Test-Path -LiteralPath $TempDir) { Remove-Item -LiteralPath $TempDir -Recurse -Force }
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
    Write-Host "  The command is available in this PowerShell session and new terminals."
    Write-Host ""
}
if (($env:PATH -split ';') -notcontains $InstallDir) {
    $env:PATH = "$InstallDir;$env:PATH"
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
