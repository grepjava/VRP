#!/usr/bin/env bash
# VRP Docker Setup — downloads map data, preprocesses OSRM, builds and starts all services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
DATA_DIR="$SCRIPT_DIR/osrm-data"

# ── Defaults (overridden by .env or flags) ────────────────────────────────────
MAP_URL="https://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf"
MAP_FILE="malaysia-singapore-brunei-latest.osm.pbf"
UI_PORT=80
API_PORT=8000
GPU_MEMORY_INITIAL=1073741824
GPU_MEMORY_MAX=8589934592
CUOPT_CONCURRENT_INSTANCES=4
CUOPT_MEMORY_PER_INSTANCE=1024

SKIP_DOWNLOAD=false
SKIP_BUILD=false
SKIP_START=false

# ── Load existing .env ────────────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
fi

# ── Help ──────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --map-url <url>      Geofabrik download URL for your map region
  --map-file <name>    .osm.pbf filename (auto-derived from URL if omitted)
  --ui-port <port>     Port for the UI  (default: 80)
  --api-port <port>    Port for the API (default: 8000)
  --instances <n>      Concurrent cuOpt solver instances (default: 4)
  --mem-per-inst <mb>  GPU memory per solver instance in MB (default: 1024)
  --gpu-mem-max <gb>   Total GPU memory pool ceiling in GB (default: 8)
  --skip-download      Skip map download (use existing osrm-data/)
  --skip-build         Skip Docker image build
  --skip-start         Prepare only — don't start services
  --help               Show this help

Region examples (https://download.geofabrik.de/):
  $0 --map-url https://download.geofabrik.de/europe/germany-latest.osm.pbf
  $0 --map-url https://download.geofabrik.de/north-america/us/california-latest.osm.pbf
EOF
    exit 0
}

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --map-url)        MAP_URL="$2";                          shift 2 ;;
        --map-file)       MAP_FILE="$2";                         shift 2 ;;
        --ui-port)        UI_PORT="$2";                          shift 2 ;;
        --api-port)       API_PORT="$2";                         shift 2 ;;
        --instances)      CUOPT_CONCURRENT_INSTANCES="$2";       shift 2 ;;
        --mem-per-inst)   CUOPT_MEMORY_PER_INSTANCE="$2";        shift 2 ;;
        --gpu-mem-max)    GPU_MEMORY_MAX=$(( $2 * 1073741824 ));  shift 2 ;;
        --skip-download)  SKIP_DOWNLOAD=true;                    shift ;;
        --skip-build)     SKIP_BUILD=true;                       shift ;;
        --skip-start)     SKIP_START=true;                       shift ;;
        --help)           usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# Derive MAP_FILE from URL if not explicitly set
if [ "$MAP_FILE" = "malaysia-singapore-brunei-latest.osm.pbf" ] && [ "$MAP_URL" != "https://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf" ]; then
    MAP_FILE="$(basename "$MAP_URL")"
fi
OSRM_FILE="${MAP_FILE%.osm.pbf}.osrm"

# ── Preflight checks ──────────────────────────────────────────────────────────
echo "=== VRP Setup ==="
echo ""

if ! docker info &>/dev/null; then
    echo "ERROR: Docker is not running. Start Docker Desktop first."
    exit 1
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo "ERROR: 'docker compose' (v2) not found. Update Docker Desktop."
    exit 1
fi

echo "[OK] Docker $(docker --version | grep -o '[0-9.]*' | head -1)"

if docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi &>/dev/null 2>&1; then
    GPU=$(docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 \
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)
    echo "[OK] GPU: $GPU"
else
    echo "[WARN] NVIDIA GPU runtime not detected — API container needs a CUDA GPU"
fi

# ── Map download & OSRM preprocessing ────────────────────────────────────────
echo ""
echo "=== OSRM Map Data ==="
echo "    File:   $MAP_FILE"
echo "    Source: $MAP_URL"
echo ""

mkdir -p "$DATA_DIR"

if [ "$SKIP_DOWNLOAD" = false ]; then
    if [ ! -f "$DATA_DIR/$MAP_FILE" ]; then
        echo "Downloading map (may be several hundred MB)..."
        curl -L --progress-bar "$MAP_URL" -o "$DATA_DIR/$MAP_FILE"
        echo "[OK] Download complete"
    else
        echo "[OK] Map file already present — checking for updates..."
        REMOTE_MODIFIED=$(curl -sI "$MAP_URL" | grep -i "^last-modified:" | sed 's/last-modified: //i' | tr -d '\r' || true)
        if [ -n "$REMOTE_MODIFIED" ]; then
            LOCAL_TS=$(stat -c %Y "$DATA_DIR/$MAP_FILE" 2>/dev/null || stat -f %m "$DATA_DIR/$MAP_FILE" 2>/dev/null || echo 0)
            REMOTE_TS=$(date -d "$REMOTE_MODIFIED" +%s 2>/dev/null || date -j -f "%a, %d %b %Y %H:%M:%S %Z" "$REMOTE_MODIFIED" +%s 2>/dev/null || echo 0)
            if [ "$REMOTE_TS" -gt "$LOCAL_TS" ] 2>/dev/null; then
                read -rp "A newer map is available. Re-download and reprocess? [y/N]: " ans
                if [[ "$ans" =~ ^[Yy]$ ]]; then
                    curl -L --progress-bar "$MAP_URL" -o "$DATA_DIR/$MAP_FILE"
                    rm -f "$DATA_DIR"/*.osrm "$DATA_DIR"/*.osrm.* 2>/dev/null || true
                    echo "[OK] Map updated"
                fi
            else
                echo "[OK] Map is up to date"
            fi
        fi
    fi
fi

if [ ! -f "$DATA_DIR/$OSRM_FILE" ]; then
    echo "Pre-processing map data (one-time, may take 5–15 min)..."
    echo ""

    echo "  [1/3] Extracting road network..."
    docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend \
        osrm-extract -p /opt/car.lua "/data/$MAP_FILE"

    echo "  [2/3] Partitioning..."
    docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend \
        osrm-partition "/data/$OSRM_FILE"

    echo "  [3/3] Customizing..."
    docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend \
        osrm-customize "/data/$OSRM_FILE"

    echo ""
    echo "[OK] Preprocessing complete"
else
    echo "[OK] Processed OSRM data found"
fi

# ── Write .env ────────────────────────────────────────────────────────────────
cat > "$ENV_FILE" <<EOF
# Generated by setup.sh on $(date '+%Y-%m-%d %H:%M:%S')

MAP_URL=$MAP_URL
MAP_FILE=$MAP_FILE
OSRM_FILE=$OSRM_FILE

UI_PORT=$UI_PORT
API_PORT=$API_PORT

GPU_MEMORY_INITIAL=$GPU_MEMORY_INITIAL
GPU_MEMORY_MAX=$GPU_MEMORY_MAX

CUOPT_CONCURRENT_INSTANCES=$CUOPT_CONCURRENT_INSTANCES
CUOPT_MEMORY_PER_INSTANCE=$CUOPT_MEMORY_PER_INSTANCE
EOF
echo "[OK] .env written"

# ── Docker build ──────────────────────────────────────────────────────────────
echo ""
echo "=== Docker Build ==="

if [ "$SKIP_BUILD" = false ]; then
    docker compose build
    echo "[OK] Images built"
else
    echo "[SKIP] Build skipped (--skip-build)"
fi

# ── Start ─────────────────────────────────────────────────────────────────────
if [ "$SKIP_START" = false ]; then
    echo ""
    echo "=== Starting Services ==="
    docker compose up -d

    printf "Waiting for OSRM"
    for i in {1..30}; do
        if curl -sf "http://localhost:5000/" &>/dev/null; then
            echo " ready"
            break
        fi
        [ "$i" -eq 30 ] && echo " (still starting — check: docker compose logs osrm)"
        printf "."
        sleep 2
    done

    echo ""
    echo "┌─────────────────────────────────────────────┐"
    echo "│  UI:   http://localhost:${UI_PORT}"
    echo "│  API:  http://localhost:${API_PORT}"
    echo "│  Docs: http://localhost:${API_PORT}/docs"
    echo "└─────────────────────────────────────────────┘"
    echo ""
    echo "  Logs: docker compose logs -f"
    echo "  Stop: docker compose down"
else
    echo ""
    echo "[SKIP] Start skipped (--skip-start)"
    echo "Run 'docker compose up -d' when ready."
fi
