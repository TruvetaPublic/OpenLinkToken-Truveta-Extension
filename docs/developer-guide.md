# Developer Guide

## Local Development Setup

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
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

This installs the package in editable mode, pulls `openlinktoken-cli` from the `develop` branch of `TruvetaPublic/OpenLinkToken`, and installs dev tools (`pytest`, `bump2version`, `build`, `autoflake`, `flake8`).

### Run Tests

```bash
pytest src/test -v
```

### Smoke Test

```bash
olt truveta login --domain dev.truveta-int.com
# Opens browser for Auth0 device code login, then prints: Welcome, <name>!
```