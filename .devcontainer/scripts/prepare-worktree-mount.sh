#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
COMPOSE_OVERRIDE="$REPO_ROOT/.devcontainer/docker-compose.worktree.yml"

write_empty_override() {
  printf '%s\n' "services: {}" > "$COMPOSE_OVERRIDE"
}

if [ ! -f "$REPO_ROOT/.git" ]; then
  write_empty_override
  exit 0
fi

gitdir="$(sed -n 's/^gitdir: //p' "$REPO_ROOT/.git")"
if [ -z "$gitdir" ]; then
  echo "Error: Could not read linked worktree metadata from $REPO_ROOT/.git." >&2
  exit 1
fi

if [[ "$gitdir" != /* ]]; then
  gitdir="$REPO_ROOT/$gitdir"
fi
if [ ! -d "$gitdir" ]; then
  echo "Error: Linked worktree metadata is unavailable at $gitdir." >&2
  exit 1
fi

if ! common_dir="$(
  env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR \
    git -C "$REPO_ROOT" rev-parse --git-common-dir
)"; then
  echo "Error: Could not locate the common Git directory for $REPO_ROOT." >&2
  exit 1
fi
if [[ "$common_dir" != /* ]]; then
  common_dir="$REPO_ROOT/$common_dir"
fi
if ! common_dir="$(cd "$common_dir" && pwd -P)"; then
  echo "Error: Common Git directory is unavailable at $common_dir." >&2
  exit 1
fi

yaml_quote() {
  local value=$1
  value=${value//\'/\'\'}
  printf "'%s'" "$value"
}

common_dir_yaml="$(yaml_quote "$common_dir")"
printf '%s\n' \
  "services:" \
  "  app:" \
  "    volumes:" \
  "      - type: bind" \
  "        source: $common_dir_yaml" \
  "        target: $common_dir_yaml" > "$COMPOSE_OVERRIDE"
