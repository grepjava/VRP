# Shared application state populated by main.py during startup.
# Routers import this module and access attributes directly.

solver_available: bool = False
cuopt_status_func = None           # () -> dict
is_cuopt_available_func = None     # () -> bool
concurrent_manager = None          # ConcurrentSolverManager | None
get_gpu_memory_info_func = None    # () -> dict
TechnicianWorkOrderSolver = None   # class
solve_optimization_problems_concurrent = None  # function
