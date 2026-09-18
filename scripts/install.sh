#!/usr/bin/env bash
# install.sh — One-line installer for the OLT Truveta CLI bundle.
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
    if [ "$ARCH" != "x86_64" ]; then
      echo "Error: unsupported Linux architecture '$ARCH'. Only x86_64 is supported." >&2
      exit 1
    fi
    PLATFORM="linux-x64"
    ;;
  Darwin)
    if [ "$ARCH" != "arm64" ]; then
      echo "Error: unsupported macOS architecture '$ARCH'. This release supports Apple Silicon arm64 only." >&2
      exit 1
    fi
    PLATFORM="macos-arm64"
    ;;
  *)
    echo "Error: unsupported operating system '$OS'." >&2
    echo "Supported platforms: Linux (x86_64), macOS (arm64)." >&2
    exit 1
    ;;
esac

if ! command -v unzip >/dev/null 2>&1; then
  echo "Error: unzip is required to install the standalone bundle." >&2
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

VERSION="${VERSION#v}"
case "$VERSION" in
  ""|*[!A-Za-z0-9._-]*)
    echo "Error: invalid release version '$VERSION'." >&2
    exit 1
    ;;
esac

PACKAGE_NAME="olt-truveta-${VERSION}-${PLATFORM}"
ARCHIVE_NAME="${PACKAGE_NAME}.zip"
CHECKSUM_NAME="${ARCHIVE_NAME}.sha256"
ARCHIVE_URL="https://github.com/${REPO}/releases/download/v${VERSION}/${ARCHIVE_NAME}"
CHECKSUM_URL="https://github.com/${REPO}/releases/download/v${VERSION}/${CHECKSUM_NAME}"

# ---------------------------------------------------------------------------
# Download and install
# ---------------------------------------------------------------------------
echo "Installing OLT Truveta v${VERSION} (${PLATFORM})..."

mkdir -p "$INSTALL_DIR"

ARCHIVE_PATH="${INSTALL_DIR}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${INSTALL_DIR}/${CHECKSUM_NAME}"
STAGING_DIR="${INSTALL_DIR}/.${PACKAGE_NAME}.staging.$$"

cleanup() {
  rm -rf "$STAGING_DIR" "$ARCHIVE_PATH" "$CHECKSUM_PATH"
}
trap cleanup EXIT

curl -fsSL --progress-bar "$ARCHIVE_URL" -o "$ARCHIVE_PATH"
curl -fsSL --progress-bar "$CHECKSUM_URL" -o "$CHECKSUM_PATH"

(
  cd "$INSTALL_DIR"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "$CHECKSUM_NAME"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c "$CHECKSUM_NAME"
  else
    echo "Error: sha256sum or shasum is required to verify the release bundle." >&2
    exit 1
  fi
)

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
unzip -q "$ARCHIVE_PATH" -d "$STAGING_DIR"

BUNDLE_DIR="${STAGING_DIR}/${PACKAGE_NAME}"
if [ ! -d "$BUNDLE_DIR" ] || [ ! -f "${BUNDLE_DIR}/olt" ] || [ ! -d "${BUNDLE_DIR}/_internal" ]; then
  echo "Error: release archive does not contain a complete OLT bundle." >&2
  exit 1
fi

INSTALLED_BUNDLE_DIR="${INSTALL_DIR}/${PACKAGE_NAME}"
rm -rf "$INSTALLED_BUNDLE_DIR"
mv "$BUNDLE_DIR" "$INSTALLED_BUNDLE_DIR"
chmod +x "${INSTALLED_BUNDLE_DIR}/olt"

LINK_PATH="${INSTALL_DIR}/olt"
if [ -L "$LINK_PATH" ] || [ -f "$LINK_PATH" ]; then
  rm -f "$LINK_PATH"
elif [ -e "$LINK_PATH" ]; then
  echo "Error: install path '${LINK_PATH}' is occupied by a directory." >&2
  exit 1
fi
ln -s "${INSTALLED_BUNDLE_DIR}/olt" "$LINK_PATH"

echo "Installed bundle: ${INSTALLED_BUNDLE_DIR}"
echo "Command: ${LINK_PATH}"

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
