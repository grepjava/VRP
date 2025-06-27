"""
FastAPI application for Technician-WorkOrder optimization
Enhanced with CUDA Streams and Concurrent Execution Support
"""

import logging
import time
import traceback
import asyncio
from typing import List, Dict, Any, Optional, Annotated
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import uvicorn

from config import CONFIG, validate_config, get_concurrent_solver_config
from core.models import OptimizationProblem, OptimizationSolution, SolutionStatus
from core.converter import (
    json_to_optimization_problem, optimization_solution_to_json,
    ConversionError, get_technician_json_schema, get_work_order_json_schema,
    get_optimization_problem_json_schema
)
from core.osrm import validate_osrm_connection

# Import solver with better error handling
solver_available = False
cuopt_status_func = None
concurrent_manager = None

try:
    from core.solver import (
        TechnicianWorkOrderSolver, is_cuopt_available, get_cuopt_status,
        get_concurrent_solver_manager, solve_optimization_problems_concurrent,
        ConcurrentSolverManager
    )
    cuopt_status_func = get_cuopt_status  # Store the function with a different name
    print("✅ Solver module imported successfully")

    if is_cuopt_available():
        solver_available = True
        print("✅ cuOpt is available and working")

        # Initialize concurrent solver manager if enabled
        concurrent_config = get_concurrent_solver_config()
        if concurrent_config['enabled']:
            try:
                concurrent_manager = get_concurrent_solver_manager()
                print(f"✅ Concurrent solver manager initialized with {concurrent_config['max_concurrent_instances']} instances")
            except Exception as e:
                print(f"⚠️ Failed to initialize concurrent solver manager: {e}")
                concurrent_manager = None
    else:
        print("❌ cuOpt is not available")
        cuopt_status = cuopt_status_func()
        print(f"cuOpt status: {cuopt_status}")

except ImportError as e:
    print(f"❌ Failed to import solver module: {e}")
    print("This usually means cuOpt import failed. Check cuOpt installation.")

    # Create a dummy solver for health checks
    class TechnicianWorkOrderSolver:
        def __init__(self, *args, **kwargs):
            pass
        def solve(self, problem):
            from core.models import OptimizationSolution, SolutionStatus
            return OptimizationSolution(
                status=SolutionStatus.ERROR,
                unassigned_orders=[]
            )

    def is_cuopt_available():
        return False

    def cuopt_status_func():
        return {"available": False, "error": str(e)}


# Configure logging
logging.basicConfig(
    level=getattr(logging, CONFIG['logging']['level']),
    format=CONFIG['logging']['format']
)
logger = logging.getLogger(__name__)


# =============================================================================
# Lifespan Event Handler
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan event handler"""
    # Startup
    logger.info("Starting Technician WorkOrder Optimization API")

    # Validate configuration
    if not validate_config():
        logger.error("Configuration validation failed")

    # Check OSRM connectivity
    if not validate_osrm_connection():
        logger.warning("OSRM server not accessible")

    # Check cuOpt availability
    if solver_available:
        logger.info("cuOpt solver is available and ready")
        print("✅ cuOpt solver ready for optimization")

        if concurrent_manager:
            logger.info("Concurrent solver manager is ready")
            print("✅ Concurrent execution enabled")
        else:
            logger.info("Concurrent execution not available")
            print("⚠️ Concurrent execution disabled")
    else:
        logger.warning("cuOpt solver is not available")
        print("⚠️ cuOpt solver not available - optimization endpoints will fail")

    logger.info("API startup completed")

    yield

    # Shutdown
    logger.info("Shutting down Technician WorkOrder Optimization API")

    # Shutdown concurrent solver manager
    if concurrent_manager:
        try:
            concurrent_manager.shutdown()
            logger.info("Concurrent solver manager shutdown completed")
        except Exception as e:
            logger.error(f"Error shutting down concurrent solver manager: {e}")


# FastAPI app initialization
app = FastAPI(
    title="Technician WorkOrder Optimization API",
    description="API for optimizing technician-workorder assignments using cuOpt and OSRM with CUDA Streams",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
if CONFIG['api']['cors_enabled']:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure as needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# =============================================================================
# Pydantic Models for Request/Response Validation
# =============================================================================

class LocationModel(BaseModel):
    """Location model for API requests"""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    address: Optional[str] = Field(None, description="Optional address description")


class TimeWindowModel(BaseModel):
    """Time window model for API requests"""
    earliest: int = Field(..., ge=0, description="Earliest time in minutes from start of day")
    latest: int = Field(..., ge=0, description="Latest time in minutes from start of day")

    @model_validator(mode='after')
    def validate_time_window(self):
        if self.latest < self.earliest:
            raise ValueError('Latest time must be >= earliest time')
        return self


class TechnicianModel(BaseModel):
    """Technician model for API requests"""
    id: str = Field(..., description="Unique technician identifier")
    name: str = Field(..., description="Technician name")
    start_location: LocationModel = Field(..., description="Technician starting location")
    work_shift: TimeWindowModel = Field(..., description="Working hours")
    break_window: TimeWindowModel = Field(..., description="Break time window")
    break_duration: int = Field(30, ge=1, description="Break duration in minutes")
    skills: List[str] = Field(default=[], description="List of technician skills")
    max_daily_orders: int = Field(10, ge=1, description="Maximum orders per day")
    max_travel_time: int = Field(240, ge=1, description="Maximum travel time per day in minutes")
    hourly_rate: float = Field(0.0, ge=0, description="Hourly rate")
    vehicle_type: str = Field("standard", description="Vehicle type")
    drop_return_trip: Optional[bool] = Field(False, description="Skip return to start location after last task")


class WorkOrderModel(BaseModel):
    """Work order model for API requests"""
    id: str = Field(..., description="Unique work order identifier")
    location: LocationModel = Field(..., description="Work order location")
    priority: str = Field(..., description="Priority level", pattern="^(low|medium|high|critical|emergency)$")
    work_type: str = Field(..., description="Type of work", pattern="^(maintenance|repair|inspection|installation|emergency)$")
    service_time: int = Field(60, ge=1, description="Service time in minutes")
    time_window: Optional[TimeWindowModel] = Field(None, description="Optional time window for appointment")
    required_skills: List[str] = Field(default=[], description="Required skills for this work order")
    customer_name: Optional[str] = Field(None, description="Customer name")
    description: Optional[str] = Field(None, description="Work order description")
    estimated_value: float = Field(0.0, ge=0, description="Estimated value of work order")


class OptimizationRequestModel(BaseModel):
    """Request model for optimization endpoint"""
    technicians: List[TechnicianModel] = Field(..., min_length=1, description="List of technicians")
    work_orders: List[WorkOrderModel] = Field(..., min_length=1, description="List of work orders")
    config: Optional[Dict[str, Any]] = Field(None, description="Optional configuration overrides")
    use_concurrent: Optional[bool] = Field(None, description="Force concurrent/sequential execution")
    priority: Optional[int] = Field(1, description="Request priority (lower = higher priority)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "technicians": [
                    {
                        "id": "TECH001",
                        "name": "John Smith",
                        "start_location": {
                            "latitude": 3.1073,
                            "longitude": 101.6067,
                            "address": "Petaling Jaya, Selangor"
                        },
                        "work_shift": {"earliest": 510, "latest": 1050},
                        "break_window": {"earliest": 720, "latest": 780},
                        "break_duration": 60,
                        "skills": ["electrical", "maintenance"],
                        "max_daily_orders": 8,
                        "max_travel_time": 300,
                        "hourly_rate": 65.0,
                        "vehicle_type": "van",
                        "drop_return_trip": False
                    }
                ],
                "work_orders": [
                    {
                        "id": "WO001",
                        "location": {
                            "latitude": 3.1478,
                            "longitude": 101.6159,
                            "address": "Damansara Heights, KL"
                        },
                        "priority": "high",
                        "work_type": "repair",
                        "service_time": 90,
                        "required_skills": ["electrical"],
                        "customer_name": "ABC Company",
                        "description": "Electrical repair",
                        "estimated_value": 500.0
                    }
                ],
                "use_concurrent": True,
                "priority": 1
            }
        }
    )


class BatchOptimizationRequestModel(BaseModel):
    """Request model for batch optimization endpoint"""
    problems: List[OptimizationRequestModel] = Field(..., min_length=1, max_length=10, description="List of optimization problems")
    timeout: Optional[float] = Field(None, description="Timeout in seconds for batch processing")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "problems": [
                    {
                        "technicians": [{"id": "TECH001", "name": "John", "start_location": {"latitude": 3.1073, "longitude": 101.6067}, "work_shift": {"earliest": 480, "latest": 1020}, "break_window": {"earliest": 720, "latest": 780}, "skills": ["electrical"]}],
                        "work_orders": [{"id": "WO001", "location": {"latitude": 3.1478, "longitude": 101.6159}, "priority": "high", "work_type": "repair", "required_skills": ["electrical"]}]
                    }
                ],
                "timeout": 120.0
            }
        }
    )


class AssignmentModel(BaseModel):
    """Assignment model for API responses"""
    technician_id: str
    work_order_id: str
    arrival_time: int
    start_time: int
    finish_time: int
    travel_time_to: int
    sequence_order: int


class TechnicianRouteModel(BaseModel):
    """Technician route model for API responses"""
    technician_id: str
    assignments: List[AssignmentModel]
    total_travel_time: int
    total_service_time: int
    total_time: int
    work_order_count: int
    break_assignment: Optional[AssignmentModel]


class OptimizationResponseModel(BaseModel):
    """Response model for optimization endpoint"""
    status: str
    routes: List[TechnicianRouteModel]
    unassigned_orders: List[str]
    total_travel_time: int
    total_service_time: int
    objective_value: float
    solve_time: float
    technicians_used: int
    orders_completed: int
    summary: Dict[str, Any]
    concurrent_execution: Optional[bool] = Field(None, description="Whether concurrent execution was used")
    solver_id: Optional[int] = Field(None, description="ID of solver that processed this request")


class BatchOptimizationResponseModel(BaseModel):
    """Response model for batch optimization endpoint"""
    results: List[OptimizationResponseModel]
    total_time: float
    concurrent_execution: bool
    success_count: int
    failure_count: int
    statistics: Dict[str, Any]


class ErrorResponseModel(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None
    timestamp: str
    request_id: Optional[str] = None


class HealthResponseModel(BaseModel):
    """Health check response model"""
    status: str
    timestamp: str
    version: str
    services: Dict[str, str]
    concurrent_execution: Dict[str, Any]


# =============================================================================
# Middleware and Exception Handlers
# =============================================================================

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header to responses"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    start_time = time.time()

    # Log request
    logger.info(f"Request: {request.method} {request.url}")

    response = await call_next(request)

    # Log response
    process_time = time.time() - start_time
    logger.info(f"Response: {response.status_code} in {process_time:.3f}s")

    return response


@app.exception_handler(ConversionError)
async def conversion_exception_handler(request: Request, exc: ConversionError):
    """Handle conversion errors"""
    logger.error(f"Conversion error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Data conversion error",
            "detail": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unexpected error: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "message": "Technician WorkOrder Optimization API",
        "version": "1.0.0",
        "docs": "/docs",
        "concurrent_execution": "enabled" if concurrent_manager else "disabled"
    }


@app.get("/health", response_model=HealthResponseModel)
async def health_check():
    """Health check endpoint"""

    # Check OSRM connectivity
    osrm_status = "ok" if validate_osrm_connection() else "error"

    # Check configuration
    config_status = "ok" if validate_config() else "error"

    # Check cuOpt availability
    cuopt_status = "ok" if solver_available and is_cuopt_available() else "error"

    # Check concurrent execution
    concurrent_status = "ok" if concurrent_manager else "disabled"

    # Overall status
    overall_status = "ok" if all(s == "ok" for s in [osrm_status, config_status, cuopt_status]) else "degraded"

    # Concurrent execution details
    concurrent_details = {"enabled": False, "status": "disabled"}
    if concurrent_manager:
        try:
            stats = concurrent_manager.get_statistics()
            concurrent_config = get_concurrent_solver_config()
            concurrent_details = {
                "enabled": True,
                "status": "ok",
                "max_concurrent_instances": concurrent_config['max_concurrent_instances'],
                "solver_threads": concurrent_config['max_concurrent_solvers'],
                "cuda_streams": concurrent_config['cuda_streams'],
                "active_requests": stats.get('active_requests', 0),
                "total_requests": stats.get('total_requests', 0),
                "success_rate": stats.get('success_rate', 0.0)
            }
        except Exception as e:
            concurrent_details = {"enabled": True, "status": "error", "error": str(e)}

    return HealthResponseModel(
        status=overall_status,
        timestamp=datetime.now().isoformat(),
        version="1.0.0",
        services={
            "osrm": osrm_status,
            "config": config_status,
            "cuopt": cuopt_status,
            "concurrent": concurrent_status
        },
        concurrent_execution=concurrent_details
    )


@app.post("/vrp/optimize", response_model=OptimizationResponseModel)
async def optimize_routes(request: OptimizationRequestModel):
    """
    Optimize technician-workorder assignments

    This endpoint takes a list of technicians and work orders and returns
    an optimized assignment that minimizes travel time while respecting
    all constraints (skills, time windows, breaks, etc.).

    Supports both sequential and concurrent execution modes.
    """
    try:
        logger.info(f"Optimization request: {len(request.technicians)} technicians, {len(request.work_orders)} work orders")
        print(f"🔍 Starting optimization request...")

        # Check if solver is available
        if not solver_available:
            print(f"❌ Solver not available")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="cuOpt solver is not available. Please check cuOpt installation and server logs."
            )

        print(f"✅ Solver is available")

        # Double-check cuOpt status
        cuopt_status = cuopt_status_func()
        print(f"🔍 cuOpt status: {cuopt_status}")

        if not cuopt_status.get('available', False):
            print(f"❌ cuOpt not available: {cuopt_status}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"cuOpt is not available: {cuopt_status.get('error', 'Unknown error')}"
            )

        # Determine execution mode
        use_concurrent = request.use_concurrent
        if use_concurrent is None:
            # Auto-determine based on configuration and problem size
            concurrent_config = get_concurrent_solver_config()
            use_concurrent = (concurrent_manager is not None and
                            concurrent_config['enabled'] and
                            len(request.technicians) + len(request.work_orders) >= 10)

        print(f"🚀 Execution mode: {'Concurrent' if use_concurrent else 'Sequential'}")

        # Convert request to optimization problem
        print(f"🔄 Converting request to optimization problem...")
        problem_data = request.model_dump()
        problem = json_to_optimization_problem(problem_data)
        print(f"✅ Problem created: {len(problem.technicians)} techs, {len(problem.work_orders)} orders")

        # Validate problem
        print(f"🔍 Validating problem...")
        validation_issues = problem.validate()
        if validation_issues:
            print(f"❌ Validation failed: {validation_issues}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Problem validation failed: {validation_issues}"
            )
        print(f"✅ Problem validation passed")

        # Solve optimization problem
        print(f"🚀 Starting optimization...")
        try:
            if use_concurrent and concurrent_manager:
                # Use concurrent execution
                request_id = concurrent_manager.submit_request(
                    problem,
                    request.config,
                    priority=request.priority or 1
                )
                result = concurrent_manager.get_result(request_id, timeout=300.0)

                if result is None:
                    raise HTTPException(
                        status_code=status.HTTP_408_REQUEST_TIMEOUT,
                        detail="Concurrent optimization request timed out"
                    )

                if not result.success:
                    raise Exception(result.error or "Concurrent optimization failed")

                solution = result.solution
                solver_id = result.solver_id
                print(f"✅ Concurrent optimization completed: {solution.status.value} (solver {solver_id})")

            else:
                # Use sequential execution
                solver = TechnicianWorkOrderSolver(request.config)
                solution = solver.solve(problem)
                solver_id = 0
                print(f"✅ Sequential optimization completed: {solution.status.value}")

        except Exception as e:
            print(f"❌ Optimization failed: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Optimization failed: {str(e)}"
            )

        # Convert solution to response format
        print(f"🔄 Converting solution to response...")
        response_data = optimization_solution_to_json(solution)
        response_data['concurrent_execution'] = use_concurrent
        response_data['solver_id'] = solver_id

        logger.info(f"Optimization completed: {solution.status.value}, {solution.orders_completed} orders assigned")
        print(f"✅ Request completed successfully")

        return OptimizationResponseModel(**response_data)

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ConversionError as e:
        logger.error(f"Conversion error: {e}")
        print(f"❌ Conversion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Data conversion error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Optimization error: {e}")
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Optimization failed: {str(e)}"
        )


@app.post("/vrp/optimize-batch", response_model=BatchOptimizationResponseModel)
async def optimize_routes_batch(request: BatchOptimizationRequestModel):
    """
    Optimize multiple technician-workorder problems concurrently

    This endpoint processes multiple optimization problems simultaneously
    using CUDA streams for maximum throughput.
    """
    try:
        if not concurrent_manager:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Concurrent execution is not available"
            )

        start_time = time.time()
        print(f"🚀 Starting batch optimization: {len(request.problems)} problems")

        # Convert all problems
        problems = []
        configs = []
        for i, problem_request in enumerate(request.problems):
            try:
                problem_data = problem_request.model_dump()
                problem = json_to_optimization_problem(problem_data)
                problems.append(problem)
                configs.append(problem_request.config)
            except Exception as e:
                logger.error(f"Failed to convert problem {i}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Problem {i} conversion failed: {str(e)}"
                )

        # Solve all problems concurrently
        solutions = solve_optimization_problems_concurrent(
            problems,
            configs,
            timeout=request.timeout
        )

        total_time = time.time() - start_time

        # Convert solutions to response format
        results = []
        success_count = 0
        failure_count = 0

        for i, solution in enumerate(solutions):
            try:
                response_data = optimization_solution_to_json(solution)
                response_data['concurrent_execution'] = True
                response_data['solver_id'] = i  # Simplified for batch mode
                results.append(OptimizationResponseModel(**response_data))

                if solution.status != SolutionStatus.ERROR:
                    success_count += 1
                else:
                    failure_count += 1

            except Exception as e:
                logger.error(f"Failed to convert solution {i}: {e}")
                failure_count += 1
                # Create error response
                error_solution_data = {
                    'status': 'error',
                    'routes': [],
                    'unassigned_orders': [],
                    'total_travel_time': 0,
                    'total_service_time': 0,
                    'objective_value': 0.0,
                    'solve_time': 0.0,
                    'technicians_used': 0,
                    'orders_completed': 0,
                    'summary': {},
                    'concurrent_execution': True,
                    'solver_id': i
                }
                results.append(OptimizationResponseModel(**error_solution_data))

        # Get statistics
        statistics = {}
        try:
            if concurrent_manager:
                statistics = concurrent_manager.get_statistics()
        except Exception as e:
            logger.warning(f"Failed to get statistics: {e}")

        response = BatchOptimizationResponseModel(
            results=results,
            total_time=total_time,
            concurrent_execution=True,
            success_count=success_count,
            failure_count=failure_count,
            statistics=statistics
        )

        print(f"✅ Batch optimization completed: {success_count} success, {failure_count} failed in {total_time:.3f}s")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch optimization error: {e}")
        print(f"❌ Batch optimization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch optimization failed: {str(e)}"
        )


@app.get("/vrp/schema/technician")
async def get_technician_schema():
    """Get JSON schema example for technician"""
    return get_technician_json_schema()


@app.get("/vrp/schema/work_order")
async def get_work_order_schema():
    """Get JSON schema example for work order"""
    return get_work_order_json_schema()


@app.get("/vrp/schema/problem")
async def get_problem_schema():
    """Get JSON schema example for optimization problem"""
    return get_optimization_problem_json_schema()


@app.post("/vrp/validate")
async def validate_problem(request: OptimizationRequestModel):
    """
    Validate optimization problem without solving
    """
    try:
        # Convert request to optimization problem
        problem_data = request.model_dump()
        problem = json_to_optimization_problem(problem_data)

        # Validate problem
        validation_issues = problem.validate()

        return {
            "valid": len(validation_issues) == 0,
            "issues": validation_issues,
            "summary": problem.to_summary_dict(),
            "concurrent_capable": concurrent_manager is not None
        }

    except ConversionError as e:
        return {
            "valid": False,
            "issues": [f"Conversion error: {str(e)}"],
            "summary": {},
            "concurrent_capable": False
        }


@app.get("/cuopt/status")
async def get_cuopt_status_endpoint():
    """Get detailed cuOpt status information"""
    try:
        if solver_available:
            status_info = cuopt_status_func()
        else:
            status_info = {
                "available": False,
                "routing_module": False,
                "basic_functionality": False,
                "error": "Solver module not imported successfully"
            }

        # Add concurrent execution info
        concurrent_info = {"enabled": False}
        if concurrent_manager:
            try:
                stats = concurrent_manager.get_statistics()
                concurrent_config = get_concurrent_solver_config()
                concurrent_info = {
                    "enabled": True,
                    "max_concurrent_instances": concurrent_config['max_concurrent_instances'],
                    "solver_threads": concurrent_config['max_concurrent_solvers'],
                    "cuda_streams": concurrent_config['cuda_streams'],
                    "statistics": stats
                }
            except Exception as e:
                concurrent_info = {"enabled": True, "error": str(e)}

        return {
            "solver_available": solver_available,
            "cuopt_details": status_info,
            "concurrent_execution": concurrent_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "solver_available": False,
            "cuopt_details": {"error": str(e)},
            "concurrent_execution": {"enabled": False, "error": str(e)},
            "timestamp": datetime.now().isoformat()
        }


@app.get("/concurrent/statistics")
async def get_concurrent_statistics():
    """Get concurrent solver statistics"""
    if not concurrent_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Concurrent execution is not available"
        )

    try:
        stats = concurrent_manager.get_statistics()
        return {
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )


@app.get("/config")
async def get_configuration():
    """Get current configuration (excluding sensitive data)"""
    safe_config = {
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
        "concurrent_execution": get_concurrent_solver_config()
    }
    return safe_config


# =============================================================================
# Main function for running the server
# =============================================================================

def main():
    """Main function to run the FastAPI server"""

    # Configuration from CONFIG
    host = CONFIG['api']['host']
    port = CONFIG['api']['port']
    debug = CONFIG['api']['debug']

    logger.info(f"Starting server on {host}:{port}")

    if concurrent_manager:
        concurrent_config = get_concurrent_solver_config()
        print(f"🚀 Server starting with concurrent execution enabled")
        print(f"   Max concurrent instances: {concurrent_config['max_concurrent_instances']}")
        print(f"   Solver threads: {concurrent_config['max_concurrent_solvers']}")
        print(f"   CUDA streams: {concurrent_config['cuda_streams']}")
    else:
        print(f"🚀 Server starting with sequential execution only")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug",
        access_log=True
    )


if __name__ == "__main__":
    main()