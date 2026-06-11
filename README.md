# openlinktoken-ext-truveta

- [openlinktoken-ext-truveta](#openlinktoken-ext-truveta)
  - [Overview](#overview)
  - [Extension Commands](#extension-commands)
    - [Environment Configuration](#environment-configuration)
    - [Upload Validation](#upload-validation)
    - [Token Storage](#token-storage)
  - [Installing the Extension](#installing-the-extension)
  - [Building a Wheel](#building-a-wheel)
  - [Versioning](#versioning)
  - [Continuous Integration](#continuous-integration)
  - [Releases](#releases)

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

Credentials are cached at `~/.openlinktoken/truveta/<domain>/credentials.json` and auto-evicted 5 minutes before expiry. The selected domain is persisted in `~/.openlinktoken/truveta/session.json`, and non-login commands derive their Auth0 and API URLs from that saved domain. Exchange keypairs are stored per UTC day at `~/.openlinktoken/openlinktoken-YYYY-MM-DD.private.pem` and `~/.openlinktoken/openlinktoken-YYYY-MM-DD.public.pem`. Run `olt truveta logout` to revoke the access token server-side and clear session files.

When `OLT_TRV_LOCAL_DEV` is set to a truthy value (`1`, `true`, `yes`, `y`, or `on`), the extension still authenticates against `dev.truveta-int.com`, but it sends exchange and upload API calls to `http://localhost:18080`.

## Installing the Extension

Once a wheel is built (or downloaded from a release), install it via the `olt` CLI:

```bash
# From a local build
olt extension install file:///$(pwd)/dist/openlinktoken_ext_truveta-0.1.0-py3-none-any.whl

# Pass --yes / -y to skip the security confirmation prompt
olt extension install -y file:///$(pwd)/dist/openlinktoken_ext_truveta-0.1.0-py3-none-any.whl
```

## Developer Guide

Local development setup now lives in [docs/developer-guide.md](docs/developer-guide.md).

## Building a Wheel

```bash
python -m build
```

This produces `dist/openlinktoken_ext_truveta-<version>-py3-none-any.whl` and the corresponding source distribution.

## Versioning

This project follows [Semantic Versioning](https://semver.org/). Version bumps are managed with [`bump2version`](https://github.com/c4urself/bump2version) and configured in `.bumpversion.cfg`.

```bash
# Patch release (0.1.0 -> 0.1.1) — bug fixes
bump2version patch

# Minor release (0.1.0 -> 0.2.0) — backwards-compatible features
bump2version minor

# Major release (0.1.0 -> 1.0.0) — breaking changes
bump2version major
```

`bump2version` updates the version in `pyproject.toml` and `src/main/openlinktoken_ext_truveta/__init__.py`, creates a commit, and tags the commit as `v<new_version>`.

## Continuous Integration

CI is defined in `.github/workflows/ci.yml` and runs on every push and pull request targeting `main`. The workflow:

1. Checks out the source.
2. Sets up Python 3.12 and uv.
3. Installs the package with dev extras.
4. Lints with flake8 and autoflake (unused import detection).
5. Runs the test suite (`pytest`).
6. Builds the wheel and sdist (`python -m build`).
7. Uploads `dist/` as a build artifact (7-day retention).

## Releases

Releases are defined in `.github/workflows/release.yml` and triggered in two ways:

- **Tag push** — push a `v*` tag (created by `bump2version`) to build and publish.
- **Manual dispatch** — enter a version number in the GitHub Actions UI.

The release workflow:

1. Builds the wheel and sdist, then publishes them to GitHub Releases.
2. Builds standalone executables for Linux, Windows, and macOS using PyInstaller.
3. Attaches all artifacts to the GitHub Release.

The standalone binary bundles both the `openlinktoken` CLI and the Truveta extension into a single file — no Python installation required for end users.
