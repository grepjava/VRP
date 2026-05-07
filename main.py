import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CONFIG, validate_config, get_concurrent_solver_config
from core.converter import ConversionError
from core.osrm import validate_osrm_connection
from api import deps
from api.routers import health, optimization, scenarios, demo

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, CONFIG['logging']['level']),
    format=CONFIG['logging']['format']
)
for _component, _level in CONFIG['logging'].get('component_levels', {}).items():
    logging.getLogger(_component).setLevel(getattr(logging, _level))
logger = logging.getLogger(__name__)

# ── Solver import ─────────────────────────────────────────────────────────────
try:
    from core.solver import (
        TechnicianWorkOrderSolver, is_cuopt_available, get_cuopt_status,
        get_concurrent_solver_manager, solve_optimization_problems_concurrent,
        get_gpu_memory_info, initialize_gpu,
    )
    deps.cuopt_status_func = get_cuopt_status
    deps.is_cuopt_available_func = is_cuopt_available
    deps.get_gpu_memory_info_func = get_gpu_memory_info
    deps.TechnicianWorkOrderSolver = TechnicianWorkOrderSolver
    deps.solve_optimization_problems_concurrent = solve_optimization_problems_concurrent
    logger.info("Solver module imported successfully")

    if is_cuopt_available():
        deps.solver_available = True
        logger.info("cuOpt is available and working")

        concurrent_config = get_concurrent_solver_config()
        if concurrent_config['enabled']:
            try:
                deps.concurrent_manager = get_concurrent_solver_manager()
                logger.info(f"Concurrent solver manager initialized with {concurrent_config['max_concurrent_instances']} instances")
            except Exception as e:
                logger.warning(f"Failed to initialize concurrent solver manager: {e}")
    else:
        logger.error("cuOpt is not available")

except ImportError as e:
    logger.error(f"Failed to import solver module: {e}")

    class _DummySolver:
        def __init__(self, *a, **kw): pass
        def solve(self, problem):
            from core.models import OptimizationSolution, SolutionStatus
            return OptimizationSolution(status=SolutionStatus.ERROR, unassigned_orders=[])

    deps.TechnicianWorkOrderSolver = _DummySolver
    deps.is_cuopt_available_func = lambda: False
    deps.cuopt_status_func = lambda: {"available": False, "error": str(e)}
    deps.get_gpu_memory_info_func = lambda: {"gpu_used_mb": 0.0, "gpu_total_mb": 0.0, "gpu_usage_percent": 0.0}


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Technician WorkOrder Optimization API")
    if not validate_config():
        logger.error("Configuration validation failed")
    if deps.solver_available:
        initialize_gpu()
    if not validate_osrm_connection():
        logger.warning("OSRM server not accessible")
    if deps.solver_available:
        if deps.concurrent_manager:
            logger.info("cuOpt solver ready with concurrent execution enabled")
        else:
            logger.warning("cuOpt available but concurrent execution disabled")
    else:
        logger.warning("cuOpt solver not available — optimization endpoints will fail")
    try:
        if deps.get_gpu_memory_info_func:
            m = deps.get_gpu_memory_info_func()
            logger.info(f"GPU Memory: {m['gpu_used_mb']:.1f}MB / {m['gpu_total_mb']:.1f}MB ({m['gpu_usage_percent']:.1f}%)")
    except Exception as e:
        logger.warning(f"Could not get GPU memory info: {e}")
    logger.info("API startup complete")

    yield

    logger.info("Shutting down Technician WorkOrder Optimization API")
    if deps.concurrent_manager:
        try:
            deps.concurrent_manager.shutdown()
            logger.info("Concurrent solver manager shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down concurrent solver manager: {e}")
    try:
        if deps.get_gpu_memory_info_func:
            m = deps.get_gpu_memory_info_func()
            logger.info(f"Final GPU Memory: {m['gpu_used_mb']:.1f}MB / {m['gpu_total_mb']:.1f}MB")
    except Exception as e:
        logger.warning(f"Could not get final GPU memory info: {e}")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Technician WorkOrder Optimization API",
    description="GPU-accelerated VRP optimizer using cuOpt and OSRM",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

if CONFIG['api']['cors_enabled']:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CONFIG['api']['cors_origins'],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── Middleware ────────────────────────────────────────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    initial = None
    try:
        if deps.get_gpu_memory_info_func:
            initial = deps.get_gpu_memory_info_func()
            logger.info(f"Request: {request.method} {request.url} (GPU: {initial['gpu_used_mb']:.1f}MB)")
        else:
            logger.info(f"Request: {request.method} {request.url}")
    except Exception:
        logger.info(f"Request: {request.method} {request.url}")

    response = await call_next(request)
    elapsed = time.time() - start

    try:
        if deps.get_gpu_memory_info_func and initial:
            final = deps.get_gpu_memory_info_func()
            delta = final['gpu_used_mb'] - initial['gpu_used_mb']
            logger.info(f"Response: {response.status_code} in {elapsed:.3f}s (GPU: {final['gpu_used_mb']:.1f}MB, Δ{delta:+.1f}MB)")
        else:
            logger.info(f"Response: {response.status_code} in {elapsed:.3f}s")
    except Exception:
        logger.info(f"Response: {response.status_code} in {elapsed:.3f}s")

    return response


# ── Exception handlers ────────────────────────────────────────────────────────
@app.exception_handler(ConversionError)
async def conversion_exception_handler(request: Request, exc: ConversionError):
    logger.error(f"Conversion error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Data conversion error",
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("Unexpected error", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(optimization.router)
app.include_router(scenarios.router)
app.include_router(demo.router)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    host = CONFIG['api']['host']
    port = CONFIG['api']['port']
    debug = CONFIG['api']['debug']
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=debug,
                log_level="debug" if debug else "info", access_log=True)


if __name__ == "__main__":
    main()
