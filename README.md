# openlinktoken-ext-truveta

- [openlinktoken-ext-truveta](#openlinktoken-ext-truveta)
  - [Overview](#overview)
  - [Extension Commands](#extension-commands)
    - [Upload Validation](#upload-validation)
    - [Environment Configuration](#environment-configuration)
    - [Token Storage](#token-storage)
  - [Local Development Setup](#local-development-setup)
    - [Prerequisites](#prerequisites)
    - [Install Dependencies](#install-dependencies)
    - [Run Tests](#run-tests)
    - [Smoke Test](#smoke-test)
  - [Installing the Extension](#installing-the-extension)
  - [Building a Wheel](#building-a-wheel)

## Overview

`openlinktoken-ext-truveta` is an [Open Link Token CLI](https://github.com/TruvetaPublic/OpenLinkToken) extension that adds Truveta-specific commands under the `truveta` subcommand.

```text
olt truveta <subcommand>
```

## Extension Commands

| Command                                           | Description                                                          |
| ------------------------------------------------- | -------------------------------------------------------------------- |
| `olt truveta login`                               | Authenticate with Truveta via OAuth 2.0 Device Code Flow             |
| `olt truveta login --force`                       | Re-authenticate, discarding any cached credentials                   |
| `olt truveta login --domain DOMAIN`               | Authenticate against a specific Truveta domain                       |
| `olt truveta initiate-exchange`                   | Negotiate exchange config with the Token Service                     |
| `olt truveta upload -i FILE`                      | Upload a tokenized CSV, Parquet, or ZIP file for overlap analysis    |
| `olt truveta upload --input FILE`                 | Same as `-i`, long form                                              |
| `olt truveta upload -i FILE --metadata META.json` | Attach a metadata JSON file (non-ZIP uploads only)                   |
| `olt truveta upload -i FILE (local dev)`          | Set `OLT_TRV_LOCAL_DEV=1` to upload to a local API                   |
| `olt truveta auto-upload -i FILE`                 | Convenience: runs initiate-exchange, package, and upload in one step |
| `olt truveta auto-upload --input FILE`            | Same as `-i`, long form                                              |
| `olt truveta logout`                              | Revoke and clear all cached Truveta credentials                      |

### Environment Configuration

| Variable            | Description                                                                                        | Default       |
| ------------------- | -------------------------------------------------------------------------------------------------- | ------------- |
| `OLT_TRV_DOMAIN`    | Override the target Truveta domain for `olt truveta login`                                         | `truveta.com` |
| `OLT_TRV_LOCAL_DEV` | Route exchange and upload calls to `http://localhost:18080` (any truthy value: `1`, `true`, `yes`) | unset         |

### Upload Validation

Before sending any data, `olt truveta upload` performs three local checks:

1. **Format** — only `.csv`, `.parquet`, and `.zip` are accepted.
2. **Schema** — the file must contain the required columns: `RuleId`, `Token`, and `RecordId`. For ZIP files, the inner data file is inspected without extracting to disk.
3. **Encryption** — a sample token is decrypted against the transport key derived from the current day's exchange config. If decryption fails, the upload is blocked with an actionable error asking you to re-run `olt package` with the current exchange config.

ZIP files are uploaded as-is. If a `.metadata.json` file is embedded inside the ZIP, it is extracted and sent automatically. Passing `--metadata` alongside a ZIP is not supported and will emit a warning; the flag is ignored.

**Example — full upload flow (recommended):**

```bash
olt truveta login --domain dev.truveta-int.com
olt truveta auto-upload -i raw_data.csv
# Runs initiate-exchange, packages to parquet in a temp dir, uploads, and cleans up automatically.
```

**Example — manual step-by-step upload:**

```bash
olt truveta login
olt truveta initiate-exchange
olt package --input raw_data.csv --output packaged.parquet --exchange-config openlinktoken-YYYY-MM-DD.exchange.json
olt truveta upload -i packaged.parquet

# Or upload as a ZIP with an optional metadata sidecar:
olt truveta upload -i packaged.zip
```

**Example — target the local Token Service:**

```bash
export OLT_TRV_LOCAL_DEV=1
olt truveta initiate-exchange
olt truveta upload -i tokenized.csv
```

**Example — target the dev environment:**

```bash
export OLT_TRV_DOMAIN=dev.truveta-int.com
olt truveta login
```

Supported domain values are:

- `dev.truveta-int.com`
- `truveta-int.com`
- `truveta.com`

### Token Storage

Credentials are cached at `~/.openlinktoken/truveta/<domain>/credentials.json` and auto-evicted 5 minutes before expiry. The selected domain is persisted in `~/.openlinktoken/truveta/session.json`, and non-login commands derive their Auth0 and API URLs from that saved domain. The session file is merge-friendly so additional session metadata can be added over time without overwriting existing fields. Exchange keypairs are stored per UTC day at `~/.openlinktoken/openlinktoken-YYYY-MM-DD.private.pem` and `~/.openlinktoken/openlinktoken-YYYY-MM-DD.public.pem`. Run `olt truveta logout` to revoke the access token server-side and clear session files.

When `OLT_TRV_LOCAL_DEV` is set to a truthy value (`1`, `true`, `yes`, `y`, or `on`), the extension still authenticates against `dev.truveta-int.com`, but it sends exchange and upload API calls to `http://localhost:18080`.

## Local Development Setup

### Prerequisites

- Python 3.10+
- `pip` or `uv`
- Access to [TruvetaPublic/OpenLinkToken](https://github.com/TruvetaPublic/OpenLinkToken) on GitHub

### Install Dependencies

`openlinktoken-cli` is not on PyPI — it is installed from the `TruvetaPublic/OpenLinkToken` GitHub repo as part of `uv sync`.

> **Dev container note:** VS Code sets `GIT_DIR` as a worktree-scoped env var, which confuses uv's git backend. Prefix all uv commands with `(unset GIT_DIR; ...)` to work around this.
> **VPN/proxy note:** If internal `*.dev.truveta-int.com` endpoints do not resolve from your shell, export the dev HTTP proxy after connecting to VPN.

```bash
export HTTP_PROXY=http://proxy-http.dev.truveta-int.com:8888
export HTTPS_PROXY=$HTTP_PROXY
```

```bash
# From the repo root (workspace-scoped, avoids unrelated workspace member deps)
(unset GIT_DIR; uv sync --package openlinktoken-ext-truveta --dev)

# Or from within the package directory
cd openlinktoken-ext-truveta
(unset GIT_DIR; uv sync --dev)
```

### Run Tests

```bash
# From the repo root
(unset GIT_DIR; uv run --package openlinktoken-ext-truveta pytest openlinktoken-ext-truveta/src/test/ -v)

# Or from within the package directory
cd openlinktoken-ext-truveta
(unset GIT_DIR; uv run pytest -v)
```

### Smoke Test

After `uv sync --dev`, run:

```bash
(unset GIT_DIR; uv run olt truveta login --domain dev.truveta-int.com)
# Opens browser for Auth0 device code login, then prints: Welcome, <name>!
```

## Installing the Extension

Once a wheel is built, install it via the `olt` CLI:

```bash
# From a local build
olt extension install file:///$(pwd)/dist/openlinktoken_ext_truveta-0.1.0-py3-none-any.whl

# Pass --yes / -y to skip the security confirmation prompt
olt extension install -y file:///$(pwd)/dist/openlinktoken_ext_truveta-0.1.0-py3-none-any.whl
```

## Building a Wheel

```bash
pip install build
python -m build
```

This produces `dist/openlinktoken_ext_truveta-0.1.0-py3-none-any.whl`.
