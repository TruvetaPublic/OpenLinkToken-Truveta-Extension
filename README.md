# openlinktoken-ext-truveta

- [openlinktoken-ext-truveta](#openlinktoken-ext-truveta)
  - [Overview](#overview)
  - [Extension Commands](#extension-commands)
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

| Command                                     | Description                                              |
| ------------------------------------------- | -------------------------------------------------------- |
| `olt truveta login`                         | Authenticate with Truveta via OAuth 2.0 Device Code Flow |
| `olt truveta login --force`                 | Re-authenticate, discarding any cached credentials       |
| `olt truveta login --domain URL`            | Authenticate against a specific environment              |
| `olt truveta initiate-exchange --local-dev` | Use local Token Service API for exchange negotiation     |
| `olt truveta upload --local-dev`            | Use local Token Service API for upload                   |
| `olt truveta logout`                        | Revoke and clear all cached Truveta credentials          |

### Environment Configuration

| Variable     | Description                                                         | Default                   |
| ------------ | ------------------------------------------------------------------- | ------------------------- |
| `TRV_DOMAIN` | Override the target Truveta environment URL for `olt truveta login` | `https://api.truveta.com` |

**Example — target the dev environment:**

```bash
export TRV_DOMAIN=https://api.dev.truveta-int.com
olt truveta login
```

### Token Storage

Credentials are cached at `~/.openlinktoken/truveta/<domain>/credentials.json` and auto-evicted 5 minutes before expiry. The selected API URL is persisted at `~/.openlinktoken/truveta/session.json` and is used by non-login commands by default. Run `olt truveta logout` to revoke the access token server-side and clear session files.

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
(unset GIT_DIR; uv run olt truveta login --domain https://api.dev.truveta-int.com)
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
