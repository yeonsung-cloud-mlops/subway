#!/bin/sh
# Docker Desktop/buildx may reject non-ASCII project paths in gRPC headers.
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PROJECT_KEY=$(printf '%s' "$ROOT_DIR" | cksum | awk '{print $1}')
ALIAS_PARENT="/tmp/subway-compose-$(id -u)"
mkdir -p "$ALIAS_PARENT"
ALIAS_PATH="$ALIAS_PARENT/$PROJECT_KEY"
if [ ! -e "$ALIAS_PATH" ] && [ ! -L "$ALIAS_PATH" ]; then
  ln -s "$ROOT_DIR" "$ALIAS_PATH"
fi
if [ "$(readlink "$ALIAS_PATH")" != "$ROOT_DIR" ]; then
  echo "Unexpected compose alias: $ALIAS_PATH" >&2
  exit 1
fi
exec docker compose --project-directory "$ALIAS_PATH" -f "$ALIAS_PATH/compose.yaml" "$@"
