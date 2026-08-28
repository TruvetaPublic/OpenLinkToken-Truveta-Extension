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
from OpenLinkToken, and installs dev tools (`pytest`, `bump2version`, `build`,
`autoflake`, `flake8`).

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

`bump2version` updates the version in `pyproject.toml`, `README.md`, and the version assertions in `src/main/openlinktoken_ext_truveta/extension.py` / `src/test/openlinktoken_ext_truveta/test_extension.py`, creates a commit, and tags the commit as `v<new_version>`.

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
2. Checks out the pinned OpenLinkToken model assets with Git LFS.
3. Builds standalone executables for Linux, Windows, and macOS using PyInstaller.
4. Runs a tokenization smoke test against each executable to verify the embedded model.
5. Attaches all artifacts to the GitHub Release.

The standalone bundle contains the `openlinktoken` CLI, the Truveta extension, and the ML1 model/tokenizer assets in a reusable one-folder distribution — no Python installation required for end users. The executable is `dist/olt/olt` on POSIX systems and `dist/olt/olt.exe` on Windows. The release build pins OpenLinkToken to commit `cde35f290a2d57f1ac7c7056f78b1ff9f150a201`, which includes the model-enabled source and lazy CLI startup changes.

### Building a Standalone Executable Locally

The standalone spec requires a hydrated checkout of OpenLinkToken's ML1 assets. Clone the same model-enabled source revision, install the release dependencies, and point the spec at the assets:

```bash
git clone --filter=blob:none --sparse https://github.com/TruvetaPublic/OpenLinkToken.git openlinktoken-source
git -C openlinktoken-source sparse-checkout set resources/inferencing/ml1
git -C openlinktoken-source checkout cde35f290a2d57f1ac7c7056f78b1ff9f150a201
git -C openlinktoken-source lfs pull
export OLT_INFERENCING_ASSETS_SOURCE="$PWD/openlinktoken-source/resources/inferencing/ml1"
uv pip install -e ".[release]"
uv pip install -r pyinstaller-requirements.txt
pyinstaller --clean --noconfirm openlinktoken-ext-truveta.spec
```

The build creates a reusable one-folder bundle under `dist/olt/`; run it with
`./dist/olt/olt --help` on macOS or Linux.

Set `OLT_TARGET_ARCH=universal2` for a macOS universal2 build; do not pass
`--target-arch` when executing a `.spec` file. For a local Apple Silicon build with
arm64-only native wheels, set `OLT_TARGET_ARCH=arm64` instead.

The spec validates the manifest, sizes, and SHA-256 digests before embedding `asset-manifest.json`, `model.onnx`, `model.onnx.data`, and `tokenizer.json` under the runtime package path.
