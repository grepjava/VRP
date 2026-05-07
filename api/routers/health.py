import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api import deps
from api.models import HealthResponseModel, MemoryInfoModel
from config import CONFIG, get_concurrent_solver_config
from core.osrm import validate_osrm_connection

router = APIRouter()
logger = logging.getLogger(__name__)

_osrm_health_cache: Dict[str, Any] = {"ok": None, "ts": 0.0}
_OSRM_TTL = 30.0


def _osrm_status_cached() -> str:
    now = time.time()
    if now - _osrm_health_cache["ts"] > _OSRM_TTL:
        _osrm_health_cache["ok"] = validate_osrm_connection()
        _osrm_health_cache["ts"] = now
    return "ok" if _osrm_health_cache["ok"] else "error"


@router.get("/", response_model=Dict[str, str])
async def root():
    return {
        "message": "Technician WorkOrder Optimization API",
        "version": "1.0.0",
        "docs": "/docs",
        "concurrent_execution": "enabled" if deps.concurrent_manager else "disabled",
        "gpu_memory_management": "enabled" if deps.get_gpu_memory_info_func else "disabled"
    }


@router.get("/health", response_model=HealthResponseModel)
async def health_check():
    osrm_status = _osrm_status_cached()
    config_status = "ok"
    cuopt_status = "ok" if deps.solver_available and deps.is_cuopt_available_func and deps.is_cuopt_available_func() else "error"
    concurrent_status = "ok" if deps.concurrent_manager else "disabled"
    overall_status = "ok" if all(s == "ok" for s in [osrm_status, config_status, cuopt_status]) else "degraded"

    concurrent_details: Dict[str, Any] = {"enabled": False, "status": "disabled"}
    if deps.concurrent_manager:
        try:
            stats = deps.concurrent_manager.get_statistics()
            concurrent_config = get_concurrent_solver_config()
            concurrent_details = {
                "enabled": True,
                "status": "ok",
                "max_concurrent_instances": concurrent_config['max_concurrent_instances'],
                "solver_threads": concurrent_config['max_concurrent_solvers'],
                "cuda_streams": concurrent_config['cuda_streams'],
                "active_requests": stats.get('active_requests', 0),
                "total_requests": stats.get('total_requests', 0),
                "success_rate": stats.get('success_rate', 0.0),
                "memory_management": True
            }
        except Exception as e:
            concurrent_details = {"enabled": True, "status": "error", "error": str(e)}

    memory_info = None
    try:
        if deps.get_gpu_memory_info_func:
            memory_info = MemoryInfoModel(**deps.get_gpu_memory_info_func())
    except Exception as e:
        logger.warning(f"Could not get memory info for health check: {e}")

    return HealthResponseModel(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
        services={
            "osrm": osrm_status,
            "config": config_status,
            "cuopt": cuopt_status,
            "concurrent": concurrent_status
        },
        concurrent_execution=concurrent_details,
        memory_info=memory_info
    )


@router.get("/cuopt/status")
async def get_cuopt_status():
    try:
        if deps.solver_available and deps.cuopt_status_func:
            status_info = deps.cuopt_status_func()
        else:
            status_info = {
                "available": False,
                "routing_module": False,
                "basic_functionality": False,
                "error": "Solver module not imported successfully"
            }

        concurrent_info: Dict[str, Any] = {"enabled": False}
        if deps.concurrent_manager:
            try:
                stats = deps.concurrent_manager.get_statistics()
                concurrent_config = get_concurrent_solver_config()
                concurrent_info = {
                    "enabled": True,
                    "max_concurrent_instances": concurrent_config['max_concurrent_instances'],
                    "solver_threads": concurrent_config['max_concurrent_solvers'],
                    "cuda_streams": concurrent_config['cuda_streams'],
                    "memory_management": True,
                    "statistics": stats
                }
            except Exception as e:
                concurrent_info = {"enabled": True, "error": str(e)}

        memory_info = None
        try:
            if deps.get_gpu_memory_info_func:
                memory_info = MemoryInfoModel(**deps.get_gpu_memory_info_func())
        except Exception as e:
            logger.warning(f"Could not get memory info for cuOpt status: {e}")

        return {
            "solver_available": deps.solver_available,
            "cuopt_details": status_info,
            "concurrent_execution": concurrent_info,
            "memory_info": memory_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "solver_available": False,
            "cuopt_details": {"error": str(e)},
            "concurrent_execution": {"enabled": False},
            "memory_info": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/concurrent/statistics")
async def get_concurrent_statistics():
    from fastapi import HTTPException, status
    if not deps.concurrent_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Concurrent execution is not available"
        )
    try:
        stats = deps.concurrent_manager.get_statistics()
        memory_info = None
        try:
            if deps.get_gpu_memory_info_func:
                memory_info = MemoryInfoModel(**deps.get_gpu_memory_info_func())
        except Exception:
            pass
        return {
            "statistics": stats,
            "memory_info": memory_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics"
        )


@router.get("/memory/status")
async def get_memory_status():
    from fastapi import HTTPException, status
    if not deps.get_gpu_memory_info_func:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GPU memory monitoring is not available"
        )
    try:
        memory_info = MemoryInfoModel(**deps.get_gpu_memory_info_func())
        return {
            "memory_info": memory_info,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "memory_management": "enabled"
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get memory status"
        )


@router.get("/config")
async def get_configuration():
    return {
        "business": CONFIG['business'],
        "optimization": CONFIG['optimization'],
        "data": {
            "max_technicians": CONFIG['data']['max_technicians'],
            "max_work_orders": CONFIG['data']['max_work_orders'],
            "supported_input_formats": CONFIG['data']['supported_input_formats'],
            "concurrent_limits": CONFIG['data']['concurrent_limits']
        },
        "osrm": {
            "max_locations_per_request": CONFIG['osrm']['max_locations_per_request'],
            "timeout": CONFIG['osrm']['timeout']
        },
        "concurrent_execution": get_concurrent_solver_config(),
        "memory_management": {
            "enabled": deps.get_gpu_memory_info_func is not None,
            "monitoring": True
        }
    }
