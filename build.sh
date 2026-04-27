#!/usr/bin/env bash
# Rebuild and restart one or both Docker images after code changes.
# Usage:
#   ./build.sh          — rebuild api + ui
#   ./build.sh --api    — rebuild api only
#   ./build.sh --ui     — rebuild ui only
#   ./build.sh --no-cache [--api|--ui]
set -euo pipefail

BUILD_API=false
BUILD_UI=false
NO_CACHE=""

for arg in "$@"; do
    case "$arg" in
        --api)      BUILD_API=true ;;
        --ui)       BUILD_UI=true ;;
        --no-cache) NO_CACHE="--no-cache" ;;
        --help)
            sed -n '2,7p' "$0" | sed 's/^# //'
            exit 0 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

# Default: build both
if [ "$BUILD_API" = false ] && [ "$BUILD_UI" = false ]; then
    BUILD_API=true; BUILD_UI=true
fi

if ! docker info &>/dev/null; then
    echo "ERROR: Docker is not running."
    exit 1
fi

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run ./setup.sh first."
    exit 1
fi

SERVICES=""
[ "$BUILD_API" = true ] && SERVICES="$SERVICES api"
[ "$BUILD_UI"  = true ] && SERVICES="$SERVICES ui"
SERVICES="${SERVICES# }"

echo "=== Building: $SERVICES ==="
# shellcheck disable=SC2086
docker compose build $NO_CACHE $SERVICES
echo "[OK] Build complete"

echo ""
echo "=== Restarting: $SERVICES ==="
# shellcheck disable=SC2086
docker compose up -d $SERVICES
echo "[OK] Done"

source .env
[ "$BUILD_UI"  = true ] && echo "UI:  http://localhost:${UI_PORT:-80}"
[ "$BUILD_API" = true ] && echo "API: http://localhost:${API_PORT:-8000}"
