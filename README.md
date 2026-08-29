# Open Link Token Truveta Extension

- [Open Link Token Truveta Extension](#open-link-token-truveta-extension)
  - [Overview](#overview)
  - [Installation](#installation)
    - [Quick Install (recommended)](#quick-install-recommended)
    - [Standalone Distributables](#standalone-distributables)
    - [Python Extension Install](#python-extension-install)
    - [Subcommand Overview](#subcommand-overview)
    - [login](#login)
    - [initiate-exchange](#initiate-exchange)
    - [upload](#upload)
    - [auto-upload](#auto-upload)
    - [logout](#logout)
  - [Developer Guide](#developer-guide)

## Overview

`openlinktoken-ext-truveta` is an [Open Link Token CLI](https://github.com/TruvetaPublic/OpenLinkToken) extension that adds Truveta-specific commands under the `truveta` subcommand.

```text
olt truveta <subcommand>
```

## Installation

### Quick Install (recommended)

**macOS / Linux** — paste into a terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.sh | bash
```

**Windows** — paste into PowerShell:

```powershell
irm https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.ps1 | iex
```

Both scripts:

- Auto-detect your platform and download the correct bundle from the [latest GitHub Release](https://github.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/releases/latest)
- Install the complete one-folder bundle and expose `~/.local/bin/olt` (macOS/Linux) or `%USERPROFILE%\.local\bin\olt.cmd` (Windows) — no administrator privileges required
- Add the install directory to your PATH if it isn't already

**Version pinning** — install a specific release instead of the latest:

```bash
# macOS / Linux
OLT_TRUVETA_VERSION=1.0.0 curl -fsSL https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.sh | bash

# Windows
$env:OLT_TRUVETA_VERSION="1.0.0"; irm https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.ps1 | iex
```

### Standalone Distributables

Pre-built one-folder ZIP bundles that include the OLT CLI, the Truveta extension,
and all runtime files — no Python required. The raw PyInstaller executable is not
published separately because it requires the adjacent `_internal/` directory.

Download the ZIP bundle and its `.sha256` checksum from the [Releases page](https://github.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/releases/latest):

| Platform | Bundle                                  | Notes               |
| -------- | --------------------------------------- | ------------------- |
| macOS    | `olt-truveta-{version}-macos-arm64.zip` | Apple Silicon arm64 |
| Linux    | `olt-truveta-{version}-linux-x64.zip`   | x86_64              |
| Windows  | `olt-truveta-{version}-windows-x64.zip` | x86_64              |

The checksum file is named `<bundle>.zip.sha256`. Keep the extracted bundle
directory intact so the executable can find its `_internal/` runtime directory.

After downloading, verify the checksum and extract the complete bundle:

```bash
# macOS
shasum -a 256 -c olt-truveta-{version}-macos-arm64.zip.sha256
unzip -q olt-truveta-{version}-macos-arm64.zip
chmod +x olt-truveta-{version}-macos-arm64/olt
./olt-truveta-{version}-macos-arm64/olt --help
```

```bash
# Linux
sha256sum -c olt-truveta-{version}-linux-x64.zip.sha256
unzip -q olt-truveta-{version}-linux-x64.zip
chmod +x olt-truveta-{version}-linux-x64/olt
./olt-truveta-{version}-linux-x64/olt --help
```

```powershell
# Windows
Expand-Archive olt-truveta-{version}-windows-x64.zip
& ".\olt-truveta-{version}-windows-x64\olt.exe" --help
```

### Python Extension Install

If you already have the OLT CLI installed via Python, you can install just this extension from a release wheel:

```bash
# From a downloaded release wheel
olt extension install openlinktoken_ext_truveta-1.0.0-py3-none-any.whl

# Pass --yes / -y to skip the security confirmation prompt
olt extension install -y openlinktoken_ext_truveta-1.0.0-py3-none-any.whl
```

### Subcommand Overview

- login: Authenticate with Truveta via OAuth 2.0 Device Code Flow.
- initiate-exchange: Negotiate exchange config with the Token Service.
- upload: Upload a tokenized CSV, Parquet, or ZIP file for overlap analysis.
- auto-upload: Run initiate-exchange, package, and upload in one step.
- logout: Revoke and clear cached Truveta credentials.

### login

Parameters:

- --domain DOMAIN: authenticate against a specific Truveta domain.
- --force: re-authenticate and discard cached credentials.

Example:

```bash
olt truveta login
```

### initiate-exchange

Parameters:

- none

Example:

```bash
olt truveta initiate-exchange
```

### upload

Uploads a tokenized file to Truveta for overlap analysis. Files are automatically split
into chunks and uploaded sequentially. Progress is reported after each chunk.

Parameters:

- `-i FILE, --input FILE`: tokenized CSV, Parquet, or ZIP to upload.
- `--metadata META.json`: optional metadata JSON for non-ZIP uploads.

Example:

```bash
olt truveta upload -i packaged.parquet
```

For all file sizes, the upload uses a chunked protocol. The server advertises the
maximum chunk size at session initialization; the CLI uses that value to split the
file automatically. Progress is displayed as each chunk is sent:

```
Uploading packaged.parquet (63.0 MB, 8 chunk(s))
chunk 1/8 (12%)
chunk 2/8 (25%)
...
chunk 8/8 (100%)
✓ Upload accepted.
```

If an upload is interrupted or a chunk is rejected, a clear error is shown
describing which chunks are missing. Re-run the same command to retry.

### auto-upload

Parameters:

- -i FILE, --input FILE: raw CSV or Parquet input file.
- --disable-inferencing: disable ML1 ONNX inference token generation.
- --inferencing-batch-size SIZE: set the ML1 ONNX inference batch size.
- --inferencing-num-threads COUNT: set the ORT inference thread count.

Example:

```bash
olt truveta auto-upload -i raw_data.csv
```

### logout

Parameters:

- none

Example:

```bash
olt truveta logout
```

**Example — full upload flow (recommended):**

```bash
olt truveta login
olt truveta auto-upload -i raw_data.csv
```

## Developer Guide

Local development setup, build/wheel instructions, versioning, CI, and release workflow details live in [docs/developer-guide.md](docs/developer-guide.md).
