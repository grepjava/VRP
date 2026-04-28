"""GPU memory management: context managers, cleanup utilities, and VRAM info."""
from __future__ import annotations

import gc
import logging
from contextlib import contextmanager
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SolverError(Exception):
    """Custom exception for solver-related errors"""
    pass


class GPUMemoryError(Exception):
    """Custom exception for GPU memory-related errors"""
    pass


@contextmanager
def gpu_memory_context(solver_id: Optional[int] = None, memory_limit_gb: float = None):
    """
    Context manager for comprehensive GPU memory cleanup with version compatibility

    Args:
        solver_id: Optional solver ID for logging
        memory_limit_gb: Optional memory limit to check against
    """
    try:
        import cupy as cp
        cupy_available = True
    except ImportError:
        cupy_available = False

    if not cupy_available:
        try:
            yield
        finally:
            gc.collect()
        return

    mempool = cp.get_default_memory_pool()

    pinned_mempool = None
    try:
        pinned_mempool = cp.get_default_pinned_memory_pool()
    except Exception as e:
        logger.debug(f"Could not get pinned memory pool: {e}")

    initial_gpu_bytes = mempool.used_bytes()
    initial_total_bytes = mempool.total_bytes()

    initial_pinned_bytes = 0
    if pinned_mempool:
        try:
            if hasattr(pinned_mempool, 'used_bytes'):
                initial_pinned_bytes = pinned_mempool.used_bytes()
            elif hasattr(pinned_mempool, 'n_bytes_used'):
                initial_pinned_bytes = pinned_mempool.n_bytes_used()
        except Exception as e:
            logger.debug(f"Could not get initial pinned memory: {e}")

    solver_prefix = f"[Solver {solver_id}]" if solver_id is not None else "[GPU Memory]"

    if memory_limit_gb:
        memory_limit_bytes = int(memory_limit_gb * 1024**3)
        if initial_gpu_bytes > memory_limit_bytes * 0.9:
            logger.warning(f"{solver_prefix} High memory usage before operation: {initial_gpu_bytes / 1024**3:.2f}GB")

    try:
        logger.debug(f"{solver_prefix} GPU memory before: {initial_gpu_bytes / 1024**2:.1f}MB used, {initial_total_bytes / 1024**2:.1f}MB total")
        yield

    except Exception as e:
        logger.error(f"{solver_prefix} GPU operation failed: {e}")
        raise

    finally:
        try:
            gc.collect()
            mempool.free_all_blocks()

            if pinned_mempool:
                try:
                    if hasattr(pinned_mempool, 'free_all_blocks'):
                        pinned_mempool.free_all_blocks()
                    elif hasattr(pinned_mempool, 'free_all_pinned'):
                        pinned_mempool.free_all_pinned()
                except Exception as e:
                    logger.debug(f"Pinned memory cleanup had issue: {e}")

            try:
                import cudf
                if hasattr(cudf, '_cuda_cleanup'):
                    cudf._cuda_cleanup()
            except Exception as cleanup_error:
                logger.debug(f"cuDF cleanup warning: {cleanup_error}")

            final_gpu_bytes = mempool.used_bytes()
            final_total_bytes = mempool.total_bytes()

            final_pinned_bytes = 0
            if pinned_mempool:
                try:
                    if hasattr(pinned_mempool, 'used_bytes'):
                        final_pinned_bytes = pinned_mempool.used_bytes()
                    elif hasattr(pinned_mempool, 'n_bytes_used'):
                        final_pinned_bytes = pinned_mempool.n_bytes_used()
                except Exception as e:
                    logger.debug(f"Could not get final pinned memory: {e}")

            gpu_diff = final_gpu_bytes - initial_gpu_bytes
            pinned_diff = final_pinned_bytes - initial_pinned_bytes

            logger.debug(f"{solver_prefix} GPU memory after: {final_gpu_bytes / 1024**2:.1f}MB used, {final_total_bytes / 1024**2:.1f}MB total")

            leak_threshold = 50 * 1024 * 1024  # 50MB
            if gpu_diff > leak_threshold:
                logger.warning(f"{solver_prefix} Potential GPU memory leak: {gpu_diff / 1024**2:.1f}MB not freed")

            if pinned_diff > leak_threshold:
                logger.warning(f"{solver_prefix} Potential pinned memory leak: {pinned_diff / 1024**2:.1f}MB not freed")

            if memory_limit_gb:
                memory_limit_bytes = int(memory_limit_gb * 1024**3)
                if final_gpu_bytes > memory_limit_bytes * 0.8:
                    logger.warning(f"{solver_prefix} High memory usage after cleanup: {final_gpu_bytes / 1024**3:.2f}GB (limit: {memory_limit_gb}GB)")

        except Exception as cleanup_error:
            logger.error(f"{solver_prefix} GPU memory cleanup failed: {cleanup_error}")


@contextmanager
def cudf_memory_context(operation_name: str = "cuDF operation"):
    """Context manager specifically for cuDF DataFrame operations"""
    try:
        yield
    finally:
        try:
            gc.collect()
            import cudf
            if hasattr(cudf, '_cleanup_memory'):
                cudf._cleanup_memory()
        except Exception as e:
            logger.debug(f"cuDF cleanup for {operation_name} had warning: {e}")


def get_gpu_memory_info() -> Dict[str, float]:
    """
    Get current GPU memory usage information.

    Uses cp.cuda.runtime.memGetInfo() which queries the CUDA driver directly,
    so it reflects RMM pool allocations as well as CuPy's own pool.

    Returns:
        dict: Memory information in MB
    """
    try:
        import cupy as cp

        # Query actual CUDA device memory — sees RMM pool + CuPy pool + all allocations
        free_bytes, total_bytes = cp.cuda.runtime.memGetInfo()
        gpu_used_bytes = total_bytes - free_bytes

        result = {
            'gpu_used_mb': gpu_used_bytes / 1024**2,
            'gpu_total_mb': total_bytes / 1024**2,
            'gpu_usage_percent': (gpu_used_bytes / max(1, total_bytes)) * 100
        }

        try:
            pinned_mempool = cp.get_default_pinned_memory_pool()

            if hasattr(pinned_mempool, 'used_bytes'):
                result['pinned_used_mb'] = pinned_mempool.used_bytes() / 1024**2
            elif hasattr(pinned_mempool, 'n_bytes_used'):
                result['pinned_used_mb'] = pinned_mempool.n_bytes_used() / 1024**2
            else:
                result['pinned_used_mb'] = 0.0

            if hasattr(pinned_mempool, 'total_bytes'):
                result['pinned_total_mb'] = pinned_mempool.total_bytes() / 1024**2
            elif hasattr(pinned_mempool, 'n_bytes_total'):
                result['pinned_total_mb'] = pinned_mempool.n_bytes_total() / 1024**2
            else:
                result['pinned_total_mb'] = 0.0

        except Exception as pinned_error:
            logger.debug(f"Could not get pinned memory info: {pinned_error}")
            result['pinned_used_mb'] = 0.0
            result['pinned_total_mb'] = 0.0

        return result

    except ImportError:
        return {
            'gpu_used_mb': 0.0,
            'gpu_total_mb': 0.0,
            'pinned_used_mb': 0.0,
            'pinned_total_mb': 0.0,
            'gpu_usage_percent': 0.0
        }
    except Exception as e:
        logger.warning(f"Failed to get GPU memory info: {e}")
        return {
            'gpu_used_mb': -1.0,
            'gpu_total_mb': -1.0,
            'pinned_used_mb': -1.0,
            'pinned_total_mb': -1.0,
            'gpu_usage_percent': -1.0
        }
