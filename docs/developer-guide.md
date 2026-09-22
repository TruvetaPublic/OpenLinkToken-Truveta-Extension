# Developer Guide

- [Developer Guide](#developer-guide)
  - [Local Development Setup](#local-development-setup)
    - [Prerequisites](#prerequisites)
    - [Install Dependencies](#install-dependencies)
    - [ML1 Assets](#ml1-assets)
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
- Git LFS, required to retrieve OpenLinkToken's ML model files

> The repository ships with a VS Code dev container under `.devcontainer/` that provisions Python 3.12, installs dev tooling, and runs an editable install automatically. This is the recommended development environment.

### Install Dependencies

```bash
uv venv .venv
source .venv/bin/activate
git lfs install --skip-repo
uv pip install -e ".[dev]"
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
git lfs install --skip-repo
pip install -e ".[dev]"
```

This installs the package in editable mode, pulls the model-enabled `openlinktoken-cli`
from OpenLinkToken's `v2.2.0` release, and installs dev tools (`pytest`, `bump2version`,
`build`, `autoflake`, `flake8`). The development and release core references use the
same released core family.

### ML1 Assets

The dev container automatically pulls the matched ML1 model, external model data,
tokenizer, and asset manifest from
`ghcr.io/truvetapublic/openlinktoken-ml1-assets:v1` into the installed Core-AI
package. The upstream OCI tag must be published before creating the container.
For a manual setup, run the same `oras pull` command after installing the
package, targeting the directory printed by:

```bash
ML1_PACKAGE_DIR="$(python -c 'from pathlib import Path; import openlinktoken.core.ai.tokens as tokens; print(Path(tokens.__file__).resolve().parent)')"
oras pull ghcr.io/truvetapublic/openlinktoken-ml1-assets:v1 --output "$ML1_PACKAGE_DIR"
```

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

`bump2version` updates the version in `pyproject.toml`, `README.md`, and `standalone/registry.json`, creates a commit, and tags the commit as `v<new_version>`.

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

Releases are defined in `.github/workflows/release.yml` and triggered in two ways:

- **Tag push** — push a `v*` tag (created by `bump2version`) to build and publish.
- **Manual dispatch** — enter a version number in the GitHub Actions UI.

The release workflow:

1. Builds the wheel and sdist, then publishes them to GitHub Releases.
2. Checks out the OpenLinkToken model assets from `v2.2.0` with Git LFS.
3. Builds one-folder standalone bundles for Linux, Windows, and macOS using PyInstaller.
4. Runs a tokenization smoke test against each executable to verify the embedded model.
5. Packages each complete bundle as a ZIP with a SHA-256 checksum.
6. Generates the extension update manifests and wheel checksum.
7. Attaches the wheel, source distribution, update manifests, ZIP bundles, and checksums to the GitHub Release.

The standalone build contains the `openlinktoken` CLI, the Truveta extension, and the ML1 model/tokenizer assets in a reusable one-folder distribution — no Python installation required for end users. The local bundle is `dist/olt/` with executable `dist/olt/olt` on POSIX systems or `dist/olt/olt.exe` on Windows. Release assets are complete ZIP bundles plus `.sha256` files; the raw executable is not published separately because it requires the adjacent `_internal/` directory. The first compatible release uses OpenLinkToken `v2.2.0` for the model-enabled source and assets. Keep the three `.[release]` dependency references in `pyproject.toml` and the standalone workflow's `OPENLINKTOKEN_SOURCE_REF` on the same core release tag; update all four references together for a future core release. Help-oriented invocations load the installed extension registry so extension commands appear in the main menu. Heavy processing dependencies remain lazy until tokenization or packaging runs.

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

The Truveta extension supports OpenLinkToken core versions `>=2.2.0,<3.0.0`.
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

#### Frozen Installer Prerequisite

OpenLinkToken core PR [#482](https://github.com/TruvetaPublic/OpenLinkToken/pull/482)'s
frozen installer currently needs a coordinated core change to allow `requests`,
`httpx`, and `pydantic` in `_BUNDLED_DEPS`. Until that core change lands, separately
installed frozen Truveta wheels must not be advertised as supported. Keep the
extension's core compatibility range and the standalone bundle's pinned core
references aligned when the prerequisite is released.

### Building a Standalone Executable Locally

The standalone spec requires a hydrated checkout of OpenLinkToken `v2.2.0` and its ML1 assets. Clone the source, install the release dependencies, and point the spec at the assets. For a future core release, change the checkout ref, the three `.[release]` references in `pyproject.toml`, and `OPENLINKTOKEN_SOURCE_REF` in `.github/workflows/release.yml` together:

```bash
git clone --filter=blob:none --sparse https://github.com/TruvetaPublic/OpenLinkToken.git openlinktoken-source
git -C openlinktoken-source sparse-checkout set resources/inferencing/ml1
git -C openlinktoken-source checkout v2.2.0
git -C openlinktoken-source lfs pull
export OLT_INFERENCING_ASSETS_SOURCE="$PWD/openlinktoken-source/resources/inferencing/ml1"
uv pip install -e ".[release]"
uv pip install -r pyinstaller-requirements.txt
pyinstaller --clean --noconfirm openlinktoken-ext-truveta.spec
```

The build creates a reusable one-folder bundle under `dist/olt/`; run it with
`./dist/olt/olt --help` on macOS or Linux.

The released macOS bundle targets Apple Silicon arm64 only. Set
`OLT_TARGET_ARCH=arm64` for macOS builds; do not pass `--target-arch` when
executing a `.spec` file. The build must run on an arm64 macOS environment
because the native dependencies are not universal2.

The spec validates the manifest, sizes, and SHA-256 digests before embedding `asset-manifest.json`, `model.onnx`, `model.onnx.data`, and `tokenizer.json` under the runtime package path.
