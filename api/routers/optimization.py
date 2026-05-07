import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from api import deps
from api.models import (
    OptimizationRequestModel, OptimizationResponseModel,
    BatchOptimizationRequestModel, BatchOptimizationResponseModel,
    MemoryInfoModel,
)
from config import get_concurrent_solver_config
from core.converter import (
    json_to_optimization_problem, optimization_solution_to_json, ConversionError,
    get_technician_json_schema, get_work_order_json_schema, get_optimization_problem_json_schema,
)
from core.models import SolutionStatus

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_memory() -> dict | None:
    try:
        if deps.get_gpu_memory_info_func:
            return deps.get_gpu_memory_info_func()
    except Exception:
        pass
    return None


@router.post("/vrp/optimize", response_model=OptimizationResponseModel)
async def optimize_routes(request: OptimizationRequestModel):
    """Optimize technician-workorder assignments using cuOpt."""
    try:
        logger.info(f"Optimization request: {len(request.technicians)} technicians, {len(request.work_orders)} work orders")

        initial_memory = _get_memory()
        if initial_memory:
            logger.info(f"Initial GPU memory: {initial_memory['gpu_used_mb']:.1f}MB")

        if not deps.solver_available:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="cuOpt solver is not available. Please check cuOpt installation and server logs."
            )

        cuopt_status = deps.cuopt_status_func()
        if not cuopt_status.get('available', False):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"cuOpt is not available: {cuopt_status.get('error', 'Unknown error')}"
            )

        use_concurrent = request.use_concurrent
        if use_concurrent is None:
            concurrent_config = get_concurrent_solver_config()
            use_concurrent = (
                deps.concurrent_manager is not None
                and concurrent_config['enabled']
                and len(request.technicians) + len(request.work_orders) >= 10
            )

        problem = json_to_optimization_problem(request.model_dump())
        validation_issues = problem.validate()
        if validation_issues:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Problem validation failed: {validation_issues}"
            )

        try:
            if use_concurrent and deps.concurrent_manager:
                request_id = deps.concurrent_manager.submit_request(
                    problem, request.config, priority=request.priority or 1
                )
                result = deps.concurrent_manager.get_result(request_id, timeout=300.0)
                if result is None:
                    raise HTTPException(
                        status_code=status.HTTP_408_REQUEST_TIMEOUT,
                        detail="Concurrent optimization request timed out"
                    )
                if not result.success:
                    raise Exception(result.error or "Concurrent optimization failed")
                solution = result.solution
                solver_id = result.solver_id
                final_memory_from_result = result.memory_info
                logger.info(f"Concurrent optimization completed: {solution.status.value} (solver {solver_id})")
            else:
                solver = deps.TechnicianWorkOrderSolver(request.config)
                solution = solver.solve(problem)
                solver_id = 0
                final_memory_from_result = None
                logger.info(f"Sequential optimization completed: {solution.status.value}")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Optimization failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Optimization failed due to an internal error"
            )

        final_memory = _get_memory()
        if final_memory and initial_memory:
            delta = final_memory['gpu_used_mb'] - initial_memory['gpu_used_mb']
            logger.info(f"Final GPU memory: {final_memory['gpu_used_mb']:.1f}MB (Δ{delta:+.1f}MB)")

        memory_info_to_use = final_memory_from_result or final_memory
        response_data = optimization_solution_to_json(solution)
        response_data['concurrent_execution'] = use_concurrent
        response_data['solver_id'] = solver_id
        if memory_info_to_use:
            try:
                response_data['memory_info'] = MemoryInfoModel(**memory_info_to_use)
            except Exception:
                pass

        logger.info(f"Optimization completed: {solution.status.value}, {solution.orders_completed} orders assigned")
        return OptimizationResponseModel(**response_data)

    except HTTPException:
        raise
    except ConversionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Data conversion error: {e}")
    except Exception as e:
        logger.exception(f"Unexpected optimization error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Optimization failed due to an internal error")


@router.post("/vrp/optimize-batch", response_model=BatchOptimizationResponseModel)
async def optimize_routes_batch(request: BatchOptimizationRequestModel):
    """Optimize multiple problems concurrently."""
    try:
        if not deps.concurrent_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Concurrent execution is not available"
            )

        start_time = time.time()
        logger.info(f"Starting batch optimization: {len(request.problems)} problems")

        initial_memory = _get_memory()

        problems = []
        configs = []
        for i, prob_req in enumerate(request.problems):
            try:
                problems.append(json_to_optimization_problem(prob_req.model_dump()))
                configs.append(prob_req.config)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Problem {i} conversion failed: {e}"
                )

        solutions = deps.solve_optimization_problems_concurrent(problems, configs, timeout=request.timeout)
        total_time = time.time() - start_time

        final_memory = _get_memory()
        if final_memory and initial_memory:
            delta = final_memory['gpu_used_mb'] - initial_memory['gpu_used_mb']
            logger.info(f"Final GPU memory: {final_memory['gpu_used_mb']:.1f}MB (Δ{delta:+.1f}MB)")

        results = []
        success_count = 0
        failure_count = 0

        for i, solution in enumerate(solutions):
            try:
                response_data = optimization_solution_to_json(solution)
                response_data['concurrent_execution'] = True
                response_data['solver_id'] = i
                if final_memory:
                    try:
                        response_data['memory_info'] = MemoryInfoModel(**final_memory)
                    except Exception:
                        pass
                results.append(OptimizationResponseModel(**response_data))
                if solution.status != SolutionStatus.ERROR:
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                logger.error(f"Failed to convert solution {i}: {e}")
                failure_count += 1
                results.append(OptimizationResponseModel(
                    status='error', routes=[], unassigned_orders=[],
                    total_travel_time=0, total_service_time=0, objective_value=0.0,
                    solve_time=0.0, technicians_used=0, orders_completed=0, summary={},
                    concurrent_execution=True, solver_id=i
                ))

        statistics = {}
        try:
            statistics = deps.concurrent_manager.get_statistics()
        except Exception:
            pass

        memory_summary = None
        if final_memory:
            try:
                memory_summary = MemoryInfoModel(**final_memory)
            except Exception:
                pass

        logger.info(f"Batch optimization completed: {success_count} success, {failure_count} failed in {total_time:.3f}s")
        return BatchOptimizationResponseModel(
            results=results,
            total_time=total_time,
            concurrent_execution=True,
            success_count=success_count,
            failure_count=failure_count,
            statistics=statistics,
            memory_summary=memory_summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Batch optimization failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Batch optimization failed due to an internal error")


@router.get("/vrp/schema/technician")
async def get_technician_schema():
    return get_technician_json_schema()


@router.get("/vrp/schema/work_order")
async def get_work_order_schema():
    return get_work_order_json_schema()


@router.get("/vrp/schema/problem")
async def get_problem_schema():
    return get_optimization_problem_json_schema()


@router.post("/vrp/validate")
async def validate_problem(request: OptimizationRequestModel):
    """Validate optimization problem without solving."""
    try:
        problem = json_to_optimization_problem(request.model_dump())
        validation_issues = problem.validate()

        memory_info = None
        try:
            if deps.get_gpu_memory_info_func:
                memory_info = MemoryInfoModel(**deps.get_gpu_memory_info_func())
        except Exception:
            pass

        return {
            "valid": len(validation_issues) == 0,
            "issues": validation_issues,
            "summary": problem.to_summary_dict(),
            "concurrent_capable": deps.concurrent_manager is not None,
            "memory_info": memory_info
        }
    except ConversionError as e:
        return {
            "valid": False,
            "issues": [f"Conversion error: {e}"],
            "summary": {},
            "concurrent_capable": False,
            "memory_info": None
        }
