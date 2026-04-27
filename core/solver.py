"""
cuOpt-based solver for technician-workorder optimization
ULTRA HIGH PERFORMANCE VERSION WITH CUDA STREAMS AND GPU MEMORY MANAGEMENT
Following the cuOpt service team routing notebook patterns with aggressive optimizations,
concurrent execution using CUDA streams, and comprehensive GPU memory cleanup
"""
from __future__ import annotations

import logging
import time
import cudf
import numpy as np
import asyncio
import threading
import gc
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from queue import Queue, Empty
from dataclasses import dataclass
from threading import Lock, Event
from contextlib import contextmanager
import uuid

# Import cuOpt with proper error handling
cuopt_available = False

print("🔍 Attempting to import cuOpt routing module...")

try:
    from cuopt.routing import DataModel, SolverSettings, Solve
    cuopt_available = True
    print("✅ cuOpt routing imported successfully")

    # Initialize GPU memory management with enhanced pool for concurrent execution
    try:
        import rmm
        from config import get_config
        config = get_config()
        memory_config = config['cuopt']['memory_management']

        rmm.reinitialize(
            pool_allocator=True,
            initial_pool_size=memory_config['initial_pool_size'],
            maximum_pool_size=memory_config['maximum_pool_size']
        )
        print("✅ GPU memory pool initialized for concurrent execution")
    except ImportError:
        print("⚠️ rmm not available, using default GPU memory management")
    except Exception as e:
        print(f"⚠️ GPU memory pool initialization failed: {e}")

    # Initialize CUDA streams for concurrent execution
    try:
        import cupy as cp
        config = get_config()
        concurrent_config = config['cuopt']['concurrent_execution']
        if concurrent_config['enabled']:
            max_instances = concurrent_config['max_concurrent_instances']
            print(f"🚀 Initializing {max_instances} CUDA streams...")
            # We'll create streams in the ConcurrentSolverManager
            print("✅ CUDA streams support ready")
    except ImportError:
        print("⚠️ CuPy not available, CUDA streams will be limited")
    except Exception as e:
        print(f"⚠️ CUDA streams initialization failed: {e}")

except ImportError as e:
    print(f"❌ cuOpt import failed: {e}")
    print("⚠️ Solver will not be available")
    cuopt_available = False
    DataModel = None
    SolverSettings = None
    Solve = None

from config import CONFIG, get_optimal_time_limit, get_concurrent_solver_config
from core.models import (
    OptimizationProblem, OptimizationSolution, TechnicianRoute, Assignment,
    Technician, WorkOrder, Priority, SolutionStatus, DistanceMatrix
)
from core.osrm import calculate_matrix_for_problem

logger = logging.getLogger(__name__)


class SolverError(Exception):
    """Custom exception for solver-related errors"""
    pass


class GPUMemoryError(Exception):
    """Custom exception for GPU memory-related errors"""
    pass


# =============================================================================
# GPU Memory Management Context Managers
# =============================================================================

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
        # Fallback for systems without CuPy
        try:
            yield
        finally:
            gc.collect()
        return

    # Get memory pools with compatibility handling
    mempool = cp.get_default_memory_pool()

    # Get pinned memory pool with compatibility check
    pinned_mempool = None
    try:
        pinned_mempool = cp.get_default_pinned_memory_pool()
    except Exception as e:
        logger.debug(f"Could not get pinned memory pool: {e}")

    # Record initial state
    initial_gpu_bytes = mempool.used_bytes()
    initial_total_bytes = mempool.total_bytes()

    # Handle pinned memory with version compatibility
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

    # Check memory availability before starting
    if memory_limit_gb:
        memory_limit_bytes = int(memory_limit_gb * 1024**3)
        if initial_gpu_bytes > memory_limit_bytes * 0.9:  # 90% threshold
            logger.warning(f"{solver_prefix} High memory usage before operation: {initial_gpu_bytes / 1024**3:.2f}GB")

    try:
        logger.debug(f"{solver_prefix} GPU memory before: {initial_gpu_bytes / 1024**2:.1f}MB used, {initial_total_bytes / 1024**2:.1f}MB total")
        yield

    except Exception as e:
        logger.error(f"{solver_prefix} GPU operation failed: {e}")
        raise

    finally:
        try:
            # Force Python garbage collection first
            gc.collect()

            # Free all blocks from memory pools
            mempool.free_all_blocks()

            # Handle pinned memory cleanup with compatibility
            if pinned_mempool:
                try:
                    if hasattr(pinned_mempool, 'free_all_blocks'):
                        pinned_mempool.free_all_blocks()
                    elif hasattr(pinned_mempool, 'free_all_pinned'):
                        pinned_mempool.free_all_pinned()
                except Exception as e:
                    logger.debug(f"Pinned memory cleanup had issue: {e}")

            # Additional cleanup for cuDF objects
            try:
                import cudf
                # Force cuDF to release any cached memory
                if hasattr(cudf, '_cuda_cleanup'):
                    cudf._cuda_cleanup()
            except Exception as cleanup_error:
                logger.debug(f"cuDF cleanup warning: {cleanup_error}")

            # Verify cleanup effectiveness
            final_gpu_bytes = mempool.used_bytes()
            final_total_bytes = mempool.total_bytes()

            # Handle pinned memory verification with compatibility
            final_pinned_bytes = 0
            if pinned_mempool:
                try:
                    if hasattr(pinned_mempool, 'used_bytes'):
                        final_pinned_bytes = pinned_mempool.used_bytes()
                    elif hasattr(pinned_mempool, 'n_bytes_used'):
                        final_pinned_bytes = pinned_mempool.n_bytes_used()
                except Exception as e:
                    logger.debug(f"Could not get final pinned memory: {e}")

            # Calculate memory changes
            gpu_diff = final_gpu_bytes - initial_gpu_bytes
            pinned_diff = final_pinned_bytes - initial_pinned_bytes

            logger.debug(f"{solver_prefix} GPU memory after: {final_gpu_bytes / 1024**2:.1f}MB used, {final_total_bytes / 1024**2:.1f}MB total")

            # Log significant memory retention (potential leaks)
            leak_threshold = 50 * 1024 * 1024  # 50MB
            if gpu_diff > leak_threshold:
                logger.warning(f"{solver_prefix} Potential GPU memory leak: {gpu_diff / 1024**2:.1f}MB not freed")

            if pinned_diff > leak_threshold:
                logger.warning(f"{solver_prefix} Potential pinned memory leak: {pinned_diff / 1024**2:.1f}MB not freed")

            # Check if we're approaching memory limits
            if memory_limit_gb:
                memory_limit_bytes = int(memory_limit_gb * 1024**3)
                if final_gpu_bytes > memory_limit_bytes * 0.8:  # 80% threshold
                    logger.warning(f"{solver_prefix} High memory usage after cleanup: {final_gpu_bytes / 1024**3:.2f}GB (limit: {memory_limit_gb}GB)")

        except Exception as cleanup_error:
            logger.error(f"{solver_prefix} GPU memory cleanup failed: {cleanup_error}")
            # Don't raise here - we don't want cleanup failures to mask the original operation


@contextmanager
def cudf_memory_context(operation_name: str = "cuDF operation"):
    """
    Context manager specifically for cuDF DataFrame operations
    """
    try:
        yield
    finally:
        try:
            # Force garbage collection of cuDF objects
            gc.collect()

            # Additional cuDF-specific cleanup
            import cudf
            if hasattr(cudf, '_cleanup_memory'):
                cudf._cleanup_memory()

        except Exception as e:
            logger.debug(f"cuDF cleanup for {operation_name} had warning: {e}")


def get_gpu_memory_info() -> Dict[str, float]:
    """
    Get current GPU memory usage information with version compatibility

    Returns:
        dict: Memory information in MB
    """
    try:
        import cupy as cp
        mempool = cp.get_default_memory_pool()

        # Get basic GPU memory info
        gpu_used_bytes = mempool.used_bytes()
        gpu_total_bytes = mempool.total_bytes()

        result = {
            'gpu_used_mb': gpu_used_bytes / 1024**2,
            'gpu_total_mb': gpu_total_bytes / 1024**2,
            'gpu_usage_percent': (gpu_used_bytes / max(1, gpu_total_bytes)) * 100
        }

        # Try to get pinned memory info with compatibility handling
        try:
            pinned_mempool = cp.get_default_pinned_memory_pool()

            # Check which attributes are available (version compatibility)
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


# =============================================================================
# Enhanced Result Classes with Memory Info
# =============================================================================

@dataclass
class SolverRequest:
    """Request wrapper for solver queue"""
    request_id: str
    problem: OptimizationProblem
    config: Optional[Dict[str, Any]]
    priority: int = 1  # Lower numbers = higher priority
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()

    def __lt__(self, other):
        # For priority queue ordering
        return self.priority < other.priority


@dataclass
class SolverResult:
    """Result wrapper for solver responses with memory information"""
    request_id: str
    solution: OptimizationSolution
    processing_time: float
    solver_id: int
    success: bool = True
    error: Optional[str] = None
    memory_info: Optional[Dict[str, float]] = None


# =============================================================================
# CUDA Stream Manager (unchanged but with memory monitoring)
# =============================================================================

class CUDAStreamManager:
    """Manages CUDA streams for concurrent cuOpt execution"""

    def __init__(self, num_streams: int):
        self.num_streams = num_streams
        self.streams = []
        self.stream_lock = Lock()
        self.available_streams = Queue()

        try:
            import cupy as cp
            # Create CUDA streams
            for i in range(num_streams):
                stream = cp.cuda.Stream(non_blocking=True)
                self.streams.append(stream)
                self.available_streams.put(i)
            print(f"✅ Created {num_streams} CUDA streams")
        except Exception as e:
            print(f"⚠️ Failed to create CUDA streams: {e}")
            # Fallback to None streams
            for i in range(num_streams):
                self.streams.append(None)
                self.available_streams.put(i)

    @contextmanager
    def get_stream(self, timeout: float = 30.0):
        """Get an available CUDA stream"""
        try:
            stream_id = self.available_streams.get(timeout=timeout)
            stream = self.streams[stream_id]
            try:
                yield stream_id, stream
            finally:
                self.available_streams.put(stream_id)
        except Empty:
            raise SolverError(f"No CUDA streams available within {timeout}s")

    def synchronize_all(self):
        """Synchronize all CUDA streams"""
        try:
            import cupy as cp
            for stream in self.streams:
                if stream is not None:
                    stream.synchronize()
        except Exception as e:
            logger.warning(f"Failed to synchronize CUDA streams: {e}")


# =============================================================================
# Enhanced Concurrent Solver Manager with Memory Management
# =============================================================================

class ConcurrentSolverManager:
    """Manages multiple concurrent cuOpt solver instances with CUDA streams and memory management"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize concurrent solver manager with memory management"""
        self.config = CONFIG.copy()
        if config:
            for key, value in config.items():
                if key in self.config and isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value

        self.concurrent_config = get_concurrent_solver_config()
        self.cuopt_config = self.config['cuopt']
        self.business_config = self.config['business']
        self.optimization_config = self.config['optimization']

        if not cuopt_available:
            logger.error("cuOpt is not available. Cannot initialize concurrent solver.")
            raise RuntimeError("cuOpt is not available. Please check cuOpt installation.")

        # Initialize concurrent execution components using single setting
        self.max_instances = self.concurrent_config['max_concurrent_instances']
        self.max_solvers = self.max_instances  # Same as max_instances
        self.num_cuda_streams = self.max_instances  # Same as max_instances

        # Memory management configuration
        self.memory_limit_per_instance = self.concurrent_config['memory_pool_per_instance'] / 1024  # Convert MB to GB

        self.cuda_streams = CUDAStreamManager(self.num_cuda_streams)

        # Request tracking
        self.results = {}  # request_id -> SolverResult
        self.active_requests = {}  # request_id -> Future

        # Thread pool for solver execution
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_solvers,
            thread_name_prefix="cuopt_solver"
        )

        # Solver assignment management
        self.solver_counter = 0
        self.solver_assignment_lock = Lock()
        self.busy_solvers = set()  # Track which solvers are currently busy

        # Enhanced monitoring and statistics with memory tracking
        self.stats = {
            'total_requests': 0,
            'completed_requests': 0,
            'failed_requests': 0,
            'active_solvers': 0,
            'average_processing_time': 0.0,
            'start_time': time.time(),
            'solver_usage': {i: 0 for i in range(self.max_solvers)},  # Track usage per solver
            'memory_stats': {
                'peak_gpu_usage_mb': 0.0,
                'average_gpu_usage_mb': 0.0,
                'memory_cleanups': 0,
                'memory_warnings': 0
            }
        }
        self.stats_lock = Lock()

        # Solver instances (one per thread/stream)
        self.solver_instances = {}
        self.solver_lock = Lock()

        logger.info(f"Initialized ConcurrentSolverManager with {self.max_instances} concurrent instances")
        print("✅ ConcurrentSolverManager initialized with GPU memory management")
        print(f"   🚀 Max concurrent instances: {self.max_instances}")
        print(f"   🧵 Solver threads: {self.max_solvers}")
        print(f"   🎯 CUDA streams: {self.num_cuda_streams}")
        print(f"   💾 Memory per instance: {self.concurrent_config['memory_pool_per_instance']}MB")
        print(f"   🧹 GPU memory cleanup: enabled")

    def _get_next_solver_id(self) -> int:
        """Get the next available solver ID using round-robin assignment"""
        with self.solver_assignment_lock:
            # Round-robin assignment
            solver_id = self.solver_counter % self.max_solvers
            self.solver_counter += 1

            # Track solver usage
            with self.stats_lock:
                self.stats['solver_usage'][solver_id] += 1

            return solver_id

    def _mark_solver_busy(self, solver_id: int):
        """Mark a solver as busy"""
        with self.solver_assignment_lock:
            self.busy_solvers.add(solver_id)

    def _mark_solver_free(self, solver_id: int):
        """Mark a solver as free"""
        with self.solver_assignment_lock:
            self.busy_solvers.discard(solver_id)

    def get_solver_instance(self, solver_id: int) -> 'TechnicianWorkOrderSolver':
        """Get or create a solver instance for the given solver ID"""
        with self.solver_lock:
            if solver_id not in self.solver_instances:
                self.solver_instances[solver_id] = TechnicianWorkOrderSolver(
                    self.config,
                    solver_id=solver_id,
                    concurrent_mode=True
                )
            return self.solver_instances[solver_id]

    def _update_memory_stats(self, memory_info: Dict[str, float]):
        """Update memory statistics"""
        with self.stats_lock:
            gpu_usage = memory_info.get('gpu_used_mb', 0.0)

            # Update peak usage
            if gpu_usage > self.stats['memory_stats']['peak_gpu_usage_mb']:
                self.stats['memory_stats']['peak_gpu_usage_mb'] = gpu_usage

            # Update average (simple moving average)
            current_avg = self.stats['memory_stats']['average_gpu_usage_mb']
            completed = self.stats['completed_requests']
            if completed > 0:
                self.stats['memory_stats']['average_gpu_usage_mb'] = (
                    (current_avg * (completed - 1) + gpu_usage) / completed
                )
            else:
                self.stats['memory_stats']['average_gpu_usage_mb'] = gpu_usage

    def submit_request(self, problem: OptimizationProblem,
                      config: Optional[Dict[str, Any]] = None,
                      priority: int = 1) -> str:
        """Submit an optimization request for concurrent processing"""
        request_id = str(uuid.uuid4())
        request = SolverRequest(
            request_id=request_id,
            problem=problem,
            config=config,
            priority=priority
        )

        # Submit to executor
        future = self.executor.submit(self._process_request, request)
        self.active_requests[request_id] = future

        with self.stats_lock:
            self.stats['total_requests'] += 1

        logger.info(f"Submitted request {request_id} with priority {priority}")
        return request_id

    def _process_request(self, request: SolverRequest) -> SolverResult:
        """Process a single optimization request with comprehensive memory management"""
        start_time = time.time()

        # Get assigned solver ID using round-robin
        solver_id = self._get_next_solver_id()

        try:
            self._mark_solver_busy(solver_id)

            with self.stats_lock:
                self.stats['active_solvers'] += 1

            print(f"🚀 Processing request {request.request_id[:8]} on solver {solver_id}")

            # Get initial memory state
            initial_memory = get_gpu_memory_info()

            # Process with comprehensive memory management
            with gpu_memory_context(solver_id=solver_id, memory_limit_gb=self.memory_limit_per_instance):
                # Get CUDA stream for this request
                with self.cuda_streams.get_stream() as (stream_id, stream):
                    print(f"   🎯 Using CUDA stream {stream_id}")

                    # Get solver instance
                    solver = self.get_solver_instance(solver_id)

                    # Apply per-request config overrides (safe: solver_id is exclusively busy)
                    saved_config = {}
                    if request.config:
                        for key, value in request.config.items():
                            saved_config[key] = solver.config.get(key, '__MISSING__')
                            solver.config[key] = value
                        print(f"   ⚙️  Request config applied: {list(request.config.keys())}")

                    # Set CUDA stream context if available
                    try:
                        if stream is not None:
                            try:
                                import cupy as cp
                                with stream:
                                    solution = solver.solve(request.problem)
                            except Exception:
                                solution = solver.solve(request.problem)
                        else:
                            solution = solver.solve(request.problem)
                    finally:
                        # Restore solver config so next request starts clean
                        for key, original in saved_config.items():
                            if original == '__MISSING__':
                                solver.config.pop(key, None)
                            else:
                                solver.config[key] = original

            # Get final memory state
            final_memory = get_gpu_memory_info()
            processing_time = time.time() - start_time

            # Update memory statistics
            self._update_memory_stats(final_memory)

            result = SolverResult(
                request_id=request.request_id,
                solution=solution,
                processing_time=processing_time,
                solver_id=solver_id,
                success=True,
                memory_info=final_memory
            )

            # Store result
            self.results[request.request_id] = result

            # Update statistics
            with self.stats_lock:
                self.stats['completed_requests'] += 1
                self.stats['active_solvers'] -= 1
                # Update average processing time
                total_completed = self.stats['completed_requests']
                self.stats['average_processing_time'] = (
                    (self.stats['average_processing_time'] * (total_completed - 1) + processing_time) / total_completed
                )
                self.stats['memory_stats']['memory_cleanups'] += 1

            print(f"✅ Completed request {request.request_id[:8]} in {processing_time:.3f}s on solver {solver_id}")
            print(f"   💾 GPU memory: {final_memory['gpu_used_mb']:.1f}MB used, {final_memory['gpu_usage_percent']:.1f}% utilization")
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)

            # Get memory info even on error
            error_memory = get_gpu_memory_info()

            result = SolverResult(
                request_id=request.request_id,
                solution=OptimizationSolution(
                    status=SolutionStatus.ERROR,
                    unassigned_orders=[wo.id for wo in request.problem.work_orders]
                ),
                processing_time=processing_time,
                solver_id=solver_id,
                success=False,
                error=error_msg,
                memory_info=error_memory
            )

            self.results[request.request_id] = result

            with self.stats_lock:
                self.stats['failed_requests'] += 1
                self.stats['active_solvers'] -= 1
                if "memory" in error_msg.lower():
                    self.stats['memory_stats']['memory_warnings'] += 1

            logger.error(f"Request {request.request_id} failed: {error_msg}")
            print(f"❌ Request {request.request_id[:8]} failed: {error_msg}")
            return result

        finally:
            # Mark solver as free and clean up
            self._mark_solver_free(solver_id)

            # Clean up request from active list
            if request.request_id in self.active_requests:
                del self.active_requests[request.request_id]

    def get_result(self, request_id: str, timeout: float = None) -> Optional[SolverResult]:
        """Get result for a specific request"""
        if request_id in self.results:
            return self.results[request_id]

        # Wait for completion if request is active
        if request_id in self.active_requests:
            try:
                future = self.active_requests[request_id]
                result = future.result(timeout=timeout)
                return result
            except Exception as e:
                logger.error(f"Failed to get result for request {request_id}: {e}")
                return None

        return None

    def wait_for_completion(self, request_ids: List[str], timeout: float = None) -> Dict[str, SolverResult]:
        """Wait for multiple requests to complete"""
        results = {}

        # Get futures for active requests
        futures = {
            self.active_requests[req_id]: req_id
            for req_id in request_ids
            if req_id in self.active_requests
        }

        # Wait for completion
        try:
            for future in as_completed(futures.keys(), timeout=timeout):
                req_id = futures[future]
                try:
                    result = future.result()
                    results[req_id] = result
                except Exception as e:
                    logger.error(f"Request {req_id} failed: {e}")
        except Exception as e:
            logger.error(f"Error waiting for completion: {e}")

        # Add already completed results
        for req_id in request_ids:
            if req_id in self.results and req_id not in results:
                results[req_id] = self.results[req_id]

        return results

    def solve_batch(self, problems: List[OptimizationProblem],
                   configs: Optional[List[Dict[str, Any]]] = None,
                   timeout: float = None) -> List[OptimizationSolution]:
        """Solve multiple problems concurrently"""
        if configs is None:
            configs = [None] * len(problems)

        # Submit all requests
        request_ids = []
        for i, (problem, config) in enumerate(zip(problems, configs)):
            request_id = self.submit_request(problem, config, priority=i)
            request_ids.append(request_id)

        print(f"🚀 Submitted {len(request_ids)} problems for concurrent processing")

        # Wait for completion
        results = self.wait_for_completion(request_ids, timeout)

        # Extract solutions in order
        solutions = []
        for req_id in request_ids:
            if req_id in results:
                solutions.append(results[req_id].solution)
            else:
                # Create error solution
                solutions.append(OptimizationSolution(
                    status=SolutionStatus.ERROR,
                    unassigned_orders=[]
                ))

        return solutions

    def get_statistics(self) -> Dict[str, Any]:
        """Get solver statistics including memory information"""
        with self.stats_lock:
            stats = self.stats.copy()

        with self.solver_assignment_lock:
            busy_solvers = self.busy_solvers.copy()

        # Add current memory info
        current_memory = get_gpu_memory_info()

        stats['uptime'] = time.time() - stats['start_time']
        stats['success_rate'] = (
            stats['completed_requests'] / max(1, stats['total_requests']) * 100
        )
        stats['queue_size'] = len(self.active_requests)
        stats['active_requests'] = len(self.active_requests)
        stats['busy_solvers'] = list(busy_solvers)
        stats['available_solvers'] = [i for i in range(self.max_solvers) if i not in busy_solvers]
        stats['max_concurrent_instances'] = self.max_instances
        stats['cuda_streams'] = self.num_cuda_streams
        stats['current_memory'] = current_memory

        return stats

    def shutdown(self):
        """Shutdown the concurrent solver manager with memory cleanup"""
        print("🔄 Shutting down ConcurrentSolverManager...")

        # Wait for active requests to complete
        for request_id, future in list(self.active_requests.items()):
            try:
                future.result(timeout=5.0)
            except Exception:
                pass

        # Shutdown executor
        self.executor.shutdown(wait=True)

        # Synchronize CUDA streams
        self.cuda_streams.synchronize_all()

        # Final memory cleanup
        try:
            with gpu_memory_context(solver_id="shutdown"):
                pass  # Just for cleanup
        except Exception as e:
            logger.warning(f"Final memory cleanup warning: {e}")

        print("✅ ConcurrentSolverManager shutdown complete")


# =============================================================================
# Enhanced TechnicianWorkOrderSolver with Memory Management
# =============================================================================

class TechnicianWorkOrderSolver:
    """
    Main solver class that integrates OSRM and cuOpt for technician-workorder optimization
    ULTRA HIGH PERFORMANCE VERSION WITH CUDA STREAMS SUPPORT AND GPU MEMORY MANAGEMENT
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 solver_id: int = 0, concurrent_mode: bool = False):
        """Initialize solver with configuration"""
        self.solver_id = solver_id
        self.concurrent_mode = concurrent_mode

        self.config = CONFIG.copy()
        if config:
            for key, value in config.items():
                if key in self.config and isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value

        self.cuopt_config = self.config['cuopt']
        self.business_config = self.config['business']
        self.optimization_config = self.config['optimization']

        if not cuopt_available:
            logger.error("cuOpt is not available. Cannot perform optimization.")
            raise RuntimeError("cuOpt is not available. Please check cuOpt installation.")

        logger.info(f"Initialized TechnicianWorkOrderSolver {solver_id} (concurrent: {concurrent_mode})")
        if concurrent_mode:
            print(f"✅ TechnicianWorkOrderSolver {solver_id} initialized for concurrent execution with memory management")
        else:
            print("✅ TechnicianWorkOrderSolver initialized with cuOpt and memory management")

    def solve(self, problem: OptimizationProblem) -> OptimizationSolution:
        """Solve the optimization problem with maximum performance and memory management"""
        start_time = time.time()

        # Determine memory limit for this solver
        concurrent_config = get_concurrent_solver_config()
        memory_limit_gb = concurrent_config['memory_pool_per_instance'] / 1024  # Convert MB to GB

        # Use comprehensive memory management for the entire solve operation
        with gpu_memory_context(solver_id=self.solver_id, memory_limit_gb=memory_limit_gb):
            try:
                # Validate problem
                issues = problem.validate()
                if issues:
                    logger.error(f"Problem validation failed: {issues}")
                    return OptimizationSolution(
                        status=SolutionStatus.ERROR,
                        unassigned_orders=[wo.id for wo in problem.work_orders]
                    )

                problem_size = len(problem.technicians) + len(problem.work_orders)
                solver_prefix = f"[Solver {self.solver_id}]" if self.concurrent_mode else ""
                print(f"🔍 {solver_prefix} Problem: {len(problem.technicians)} techs, {len(problem.work_orders)} orders (total: {problem_size})")

                # Step 1: Calculate distance matrix using OSRM
                matrix_time = 0.0
                if problem.distance_matrix is None:
                    print(f"🌐 {solver_prefix} Calculating travel times via OSRM...")
                    matrix_start = time.time()
                    problem.distance_matrix = calculate_matrix_for_problem(
                        problem.technicians, problem.work_orders
                    )
                    matrix_time = time.time() - matrix_start
                    print(f"✅ {solver_prefix} Distance matrix calculated in {matrix_time:.3f}s")

                # Step 2: Build cuOpt DataModel with performance optimizations and memory management
                print(f"🏗️ {solver_prefix} Building cuOpt data model...")
                model_start = time.time()

                with cudf_memory_context("data model building"):
                    data_model = self._build_cuopt_model(problem)

                model_time = time.time() - model_start
                print(f"✅ {solver_prefix} cuOpt data model built in {model_time:.3f}s")

                # Step 3: Configure solver with ultra-aggressive settings
                print(f"⚙️ {solver_prefix} Configuring high-performance solver...")
                solver_settings = self._configure_solver(problem_size)

                # Step 4: Verify GPU and run solver
                if not self.concurrent_mode:  # Only verify once for concurrent mode
                    self._verify_gpu_status()

                print(f"🚀 {solver_prefix} Running cuOpt optimization...")
                solve_start = time.time()

                # Run solver with memory context
                with cudf_memory_context("cuOpt solving"):
                    solution = Solve(data_model, solver_settings)

                solve_time = time.time() - solve_start
                print(f"✅ {solver_prefix} cuOpt solved in {solve_time:.3f}s")

                # Step 5: Check solver status
                solver_status = solution.get_status()
                if solver_status == 0:
                    print(f"📊 {solver_prefix} SUCCESS: Objective value = {solution.get_total_objective():.2f}")
                else:
                    try:
                        err_msg = solution.get_error_message()
                    except Exception:
                        err_msg = "unknown"
                    print(f"📊 {solver_prefix} Status {solver_status}: {err_msg}")

                # Step 6: Convert results to our format
                conversion_start = time.time()

                with cudf_memory_context("solution conversion"):
                    optimization_solution = self._convert_solution(solution, problem)

                conversion_time = time.time() - conversion_start
                optimization_solution.solve_time = time.time() - start_time

                # Performance summary
                total_time = optimization_solution.solve_time
                if not self.concurrent_mode or logger.isEnabledFor(logging.INFO):
                    print(f"🏁 {solver_prefix} PERFORMANCE SUMMARY:")
                    print(f"   OSRM Matrix: {matrix_time:.3f}s ({100*matrix_time/total_time:.1f}%)")
                    print(f"   Model Build: {model_time:.3f}s ({100*model_time/total_time:.1f}%)")
                    print(f"   cuOpt Solve: {solve_time:.3f}s ({100*solve_time/total_time:.1f}%)")
                    print(f"   Conversion:  {conversion_time:.3f}s ({100*conversion_time/total_time:.1f}%)")
                    print(f"   TOTAL TIME:  {total_time:.3f}s")
                    print(f"   Status: {optimization_solution.status.value}, Orders: {optimization_solution.orders_completed}")

                return optimization_solution

            except Exception as e:
                logger.error(f"Solver error: {e}")
                solver_prefix = f"[Solver {self.solver_id}]" if self.concurrent_mode else ""
                print(f"❌ {solver_prefix} Solver error: {e}")
                return OptimizationSolution(
                    status=SolutionStatus.ERROR,
                    unassigned_orders=[wo.id for wo in problem.work_orders],
                    solve_time=time.time() - start_time
                )

    def _configure_solver(self, problem_size: int) -> SolverSettings:
        """Configure solver with ultra-aggressive performance settings"""
        solver_settings = SolverSettings()

        time_limit_override = self.config.get('time_limit_override', None)
        if time_limit_override:
            time_limit = float(time_limit_override)
        else:
            time_limit = get_optimal_time_limit(problem_size, self.concurrent_mode)

        solver_settings.set_time_limit(time_limit)

        # Disable all verbose output for maximum performance
        solver_settings.set_verbose_mode(False)
        solver_settings.set_error_logging_mode(False)

        mode_str = "CONCURRENT" if self.concurrent_mode else "ULTRA-fast"
        print(f"   ⚡⚡ {mode_str} mode: {time_limit}s limit for {problem_size} locations")

        return solver_settings

    def _verify_gpu_status(self):
        """Verify GPU availability and performance"""
        try:
            import cupy as cp
            device_id = cp.cuda.runtime.getDevice()
            device_props = cp.cuda.runtime.getDeviceProperties(device_id)
            meminfo = cp.cuda.runtime.memGetInfo()

            print(f"   🎯 GPU {device_id}: {device_props['name'].decode()}")
            print(f"   🎯 Memory: {meminfo[0]//1024//1024}MB free / {meminfo[1]//1024//1024}MB total")
            print(f"   🎯 CUDA Cores: {device_props['multiProcessorCount'] * 128}")  # Rough estimate

        except Exception as e:
            print(f"   ⚠️ GPU verification failed: {e}")

    def _build_cuopt_model(self, problem: OptimizationProblem) -> DataModel:
        """
        Build cuOpt DataModel with ultra performance optimizations and memory management
        """
        n_technicians = len(problem.technicians)
        n_work_orders = len(problem.work_orders)
        n_locations = n_technicians + n_work_orders
        problem_size = n_technicians + n_work_orders

        # Create data model
        data_model = DataModel(n_locations, n_technicians, n_work_orders)

        # 1. Set cost matrix + transit time matrix (same duration data, different purposes:
        #    cost drives objective, transit time drives time-window/max-time constraints)
        with cudf_memory_context("cost matrix creation"):
            cost_matrix = cudf.DataFrame(problem.distance_matrix.durations, dtype=np.float32)
            data_model.add_cost_matrix(cost_matrix)
            try:
                data_model.add_transit_time_matrix(cost_matrix)
            except AttributeError:
                pass  # older cuOpt versions don't have this; time constraints use cost matrix

        # 2. Set vehicle start and end locations (vectorized)
        with cudf_memory_context("vehicle locations"):
            vehicle_locs = cudf.Series(list(range(n_technicians)), dtype=np.int32)
            data_model.set_vehicle_locations(vehicle_locs, vehicle_locs)

        # 3. Set drop return trips
        drop_return_flags = [tech.drop_return_trip for tech in problem.technicians]
        if any(drop_return_flags):  # Only set if any technician has drop_return_trip=True
            with cudf_memory_context("drop return trips"):
                data_model.set_drop_return_trips(cudf.Series(drop_return_flags, dtype=bool))
            print(f"   🚗 Drop return trips configured: {sum(drop_return_flags)} technicians")

        # 4. Set order locations (vectorized)
        with cudf_memory_context("order locations"):
            order_locs = cudf.Series(list(range(n_technicians, n_locations)), dtype=np.int32)
            data_model.set_order_locations(order_locs)

        # 5. Set order time windows (vectorized)
        with cudf_memory_context("order time windows"):
            earliest_times = np.array([wo.time_window.earliest if wo.time_window else 0 for wo in problem.work_orders], dtype=np.int32)
            latest_times = np.array([wo.time_window.latest if wo.time_window else 1440 for wo in problem.work_orders], dtype=np.int32)

            data_model.set_order_time_windows(
                cudf.Series(earliest_times, dtype=np.int32),
                cudf.Series(latest_times, dtype=np.int32)
            )

        # 6. Set order service times (vectorized)
        with cudf_memory_context("service times"):
            service_times = np.array([wo.service_time for wo in problem.work_orders], dtype=np.int32)
            data_model.set_order_service_times(cudf.Series(service_times))

        # 7. Set vehicle time windows (vectorized)
        with cudf_memory_context("vehicle time windows"):
            veh_earliest = np.array([tech.work_shift.earliest for tech in problem.technicians], dtype=np.int32)
            veh_latest = np.array([tech.work_shift.latest for tech in problem.technicians], dtype=np.int32)
            data_model.set_vehicle_time_windows(cudf.Series(veh_earliest, dtype=np.int32), cudf.Series(veh_latest, dtype=np.int32))

        # 8. CONDITIONAL: Skip breaks for tiny problems (major speedup)
        skip_breaks_threshold = self.cuopt_config.get('skip_breaks_threshold', 10)
        if problem_size > skip_breaks_threshold:
            with cudf_memory_context("break configuration"):
                for i, tech in enumerate(problem.technicians):
                    data_model.add_vehicle_break(
                        vehicle_id=i,
                        earliest=int(tech.break_window.earliest),
                        latest=int(tech.break_window.latest),
                        duration=int(tech.break_duration),
                        locations=cudf.Series([], dtype='int32')
                    )
        else:
            if not self.concurrent_mode:
                print("   ⚡⚡ Skipping breaks (ultra-performance mode)")

        # 9. Set capacity dimensions (daily limit + optional skill matching)
        enforce_skills = bool(self.config.get('enforce_skill_constraints', False))
        self._set_capacity_dimensions(data_model, problem.technicians, problem.work_orders, enforce_skills)

        # 10. Order prizes — higher-priority orders rewarded more (API availability varies by version)
        _PRIORITY_PRIZES = {'emergency': 1000.0, 'critical': 500.0, 'high': 200.0, 'medium': 100.0, 'low': 50.0}
        try:
            prizes = np.array([
                _PRIORITY_PRIZES.get(str(wo.priority).split('.')[-1].lower(), 100.0)
                for wo in problem.work_orders
            ], dtype=np.float32)
            data_model.set_order_prizes(cudf.Series(prizes))
            print(f"   🏆 Order prizes set (emergency=1000 → low=50)")
        except AttributeError:
            logger.debug("set_order_prizes not available in this cuOpt version — skipping")

        # 11. Vehicle fixed costs (optional, from settings config)
        vehicle_fixed_cost = float(self.config.get('vehicle_fixed_cost', 0))
        if vehicle_fixed_cost > 0:
            try:
                with cudf_memory_context("vehicle fixed costs"):
                    fixed_costs = np.full(n_technicians, vehicle_fixed_cost, dtype=np.float32)
                    data_model.set_vehicle_fixed_costs(cudf.Series(fixed_costs))
                print(f"   💰 Vehicle fixed cost: {vehicle_fixed_cost} per technician deployed")
            except AttributeError:
                logger.warning("set_vehicle_fixed_costs not available in this cuOpt version — skipping")

        # 12. Balance workload — cap total route time per vehicle (travel + service + wait)
        max_route_hours = self.config.get('max_route_hours', None)
        if max_route_hours:
            cap = float(max_route_hours) * 60.0  # convert hours → minutes
            try:
                with cudf_memory_context("vehicle max times"):
                    max_times = np.full(n_technicians, cap, dtype=np.float32)
                    data_model.set_vehicle_max_times(cudf.Series(max_times))
                print(f"   ⏱ Vehicle max time: {max_route_hours}h ({cap:.0f} min) per technician")
            except Exception as e:
                logger.warning(f"set_vehicle_max_times failed ({type(e).__name__}: {e}) — using min_vehicles fallback")
                # Fallback: request all vehicles so solver distributes work across all technicians
                try:
                    data_model.set_min_vehicles(n_technicians)
                    print(f"   ⏱ Balance workload fallback: set_min_vehicles({n_technicians})")
                except Exception as e2:
                    logger.warning(f"set_min_vehicles also failed: {e2}")

        return data_model

    def _set_capacity_dimensions(self, data_model: DataModel, technicians: List[Technician],
                                 work_orders: List[WorkOrder], enforce_skills: bool = False):
        """Set capacity dimensions: daily order limit + optional skill matching"""

        # Daily order limit
        with cudf_memory_context("daily order capacity"):
            max_orders = np.array([tech.max_daily_orders for tech in technicians], dtype=np.int32)
            order_demands = np.ones(len(work_orders), dtype=np.int32)
            data_model.add_capacity_dimension(
                "daily_orders",
                cudf.Series(order_demands),
                cudf.Series(max_orders)
            )

        if not enforce_skills:
            print("   ℹ️  Skill constraints disabled (enable in Settings)")
            return

        # Use add_order_vehicle_match — the purpose-built API for skill routing.
        # For each order, compute which technicians satisfy ALL required skills, then
        # tell cuOpt only those vehicles are eligible. No dimension cap, no hacks.
        try:
            constrained = 0
            for order_idx, wo in enumerate(work_orders):
                if not wo.required_skills:
                    continue
                required = set(wo.required_skills)
                eligible = [
                    t_idx for t_idx, tech in enumerate(technicians)
                    if required.issubset(set(tech.skills))
                ]
                if not eligible:
                    logger.warning(f"Order {wo.id} requires {required} — no technician qualifies, order will be unassigned")
                    continue
                data_model.add_order_vehicle_match(
                    order_idx,
                    cudf.Series(eligible, dtype=np.int32)
                )
                constrained += 1
            print(f"   🎯 Skill matching: {constrained} order(s) constrained via add_order_vehicle_match")
        except AttributeError:
            logger.warning("add_order_vehicle_match not available in this cuOpt version — skill constraints skipped")

    def _convert_solution(self, solution, problem: OptimizationProblem) -> OptimizationSolution:
        """Convert cuOpt solution to our solution format - optimized version with memory management"""
        # Get cuOpt status
        cuopt_status = solution.get_status()

        # Map cuOpt status to our status
        status_mapping = {
            0: SolutionStatus.SUCCESS,
            1: SolutionStatus.ERROR,
            2: SolutionStatus.TIMEOUT,
            3: SolutionStatus.ERROR  # EMPTY: solver ran but assigned no routes
        }

        status = status_mapping.get(cuopt_status, SolutionStatus.ERROR)

        if status != SolutionStatus.SUCCESS:
            try:
                err_msg = solution.get_error_message()
            except Exception as e:
                err_msg = f"(get_error_message unavailable: {e})"
            try:
                infeasible_indices = solution.get_infeasible_orders().to_arrow().to_pylist()
                infeasible_ids = [problem.work_orders[i].id for i in infeasible_indices if i < len(problem.work_orders)]
            except Exception as e:
                infeasible_ids = f"(get_infeasible_orders unavailable: {e})"
            logger.warning(f"cuOpt status {cuopt_status}: {err_msg} | infeasible: {infeasible_ids}")
            return OptimizationSolution(
                status=status,
                unassigned_orders=[wo.id for wo in problem.work_orders],
                objective_value=0.0
            )

        # Get route data with memory management
        with cudf_memory_context("route extraction"):
            route_df = solution.get_route()
            route_pandas = route_df.to_pandas() if len(route_df) > 0 else None

        # Build technician routes (optimized)
        routes = self._build_technician_routes(route_pandas, problem)

        # Find unassigned orders
        assigned_order_ids = set()
        for route in routes:
            for assignment in route.assignments:
                assigned_order_ids.add(assignment.work_order_id)

        unassigned_orders = [wo.id for wo in problem.work_orders if wo.id not in assigned_order_ids]

        # Get objective value
        try:
            objective_value = solution.get_total_objective()
        except:
            objective_value = 0.0

        # Create solution
        optimization_solution = OptimizationSolution(
            status=status,
            routes=routes,
            unassigned_orders=unassigned_orders,
            objective_value=objective_value
        )

        # Calculate summary statistics
        optimization_solution.calculate_summary_stats()

        return optimization_solution

    def _build_technician_routes(self, route_df, problem: OptimizationProblem) -> List[TechnicianRoute]:
        """Build technician routes from cuOpt route dataframe - optimized version"""
        routes = []
        n_technicians = len(problem.technicians)

        if route_df is None or len(route_df) == 0:
            # No routes found - create empty routes
            for tech in problem.technicians:
                routes.append(TechnicianRoute(technician_id=tech.id))
            return routes

        # Group by technician (truck_id) - optimized
        for tech_idx in range(n_technicians):
            tech_routes = route_df[route_df['truck_id'] == tech_idx]

            if len(tech_routes) == 0:
                routes.append(TechnicianRoute(technician_id=problem.technicians[tech_idx].id))
                continue

            # Create route for this technician
            route = TechnicianRoute(technician_id=problem.technicians[tech_idx].id)

            # Process each stop in the route (optimized)
            tech_routes_sorted = tech_routes.sort_values('arrival_stamp')

            # Track previous location to look up travel time from the matrix
            prev_location_idx = tech_idx  # Technician depot is at row tech_idx

            for _, row in tech_routes_sorted.iterrows():
                location_idx = int(row['location'])
                row_type = row.get('type', 'Unknown')

                # Skip depot locations and breaks
                if location_idx < n_technicians or row_type in ['Depot', 'Break']:
                    continue

                # This should be a work order location
                work_order_idx = location_idx - n_technicians

                if 0 <= work_order_idx < len(problem.work_orders):
                    wo = problem.work_orders[work_order_idx]

                    # Look up actual travel time from the distance matrix
                    travel_time = 0
                    durations = problem.distance_matrix.durations
                    if (prev_location_idx < len(durations) and
                            location_idx < len(durations[0])):
                        travel_time = int(durations[prev_location_idx][location_idx])
                    prev_location_idx = location_idx

                    assignment = Assignment(
                        technician_id=problem.technicians[tech_idx].id,
                        work_order_id=wo.id,
                        arrival_time=int(row['arrival_stamp']),
                        start_time=int(row['arrival_stamp']),
                        finish_time=int(row['arrival_stamp']) + wo.service_time,
                        travel_time_to=travel_time,
                        sequence_order=len(route.assignments) + 1
                    )

                    route.add_assignment(assignment)

            # Calculate route totals
            route.calculate_totals()
            routes.append(route)

        return routes


# Global concurrent solver manager instance
_concurrent_solver_manager = None
_manager_lock = Lock()

def get_concurrent_solver_manager() -> ConcurrentSolverManager:
    """Get the global concurrent solver manager instance"""
    global _concurrent_solver_manager

    with _manager_lock:
        if _concurrent_solver_manager is None:
            concurrent_config = get_concurrent_solver_config()
            if concurrent_config['enabled']:
                _concurrent_solver_manager = ConcurrentSolverManager()
            else:
                raise RuntimeError("Concurrent execution is not enabled")

    return _concurrent_solver_manager


# Convenience functions

def is_cuopt_available() -> bool:
    """Check if cuOpt is available and working"""
    return cuopt_available


def get_cuopt_status() -> Dict[str, Any]:
    """Get detailed cuOpt status information"""
    status = {
        'available': cuopt_available,
        'routing_module': cuopt_available,
        'error': None,
        'concurrent_execution': False,
        'memory_management': False
    }

    if cuopt_available:
        try:
            # Test basic functionality
            test_dm = DataModel(2, 1, 1)
            status['basic_functionality'] = True

            # Check memory management capability
            try:
                memory_info = get_gpu_memory_info()
                status['memory_management'] = memory_info['gpu_total_mb'] > 0
                status['current_memory_mb'] = memory_info['gpu_used_mb']
                status['total_memory_mb'] = memory_info['gpu_total_mb']
            except Exception as e:
                status['memory_management'] = False
                status['memory_error'] = str(e)

            # Check concurrent execution capability
            concurrent_config = get_concurrent_solver_config()
            status['concurrent_execution'] = concurrent_config['enabled']
            status['max_concurrent_instances'] = concurrent_config['max_concurrent_instances']
            status['solver_threads'] = concurrent_config['max_concurrent_solvers']
            status['cuda_streams'] = concurrent_config['cuda_streams']

        except Exception as e:
            status['basic_functionality'] = False
            status['error'] = str(e)
    else:
        status['basic_functionality'] = False
        status['error'] = "cuOpt not available"

    return status


def solve_optimization_problem(technicians: List[Technician],
                             work_orders: List[WorkOrder],
                             config: Optional[Dict[str, Any]] = None) -> OptimizationSolution:
    """Convenience function to solve optimization problem with memory management"""
    problem = OptimizationProblem(
        technicians=technicians,
        work_orders=work_orders,
        config=config
    )

    solver = TechnicianWorkOrderSolver(config)
    return solver.solve(problem)


def solve_optimization_problems_concurrent(problems: List[OptimizationProblem],
                                         configs: Optional[List[Dict[str, Any]]] = None,
                                         timeout: float = None) -> List[OptimizationSolution]:
    """Solve multiple optimization problems concurrently using CUDA streams with memory management"""
    try:
        manager = get_concurrent_solver_manager()
        return manager.solve_batch(problems, configs, timeout)
    except RuntimeError:
        # Fallback to sequential processing
        logger.warning("Concurrent execution not available, falling back to sequential processing")
        solutions = []
        for i, problem in enumerate(problems):
            config = configs[i] if configs and i < len(configs) else None
            solver = TechnicianWorkOrderSolver(config)
            solution = solver.solve(problem)
            solutions.append(solution)
        return solutions


def test_solver():
    """Test solver with simple sample data and memory monitoring"""
    from core.models import Technician, WorkOrder, Location, TimeWindow, Priority, WorkOrderType

    print("=== CREATING SIMPLE TEST CASE ===")

    technicians = [
        Technician(
            id="TECH001",
            name="John Smith",
            start_location=Location(3.1073, 101.6067, "PJ Centre"),
            work_shift=TimeWindow(480, 1020),  # 8 AM - 5 PM
            break_window=TimeWindow(720, 780), # 12 PM - 1 PM
            break_duration=60,
            skills={"electrical"},
            max_daily_orders=5,
            max_travel_time=180
        )
    ]

    work_orders = [
        WorkOrder(
            id="WO001",
            location=Location(3.1319, 101.6292, "SS2 PJ"),
            priority=Priority.MEDIUM,
            work_type=WorkOrderType.MAINTENANCE,
            required_skills={"electrical"},
            service_time=60,
        )
    ]

    try:
        print("=== STARTING SOLVER TEST WITH MEMORY MONITORING ===")

        # Get initial memory state
        initial_memory = get_gpu_memory_info()
        print(f"Initial GPU memory: {initial_memory['gpu_used_mb']:.1f}MB used")

        solution = solve_optimization_problem(technicians, work_orders)

        # Get final memory state
        final_memory = get_gpu_memory_info()
        print(f"Final GPU memory: {final_memory['gpu_used_mb']:.1f}MB used")
        print(f"Memory change: {final_memory['gpu_used_mb'] - initial_memory['gpu_used_mb']:.1f}MB")

        print(f"\n=== OPTIMIZATION RESULTS ===")
        print(f"Status: {solution.status.value}")
        print(f"Technicians used: {solution.technicians_used}")
        print(f"Orders completed: {solution.orders_completed}")
        print(f"Solve time: {solution.solve_time:.3f}s")

        # Print detailed results
        if solution.routes:
            for route in solution.routes:
                print(f"\n{route.technician_id}:")
                if route.assignments:
                    for assignment in route.assignments:
                        print(f"  ✅ {assignment.work_order_id}")
                        print(f"     Arrival: {assignment.arrival_time} min")
                        print(f"     Travel time: {assignment.travel_time_to} min")
                else:
                    print(f"  ❌ No assignments")

        if solution.unassigned_orders:
            print(f"\n❌ Unassigned orders: {solution.unassigned_orders}")

        success = (solution.status.value != "error") or (solution.orders_completed > 0)
        print(f"\n🎯 Test result: {'✅ PASS' if success else '❌ FAIL'}")
        return success

    except Exception as e:
        print(f"❌ Solver test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_concurrent_solver():
    """Test concurrent solver with multiple problems and memory monitoring"""
    from core.models import Technician, WorkOrder, Location, TimeWindow, Priority, WorkOrderType

    print("=== TESTING CONCURRENT SOLVER WITH MEMORY MONITORING ===")

    # Create multiple test problems
    problems = []
    for i in range(3):
        technicians = [
            Technician(
                id=f"TECH{i:03d}",
                name=f"Technician {i}",
                start_location=Location(3.1073 + i*0.01, 101.6067 + i*0.01, f"Location {i}"),
                work_shift=TimeWindow(480, 1020),
                break_window=TimeWindow(720, 780),
                break_duration=60,
                skills={"electrical", "maintenance"},
                max_daily_orders=5,
                max_travel_time=180
            )
        ]

        work_orders = [
            WorkOrder(
                id=f"WO{i:03d}",
                location=Location(3.1319 + i*0.01, 101.6292 + i*0.01, f"Work Location {i}"),
                priority=Priority.MEDIUM,
                work_type=WorkOrderType.MAINTENANCE,
                required_skills={"electrical"},
                service_time=60,
            )
        ]

        problem = OptimizationProblem(technicians=technicians, work_orders=work_orders)
        problems.append(problem)

    try:
        print(f"=== STARTING CONCURRENT SOLVER TEST WITH {len(problems)} PROBLEMS ===")

        # Get initial memory state
        initial_memory = get_gpu_memory_info()
        print(f"Initial GPU memory: {initial_memory['gpu_used_mb']:.1f}MB used")

        start_time = time.time()

        solutions = solve_optimization_problems_concurrent(problems, timeout=60.0)

        total_time = time.time() - start_time

        # Get final memory state
        final_memory = get_gpu_memory_info()
        print(f"Final GPU memory: {final_memory['gpu_used_mb']:.1f}MB used")
        print(f"Memory change: {final_memory['gpu_used_mb'] - initial_memory['gpu_used_mb']:.1f}MB")

        print(f"\n=== CONCURRENT OPTIMIZATION RESULTS ===")
        print(f"Total problems: {len(problems)}")
        print(f"Total time: {total_time:.3f}s")
        print(f"Average time per problem: {total_time/len(problems):.3f}s")

        success_count = 0
        for i, solution in enumerate(solutions):
            status = solution.status.value
            orders_completed = solution.orders_completed
            if status != "error" and orders_completed > 0:
                success_count += 1
            print(f"Problem {i}: Status={status}, Orders={orders_completed}, Time={solution.solve_time:.3f}s")

        success_rate = success_count / len(problems) * 100
        print(f"\nSuccess rate: {success_rate:.1f}% ({success_count}/{len(problems)})")

        # Get manager statistics if available
        try:
            manager = get_concurrent_solver_manager()
            stats = manager.get_statistics()
            print(f"\nManager Statistics:")
            print(f"  Max concurrent instances: {stats['max_concurrent_instances']}")
            print(f"  CUDA streams: {stats['cuda_streams']}")
            print(f"  Total requests: {stats['total_requests']}")
            print(f"  Completed: {stats['completed_requests']}")
            print(f"  Failed: {stats['failed_requests']}")
            print(f"  Success rate: {stats['success_rate']:.1f}%")
            print(f"  Average processing time: {stats['average_processing_time']:.3f}s")

            # Memory statistics
            memory_stats = stats.get('memory_stats', {})
            print(f"  Peak GPU usage: {memory_stats.get('peak_gpu_usage_mb', 0):.1f}MB")
            print(f"  Average GPU usage: {memory_stats.get('average_gpu_usage_mb', 0):.1f}MB")
            print(f"  Memory cleanups: {memory_stats.get('memory_cleanups', 0)}")
            print(f"  Memory warnings: {memory_stats.get('memory_warnings', 0)}")
        except:
            pass

        overall_success = success_rate >= 80  # 80% success rate threshold
        print(f"\n🎯 Concurrent test result: {'✅ PASS' if overall_success else '❌ FAIL'}")
        return overall_success

    except Exception as e:
        print(f"❌ Concurrent solver test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Testing solver with GPU memory management...")

    # Test basic solver
    basic_success = test_solver()

    # Test concurrent solver if available
    concurrent_config = get_concurrent_solver_config()
    if concurrent_config['enabled']:
        print("\n" + "="*50)
        concurrent_success = test_concurrent_solver()

        if basic_success and concurrent_success:
            print("\n🎉 All tests passed!")
        else:
            print("\n❌ Some tests failed")
    else:
        print("\n⚠️ Concurrent execution disabled, skipping concurrent tests")
        if basic_success:
            print("\n🎉 Basic tests passed!")
        else:
            print("\n❌ Basic tests failed")