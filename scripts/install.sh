#!/usr/bin/env bash
# install.sh — One-line installer for the OLT Truveta CLI bundle.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/TruvetaPublic/OpenLinkToken-Truveta-Extension/main/scripts/install.sh | bash
#
# Environment overrides:
#   OLT_TRUVETA_VERSION  — Pin to a specific release (e.g., "1.0.0"). Defaults to latest.
#   OLT_ML1_MODEL_TAG    — Select an immutable model tag (e.g., "v1").
#   OLT_INSTALL_DIR      — Override the install directory. Defaults to ~/.local/bin.

set -euo pipefail

REPO="TruvetaPublic/OpenLinkToken-Truveta-Extension"
MODEL_PACKAGE="ghcr.io/truvetapublic/openlinktoken-ml1-assets"
ORAS_VERSION="1.3.3"
INSTALL_DIR="${OLT_INSTALL_DIR:-$HOME/.local/bin}"
VERSION="${OLT_TRUVETA_VERSION:-}"
MODEL_TAG="${OLT_ML1_MODEL_TAG:-v1}"

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "Error: shasum or sha256sum is required to verify downloads." >&2
    exit 1
  fi
}

verify_sha256() {
  local expected actual file description
  expected="$1"
  file="$2"
  description="$3"
  if [[ ! "$expected" =~ ^[[:xdigit:]]{64}$ ]]; then
    echo "Error: invalid SHA-256 checksum for ${description}." >&2
    exit 1
  fi
  actual="$(sha256_file "$file")"
  expected="$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')"
  actual="$(printf '%s' "$actual" | tr '[:upper:]' '[:lower:]')"
  if [[ "$actual" != "$expected" ]]; then
    echo "Error: SHA-256 verification failed for ${description}." >&2
    exit 1
  fi
}

install_ml1_assets() {
  local bundle_root="$1"
  local oras_archive oras_checksum oras_url oras_dir oras_binary model_assets_dir
  local filename metadata expected_checksum expected_size actual_size

  if [[ ! "$MODEL_TAG" =~ ^v[0-9]+$ ]]; then
    echo "Error: invalid ML1 model tag '$MODEL_TAG'; expected vN." >&2
    exit 1
  fi

  case "$(uname -s):$(uname -m)" in
    Linux:x86_64|Linux:amd64)
      oras_archive="oras_${ORAS_VERSION}_linux_amd64.tar.gz"
      oras_checksum="9ce999f8d2de03fc03968b29d743077a58783e545e5eaa53917ca177352d0e59"
      ;;
    Darwin:arm64|Darwin:aarch64)
      oras_archive="oras_${ORAS_VERSION}_darwin_arm64.tar.gz"
      oras_checksum="f33fc12753c54172b0d0d19eaa0318d3f90fe9b094d96e8b259c881713c92e1c"
      ;;
    *)
      echo "Error: no verified ORAS binary is available for $(uname -s) $(uname -m)." >&2
      exit 1
      ;;
  esac

  oras_dir="$TEMP_DIR/oras"
  mkdir -p "$oras_dir"
  oras_url="https://github.com/oras-project/oras/releases/download/v${ORAS_VERSION}/${oras_archive}"
  echo "Downloading ORAS ${ORAS_VERSION}..."
  curl -fL --retry 3 --output "$oras_dir/$oras_archive" "$oras_url"
  verify_sha256 "$oras_checksum" "$oras_dir/$oras_archive" "ORAS ${ORAS_VERSION}"
  tar -xzf "$oras_dir/$oras_archive" -C "$oras_dir" oras
  oras_binary="$oras_dir/oras"

  model_assets_dir="$TEMP_DIR/ml1-assets"
  mkdir -p "$model_assets_dir"
  echo "Downloading ML1 model assets ${MODEL_TAG}..."
  "$oras_binary" pull "${MODEL_PACKAGE}:${MODEL_TAG}" --output "$model_assets_dir"

  for filename in asset-manifest.json model.onnx model.onnx.data tokenizer.json; do
    if [[ ! -s "$model_assets_dir/$filename" ]]; then
      echo "Error: ML1 OCI artifact is missing $filename." >&2
      exit 1
    fi
  done

  for filename in model.onnx model.onnx.data tokenizer.json; do
    metadata="$(awk -v asset="\"$filename\"" '
      index($0, asset) { in_asset = 1; next }
      in_asset && /"sha256"[[:space:]]*:/ {
        sub(/^.*"sha256"[[:space:]]*:[[:space:]]*"/, "")
        sub(/".*$/, "")
        checksum = $0
      }
      in_asset && /"size"[[:space:]]*:/ {
        sub(/^.*"size"[[:space:]]*:[[:space:]]*/, "")
        sub(/[,[:space:]]*$/, "")
        print checksum "\t" $0
        exit
      }
      in_asset && /}/ { in_asset = 0 }
    ' "$model_assets_dir/asset-manifest.json")"
    IFS=$'\t' read -r expected_checksum expected_size <<< "$metadata"
    if [[ ! "$expected_checksum" =~ ^[[:xdigit:]]{64}$ ||
      ! "$expected_size" =~ ^[0-9]+$ ]]; then
      echo "Error: invalid ML1 asset manifest entry for $filename." >&2
      exit 1
    fi
    verify_sha256 "$expected_checksum" "$model_assets_dir/$filename" "$filename"
    actual_size="$(wc -c < "$model_assets_dir/$filename" | tr -d '[:space:]')"
    if [[ "$actual_size" != "$expected_size" ]]; then
      echo "Error: unexpected size for ML1 asset $filename." >&2
      exit 1
    fi
  done

  mkdir -p "$bundle_root/_internal/openlinktoken/core/ai/tokens"
  cp "$model_assets_dir"/{asset-manifest.json,model.onnx,model.onnx.data,tokenizer.json} \
    "$bundle_root/_internal/openlinktoken/core/ai/tokens/"
}

usage() {
  cat <<'EOF'
Install the Open Link Token Truveta CLI for Linux or macOS.

Usage:
  install.sh [--model-tag TAG]

Options:
  --model-tag TAG  Install this ML1 model tag (default: v1 or OLT_ML1_MODEL_TAG)
  -h, --help       Show this help
EOF
}

while (($# > 0)); do
  case "$1" in
    --model-tag)
      (($# >= 2)) || {
        echo "Error: --model-tag requires a value." >&2
        exit 1
      }
      MODEL_TAG="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown option '$1'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

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
    | sed -nE 's/^[[:space:]]*"tag_name":[[:space:]]*"v?([^"]*)".*/\1/p')"
fi

if [ -z "$VERSION" ]; then
  echo "Error: could not determine the latest release version." >&2
  echo "Set OLT_TRUVETA_VERSION to install a specific version." >&2
  exit 1
fi

if [[ ! "$MODEL_TAG" =~ ^v[0-9]+$ ]]; then
  echo "Error: invalid ML1 model tag '$MODEL_TAG'; expected vN." >&2
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
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/olt-truveta-install.XXXXXX")"

cleanup() {
  rm -rf "$STAGING_DIR" "$ARCHIVE_PATH" "$CHECKSUM_PATH" "$TEMP_DIR"
}
trap cleanup EXIT

curl -fsSL --progress-bar "$ARCHIVE_URL" -o "$ARCHIVE_PATH"
curl -fsSL --progress-bar "$CHECKSUM_URL" -o "$CHECKSUM_PATH"

EXPECTED_CHECKSUM="$(awk 'NF { print $1; exit }' "$CHECKSUM_PATH")"
verify_sha256 "$EXPECTED_CHECKSUM" "$ARCHIVE_PATH" "$ARCHIVE_NAME"

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
unzip -q "$ARCHIVE_PATH" -d "$STAGING_DIR"

BUNDLE_DIR="${STAGING_DIR}/${PACKAGE_NAME}"
if [ ! -d "$BUNDLE_DIR" ] || [ ! -f "${BUNDLE_DIR}/olt" ] || [ ! -d "${BUNDLE_DIR}/_internal" ]; then
  echo "Error: release archive does not contain a complete OLT bundle." >&2
  exit 1
fi

install_ml1_assets "$BUNDLE_DIR"

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
