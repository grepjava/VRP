"""
Technician-workorder VRP solver backed by NVIDIA cuOpt.

Supports concurrent execution via a pool of solver instances, each pinned to a
dedicated CUDA stream. GPU memory is managed through an RMM pool allocator with
per-operation context managers to ensure prompt release between requests.
"""
from __future__ import annotations

import copy
import logging
import math
import time
import numpy as np
from threading import Lock
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# =============================================================================
# cuOpt import + GPU initialisation (RMM pool, CUDA streams)
# =============================================================================

cuopt_available = False
logger.info("🔍 Attempting to import cuOpt routing module...")

try:
    from cuopt.routing import DataModel, SolverSettings, Solve
    cuopt_available = True
    logger.info("✅ cuOpt routing imported successfully")
except ImportError as e:
    logger.error(f"❌ cuOpt import failed: {e}")
    logger.warning("⚠️ Solver will not be available")
    DataModel = None
    SolverSettings = None
    Solve = None


def initialize_gpu() -> None:
    """Initialize the RMM memory pool and log CUDA stream readiness.

    Must be called once at application startup (from the lifespan handler),
    not at import time, so test contexts can import this module without
    triggering a GPU pool allocation.
    """
    if not cuopt_available:
        return

    try:
        import rmm
        from config import get_config
        memory_config = get_config()['cuopt']['memory_management']
        rmm.reinitialize(
            pool_allocator=True,
            initial_pool_size=memory_config['initial_pool_size'],
            maximum_pool_size=memory_config['maximum_pool_size']
        )
        logger.info("✅ GPU memory pool initialized")
    except ImportError:
        logger.warning("⚠️ rmm not available, using default GPU memory management")
    except Exception as e:
        logger.warning(f"⚠️ GPU memory pool initialization failed: {e}")

    try:
        import cupy as cp  # noqa: F401 — presence check only
        from config import get_config
        concurrent_config = get_config()['cuopt']['concurrent_execution']
        if concurrent_config['enabled']:
            logger.info(f"✅ CUDA streams ready ({concurrent_config['max_concurrent_instances']} instances)")
    except ImportError:
        logger.warning("⚠️ CuPy not available, CUDA streams will be limited")
    except Exception as e:
        logger.warning(f"⚠️ CUDA streams initialization failed: {e}")

try:
    import cudf
except ImportError:
    cudf = None

from config import CONFIG, get_optimal_time_limit, get_concurrent_solver_config
from core.models import (
    OptimizationProblem, OptimizationSolution, TechnicianRoute, Assignment,
    Technician, WorkOrder, Priority, SolutionStatus, DistanceMatrix
)
from core.osrm import calculate_matrix_for_problem

# Re-exported from sub-modules so main.py imports remain unchanged
from core.gpu_memory import (                          # noqa: F401
    SolverError, GPUMemoryError,
    gpu_memory_context, cudf_memory_context, get_gpu_memory_info,
)
from core.cuda_streams import CUDAStreamManager        # noqa: F401
from core.solver_pool import (                         # noqa: F401
    SolverRequest, SolverResult, ConcurrentSolverManager,
)


# =============================================================================
# VRP solver
# =============================================================================

class TechnicianWorkOrderSolver:
    """
    Main solver class that integrates OSRM and cuOpt for technician-workorder optimization.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 solver_id: int = 0, concurrent_mode: bool = False):
        self.solver_id = solver_id
        self.concurrent_mode = concurrent_mode

        self.config = copy.deepcopy(CONFIG)
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
            logger.info(f"✅ TechnicianWorkOrderSolver {solver_id} initialized for concurrent execution with memory management")
        else:
            logger.info("✅ TechnicianWorkOrderSolver initialized with cuOpt and memory management")

    def solve(self, problem: OptimizationProblem) -> OptimizationSolution:
        """Solve the optimization problem with maximum performance and memory management"""
        start_time = time.time()

        concurrent_config = get_concurrent_solver_config()
        memory_limit_gb = concurrent_config['memory_pool_per_instance'] / 1024

        with gpu_memory_context(solver_id=self.solver_id, memory_limit_gb=memory_limit_gb):
            try:
                issues = problem.validate()
                if issues:
                    logger.error(f"Problem validation failed: {issues}")
                    return OptimizationSolution(
                        status=SolutionStatus.ERROR,
                        unassigned_orders=[wo.id for wo in problem.work_orders]
                    )

                problem_size = len(problem.technicians) + len(problem.work_orders)
                solver_prefix = f"[Solver {self.solver_id}]" if self.concurrent_mode else ""
                logger.info(f"🔍 {solver_prefix} Problem: {len(problem.technicians)} techs, {len(problem.work_orders)} orders (total: {problem_size})")

                # Step 1: Calculate distance matrix via OSRM
                matrix_time = 0.0
                if problem.distance_matrix is None:
                    logger.info(f"🌐 {solver_prefix} Calculating travel times via OSRM...")
                    matrix_start = time.time()
                    problem.distance_matrix = calculate_matrix_for_problem(
                        problem.technicians, problem.work_orders
                    )
                    matrix_time = time.time() - matrix_start
                    logger.info(f"✅ {solver_prefix} Distance matrix calculated in {matrix_time:.3f}s")

                # Step 2: Build cuOpt DataModel
                logger.info(f"🏗️ {solver_prefix} Building cuOpt data model...")
                model_start = time.time()
                with cudf_memory_context("data model building"):
                    data_model = self._build_cuopt_model(problem)
                model_time = time.time() - model_start
                logger.info(f"✅ {solver_prefix} cuOpt data model built in {model_time:.3f}s")

                # Step 3: Configure solver
                logger.info(f"⚙️ {solver_prefix} Configuring high-performance solver...")
                solver_settings = self._configure_solver(problem_size)

                # Step 4: Verify GPU and run solver
                if not self.concurrent_mode:
                    self._verify_gpu_status()

                logger.info(f"🚀 {solver_prefix} Running cuOpt optimization...")
                solve_start = time.time()
                with cudf_memory_context("cuOpt solving"):
                    solution = Solve(data_model, solver_settings)
                solve_time = time.time() - solve_start
                logger.info(f"✅ {solver_prefix} cuOpt solved in {solve_time:.3f}s")

                # Step 5: Check solver status
                solver_status = solution.get_status()
                if solver_status == 0:
                    logger.info(f"📊 {solver_prefix} SUCCESS: Objective value = {solution.get_total_objective():.2f}")
                else:
                    try:
                        err_msg = solution.get_error_message()
                    except Exception:
                        err_msg = "unknown"
                    logger.info(f"📊 {solver_prefix} Status {solver_status}: {err_msg}")

                # Step 6: Convert results
                conversion_start = time.time()
                with cudf_memory_context("solution conversion"):
                    optimization_solution = self._convert_solution(solution, problem)
                conversion_time = time.time() - conversion_start
                optimization_solution.solve_time = time.time() - start_time

                total_time = optimization_solution.solve_time
                logger.info(f"🏁 {solver_prefix} PERFORMANCE SUMMARY:")
                logger.info(f"   OSRM Matrix: {matrix_time:.3f}s ({100*matrix_time/total_time:.1f}%)")
                logger.info(f"   Model Build: {model_time:.3f}s ({100*model_time/total_time:.1f}%)")
                logger.info(f"   cuOpt Solve: {solve_time:.3f}s ({100*solve_time/total_time:.1f}%)")
                logger.info(f"   Conversion:  {conversion_time:.3f}s ({100*conversion_time/total_time:.1f}%)")
                logger.info(f"   TOTAL TIME:  {total_time:.3f}s")
                logger.info(f"   Status: {optimization_solution.status.value}, Orders: {optimization_solution.orders_completed}")

                return optimization_solution

            except Exception as e:
                solver_prefix = f"[Solver {self.solver_id}]" if self.concurrent_mode else ""
                logger.error(f"❌ {solver_prefix} Solver error: {e}")
                return OptimizationSolution(
                    status=SolutionStatus.ERROR,
                    unassigned_orders=[wo.id for wo in problem.work_orders],
                    solve_time=time.time() - start_time
                )

    def _configure_solver(self, problem_size: int) -> SolverSettings:
        solver_settings = SolverSettings()
        time_limit_override = self.config.get('time_limit_override', None)
        if time_limit_override:
            time_limit = float(time_limit_override)
        else:
            time_limit = get_optimal_time_limit(problem_size, self.concurrent_mode)
        solver_settings.set_time_limit(time_limit)
        solver_settings.set_verbose_mode(False)
        solver_settings.set_error_logging_mode(False)
        mode_str = "CONCURRENT" if self.concurrent_mode else "ULTRA-fast"
        logger.info(f"   ⚡⚡ {mode_str} mode: {time_limit}s limit for {problem_size} locations")
        return solver_settings

    def _verify_gpu_status(self):
        try:
            import cupy as cp
            device_id = cp.cuda.runtime.getDevice()
            device_props = cp.cuda.runtime.getDeviceProperties(device_id)
            meminfo = cp.cuda.runtime.memGetInfo()
            logger.info(f"   🎯 GPU {device_id}: {device_props['name'].decode()}")
            logger.info(f"   🎯 Memory: {meminfo[0]//1024//1024}MB free / {meminfo[1]//1024//1024}MB total")
            logger.info(f"   🎯 CUDA Cores: {device_props['multiProcessorCount'] * 128}")
        except Exception as e:
            logger.warning(f"   ⚠️ GPU verification failed: {e}")

    def _build_cuopt_model(self, problem: OptimizationProblem) -> DataModel:
        """Build cuOpt DataModel with performance optimizations and memory management"""
        n_technicians = len(problem.technicians)
        n_work_orders = len(problem.work_orders)
        n_locations = n_technicians + n_work_orders
        problem_size = n_locations

        data_model = DataModel(n_locations, n_technicians, n_work_orders)

        # 1. Cost matrix + transit time matrix (same duration data, different purposes:
        #    cost drives objective, transit time drives time-window/max-time constraints)
        with cudf_memory_context("cost matrix creation"):
            # Convert to float32; replace nan/inf with large value so cuOpt treats them as infeasible.
            raw = np.array(problem.distance_matrix.durations, dtype=np.float32)
            np.nan_to_num(raw, nan=1e7, posinf=1e7, neginf=0.0, copy=False)
            cost_matrix = cudf.DataFrame(raw)
            # cuDF can promote float NaN to cuDF NULL during DataFrame construction;
            # fillna is the safety net after the numpy-level nan_to_num above.
            cost_matrix = cost_matrix.fillna(1e7)
            data_model.add_cost_matrix(cost_matrix)
            try:
                data_model.add_transit_time_matrix(cost_matrix)
            except AttributeError:
                pass  # older cuOpt versions don't have this

        # 2. Vehicle start/end locations
        with cudf_memory_context("vehicle locations"):
            vehicle_locs = cudf.Series(list(range(n_technicians)), dtype=np.int32)
            data_model.set_vehicle_locations(vehicle_locs, vehicle_locs)

        # 3. Drop return trips
        drop_return_flags = [tech.drop_return_trip for tech in problem.technicians]
        if any(drop_return_flags):
            with cudf_memory_context("drop return trips"):
                data_model.set_drop_return_trips(cudf.Series(drop_return_flags, dtype=bool))
            logger.info(f"   🚗 Drop return trips configured: {sum(drop_return_flags)} technicians")

        # 4. Order locations
        with cudf_memory_context("order locations"):
            order_locs = cudf.Series(list(range(n_technicians, n_locations)), dtype=np.int32)
            data_model.set_order_locations(order_locs)

        # 5. Order time windows
        with cudf_memory_context("order time windows"):
            earliest_times = np.array([wo.time_window.earliest if wo.time_window else 0 for wo in problem.work_orders], dtype=np.int32)
            latest_times = np.array([wo.time_window.latest if wo.time_window else 1440 for wo in problem.work_orders], dtype=np.int32)
            data_model.set_order_time_windows(
                cudf.Series(earliest_times, dtype=np.int32),
                cudf.Series(latest_times, dtype=np.int32)
            )

        # 6. Order service times
        with cudf_memory_context("service times"):
            service_times = np.array([wo.service_time for wo in problem.work_orders], dtype=np.int32)
            data_model.set_order_service_times(cudf.Series(service_times))

        # 7. Vehicle time windows
        with cudf_memory_context("vehicle time windows"):
            veh_earliest = np.array([tech.work_shift.earliest for tech in problem.technicians], dtype=np.int32)
            veh_latest = np.array([tech.work_shift.latest for tech in problem.technicians], dtype=np.int32)
            data_model.set_vehicle_time_windows(cudf.Series(veh_earliest, dtype=np.int32), cudf.Series(veh_latest, dtype=np.int32))

        # 8. Breaks (skipped for small problems)
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
        elif not self.concurrent_mode:
            logger.info("   ⚡⚡ Skipping breaks (ultra-performance mode)")

        # 9. Capacity dimensions (daily limit + optional skill matching)
        enforce_skills = bool(self.config.get('enforce_skill_constraints', False))
        self._set_capacity_dimensions(data_model, problem.technicians, problem.work_orders, enforce_skills)

        # 10. Order prizes — higher-priority orders rewarded more
        _PRIORITY_PRIZES = {'emergency': 1000.0, 'critical': 500.0, 'high': 200.0, 'medium': 100.0, 'low': 50.0}
        try:
            prizes = np.array([
                _PRIORITY_PRIZES.get(str(wo.priority).split('.')[-1].lower(), 100.0)
                for wo in problem.work_orders
            ], dtype=np.float32)
            data_model.set_order_prizes(cudf.Series(prizes))
            logger.info(f"   🏆 Order prizes set (emergency=1000 → low=50)")
        except AttributeError:
            logger.debug("set_order_prizes not available in this cuOpt version — skipping")

        # 11. Vehicle fixed costs
        vehicle_fixed_cost = float(self.config.get('vehicle_fixed_cost', 0))
        if vehicle_fixed_cost > 0:
            try:
                with cudf_memory_context("vehicle fixed costs"):
                    fixed_costs = np.full(n_technicians, vehicle_fixed_cost, dtype=np.float32)
                    data_model.set_vehicle_fixed_costs(cudf.Series(fixed_costs))
                logger.info(f"   💰 Vehicle fixed cost: {vehicle_fixed_cost} per technician deployed")
            except AttributeError:
                logger.warning("set_vehicle_fixed_costs not available in this cuOpt version — skipping")

        # 12. Workload balance — cap total service time per vehicle.
        #     Using add_capacity_dimension avoids the solver gaming the constraint
        #     by pushing all routes to late in the day.
        max_route_hours = self.config.get('max_route_hours', None)
        if max_route_hours:
            cap_minutes = int(float(max_route_hours) * 60)
            try:
                with cudf_memory_context("workload capacity dimension"):
                    order_demands = cudf.Series([wo.service_time for wo in problem.work_orders], dtype=np.int32)
                    vehicle_capacities = cudf.Series([cap_minutes] * n_technicians, dtype=np.int32)
                    data_model.add_capacity_dimension("workload", order_demands, vehicle_capacities)
                logger.info(f"   ⏱ Workload cap: {max_route_hours}h ({cap_minutes} min) service time per technician")
            except Exception as e:
                logger.warning(f"add_capacity_dimension failed ({type(e).__name__}: {e}) — using min_vehicles fallback")
                try:
                    data_model.set_min_vehicles(n_technicians)
                    logger.info(f"   ⏱ Balance workload fallback: set_min_vehicles({n_technicians})")
                except Exception as e2:
                    logger.warning(f"set_min_vehicles also failed: {e2}")

        return data_model

    def _set_capacity_dimensions(self, data_model: DataModel, technicians: List[Technician],
                                 work_orders: List[WorkOrder], enforce_skills: bool = False):
        """Set capacity dimensions: daily order limit + optional skill matching"""
        with cudf_memory_context("daily order capacity"):
            max_orders = np.array([tech.max_daily_orders for tech in technicians], dtype=np.int32)
            order_demands = np.ones(len(work_orders), dtype=np.int32)
            data_model.add_capacity_dimension(
                "daily_orders",
                cudf.Series(order_demands),
                cudf.Series(max_orders)
            )

        if not enforce_skills:
            logger.info("   ℹ️  Skill constraints disabled (enable in Settings)")
            return

        # Use add_order_vehicle_match — the purpose-built API for skill routing.
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
            logger.info(f"   🎯 Skill matching: {constrained} order(s) constrained via add_order_vehicle_match")
        except AttributeError:
            logger.warning("add_order_vehicle_match not available in this cuOpt version — skill constraints skipped")

    def _convert_solution(self, solution, problem: OptimizationProblem) -> OptimizationSolution:
        """Convert cuOpt solution to our solution format"""
        cuopt_status = solution.get_status()
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

        with cudf_memory_context("route extraction"):
            route_df = solution.get_route()
            route_pandas = route_df.to_pandas() if len(route_df) > 0 else None

        routes = self._build_technician_routes(route_pandas, problem)

        assigned_order_ids = {assignment.work_order_id for route in routes for assignment in route.assignments}
        unassigned_orders = [wo.id for wo in problem.work_orders if wo.id not in assigned_order_ids]

        try:
            objective_value = solution.get_total_objective()
        except Exception:
            objective_value = 0.0

        optimization_solution = OptimizationSolution(
            status=status,
            routes=routes,
            unassigned_orders=unassigned_orders,
            objective_value=objective_value
        )
        optimization_solution.calculate_summary_stats()
        return optimization_solution

    def _build_technician_routes(self, route_df, problem: OptimizationProblem) -> List[TechnicianRoute]:
        """Build technician routes from cuOpt route dataframe"""
        routes = []
        n_technicians = len(problem.technicians)

        if route_df is None or len(route_df) == 0:
            return [TechnicianRoute(technician_id=tech.id) for tech in problem.technicians]

        for tech_idx in range(n_technicians):
            tech_routes = route_df[route_df['truck_id'] == tech_idx]

            if len(tech_routes) == 0:
                routes.append(TechnicianRoute(technician_id=problem.technicians[tech_idx].id))
                continue

            route = TechnicianRoute(technician_id=problem.technicians[tech_idx].id)
            tech_routes_sorted = tech_routes.sort_values('arrival_stamp')
            prev_location_idx = tech_idx  # Technician depot is at row tech_idx

            for _, row in tech_routes_sorted.iterrows():
                location_idx = int(row['location'])
                row_type = row.get('type', 'Unknown')

                if location_idx < n_technicians or row_type in ['Depot', 'Break']:
                    continue

                work_order_idx = location_idx - n_technicians
                if 0 <= work_order_idx < len(problem.work_orders):
                    wo = problem.work_orders[work_order_idx]

                    travel_time = 0
                    durations = problem.distance_matrix.durations
                    if (prev_location_idx < len(durations) and location_idx < len(durations[0])):
                        travel_time = int(durations[prev_location_idx][location_idx])
                    prev_location_idx = location_idx

                    stamp = row['arrival_stamp']
                    arrival_mins = int(stamp) if stamp is not None and not math.isnan(float(stamp)) else 0
                    assignment = Assignment(
                        technician_id=problem.technicians[tech_idx].id,
                        work_order_id=wo.id,
                        arrival_time=arrival_mins,
                        start_time=arrival_mins,
                        finish_time=arrival_mins + wo.service_time,
                        travel_time_to=travel_time,
                        sequence_order=len(route.assignments) + 1
                    )
                    route.add_assignment(assignment)

            route.calculate_totals()
            routes.append(route)

        return routes


# =============================================================================
# Global manager + public API
# =============================================================================

_concurrent_solver_manager = None
_manager_lock = Lock()


def get_concurrent_solver_manager() -> ConcurrentSolverManager:
    """Get the global concurrent solver manager instance"""
    global _concurrent_solver_manager

    with _manager_lock:
        if _concurrent_solver_manager is None:
            if not cuopt_available:
                raise RuntimeError("cuOpt is not available. Cannot initialize concurrent solver.")
            concurrent_config = get_concurrent_solver_config()
            if not concurrent_config['enabled']:
                raise RuntimeError("Concurrent execution is not enabled")
            _concurrent_solver_manager = ConcurrentSolverManager()

    return _concurrent_solver_manager


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
            test_dm = DataModel(2, 1, 1)
            status['basic_functionality'] = True

            try:
                memory_info = get_gpu_memory_info()
                status['memory_management'] = memory_info['gpu_total_mb'] > 0
                status['current_memory_mb'] = memory_info['gpu_used_mb']
                status['total_memory_mb'] = memory_info['gpu_total_mb']
            except Exception as e:
                status['memory_management'] = False
                status['memory_error'] = str(e)

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
    """Convenience function to solve a single optimization problem"""
    problem = OptimizationProblem(technicians=technicians, work_orders=work_orders, config=config)
    return TechnicianWorkOrderSolver(config).solve(problem)


def solve_optimization_problems_concurrent(problems: List[OptimizationProblem],
                                           configs: Optional[List[Dict[str, Any]]] = None,
                                           timeout: float = None) -> List[OptimizationSolution]:
    """Solve multiple optimization problems concurrently using CUDA streams"""
    try:
        manager = get_concurrent_solver_manager()
        return manager.solve_batch(problems, configs, timeout)
    except RuntimeError:
        logger.warning("Concurrent execution not available, falling back to sequential processing")
        solutions = []
        for i, problem in enumerate(problems):
            config = configs[i] if configs and i < len(configs) else None
            solutions.append(TechnicianWorkOrderSolver(config).solve(problem))
        return solutions
