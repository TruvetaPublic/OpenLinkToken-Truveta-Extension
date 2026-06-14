#!/usr/bin/env bash
# install.sh — One-line installer for the OLT Truveta CLI distributable.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.sh | bash
#
# Environment overrides:
#   OLT_TRUVETA_VERSION  — Pin to a specific release (e.g., "1.0.0"). Defaults to latest.
#   OLT_INSTALL_DIR      — Override the install directory. Defaults to ~/.local/bin.

set -euo pipefail

REPO="TruvetaPublic/OpenLinkToken-Truveta-Extension"
INSTALL_DIR="${OLT_INSTALL_DIR:-$HOME/.local/bin}"
VERSION="${OLT_TRUVETA_VERSION:-}"

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    PLATFORM="linux-x86_64"
    ;;
  Darwin)
    PLATFORM="macos-universal"
    ;;
  *)
    echo "Error: unsupported operating system '$OS'." >&2
    echo "Supported platforms: Linux (x86_64), macOS (x86_64 / arm64)." >&2
    exit 1
    ;;
esac

if [ "$OS" = "Linux" ] && [ "$ARCH" != "x86_64" ]; then
  echo "Error: unsupported Linux architecture '$ARCH'. Only x86_64 is supported." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------
if [ -z "$VERSION" ]; then
  echo "Fetching latest release..."
  VERSION="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep '"tag_name"' \
    | head -1 \
    | sed 's/.*"tag_name": *"v\?\([^"]*\)".*/\1/')"
fi

if [ -z "$VERSION" ]; then
  echo "Error: could not determine the latest release version." >&2
  echo "Set OLT_TRUVETA_VERSION to install a specific version." >&2
  exit 1
fi

BINARY_NAME="olt-truveta-v${VERSION}-${PLATFORM}"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/v${VERSION}/${BINARY_NAME}"

# ---------------------------------------------------------------------------
# Download and install
# ---------------------------------------------------------------------------
echo "Installing OLT Truveta v${VERSION} (${PLATFORM})..."

mkdir -p "$INSTALL_DIR"

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

curl -fsSL --progress-bar "$DOWNLOAD_URL" -o "$TMP_FILE"
chmod +x "$TMP_FILE"
mv "$TMP_FILE" "${INSTALL_DIR}/olt"

echo "Installed: ${INSTALL_DIR}/olt"

# ---------------------------------------------------------------------------
# PATH guidance
# ---------------------------------------------------------------------------
case ":${PATH}:" in
  *":${INSTALL_DIR}:"*)
    ;;
  *)
    echo ""
    echo "  ${INSTALL_DIR} is not in your PATH."
    echo "  Add the following line to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
    echo ""
    echo "    export PATH=\"${INSTALL_DIR}:\$PATH\""
    echo ""
    ;;
esac

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
if command -v olt >/dev/null 2>&1 || [ -x "${INSTALL_DIR}/olt" ]; then
  "${INSTALL_DIR}/olt" --help >/dev/null && echo "Verification passed."
fi

echo "Done. Run 'olt truveta --help' to get started."
