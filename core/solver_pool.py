"""Concurrent solver pool: request queuing, CUDA stream assignment, and lifecycle."""
from __future__ import annotations

import copy
import logging
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional

from config import CONFIG, get_concurrent_solver_config
from core.cuda_streams import CUDAStreamManager
from core.gpu_memory import get_gpu_memory_info, gpu_memory_context
from core.models import OptimizationProblem, OptimizationSolution, SolutionStatus

logger = logging.getLogger(__name__)


@dataclass
class SolverRequest:
    """Request wrapper for solver queue"""
    request_id: str
    problem: OptimizationProblem
    config: Optional[Dict[str, Any]]
    priority: int = 1
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()

    def __lt__(self, other):
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


class ConcurrentSolverManager:
    """Manages multiple concurrent cuOpt solver instances with CUDA streams and memory management"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = copy.deepcopy(CONFIG)
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

        self.max_instances = self.concurrent_config['max_concurrent_instances']
        self.max_solvers = self.max_instances
        self.num_cuda_streams = self.max_instances

        self.memory_limit_per_instance = self.concurrent_config['memory_pool_per_instance'] / 1024  # MB → GB

        queue_timeout = self.concurrent_config.get('queue_timeout', 30.0)
        self.cuda_streams = CUDAStreamManager(self.num_cuda_streams, queue_timeout=queue_timeout)

        # Request tracking — capped at 500 entries (oldest evicted) to prevent unbounded growth
        self.results: OrderedDict = OrderedDict()
        self._results_max = 500
        self.active_requests = {}

        self.executor = ThreadPoolExecutor(
            max_workers=self.max_solvers,
            thread_name_prefix="cuopt_solver"
        )

        self.solver_counter = 0
        self.solver_assignment_lock = Lock()
        self.busy_solvers = set()

        self.stats = {
            'total_requests': 0,
            'completed_requests': 0,
            'failed_requests': 0,
            'active_solvers': 0,
            'average_processing_time': 0.0,
            'start_time': time.time(),
            'solver_usage': {i: 0 for i in range(self.max_solvers)},
            'memory_stats': {
                'peak_gpu_usage_mb': 0.0,
                'average_gpu_usage_mb': 0.0,
                'memory_cleanups': 0,
                'memory_warnings': 0
            }
        }
        self.stats_lock = Lock()

        self.solver_instances = {}
        self.solver_lock = Lock()

        logger.info(f"Initialized ConcurrentSolverManager with {self.max_instances} concurrent instances")
        logger.info("✅ ConcurrentSolverManager initialized with GPU memory management")
        logger.info(f"   🚀 Max concurrent instances: {self.max_instances}")
        logger.info(f"   🧵 Solver threads: {self.max_solvers}")
        logger.info(f"   🎯 CUDA streams: {self.num_cuda_streams}")
        logger.info(f"   💾 Memory per instance: {self.concurrent_config['memory_pool_per_instance']}MB")
        logger.info(f"   🧹 GPU memory cleanup: enabled")

    def _get_next_solver_id(self) -> int:
        """Get the next available solver ID using round-robin assignment"""
        with self.solver_assignment_lock:
            solver_id = self.solver_counter % self.max_solvers
            self.solver_counter += 1
            with self.stats_lock:
                self.stats['solver_usage'][solver_id] += 1
            return solver_id

    def _mark_solver_busy(self, solver_id: int):
        with self.solver_assignment_lock:
            self.busy_solvers.add(solver_id)

    def _mark_solver_free(self, solver_id: int):
        with self.solver_assignment_lock:
            self.busy_solvers.discard(solver_id)

    def get_solver_instance(self, solver_id: int):
        """Get or create a solver instance for the given solver ID"""
        with self.solver_lock:
            if solver_id not in self.solver_instances:
                # Lazy import breaks the circular dependency:
                # solver_pool → solver (TechnicianWorkOrderSolver)
                # solver → solver_pool (ConcurrentSolverManager)
                from core.solver import TechnicianWorkOrderSolver
                self.solver_instances[solver_id] = TechnicianWorkOrderSolver(
                    self.config,
                    solver_id=solver_id,
                    concurrent_mode=True
                )
            return self.solver_instances[solver_id]

    def _update_memory_stats(self, memory_info: Dict[str, float]):
        with self.stats_lock:
            gpu_usage = memory_info.get('gpu_used_mb', 0.0)
            if gpu_usage > self.stats['memory_stats']['peak_gpu_usage_mb']:
                self.stats['memory_stats']['peak_gpu_usage_mb'] = gpu_usage
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
        try:
            future = self.executor.submit(self._process_request, request)
        except RuntimeError as exc:
            raise RuntimeError(f"Solver pool is shut down, cannot accept new requests: {exc}") from exc
        self.active_requests[request_id] = future
        with self.stats_lock:
            self.stats['total_requests'] += 1
        logger.info(f"Submitted request {request_id} with priority {priority}")
        return request_id

    def _process_request(self, request: SolverRequest) -> SolverResult:
        """Process a single optimization request with comprehensive memory management"""
        start_time = time.time()
        solver_id = self._get_next_solver_id()

        try:
            self._mark_solver_busy(solver_id)
            with self.stats_lock:
                self.stats['active_solvers'] += 1

            logger.info(f"🚀 Processing request {request.request_id[:8]} on solver {solver_id}")
            initial_memory = get_gpu_memory_info()

            with gpu_memory_context(solver_id=solver_id, memory_limit_gb=self.memory_limit_per_instance):
                with self.cuda_streams.get_stream() as (stream_id, stream):
                    logger.info(f"   🎯 Using CUDA stream {stream_id}")

                    solver = self.get_solver_instance(solver_id)

                    # Apply per-request config overrides (safe: solver_id is exclusively busy)
                    saved_config = {}
                    if request.config:
                        for key, value in request.config.items():
                            saved_config[key] = solver.config.get(key, '__MISSING__')
                            solver.config[key] = value
                        logger.info(f"   ⚙️  Request config applied: {list(request.config.keys())}")

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

            final_memory = get_gpu_memory_info()
            processing_time = time.time() - start_time
            self._update_memory_stats(final_memory)

            result = SolverResult(
                request_id=request.request_id,
                solution=solution,
                processing_time=processing_time,
                solver_id=solver_id,
                success=True,
                memory_info=final_memory
            )

            self.results[request.request_id] = result
            if len(self.results) > self._results_max:
                self.results.popitem(last=False)

            with self.stats_lock:
                self.stats['completed_requests'] += 1
                self.stats['active_solvers'] -= 1
                total_completed = self.stats['completed_requests']
                self.stats['average_processing_time'] = (
                    (self.stats['average_processing_time'] * (total_completed - 1) + processing_time) / total_completed
                )
                self.stats['memory_stats']['memory_cleanups'] += 1

            logger.info(f"✅ Completed request {request.request_id[:8]} in {processing_time:.3f}s on solver {solver_id}")
            logger.info(f"   💾 GPU memory: {final_memory['gpu_used_mb']:.1f}MB used, {final_memory['gpu_usage_percent']:.1f}% utilization")
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)
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
            if len(self.results) > self._results_max:
                self.results.popitem(last=False)

            with self.stats_lock:
                self.stats['failed_requests'] += 1
                self.stats['active_solvers'] -= 1
                if "memory" in error_msg.lower():
                    self.stats['memory_stats']['memory_warnings'] += 1

            logger.exception(f"Request {request.request_id[:8]} failed: {error_msg}")
            return result

        finally:
            self._mark_solver_free(solver_id)
            if request.request_id in self.active_requests:
                del self.active_requests[request.request_id]

    def get_result(self, request_id: str, timeout: float = None) -> Optional[SolverResult]:
        """Get result for a specific request"""
        if request_id in self.results:
            return self.results[request_id]
        if request_id in self.active_requests:
            try:
                future = self.active_requests[request_id]
                return future.result(timeout=timeout)
            except Exception as e:
                logger.error(f"Failed to get result for request {request_id}: {e}")
                return None
        return None

    def wait_for_completion(self, request_ids: List[str], timeout: float = None) -> Dict[str, SolverResult]:
        """Wait for multiple requests to complete"""
        results = {}
        futures = {
            self.active_requests[req_id]: req_id
            for req_id in request_ids
            if req_id in self.active_requests
        }
        try:
            for future in as_completed(futures.keys(), timeout=timeout):
                req_id = futures[future]
                try:
                    results[req_id] = future.result()
                except Exception as e:
                    logger.error(f"Request {req_id} failed: {e}")
        except Exception as e:
            logger.error(f"Error waiting for completion: {e}")

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

        request_ids = []
        for i, (problem, config) in enumerate(zip(problems, configs)):
            request_ids.append(self.submit_request(problem, config, priority=i))

        logger.info(f"🚀 Submitted {len(request_ids)} problems for concurrent processing")

        results = self.wait_for_completion(request_ids, timeout)

        solutions = []
        for req_id in request_ids:
            if req_id in results:
                solutions.append(results[req_id].solution)
            else:
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

        current_memory = get_gpu_memory_info()
        stats['uptime'] = time.time() - stats['start_time']
        stats['success_rate'] = stats['completed_requests'] / max(1, stats['total_requests']) * 100
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
        logger.info("🔄 Shutting down ConcurrentSolverManager...")

        for request_id, future in list(self.active_requests.items()):
            try:
                future.result(timeout=5.0)
            except Exception:
                pass

        self.executor.shutdown(wait=True)
        self.cuda_streams.synchronize_all()

        try:
            with gpu_memory_context(solver_id="shutdown"):
                pass
        except Exception as e:
            logger.warning(f"Final memory cleanup warning: {e}")

        logger.info("✅ ConcurrentSolverManager shutdown complete")
