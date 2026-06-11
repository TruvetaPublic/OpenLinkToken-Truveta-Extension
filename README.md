# OpenLinkToken Truveta Extension

- [OpenLinkToken Truveta Extension](#openlinktoken-truveta-extension)
  - [Overview](#overview)
  - [Extension Commands](#extension-commands)
    - [Subcommand Overview](#subcommand-overview)
    - [login](#login)
    - [initiate-exchange](#initiate-exchange)
    - [upload](#upload)
    - [auto-upload](#auto-upload)
    - [logout](#logout)
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
