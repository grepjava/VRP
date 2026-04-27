#!/bin/bash

CONDA_PATH="/home/grepjava/miniforge3"
ENV_NAME="cuopt"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATA_DIR="$SCRIPT_DIR/osrm-data"
MAP_FILE="malaysia-singapore-brunei-latest.osm.pbf"
OSRM_FILE="malaysia-singapore-brunei-latest.osrm"
CONTAINER_NAME="osrm-malaysia"
MAP_URL="https://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf"
OSRM_HOST="${OSRM_HOST:-localhost}"
OSRM_PORT="${OSRM_PORT:-5000}"

# ── OSRM ──────────────────────────────────────────────────────────────────────

echo "=== OSRM ==="

if ! docker info &>/dev/null; then
    echo "ERROR: Docker is not running. Start Docker Desktop first."
    exit 1
fi

if docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" --format "{{.Names}}" | grep -qx "$CONTAINER_NAME"; then
    echo "[OK] OSRM already running"
else
    # Remove stopped container with same name if it exists
    if docker ps -a --filter "name=$CONTAINER_NAME" --format "{{.Names}}" | grep -qx "$CONTAINER_NAME"; then
        docker rm "$CONTAINER_NAME" &>/dev/null
    fi

    mkdir -p "$DATA_DIR"

    # Check for newer map on Geofabrik
    if [ -f "$DATA_DIR/$MAP_FILE" ]; then
        echo "Checking for map update..."
        LOCAL_TS=$(stat -c %Y "$DATA_DIR/$MAP_FILE")
        REMOTE_HEADER=$(curl -sI "$MAP_URL" | grep -i "^last-modified:" | sed 's/last-modified: //i' | tr -d '\r')
        REMOTE_TS=$(date -d "$REMOTE_HEADER" +%s 2>/dev/null)

        if [ -n "$REMOTE_TS" ] && [ "$REMOTE_TS" -gt "$LOCAL_TS" ]; then
            LOCAL_DATE=$(date -d "@$LOCAL_TS" '+%Y-%m-%d')
            REMOTE_DATE=$(date -d "@$REMOTE_TS" '+%Y-%m-%d')
            echo "Map update available  (local: $LOCAL_DATE  remote: $REMOTE_DATE)"
            read -rp "Download updated map? This will re-process data (~10 min) [y/N]: " answer
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                echo "Downloading updated map..."
                curl -L "$MAP_URL" -o "$DATA_DIR/$MAP_FILE"
                rm -f "$DATA_DIR/$OSRM_FILE" "$DATA_DIR"/*.osrm.* 2>/dev/null
                echo "[OK] Map downloaded"
            else
                echo "Skipping update"
            fi
        else
            echo "[OK] Map is up to date"
        fi
    else
        echo "Downloading Malaysia map data (~300MB)..."
        curl -L --progress-bar "$MAP_URL" -o "$DATA_DIR/$MAP_FILE"
        echo "[OK] Map downloaded"
    fi

    # Pre-process if .osrm not present
    if [ ! -f "$DATA_DIR/$OSRM_FILE" ]; then
        echo "Pre-processing map (runs once, ~5-15 min)..."

        echo "  Step 1/3: Extracting..."
        docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend \
            osrm-extract -p /opt/car.lua /data/$MAP_FILE
        [ $? -ne 0 ] && echo "ERROR: osrm-extract failed" && exit 1

        echo "  Step 2/3: Partitioning..."
        docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend \
            osrm-partition /data/$OSRM_FILE
        [ $? -ne 0 ] && echo "ERROR: osrm-partition failed" && exit 1

        echo "  Step 3/3: Customizing..."
        docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend \
            osrm-customize /data/$OSRM_FILE
        [ $? -ne 0 ] && echo "ERROR: osrm-customize failed" && exit 1

        echo "[OK] Pre-processing complete"
    else
        echo "[OK] Pre-processed data found"
    fi

    echo "Starting OSRM server..."
    docker run -d --name "$CONTAINER_NAME" -p 5000:5000 -v "$DATA_DIR:/data" osrm/osrm-backend \
        osrm-routed --algorithm mld --max-table-size 10000 /data/$OSRM_FILE
    [ $? -ne 0 ] && echo "ERROR: Failed to start OSRM container" && exit 1

    # Wait for OSRM to be ready
    printf "Waiting for OSRM"
    for i in {1..20}; do
        if curl -sf "http://$OSRM_HOST:$OSRM_PORT/" &>/dev/null; then
            echo " ready"
            break
        fi
        printf "."
        sleep 1
    done
    echo "[OK] OSRM running at http://$OSRM_HOST:$OSRM_PORT"
fi

echo ""

# ── cuOpt API ─────────────────────────────────────────────────────────────────

echo "=== cuOpt API ==="

if [ ! -f "$CONDA_PATH/etc/profile.d/conda.sh" ]; then
    echo "ERROR: Miniforge not found at $CONDA_PATH"
    exit 1
fi

source "$CONDA_PATH/etc/profile.d/conda.sh"
conda activate "$ENV_NAME" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: conda environment '$ENV_NAME' not found"
    exit 1
fi

if ! nvidia-smi &>/dev/null; then
    echo "ERROR: GPU not accessible in WSL2"
    exit 1
fi

export OSRM_HOST
export OSRM_PORT

echo "GPU:  $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
echo "OSRM: http://$OSRM_HOST:$OSRM_PORT"
echo ""

# Start Vite dev server
UI_DIR="$SCRIPT_DIR/ui"
source /home/grepjava/.nvm/nvm.sh 2>/dev/null
if [ -d "$UI_DIR/node_modules" ]; then
    echo "Starting UI dev server on http://localhost:3000"
    (cd "$UI_DIR" && npm run dev) &
    UI_PID=$!
else
    echo "WARNING: Run 'npm install' in ui/ first"
fi

# Open browser after both servers start
(sleep 5 && cmd.exe /c start http://localhost:3000 2>/dev/null) &

echo "API:  http://localhost:8000"
echo "UI:   http://localhost:3000"
echo ""
cd "$SCRIPT_DIR"
python main.py

[ -n "$UI_PID" ] && kill "$UI_PID" 2>/dev/null
