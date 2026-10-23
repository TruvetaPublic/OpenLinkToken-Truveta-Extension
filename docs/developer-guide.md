# Developer Guide

- [Developer Guide](#developer-guide)
  - [Local Development Setup](#local-development-setup)
    - [Prerequisites](#prerequisites)
    - [Install Dependencies](#install-dependencies)
    - [ML1 Assets](#ml1-assets)
    - [Manual Model Setup](#manual-model-setup)
    - [Run Tests](#run-tests)
    - [Smoke Test](#smoke-test)
  - [Building a Wheel](#building-a-wheel)
  - [Branching and Release Policy](#branching-and-release-policy)
  - [Versioning](#versioning)
  - [Continuous Integration](#continuous-integration)
  - [Releases](#releases)
  - [Independent Extension Updates](#independent-extension-updates)
    - [Bootstrap, Inspection, and Recovery](#bootstrap-inspection-and-recovery)
    - [Release Assets](#release-assets)
    - [Frozen Installer Prerequisite](#frozen-installer-prerequisite)
  - [Building a Standalone Executable Locally](#building-a-standalone-executable-locally)

## Local Development Setup

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- [ORAS](https://oras.land/) 1.3.3, required to retrieve OpenLinkToken's ML1 assets outside the dev container
- Access to [TruvetaPublic/OpenLinkToken](https://github.com/TruvetaPublic/OpenLinkToken) on GitHub (the `openlinktoken-cli` dev dependency is installed from this repo)

> The repository ships with a VS Code dev container under `.devcontainer/` that provisions Python 3.12, installs dev tooling, and runs an editable install automatically. This is the recommended development environment.

### Install Dependencies

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the package in editable mode, pulls `openlinktoken-cli` from the
OpenLinkToken `develop` branch, and installs dev tools (`pytest`, `bump2version`,
`build`, `autoflake`, `flake8`). The Truveta extension supports OpenLinkToken core
versions `>=2.2.1,<3.0.0`.

### ML1 Assets

The dev container automatically pulls the matched ML1 model, external model data,
tokenizer, and asset manifest from
`ghcr.io/truvetapublic/openlinktoken-ml1-assets:v1` into the installed Core-AI
package. The OCI package is public and model tags are independent of CLI
releases. For a manual development setup, pull the model into a temporary
directory and use the extension helper to validate and install it beside the
Core-AI package:

```bash
ML1_PACKAGE_DIR="$(python -c 'from pathlib import Path; import openlinktoken.core.ai.tokens as tokens; print(Path(tokens.__file__).resolve().parent)')"
ML1_ASSET_DIR="$(mktemp -d)"
oras pull "ghcr.io/truvetapublic/openlinktoken-ml1-assets:${OLT_ML1_MODEL_TAG:-v1}" \
  --output "$ML1_ASSET_DIR"
python -c 'import sys; from openlinktoken_ext_truveta.util.inferencing_assets import copy_ml1_assets; copy_ml1_assets(sys.argv[1], sys.argv[2])' \
  "$ML1_ASSET_DIR" "$ML1_PACKAGE_DIR"
```

The helper checks that all required files are present and match the sizes and
SHA-256 digests in `asset-manifest.json` before copying them.

### Manual Model Setup

Standalone release ZIPs omit `asset-manifest.json`, `model.onnx`,
`model.onnx.data`, and `tokenizer.json`. The official `scripts/install.sh` and
`scripts/install.ps1` installers retrieve the selected OCI model tag and verify
the downloaded assets before completing installation. They default to `v1`;
select another `vN` tag with `OLT_ML1_MODEL_TAG` (or `--model-tag vN` on the
POSIX installer, or `-ModelTag vN` on Windows).

Users who manually extract a ZIP must install the model beside the frozen
Core-AI package before using ML1 tokenization. Follow OpenLinkToken's
[manual ZIP installation guide](https://github.com/TruvetaPublic/OpenLinkToken/blob/main/pages/quickstarts/cli-quickstart.md#manual-zip-installation)
for the ORAS commands and platform-specific manifest verification. Do not mix
files from different model tags.

### Run Tests

```bash
pytest src/test -v
```

### Smoke Test

```bash
olt truveta login --domain dev.truveta-int.com
# Opens browser for Auth0 device code login, then prints: Welcome, <name>!
```

## Building a Wheel

```bash
python -m build
```

This produces `dist/openlinktoken_ext_truveta-<version>-py3-none-any.whl` and the corresponding source distribution.

## Branching and Release Policy

Feature work and standard pull requests should target `develop`. `main` is reserved for release PRs created from `release/x.y.z` branches only. The repository includes `.github/workflows/retarget-pr-to-develop.yml`, which automatically moves any PR that targets `main` from a non-release branch back to `develop`, and `.github/workflows/validate-pr-target.yml`, which fails PR validation unless the PR comes from a `release/*` branch when targeting `main`.

After a release is merged into `main`, `.github/workflows/sync-develop-on-merge.yml` synchronizes `develop` from `main`. If both branches changed the same file, the synchronization preserves the `main` version.

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

`bump2version` updates the version in `.bumpversion.cfg`, `pyproject.toml`, and the README wheel examples. The release workflow uses the resulting `current_version` value when creating the GitHub Release.
It also updates `standalone/registry.json` so bootstrap metadata stays aligned with the extension package version.

For release branches, `.github/workflows/auto-version-bump.yml` automatically extracts the target version from the `release/x.y.z` branch name and pushes the version bump back to that branch before the PR is merged.

## Continuous Integration

CI is defined in `.github/workflows/ci.yml` and runs on every push and pull request targeting `main` and `develop`. The workflow:

1. Checks out the source.
2. Sets up Python 3.12 and uv.
3. Installs the package with dev extras.
4. Lints with flake8 and autoflake (unused import detection).
5. Runs the test suite (`pytest`).
6. Builds the wheel and sdist (`python -m build`).
7. Uploads `dist/` as a build artifact (7-day retention).

## Releases

Releases are defined in `.github/workflows/auto-release.yml` and `.github/workflows/release.yml`:

1. When a `release/x.y.z` pull request is merged into `main`, `Create Release on Merge` reads `current_version` from `.bumpversion.cfg`, creates the corresponding `v<version>` tag, and creates the GitHub Release.
2. `Build Release Assets` runs after the release is created or published. It also supports manual dispatch for rebuilding assets for an existing release.

The asset workflow:

1. Builds the wheel and sdist, generates extension update manifests and a wheel checksum, then attaches them to the GitHub Release.
2. Builds one-folder standalone bundles for Linux x64, Windows x64, and macOS Apple Silicon arm64 using PyInstaller.
3. Pulls the public OpenLinkToken ML1 OCI artifact with ORAS 1.3.3, verifies its manifest-declared sizes and SHA-256 digests, and installs it into the temporary smoke-test bundle.
4. Runs a tokenization smoke test against each executable and verifies that the published ZIP does not contain any ML1 payload files.
5. Packages each model-free bundle as a ZIP with a SHA-256 checksum.
6. Attaches the wheel, source distribution, update manifests, ZIP bundles, and checksums to the GitHub Release.

The standalone build contains the `openlinktoken` CLI, the Truveta extension, and runtime dependencies in a reusable one-folder distribution — no Python installation required for end users. Model payloads are not included in release ZIPs; the official installers retrieve and verify them from `ghcr.io/truvetapublic/openlinktoken-ml1-assets:v1` by default. The local bundle is `dist/olt/` with executable `dist/olt/olt` on POSIX systems or `dist/olt/olt.exe` on Windows. Release assets are ZIP bundles plus `.sha256` files; the raw executable is not published separately because it requires the adjacent `_internal/` directory. Release dependencies and model assets use OpenLinkToken `main`; development tooling uses the `develop` branch. The extension runtime compatibility range remains `>=2.2.1,<3.0.0`. Standalone macOS releases support Apple Silicon arm64 only; Intel macOS is not supported. Help-oriented invocations load the installed extension registry so extension commands appear in the main menu. Heavy processing dependencies remain lazy until tokenization or packaging runs.

### Independent Extension Updates

The extension registry is persistent and core-managed so a standalone bundle can be
replaced without silently replacing an extension that was installed or updated
separately. The bootstrap manifest and the update manifest are generated from the
release version and wheel digest.

#### Bootstrap, Inspection, and Recovery

For an existing OLT installation, bootstrap the Truveta extension from the stable
latest-release manifest:

```bash
olt extension install --yes \
  --manifest https://github.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/releases/latest/download/openlinktoken-ext-truveta-bootstrap.json
```

Standalone bundles seed the core CLI's persistent extension registry from their
embedded registry on first launch, but only when that persistent registry is missing.
An existing registry, including an intentionally empty one, is never overwritten. The
persistent registry is outside the extracted bundle, so replacing a standalone core
bundle later leaves that registry untouched. Inspect and apply updates explicitly:

```bash
olt extension list
olt extension update truveta --dry-run
olt extension update truveta --yes
```

Update checks are non-blocking and do not silently replace installed extension
content. The registry is core-managed: explicit install, bootstrap, update, and
uninstall operations can write it, and core discovery can persist `disabled` and
`error` state for incompatible or failed frozen extensions.

The Truveta extension supports OpenLinkToken core versions `>=2.2.1,<3.0.0`.
For frozen standalone bundles, an incompatible extension is disabled instead of being
allowed to break core commands. Update the extension to a compatible release, or roll
back the core bundle to a version in the supported range.

Python installations rely on the host-runtime compatibility diagnostic because the
OpenLinkToken CLI and Core-AI distributions are host packages, not normal PyPI
dependencies of this extension. The check runs when a Truveta command is invoked; if
it reports a missing or incompatible core distribution, install a compatible
OpenLinkToken core or update the extension while core CLI discovery and commands
remain available.

#### Release Assets

After `uv build`, the release workflow generates these extension assets in
`release-assets/`:

- `openlinktoken_ext_truveta-<version>-py3-none-any.whl.sha256`
- `openlinktoken-ext-truveta-bootstrap.json`
- `openlinktoken-ext-truveta-update.json`

The workflow publishes those files together with `dist/*.whl` and `dist/*.tar.gz` to
the same GitHub Release. Each standalone build additionally publishes the complete
bundle and checksum pair for every supported platform:

- `olt-truveta-<version>-linux-x64.zip` and `.zip.sha256`
- `olt-truveta-<version>-macos-arm64.zip` and `.zip.sha256`
- `olt-truveta-<version>-windows-x64.zip` and `.zip.sha256`

### Building a Standalone Executable Locally

The standalone spec requires the OpenLinkToken release dependencies from
`main`, but no separate OpenLinkToken checkout or Git LFS model download.
Install the release dependencies and build the model-free bundle:

```bash
uv pip install -e ".[release]"
uv pip install -r pyinstaller-requirements.txt
pyinstaller --clean --noconfirm openlinktoken-ext-truveta.spec
```

The build creates a reusable one-folder bundle under `dist/olt/`; run it with
`./dist/olt/olt --help` on macOS or Linux.
For a local ML1 tokenization smoke test, pull and verify the OCI assets into the
bundle before running tokenization:

```bash
MODEL_ASSET_DIR="$(mktemp -d)"
oras pull "ghcr.io/truvetapublic/openlinktoken-ml1-assets:${OLT_ML1_MODEL_TAG:-v1}" \
  --output "$MODEL_ASSET_DIR"
python -c 'import sys; from openlinktoken_ext_truveta.util.inferencing_assets import copy_ml1_assets; copy_ml1_assets(sys.argv[1], sys.argv[2])' \
  "$MODEL_ASSET_DIR" "dist/olt/_internal/openlinktoken/core/ai/tokens"
```

The released macOS bundle targets Apple Silicon arm64 only. Set
`OLT_TARGET_ARCH=arm64` for macOS builds; do not pass `--target-arch` when
executing a `.spec` file. The build must run on an arm64 macOS environment
because the native dependencies are not universal2.
