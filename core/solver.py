"""
cuOpt-based solver for technician-workorder optimization
ULTRA HIGH PERFORMANCE VERSION WITH CUDA STREAMS
Following the cuOpt service team routing notebook patterns with aggressive optimizations
and concurrent execution using CUDA streams
"""

import logging
import time
import cudf
import numpy as np
import asyncio
import threading
from typing import List, Dict, Any, Optional, Set, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from queue import Queue, PriorityQueue, Empty
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

from config import CONFIG, get_optimal_time_limit, should_skip_complex_constraints, get_concurrent_solver_config
from core.models import (
    OptimizationProblem, OptimizationSolution, TechnicianRoute, Assignment,
    Technician, WorkOrder, Priority, SolutionStatus, DistanceMatrix
)
from core.osrm import calculate_matrix_for_problem

logger = logging.getLogger(__name__)


class SolverError(Exception):
    """Custom exception for solver-related errors"""
    pass


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
    """Result wrapper for solver responses"""
    request_id: str
    solution: OptimizationSolution
    processing_time: float
    solver_id: int
    success: bool = True
    error: Optional[str] = None


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


class ConcurrentSolverManager:
    """Manages multiple concurrent cuOpt solver instances with CUDA streams"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize concurrent solver manager"""
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

        self.cuda_streams = CUDAStreamManager(self.num_cuda_streams)

        # Request queue and processing
        self.request_queue = PriorityQueue()
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

        # Monitoring and statistics
        self.stats = {
            'total_requests': 0,
            'completed_requests': 0,
            'failed_requests': 0,
            'active_solvers': 0,
            'average_processing_time': 0.0,
            'start_time': time.time(),
            'solver_usage': {i: 0 for i in range(self.max_solvers)}  # Track usage per solver
        }
        self.stats_lock = Lock()

        # Solver instances (one per thread/stream)
        self.solver_instances = {}
        self.solver_lock = Lock()

        logger.info(f"Initialized ConcurrentSolverManager with {self.max_instances} concurrent instances")
        print("✅ ConcurrentSolverManager initialized")
        print(f"   🚀 Max concurrent instances: {self.max_instances}")
        print(f"   🧵 Solver threads: {self.max_solvers}")
        print(f"   🎯 CUDA streams: {self.num_cuda_streams}")
        print(f"   💾 Memory per instance: {self.concurrent_config['memory_pool_per_instance']}MB")

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

        # Add to queue
        self.request_queue.put(request)

        # Submit to executor
        future = self.executor.submit(self._process_request, request)
        self.active_requests[request_id] = future

        with self.stats_lock:
            self.stats['total_requests'] += 1

        logger.info(f"Submitted request {request_id} with priority {priority}")
        return request_id

    def _process_request(self, request: SolverRequest) -> SolverResult:
        """Process a single optimization request"""
        start_time = time.time()

        # Get assigned solver ID using round-robin
        solver_id = self._get_next_solver_id()

        try:
            self._mark_solver_busy(solver_id)

            with self.stats_lock:
                self.stats['active_solvers'] += 1

            print(f"🚀 Processing request {request.request_id[:8]} on solver {solver_id}")

            # Get CUDA stream for this request
            with self.cuda_streams.get_stream() as (stream_id, stream):
                print(f"   🎯 Using CUDA stream {stream_id}")

                # Get solver instance
                solver = self.get_solver_instance(solver_id)

                # Set CUDA stream context if available
                if stream is not None:
                    try:
                        import cupy as cp
                        with stream:
                            solution = solver.solve(request.problem)
                    except Exception:
                        # Fallback without stream context
                        solution = solver.solve(request.problem)
                else:
                    solution = solver.solve(request.problem)

                processing_time = time.time() - start_time

                result = SolverResult(
                    request_id=request.request_id,
                    solution=solution,
                    processing_time=processing_time,
                    solver_id=solver_id,
                    success=True
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

                print(f"✅ Completed request {request.request_id[:8]} in {processing_time:.3f}s on solver {solver_id}")
                return result

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)

            result = SolverResult(
                request_id=request.request_id,
                solution=OptimizationSolution(
                    status=SolutionStatus.ERROR,
                    unassigned_orders=[wo.id for wo in request.problem.work_orders]
                ),
                processing_time=processing_time,
                solver_id=solver_id,
                success=False,
                error=error_msg
            )

            self.results[request.request_id] = result

            with self.stats_lock:
                self.stats['failed_requests'] += 1
                self.stats['active_solvers'] -= 1

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
        """Get solver statistics"""
        with self.stats_lock:
            stats = self.stats.copy()

        with self.solver_assignment_lock:
            busy_solvers = self.busy_solvers.copy()

        stats['uptime'] = time.time() - stats['start_time']
        stats['success_rate'] = (
            stats['completed_requests'] / max(1, stats['total_requests']) * 100
        )
        stats['queue_size'] = self.request_queue.qsize()
        stats['active_requests'] = len(self.active_requests)
        stats['busy_solvers'] = list(busy_solvers)
        stats['available_solvers'] = [i for i in range(self.max_solvers) if i not in busy_solvers]
        stats['max_concurrent_instances'] = self.max_instances
        stats['cuda_streams'] = self.num_cuda_streams

        return stats

    def shutdown(self):
        """Shutdown the concurrent solver manager"""
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

        print("✅ ConcurrentSolverManager shutdown complete")


class TechnicianWorkOrderSolver:
    """
    Main solver class that integrates OSRM and cuOpt for technician-workorder optimization
    ULTRA HIGH PERFORMANCE VERSION WITH CUDA STREAMS SUPPORT
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
            print(f"✅ TechnicianWorkOrderSolver {solver_id} initialized for concurrent execution")
        else:
            print("✅ TechnicianWorkOrderSolver initialized with cuOpt")

    def solve(self, problem: OptimizationProblem) -> OptimizationSolution:
        """Solve the optimization problem with maximum performance"""
        start_time = time.time()

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
            if problem.distance_matrix is None:
                print(f"🌐 {solver_prefix} Calculating travel times via OSRM...")
                matrix_start = time.time()
                problem.distance_matrix = calculate_matrix_for_problem(
                    problem.technicians, problem.work_orders
                )
                matrix_time = time.time() - matrix_start
                print(f"✅ {solver_prefix} Distance matrix calculated in {matrix_time:.3f}s")

            # Step 2: Build cuOpt DataModel with performance optimizations
            print(f"🏗️ {solver_prefix} Building cuOpt data model...")
            model_start = time.time()
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
            solution = Solve(data_model, solver_settings)
            solve_time = time.time() - solve_start
            print(f"✅ {solver_prefix} cuOpt solved in {solve_time:.3f}s")

            # Step 5: Check solver status
            solver_status = solution.get_status()
            if solver_status == 0:
                print(f"📊 {solver_prefix} SUCCESS: Objective value = {solution.get_total_objective():.2f}")
            else:
                print(f"📊 {solver_prefix} Status {solver_status}: {solution.get_message()}")

            # Step 6: Convert results to our format
            conversion_start = time.time()
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
            print(f"❌ {solver_prefix} Solver error: {e}")
            return OptimizationSolution(
                status=SolutionStatus.ERROR,
                unassigned_orders=[wo.id for wo in problem.work_orders],
                solve_time=time.time() - start_time
            )

    def _configure_solver(self, problem_size: int) -> SolverSettings:
        """Configure solver with ultra-aggressive performance settings"""
        solver_settings = SolverSettings()

        # Use concurrent time limits if in concurrent mode
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
        Build cuOpt DataModel with ultra performance optimizations
        """
        n_technicians = len(problem.technicians)
        n_work_orders = len(problem.work_orders)
        n_locations = n_technicians + n_work_orders
        problem_size = n_technicians + n_work_orders

        # Create data model
        data_model = DataModel(n_locations, n_technicians, n_work_orders)

        # 1. Set cost matrix (pre-convert to optimal format)
        cost_matrix = cudf.DataFrame(problem.distance_matrix.durations, dtype=np.float32)
        data_model.add_cost_matrix(cost_matrix)

        # 2. Set vehicle start and end locations (vectorized)
        vehicle_locs = cudf.Series(list(range(n_technicians)), dtype=np.int32)
        data_model.set_vehicle_locations(vehicle_locs, vehicle_locs)

        # 3. Set order locations (vectorized)
        order_locs = cudf.Series(list(range(n_technicians, n_locations)), dtype=np.int32)
        data_model.set_order_locations(order_locs)

        # 4. Set order time windows (vectorized)
        earliest_times = np.array([wo.time_window.earliest if wo.time_window else 0 for wo in problem.work_orders], dtype=np.int32)
        latest_times = np.array([wo.time_window.latest if wo.time_window else 1440 for wo in problem.work_orders], dtype=np.int32)

        data_model.set_order_time_windows(
            cudf.Series(earliest_times),
            cudf.Series(latest_times)
        )

        # 5. Set order service times (vectorized)
        service_times = np.array([wo.service_time for wo in problem.work_orders], dtype=np.int32)
        data_model.set_order_service_times(cudf.Series(service_times))

        # 6. Set vehicle time windows (vectorized)
        veh_earliest = np.array([tech.work_shift.earliest for tech in problem.technicians], dtype=np.int32)
        veh_latest = np.array([tech.work_shift.latest for tech in problem.technicians], dtype=np.int32)
        data_model.set_vehicle_time_windows(cudf.Series(veh_earliest), cudf.Series(veh_latest))

        # 7. CONDITIONAL: Skip breaks for tiny problems (major speedup)
        skip_breaks_threshold = self.cuopt_config.get('skip_breaks_threshold', 10)
        if problem_size > skip_breaks_threshold:
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

        # 8. Set capacity dimensions with performance optimizations
        self._set_capacity_dimensions(data_model, problem.technicians, problem.work_orders, problem_size)

        return data_model

    def _set_capacity_dimensions(self, data_model: DataModel, technicians: List[Technician],
                                 work_orders: List[WorkOrder], problem_size: int):
        """Set capacity dimensions with ultra performance optimizations"""

        # Always set daily order limits (essential constraint) - vectorized
        max_orders = np.array([tech.max_daily_orders for tech in technicians], dtype=np.int32)
        order_demands = np.ones(len(work_orders), dtype=np.int32)

        data_model.add_capacity_dimension(
            "daily_orders",
            cudf.Series(order_demands),
            cudf.Series(max_orders)
        )

        # For tiny problems, use minimal constraints only (major speedup)
        minimal_threshold = self.cuopt_config.get('minimal_constraints_threshold', 15)
        if problem_size <= minimal_threshold:
            if not self.concurrent_mode:
                print("   ⚡⚡ Minimal constraints only (ultra-performance mode)")
            return

        # For larger problems, check if we should skip complex constraints
        if should_skip_complex_constraints(problem_size):
            if not self.concurrent_mode:
                print("   ⚡ Skipping skill constraints (performance mode)")
            return

        # For larger problems, set simplified skill constraints
        # Get all unique skills
        all_skills = set()
        for tech in technicians:
            all_skills.update(tech.skills)
        for wo in work_orders:
            all_skills.update(wo.required_skills)

        if not all_skills:
            return

        # Find the most critical skill (creates biggest constraint)
        critical_skill = None
        max_constraint_value = 0

        for skill in all_skills:
            techs_with_skill = sum(1 for tech in technicians if skill in tech.skills)
            orders_needing_skill = sum(1 for wo in work_orders if skill in wo.required_skills)

            if techs_with_skill > 0 and orders_needing_skill > 0:
                constraint_value = orders_needing_skill / techs_with_skill
                if constraint_value > max_constraint_value:
                    max_constraint_value = constraint_value
                    critical_skill = skill

        if not critical_skill:
            return

        # Set up capacity dimension for the critical skill only (vectorized)
        vehicle_capacities = np.array([100 if critical_skill in tech.skills else 0 for tech in technicians], dtype=np.int32)
        order_demands = np.array([1 if critical_skill in wo.required_skills else 0 for wo in work_orders], dtype=np.int32)

        data_model.add_capacity_dimension(
            f"skill_{critical_skill}",
            cudf.Series(order_demands),
            cudf.Series(vehicle_capacities)
        )

    def _convert_solution(self, solution, problem: OptimizationProblem) -> OptimizationSolution:
        """Convert cuOpt solution to our solution format - optimized version"""
        # Get cuOpt status
        cuopt_status = solution.get_status()

        # Map cuOpt status to our status
        status_mapping = {
            0: SolutionStatus.SUCCESS,
            1: SolutionStatus.ERROR,
            2: SolutionStatus.TIMEOUT,
            3: SolutionStatus.INFEASIBLE
        }

        status = status_mapping.get(cuopt_status, SolutionStatus.ERROR)

        if status != SolutionStatus.SUCCESS:
            return OptimizationSolution(
                status=status,
                unassigned_orders=[wo.id for wo in problem.work_orders],
                objective_value=0.0
            )

        # Get route data
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

                    # Simplified travel time calculation for performance
                    travel_time = 0
                    if len(route.assignments) > 0:
                        # Use simplified calculation
                        travel_time = 10  # Default assumption for now
                    else:
                        # Travel from technician start location
                        if (tech_idx < len(problem.distance_matrix.durations) and
                            location_idx < len(problem.distance_matrix.durations[0])):
                            travel_time = int(problem.distance_matrix.durations[tech_idx][location_idx])

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
        'concurrent_execution': False
    }

    if cuopt_available:
        try:
            # Test basic functionality
            test_dm = DataModel(2, 1, 1)
            status['basic_functionality'] = True

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
    """Convenience function to solve optimization problem"""
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
    """Solve multiple optimization problems concurrently using CUDA streams"""
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
    """Test solver with simple sample data"""
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
        print("=== STARTING SOLVER TEST ===")
        solution = solve_optimization_problem(technicians, work_orders)

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
    """Test concurrent solver with multiple problems"""
    from core.models import Technician, WorkOrder, Location, TimeWindow, Priority, WorkOrderType

    print("=== TESTING CONCURRENT SOLVER ===")

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
        start_time = time.time()

        solutions = solve_optimization_problems_concurrent(problems, timeout=60.0)

        total_time = time.time() - start_time
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
    print("Testing solver...")

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