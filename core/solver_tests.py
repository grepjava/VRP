"""Development-only test harness for the VRP solver and concurrent pool."""
from __future__ import annotations

import logging
import time

from core.gpu_memory import get_gpu_memory_info
from core.models import (
    Location, OptimizationProblem, Priority, Technician, TimeWindow,
    WorkOrder, WorkOrderType,
)
from core.solver import solve_optimization_problem, solve_optimization_problems_concurrent

logger = logging.getLogger(__name__)


def test_solver():
    """Test solver with simple sample data and memory monitoring"""
    logger.info("=== CREATING SIMPLE TEST CASE ===")

    technicians = [
        Technician(
            id="TECH001",
            name="John Smith",
            start_location=Location(3.1073, 101.6067, "PJ Centre"),
            work_shift=TimeWindow(480, 1020),
            break_window=TimeWindow(720, 780),
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
        logger.info("=== STARTING SOLVER TEST WITH MEMORY MONITORING ===")

        initial_memory = get_gpu_memory_info()
        logger.info(f"Initial GPU memory: {initial_memory['gpu_used_mb']:.1f}MB used")

        solution = solve_optimization_problem(technicians, work_orders)

        final_memory = get_gpu_memory_info()
        logger.info(f"Final GPU memory: {final_memory['gpu_used_mb']:.1f}MB used")
        logger.info(f"Memory change: {final_memory['gpu_used_mb'] - initial_memory['gpu_used_mb']:.1f}MB")

        logger.info(f"\n=== OPTIMIZATION RESULTS ===")
        logger.info(f"Status: {solution.status.value}")
        logger.info(f"Technicians used: {solution.technicians_used}")
        logger.info(f"Orders completed: {solution.orders_completed}")
        logger.info(f"Solve time: {solution.solve_time:.3f}s")

        if solution.routes:
            for route in solution.routes:
                logger.info(f"\n{route.technician_id}:")
                if route.assignments:
                    for assignment in route.assignments:
                        logger.info(f"  ✅ {assignment.work_order_id}")
                        logger.info(f"     Arrival: {assignment.arrival_time} min")
                        logger.info(f"     Travel time: {assignment.travel_time_to} min")
                else:
                    logger.error(f"  ❌ No assignments")

        if solution.unassigned_orders:
            logger.error(f"\n❌ Unassigned orders: {solution.unassigned_orders}")

        success = (solution.status.value != "error") or (solution.orders_completed > 0)
        logger.info(f"\n🎯 Test result: {'✅ PASS' if success else '❌ FAIL'}")
        return success

    except Exception as e:
        logger.error(f"❌ Solver test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_concurrent_solver():
    """Test concurrent solver with multiple problems and memory monitoring"""
    logger.info("=== TESTING CONCURRENT SOLVER WITH MEMORY MONITORING ===")

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
        problems.append(OptimizationProblem(technicians=technicians, work_orders=work_orders))

    try:
        logger.info(f"=== STARTING CONCURRENT SOLVER TEST WITH {len(problems)} PROBLEMS ===")

        initial_memory = get_gpu_memory_info()
        logger.info(f"Initial GPU memory: {initial_memory['gpu_used_mb']:.1f}MB used")

        start_time = time.time()
        solutions = solve_optimization_problems_concurrent(problems, timeout=60.0)
        total_time = time.time() - start_time

        final_memory = get_gpu_memory_info()
        logger.info(f"Final GPU memory: {final_memory['gpu_used_mb']:.1f}MB used")
        logger.info(f"Memory change: {final_memory['gpu_used_mb'] - initial_memory['gpu_used_mb']:.1f}MB")

        logger.info(f"\n=== CONCURRENT OPTIMIZATION RESULTS ===")
        logger.info(f"Total problems: {len(problems)}")
        logger.info(f"Total time: {total_time:.3f}s")
        logger.info(f"Average time per problem: {total_time/len(problems):.3f}s")

        success_count = 0
        for i, solution in enumerate(solutions):
            status = solution.status.value
            orders_completed = solution.orders_completed
            if status != "error" and orders_completed > 0:
                success_count += 1
            logger.info(f"Problem {i}: Status={status}, Orders={orders_completed}, Time={solution.solve_time:.3f}s")

        success_rate = success_count / len(problems) * 100
        logger.info(f"\nSuccess rate: {success_rate:.1f}% ({success_count}/{len(problems)})")

        try:
            from core.solver import get_concurrent_solver_manager
            manager = get_concurrent_solver_manager()
            stats = manager.get_statistics()
            logger.info(f"\nManager Statistics:")
            logger.info(f"  Total requests: {stats['total_requests']}")
            logger.info(f"  Completed: {stats['completed_requests']}")
            logger.info(f"  Failed: {stats['failed_requests']}")
            logger.info(f"  Average processing time: {stats['average_processing_time']:.3f}s")
            memory_stats = stats.get('memory_stats', {})
            logger.info(f"  Peak GPU usage: {memory_stats.get('peak_gpu_usage_mb', 0):.1f}MB")
            logger.info(f"  Memory cleanups: {memory_stats.get('memory_cleanups', 0)}")
        except Exception:
            pass

        overall_success = success_rate >= 80
        logger.info(f"\n🎯 Concurrent test result: {'✅ PASS' if overall_success else '❌ FAIL'}")
        return overall_success

    except Exception as e:
        logger.error(f"❌ Concurrent solver test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    from config import get_concurrent_solver_config

    logger.info("Testing solver with GPU memory management...")
    basic_success = test_solver()

    concurrent_config = get_concurrent_solver_config()
    if concurrent_config['enabled']:
        logger.info("\n" + "="*50)
        concurrent_success = test_concurrent_solver()
        if basic_success and concurrent_success:
            logger.info("\n🎉 All tests passed!")
        else:
            logger.error("\n❌ Some tests failed")
    else:
        logger.warning("\n⚠️ Concurrent execution disabled, skipping concurrent tests")
        if basic_success:
            logger.info("\n🎉 Basic tests passed!")
        else:
            logger.error("\n❌ Basic tests failed")
