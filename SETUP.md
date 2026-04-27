# Setup & Configuration Guide

## Choose a workflow

There are two ways to run this project. **Pick one — they are not combined.**

| | Docker (`start.sh` / `stop.sh`) | Dev (`start-dev.sh`) |
|---|---|---|
| **Use when** | Running in production, sharing with others | Actively changing backend or UI code |
| **First run** | `./setup.sh` | `./start-dev.sh` |
| **Start (day 2+)** | `./start.sh` | `./start-dev.sh` |
| **Stop** | `./stop.sh` | `Ctrl+C` |
| **Hot reload** | No (rebuild image to update) | Yes (API + UI auto-reload on save) |

---

## Contents

1. [Prerequisites](#prerequisites)
2. [Docker setup](#docker-setup) — recommended
3. [Development workflow](#development-workflow) — without Docker
4. [Configuration reference](#configuration-reference)
5. [API usage](#api-usage)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Docker setup
| Requirement | Notes |
|---|---|
| Docker Desktop ≥ 4.20 | With Compose v2 (`docker compose`, not `docker-compose`) |
| NVIDIA GPU | Any CUDA-capable card with ≥ 4 GB VRAM |
| NVIDIA Container Toolkit | Enables GPU passthrough into containers |
| 15 GB free disk | ~11 GB map data + images |

Install the NVIDIA Container Toolkit on the Docker host (WSL2 or Linux):

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify GPU access in Docker:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

### Development workflow
| Requirement | Notes |
|---|---|
| NVIDIA GPU + CUDA 12.x | Same GPU requirement |
| Miniforge / Conda | For the cuOpt conda environment |
| cuOpt conda env | See [Development workflow](#development-workflow) |
| Node.js ≥ 20 | For the Svelte UI dev server |
| Docker (OSRM only) | OSRM still runs in Docker |

---

## Docker setup

### 1. Clone and run setup

```bash
git clone https://github.com/grepjava/VRP.git
cd VRP
./setup.sh
```

`setup.sh` will:
1. Download and preprocess the default Malaysia map (~300 MB download, ~10 min preprocessing — one-time)
2. Write a `.env` file with your configuration
3. Build the `api` and `ui` Docker images
4. Start all three services (`osrm`, `api`, `ui`)

Open **http://localhost** when complete.

### 2. Choose a map region

Find your region at **https://download.geofabrik.de/** and pass the URL:

```bash
# Western Europe
./setup.sh --map-url https://download.geofabrik.de/europe/germany-latest.osm.pbf

# US state
./setup.sh --map-url https://download.geofabrik.de/north-america/us/california-latest.osm.pbf

# Southeast Asia
./setup.sh --map-url https://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf
```

The map file name is derived automatically from the URL.

### 3. Tune for your GPU

```bash
# 16 GB GPU — 8 solver instances at 1.5 GB each
./setup.sh --instances 8 --mem-per-inst 1536 --gpu-mem-max 16

# 8 GB GPU — 4 solver instances at 1 GB each (default)
./setup.sh --instances 4 --mem-per-inst 1024 --gpu-mem-max 8
```

### Managing the stack

```bash
# Start / stop
docker compose up -d
docker compose down

# View logs
docker compose logs -f
docker compose logs -f api        # API only
docker compose logs -f osrm       # OSRM only

# Rebuild after code changes
docker compose build api
docker compose up -d api

# Full reset (keeps map data)
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Updating the map

Re-run setup — it checks the Geofabrik modification date and prompts before downloading:

```bash
./setup.sh --skip-build --skip-start
```

---

## Development workflow

Run the API and UI outside Docker for faster iteration. OSRM still runs in Docker.

### 1. Start OSRM

```bash
./setup.sh --skip-build --skip-start   # download and preprocess map if needed

docker compose up -d osrm
```

### 2. Set up the cuOpt conda environment

```bash
conda create -n cuopt python=3.12
conda activate cuopt

# Install RAPIDS (cuDF, RMM) and cuOpt
conda install -c rapidsai -c nvidia -c conda-forge cuopt

# Install API dependencies
pip install -r requirements.txt
```

### 3. Start the API

```bash
conda activate cuopt
OSRM_HOST=localhost python main.py
```

API available at **http://localhost:8000** — interactive docs at **http://localhost:8000/docs**.

### 4. Start the UI dev server

```bash
cd ui
npm install        # first time only
npm run dev
```

UI available at **http://localhost:3000** (hot-reload enabled).

The file `ui/.env.local` (not committed) points the UI at the local API:

```
VITE_API_URL=http://localhost:8000
```

---

## Configuration reference

All settings are controlled through environment variables. In Docker they come from `.env` (written by `setup.sh`). In development, set them in your shell or pass on the command line.

### setup.sh flags

| Flag | Default | Description |
|---|---|---|
| `--map-url <url>` | Malaysia | Geofabrik `.osm.pbf` download URL |
| `--map-file <name>` | _(derived from URL)_ | Override the local filename |
| `--ui-port <port>` | `80` | Host port for the web UI |
| `--api-port <port>` | `8000` | Host port for the REST API |
| `--instances <n>` | `4` | Parallel cuOpt solver instances |
| `--mem-per-inst <mb>` | `1024` | GPU memory per solver instance (MB) |
| `--gpu-mem-max <gb>` | `8` | Total GPU memory pool ceiling (GB) |
| `--skip-download` | — | Skip map download, use existing `osrm-data/` |
| `--skip-build` | — | Skip `docker compose build` |
| `--skip-start` | — | Prepare only, don't start services |

### Environment variables

Copy `.env.example` to `.env` and edit as needed. These are the full set of variables read by the application:

#### Map and OSRM

| Variable | Default | Description |
|---|---|---|
| `MAP_URL` | Malaysia URL | Source URL for the map download |
| `MAP_FILE` | `malaysia-singapore-brunei-latest.osm.pbf` | Local filename of the raw map |
| `OSRM_FILE` | `malaysia-singapore-brunei-latest.osrm` | Processed OSRM file (auto-derived) |
| `OSRM_HOST` | `192.168.100.20` | OSRM server hostname (set to `osrm` in Docker, `localhost` in dev) |
| `OSRM_PORT` | `5000` | OSRM server port |

#### Ports

| Variable | Default | Description |
|---|---|---|
| `UI_PORT` | `80` | Host port the UI is exposed on |
| `API_PORT` | `8000` | Host port the API is exposed on |

#### GPU and solver performance

| Variable | Default | Description |
|---|---|---|
| `GPU_MEMORY_INITIAL` | `1073741824` | Initial GPU memory pool (bytes). 1 GB = 1073741824 |
| `GPU_MEMORY_MAX` | `8589934592` | Maximum GPU memory pool (bytes). 8 GB = 8589934592 |
| `CUOPT_CONCURRENT_INSTANCES` | `4` | Number of parallel cuOpt solver instances (also sets CUDA stream count) |
| `CUOPT_MEMORY_PER_INSTANCE` | `1024` | GPU memory reserved per solver instance (MB) |

**Tuning guide:**

```
CUOPT_CONCURRENT_INSTANCES = floor(GPU_VRAM_GB / (CUOPT_MEMORY_PER_INSTANCE / 1024))

Examples:
  8 GB  GPU → instances=4,  mem-per-inst=1024 MB  (leaves ~4 GB headroom)
  16 GB GPU → instances=8,  mem-per-inst=1536 MB
  24 GB GPU → instances=12, mem-per-inst=1536 MB
```

#### Docker build arguments

These can be passed as `--build-arg` or set in `docker-compose.yml`:

| Argument | Default | Description |
|---|---|---|
| `RAPIDS_IMAGE` | `rapidsai/base:26.06a-cuda13-py3.13-amd64` | Base image for the API container. Change to match your CUDA version. Available tags: https://hub.docker.com/r/rapidsai/base/tags |
| `VITE_API_URL` | _(empty)_ | API base URL baked into the UI build. Empty = use nginx proxy (Docker). Set to `http://localhost:8000` for standalone UI builds. |

To change the RAPIDS base image in `docker-compose.yml`:

```yaml
api:
  build:
    args:
      RAPIDS_IMAGE: rapidsai/base:24.12-cuda12.4-py3.11
```

### Solver time limits

The API automatically scales the solver time limit based on problem size. These are configured in `config.py` and can be adjusted directly:

| Problem size | Sequential limit | Concurrent limit |
|---|---|---|
| ≤ 15 locations | 5 s | 3 s |
| ≤ 50 locations | 10 s | 8 s |
| ≤ 100 locations | 30 s | 20 s |
| > 100 locations | 60 s | 45 s |

Users can override the time limit per request via the **Custom solver time limit** setting in the UI.

---

## API usage

### Optimize endpoint

```
POST /vrp/optimize
Content-Type: application/json
```

**Minimal request:**

```json
{
  "technicians": [
    {
      "id": "tech-1",
      "name": "Alice",
      "start_location": { "latitude": 3.1200, "longitude": 101.6100, "address": "HQ" },
      "skills": ["electrical"],
      "work_shift": { "earliest": 480, "latest": 1020 },
      "break_window": { "earliest": 720, "latest": 780 },
      "break_duration": 60,
      "max_daily_orders": 8
    }
  ],
  "work_orders": [
    {
      "id": "wo-1",
      "customer_name": "Client A",
      "location": { "latitude": 3.1517, "longitude": 101.6150, "address": "Site A" },
      "priority": "high",
      "work_type": "maintenance",
      "service_time": 90,
      "required_skills": ["electrical"]
    }
  ]
}
```

> **Time values** are in minutes since midnight. `480` = 08:00, `1020` = 17:00.  
> **Priority values:** `emergency`, `critical`, `high`, `medium`, `low`  
> **Work type values:** `maintenance`, `repair`, `inspection`, `installation`, `emergency`

**With solver settings:**

```json
{
  "technicians": [...],
  "work_orders": [...],
  "config": {
    "enforce_skill_constraints": true,
    "vehicle_fixed_cost": 300,
    "max_route_hours": 7,
    "time_limit_override": 60
  }
}
```

| Config key | Type | Description |
|---|---|---|
| `enforce_skill_constraints` | bool | Only assign technicians with required skills |
| `vehicle_fixed_cost` | number | Fixed penalty per technician deployed (higher = fewer vehicles) |
| `max_route_hours` | number | Cap total service time per technician (hours) — work is spread evenly without shifting routes to late in the day |
| `time_limit_override` | number | Solver time limit in seconds |

**Response:**

```json
{
  "status": "success",
  "routes": [
    {
      "technician_id": "tech-1",
      "assignments": [
        {
          "work_order_id": "wo-1",
          "arrival_time": 495,
          "start_time": 495,
          "finish_time": 585,
          "travel_time_to": 15,
          "sequence_order": 1
        }
      ],
      "total_travel_time": 15,
      "total_service_time": 90,
      "total_time": 105
    }
  ],
  "unassigned_orders": [],
  "solve_time": 2.1,
  "objective_value": -3950.52
}
```

### Other endpoints

```bash
# Health check
GET /health

# Solver and GPU status
GET /status

# Interactive docs
GET /docs        # Swagger UI
GET /redoc       # ReDoc
```

---

## Troubleshooting

### OSRM container exits immediately

The processed `.osrm` file is missing. Re-run setup without `--skip-download`:

```bash
./setup.sh --skip-build --skip-start
docker compose up -d
```

### API container fails to start (GPU error)

Verify the NVIDIA Container Toolkit is installed and Docker can see the GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If that fails, reinstall the toolkit and restart Docker:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### cuOpt import error in API container

The RAPIDS base image version must match your CUDA driver version. Check your driver:

```bash
nvidia-smi | grep "CUDA Version"
```

Then update `RAPIDS_IMAGE` in `docker-compose.yml` to use a compatible tag from  
https://hub.docker.com/r/rapidsai/base/tags

```yaml
args:
  RAPIDS_IMAGE: rapidsai/base:26.06a-cuda13-py3.13-amd64   # match your CUDA version
```

### "Time matrix should be set" error from cuOpt

This is handled automatically — the API sets both a cost matrix and a transit time matrix. If you see this in logs it means `add_transit_time_matrix` failed; check that your cuOpt version supports it.

### OSRM returns no routes / wrong area

The loaded map doesn't cover the coordinates you're routing. Download the correct region:

```bash
./setup.sh --map-url https://download.geofabrik.de/<your-region>.osm.pbf
```

### UI shows "Server error" on optimize

Check API logs for the actual error:

```bash
docker compose logs -f api
```

Common causes: OSRM not ready yet (wait a few seconds), GPU out of memory (reduce `CUOPT_CONCURRENT_INSTANCES`), invalid request body.

### Map data on Windows host (WSL2)

Store `osrm-data/` inside the WSL2 filesystem (`~/` or similar) rather than on the Windows drive (`/mnt/c/`). Cross-filesystem I/O is significantly slower and causes OSRM preprocessing to take much longer.

```bash
# Clone into WSL2 filesystem, not /mnt/c/
cd ~
git clone https://github.com/grepjava/VRP.git
cd VRP
./setup.sh
```
