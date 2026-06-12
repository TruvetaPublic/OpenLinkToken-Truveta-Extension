# Open Link Token Truveta Extension

- [Overview](#overview)
- [Extension Commands](#extension-commands)
  - [Subcommand Overview](#subcommand-overview)
  - [login](#login)
  - [initiate-exchange](#initiate-exchange)
  - [upload](#upload)
  - [auto-upload](#auto-upload)
  - [logout](#logout)
- [Installing the Extension](#installing-the-extension)
- [Developer Guide](#developer-guide)

## Overview

`openlinktoken-ext-truveta` is an [Open Link Token CLI](https://github.com/TruvetaPublic/OpenLinkToken) extension that adds Truveta-specific commands under the `truveta` subcommand.

```text
olt truveta <subcommand>
```

## Extension Commands

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

Parameters:
- -i FILE, --input FILE: tokenized CSV, Parquet, or ZIP to upload.
- --metadata META.json: optional metadata JSON for non-ZIP uploads.

Example:
```bash
olt truveta upload -i packaged.parquet
```

### auto-upload

Parameters:
- -i FILE, --input FILE: raw CSV or Parquet input file.

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

## Installing the Extension

Once a wheel is built (or downloaded from a release), install it via the `olt` CLI:

```bash
# From a local build
olt extension install file:///$(pwd)/dist/openlinktoken_ext_truveta-0.1.0-py3-none-any.whl

# Pass --yes / -y to skip the security confirmation prompt
olt extension install -y file:///$(pwd)/dist/openlinktoken_ext_truveta-0.1.0-py3-none-any.whl
```

## Developer Guide

Local development setup, build/wheel instructions, versioning, CI, and release workflow details live in [docs/developer-guide.md](docs/developer-guide.md).
