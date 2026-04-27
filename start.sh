#!/usr/bin/env bash
# Start all services (Docker). Run ./setup.sh first if this is a fresh clone.
set -euo pipefail

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run ./setup.sh first."
    exit 1
fi

docker compose up -d

source .env
echo "UI:   http://localhost:${UI_PORT:-80}"
echo "API:  http://localhost:${API_PORT:-8000}"
echo "Logs: docker compose logs -f"
