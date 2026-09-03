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

- Auto-detect your platform and download the correct binary from the [latest GitHub Release](https://github.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/releases/latest)
- Install to `~/.local/bin/olt` (macOS/Linux) or `%USERPROFILE%\.local\bin\olt.exe` (Windows) — no administrator privileges required
- Add the install directory to your PATH if it isn't already

**Version pinning** — install a specific release instead of the latest:

```bash
# macOS / Linux
OLT_TRUVETA_VERSION=1.0.0 curl -fsSL https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.sh | bash

# Windows
$env:OLT_TRUVETA_VERSION="1.0.0"; irm https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.ps1 | iex
```

### Standalone Distributables

Pre-built single-file executables that bundle the OLT CLI and the Truveta extension together — no Python required.

Download the binary for your platform from the [Releases page](https://github.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/releases/latest):

| Platform | Binary                                      | Notes                                              |
| -------- | ------------------------------------------- | -------------------------------------------------- |
| macOS    | `olt-truveta-v{version}-macos-universal`    | Universal binary — runs on Intel and Apple Silicon |
| Linux    | `olt-truveta-v{version}-linux-x86_64`       | x86_64                                             |
| Windows  | `olt-truveta-v{version}-windows-x86_64.exe` | x86_64                                             |

Each binary is accompanied by a `.zip` archive and a `.sha256` checksum file.

After downloading, make the binary executable and optionally move it onto your PATH:

```bash
# macOS
chmod +x olt-truveta-v*-macos-universal
mv olt-truveta-v*-macos-universal ~/.local/bin/olt
olt --help
```

```bash
# Linux
chmod +x olt-truveta-v*-linux-x86_64
mv olt-truveta-v*-linux-x86_64 ~/.local/bin/olt
olt --help
```

```powershell
# Windows — rename and move to a directory on your PATH
Move-Item olt-truveta-v*-windows-x86_64.exe "$env:USERPROFILE\.local\bin\olt.exe"
olt --help
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
✓ Upload accepted. Exchange ID: <exchange-id>
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
