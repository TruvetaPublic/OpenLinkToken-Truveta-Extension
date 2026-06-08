#!/usr/bin/env bash
set -euo pipefail

echo "=== OpenLinkToken-Truveta-Extension Unified Setup ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_DIR="${UV_PROJECT_ENVIRONMENT:-/home/vscode/.local/share/openlinktoken-ext-truveta/.venv}"
WORKSPACE_VENV_DIR="$REPO_ROOT/.venv"
STATE_DIR="${VENV_DIR}/.setup-state"
PHASE="${1:-full}"

mkdir -p "$STATE_DIR"

mark_complete() { touch "$STATE_DIR/$1"; }
is_complete() { [ -f "$STATE_DIR/$1" ]; }
skip_if_complete() {
  if is_complete "$1"; then
    echo "⊘ Skipping $2 (already completed)"
    return 0
  fi
  return 1
}

step_install_uv() {
  skip_if_complete "uv-installed" "UV installation" && return 0
  if ! command -v uv >/dev/null 2>&1; then
    echo "→ Installing UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  mark_complete "uv-installed"
}

step_setup_cache_dir() {
  skip_if_complete "cache-setup" "cache directory setup" && return 0
  echo "→ Setting up UV cache directory"
  DEFAULT_UV_CACHE_DIR="/home/vscode/.cache/uv"
  if mkdir -p "$DEFAULT_UV_CACHE_DIR" 2>/dev/null && [ -w "$DEFAULT_UV_CACHE_DIR" ]; then
    export UV_CACHE_DIR="$DEFAULT_UV_CACHE_DIR"
  else
    export UV_CACHE_DIR="$REPO_ROOT/.cache/uv"
    mkdir -p "$UV_CACHE_DIR"
  fi
  mark_complete "cache-setup"
}

step_create_venv() {
  skip_if_complete "venv-created" "virtual environment creation" && return 0
  echo "→ Creating virtual environment at $VENV_DIR"
  mkdir -p "$VENV_DIR"
  if [ "$(id -u)" -eq 0 ]; then
    chown -R "$(id -u)":"$(id -g)" "$VENV_DIR" 2>/dev/null || true
  elif command -v sudo >/dev/null 2>&1; then
    sudo chown -R "$(id -u)":"$(id -g)" "$VENV_DIR" 2>/dev/null || true
  fi
  uv venv --allow-existing --seed "$VENV_DIR"
  mark_complete "venv-created"
}

step_symlink_venv() {
  skip_if_complete "venv-symlink" "workspace .venv symlink" && return 0
  if [ "$WORKSPACE_VENV_DIR" != "$VENV_DIR" ]; then
    if [ -e "$WORKSPACE_VENV_DIR" ] && [ ! -L "$WORKSPACE_VENV_DIR" ]; then
      echo "→ Replacing workspace-local .venv with symlink to shared environment..."
      rm -rf "$WORKSPACE_VENV_DIR"
    fi
    if [ ! -L "$WORKSPACE_VENV_DIR" ] || [ "$(readlink "$WORKSPACE_VENV_DIR" 2>/dev/null || true)" != "$VENV_DIR" ]; then
      ln -sfn "$VENV_DIR" "$WORKSPACE_VENV_DIR"
    fi
  fi
  mark_complete "venv-symlink"
}

step_activate_venv() {
  export UV_PROJECT_ENVIRONMENT="$VENV_DIR"
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
}

step_install_packages() {
  echo "→ Installing extension package with dev extras"
  cd "$REPO_ROOT"
  uv pip install -e ".[dev]"
}

step_refresh_packages() {
  echo "→ Refreshing extension package"
  cd "$REPO_ROOT"
  uv pip install -e ".[dev]"
  echo "✓ Packages refreshed"
}

step_activate_shell_init() {
  echo "→ Adding venv activation to shell rc files"
  local activation_line="source $VENV_DIR/bin/activate 2>/dev/null || true"
  grep -qF "$activation_line" ~/.bashrc 2>/dev/null || echo "$activation_line" >> ~/.bashrc
  grep -qF "$activation_line" ~/.zshrc 2>/dev/null || echo "$activation_line" >> ~/.zshrc
}

run_core_setup() {
  step_install_uv
  step_setup_cache_dir
  step_create_venv
  step_symlink_venv
  step_activate_venv
}

run_full_setup() {
  run_core_setup
  step_install_packages
  step_activate_shell_init
}

run_refresh_setup() {
  run_core_setup
  step_refresh_packages
  step_activate_shell_init
}

main() {
  cd "$REPO_ROOT"
  echo "Phase: $PHASE"
  case "$PHASE" in
    full|post-create) run_full_setup ;;
    post-start) run_core_setup ;;
    post-attach) run_refresh_setup ;;
    *) echo "Unknown setup phase: $PHASE" >&2; exit 1 ;;
  esac
  echo ""
  echo "✓ Setup complete (phase: $PHASE)"
  echo "To activate manually, run: source $VENV_DIR/bin/activate"
}

main "$@"
