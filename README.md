# VRP — GPU-Accelerated Field Service Optimizer

Real-time Vehicle Routing Problem solver for field service operations. Dispatches technicians to work orders using road-accurate travel times, skill matching, and workload balancing — powered by NVIDIA cuOpt on GPU.

![Status](https://img.shields.io/badge/status-active-brightgreen) ![GPU](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-76b900) ![License](https://img.shields.io/badge/license-MIT-blue)

---

## What it does

- Assigns technicians to work orders optimally, minimising total travel time
- Respects time windows, shift hours, lunch breaks, and daily order limits
- Optional skill matching — only qualified technicians get assigned
- Optional workload balancing — caps total service time per technician so work is spread evenly
- Real road travel times via OSRM (not straight-line estimates)
- Interactive map with colour-coded routes and priority legends

## Architecture

```
Browser (Svelte + Leaflet)
    │  HTTP (same-origin in Docker, localhost:8000 in dev)
    ▼
nginx                         ← serves UI, proxies /vrp/* to API
    │
    ├── FastAPI (Python)       ← REST API, problem validation, result formatting
    │       │
    │       ├── cuOpt          ← NVIDIA GPU solver (DataModel → Solve)
    │       └── OSRM client   ← travel time matrix via HTTP
    │
    └── OSRM server           ← road routing engine (Docker container)
```

## Quick start (Docker)

**Prerequisites:** Docker Desktop with NVIDIA GPU runtime, CUDA-capable GPU.

```bash
git clone https://github.com/grepjava/VRP.git
cd VRP
./setup.sh
```

Open **http://localhost** in your browser.

To use a different map region:

```bash
./setup.sh --map-url https://download.geofabrik.de/europe/germany-latest.osm.pbf
```

See [SETUP.md](SETUP.md) for full installation and configuration options.

## Development (without Docker)

See [SETUP.md — Development workflow](SETUP.md#development-workflow).

## Solver settings

The UI exposes four cuOpt settings via the ⚙ Settings panel:

| Setting | cuOpt API | Effect |
|---|---|---|
| Enforce skill matching | `add_order_vehicle_match` | Hard constraint — only assigns qualified technicians |
| Minimize fleet size | `set_vehicle_fixed_costs` | Penalises deploying extra vehicles |
| Balance workload | `add_capacity_dimension` | Caps total service time per technician — prevents overloading without pushing routes to late in the day |
| Custom time limit | `SolverSettings.set_time_limit` | More time = better solution quality |
| Drop return to base | `set_drop_return_trips` | Omit the final leg back to the depot (global toggle) |

## API

```
POST /vrp/optimize      Run the solver
GET  /health            Service health check
GET  /status            Solver and GPU status
GET  /docs              Interactive API docs (Swagger)
```

Example request body: see [SETUP.md — API usage](SETUP.md#api-usage).

## Tech stack

| Layer | Technology |
|---|---|
| Solver | NVIDIA cuOpt (GPU-accelerated VRP) |
| Routing | OSRM (Open Source Routing Machine) |
| API | FastAPI + Uvicorn |
| GPU memory | RAPIDS RMM |
| Data | cuDF (GPU DataFrames) |
| Frontend | Svelte 4 + Leaflet |
| Container | Docker Compose + nginx |
