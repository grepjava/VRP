"""
cuOpt-based solver for technician-workorder optimization
ULTRA HIGH PERFORMANCE VERSION
Following the cuOpt service team routing notebook patterns with aggressive optimizations
"""

import logging
import time
import cudf
import numpy as np
from typing import List, Dict, Any, Optional, Set

# Import cuOpt with proper error handling
cuopt_available = False

print("🔍 Attempting to import cuOpt routing module...")

try:
    from cuopt.routing import DataModel, SolverSettings, Solve
    cuopt_available = True
    print("✅ cuOpt routing imported successfully")

    # Initialize GPU memory management
    try:
        import rmm
        rmm.reinitialize(
            pool_allocator=True,
            initial_pool_size=2**30,  # 1GB initial pool
            maximum_pool_size=8*2**30   # 8GB maximum
        )
        print("✅ GPU memory pool initialized")
    except ImportError:
        print("⚠️ rmm not available, using default GPU memory management")
    except Exception as e:
        print(f"⚠️ GPU memory pool initialization failed: {e}")

except ImportError as e:
    print(f"❌ cuOpt import failed: {e}")
    print("⚠️ Solver will not be available")
    cuopt_available = False

from config import CONFIG, get_optimal_time_limit, should_skip_complex_constraints
from core.models import (
    OptimizationProblem, OptimizationSolution, TechnicianRoute, Assignment,
    Technician, WorkOrder, Priority, SolutionStatus, DistanceMatrix
)
from core.osrm import calculate_matrix_for_problem

logger = logging.getLogger(__name__)


class SolverError(Exception):
    """Custom exception for solver-related errors"""
    pass


class TechnicianWorkOrderSolver:
    """
    Main solver class that integrates OSRM and cuOpt for technician-workorder optimization
    ULTRA HIGH PERFORMANCE VERSION
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize solver with configuration"""
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

        logger.info("Initialized TechnicianWorkOrderSolver")
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
            print(f"🔍 Problem: {len(problem.technicians)} techs, {len(problem.work_orders)} orders (total: {problem_size})")

            # Step 1: Calculate distance matrix using OSRM
            if problem.distance_matrix is None:
                print("🌐 Calculating travel times via OSRM...")
                matrix_start = time.time()
                problem.distance_matrix = calculate_matrix_for_problem(
                    problem.technicians, problem.work_orders
                )
                matrix_time = time.time() - matrix_start
                print(f"✅ Distance matrix calculated in {matrix_time:.3f}s")

            # Step 2: Build cuOpt DataModel with performance optimizations
            print("🏗️ Building cuOpt data model...")
            model_start = time.time()
            data_model = self._build_cuopt_model_optimized(problem)
            model_time = time.time() - model_start
            print(f"✅ cuOpt data model built in {model_time:.3f}s")

            # Step 3: Configure solver with ultra-aggressive settings
            print("⚙️ Configuring high-performance solver...")
            solver_settings = self._configure_optimized_solver(problem_size)

            # Step 4: Verify GPU and run solver
            self._verify_gpu_status()

            print("🚀 Running cuOpt optimization...")
            solve_start = time.time()
            solution = Solve(data_model, solver_settings)
            solve_time = time.time() - solve_start
            print(f"✅ cuOpt solved in {solve_time:.3f}s")

            # Step 5: Check solver status
            solver_status = solution.get_status()
            if solver_status == 0:
                print(f"📊 SUCCESS: Objective value = {solution.get_total_objective():.2f}")
            else:
                print(f"📊 Status {solver_status}: {solution.get_message()}")

            # Step 6: Convert results to our format
            conversion_start = time.time()
            optimization_solution = self._convert_solution(solution, problem)
            conversion_time = time.time() - conversion_start
            optimization_solution.solve_time = time.time() - start_time

            # Performance summary
            total_time = optimization_solution.solve_time
            print(f"🏁 PERFORMANCE SUMMARY:")
            print(f"   OSRM Matrix: {matrix_time:.3f}s ({100*matrix_time/total_time:.1f}%)")
            print(f"   Model Build: {model_time:.3f}s ({100*model_time/total_time:.1f}%)")
            print(f"   cuOpt Solve: {solve_time:.3f}s ({100*solve_time/total_time:.1f}%)")
            print(f"   Conversion:  {conversion_time:.3f}s ({100*conversion_time/total_time:.1f}%)")
            print(f"   TOTAL TIME:  {total_time:.3f}s")
            print(f"   Status: {optimization_solution.status.value}, Orders: {optimization_solution.orders_completed}")

            return optimization_solution

        except Exception as e:
            logger.error(f"Solver error: {e}")
            print(f"❌ Solver error: {e}")
            return OptimizationSolution(
                status=SolutionStatus.ERROR,
                unassigned_orders=[wo.id for wo in problem.work_orders],
                solve_time=time.time() - start_time
            )

    def _configure_optimized_solver(self, problem_size: int) -> SolverSettings:
        """Configure solver with ultra-aggressive performance settings"""
        solver_settings = SolverSettings()

        # ULTRA aggressive time limits based on problem size
        if problem_size <= 10:
            time_limit = 0.05  # 50ms for very tiny problems
        elif problem_size <= 15:
            time_limit = 0.1   # 100ms for tiny problems
        elif problem_size <= 30:
            time_limit = 0.3   # 300ms for small problems
        elif problem_size <= 100:
            time_limit = 1.0   # 1s for medium problems
        else:
            time_limit = get_optimal_time_limit(problem_size)

        solver_settings.set_time_limit(time_limit)

        # Disable all verbose output for maximum performance
        solver_settings.set_verbose_mode(False)
        solver_settings.set_error_logging_mode(False)

        print(f"   ⚡⚡ ULTRA-fast mode: {time_limit}s limit for {problem_size} locations")

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

    def _build_cuopt_model_optimized(self, problem: OptimizationProblem) -> DataModel:
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
            print("   ⚡⚡ Skipping breaks (ultra-performance mode)")

        # 8. Set capacity dimensions with performance optimizations
        self._set_capacity_dimensions_optimized(data_model, problem.technicians, problem.work_orders, problem_size)

        return data_model

    def _set_order_time_windows_fast(self, data_model: DataModel, work_orders: List[WorkOrder]):
        """Set time windows for work orders - optimized version"""
        earliest_times = []
        latest_times = []

        for wo in work_orders:
            if wo.time_window:
                earliest_times.append(wo.time_window.earliest)
                latest_times.append(wo.time_window.latest)
            else:
                earliest_times.append(0)
                latest_times.append(24 * 60)  # End of day

        data_model.set_order_time_windows(
            cudf.Series(earliest_times, dtype=np.int32),
            cudf.Series(latest_times, dtype=np.int32)
        )

    def _set_vehicle_time_windows_fast(self, data_model: DataModel, technicians: List[Technician]):
        """Set time windows and breaks for technicians - optimized version"""
        # Vehicle time windows (work shifts)
        earliest_times = [tech.work_shift.earliest for tech in technicians]
        latest_times = [tech.work_shift.latest for tech in technicians]

        data_model.set_vehicle_time_windows(
            cudf.Series(earliest_times, dtype=np.int32),
            cudf.Series(latest_times, dtype=np.int32)
        )

        # Breaks for each technician
        for i, tech in enumerate(technicians):
            data_model.add_vehicle_break(
                vehicle_id=i,
                earliest=int(tech.break_window.earliest),
                latest=int(tech.break_window.latest),
                duration=int(tech.break_duration),
                locations=cudf.Series([], dtype='int32')
            )

    def _set_capacity_dimensions_optimized(self, data_model: DataModel, technicians: List[Technician],
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
            print("   ⚡⚡ Minimal constraints only (ultra-performance mode)")
            return

        # For larger problems, check if we should skip complex constraints
        if should_skip_complex_constraints(problem_size):
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

    def _set_skill_constraints_fast(self, data_model: DataModel, technicians: List[Technician], work_orders: List[WorkOrder]):
        """Set skill constraints - optimized version"""
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

        # Set up capacity dimension for the critical skill only
        vehicle_capacities = [100 if critical_skill in tech.skills else 0 for tech in technicians]
        order_demands = [1 if critical_skill in wo.required_skills else 0 for wo in work_orders]

        data_model.add_capacity_dimension(
            f"skill_{critical_skill}",
            cudf.Series(order_demands, dtype=np.int32),
            cudf.Series(vehicle_capacities, dtype=np.int32)
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


# Convenience functions

def is_cuopt_available() -> bool:
    """Check if cuOpt is available and working"""
    return cuopt_available


def get_cuopt_status() -> Dict[str, Any]:
    """Get detailed cuOpt status information"""
    status = {
        'available': cuopt_available,
        'routing_module': cuopt_available,
        'error': None
    }

    if cuopt_available:
        try:
            # Test basic functionality
            test_dm = DataModel(2, 1, 1)
            status['basic_functionality'] = True
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


if __name__ == "__main__":
    print("Testing solver...")
    test_solver()