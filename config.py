"""
Configuration file for Technician-WorkOrder Matching Application
using cuOpt and OSRM for route optimization
OPTIMIZED FOR HIGH PERFORMANCE WITH CUDA STREAMS AND GPU MEMORY MANAGEMENT
"""

import os
from typing import Dict, Any, Optional

# =============================================================================
# OSRM Configuration
# =============================================================================

OSRM_CONFIG = {
    'host': '192.168.100.20',
    'port': 5000,
    'base_url': 'http://192.168.100.20:5000',
    'table_endpoint': '/table/v1/driving/',
    'timeout': 30,  # seconds
    'max_locations_per_request': 500,  # OSRM limitation
    'annotations': ['duration', 'distance']
}

# =============================================================================
# cuOpt Solver Configuration - PERFORMANCE OPTIMIZED WITH CUDA STREAMS AND MEMORY MANAGEMENT
# =============================================================================

CUOPT_CONFIG = {
    'default_time_limit': 1,      # Reduced from 2 to 1 second
    'verbose_mode': False,        # Always false for performance
    'error_logging': False,       # Disable for maximum performance
    'min_vehicles_auto': True,
    'dump_results': False,
    'results_file_path': './results/',
    'results_interval': 10,

    # CUDA Streams Configuration for Concurrent Execution - SIMPLIFIED
    'concurrent_execution': {
        'enabled': True,
        'max_concurrent_instances': 16,        # Single setting for both threads and CUDA streams
        'memory_pool_per_instance': 1024,     # MB per solver instance
        'queue_timeout': 30,                  # Timeout for solver queue in seconds
        'batch_processing': True,             # Enable batch processing mode
        'load_balancing': 'round_robin'       # 'round_robin', 'least_loaded', 'memory_based'
    },

    # Enhanced GPU Memory Management
    'memory_management': {
        'initial_pool_size': 2**30,       # 1GB initial pool
        'maximum_pool_size': 8*2**30,     # 8GB maximum pool
        'per_solver_limit': 1.2*2**30,    # 1.2GB per solver max
        'enable_memory_pool': True,
        'auto_defragment': True,
        'memory_growth_strategy': 'linear',  # 'linear', 'exponential'

        # New memory management settings
        'cleanup_threshold_mb': 100,      # Clean up if more than 100MB left after operation
        'memory_warning_threshold': 0.8,  # Warn if using >80% of allocated memory
        'force_cleanup_interval': 10,     # Force cleanup every 10 operations
        'enable_memory_monitoring': True, # Enable detailed memory monitoring
        'log_memory_usage': True,         # Log memory usage for debugging
        'enable_context_managers': True,  # Use context managers for memory cleanup
        'aggressive_cleanup': True        # Enable aggressive memory cleanup
    },

    # Performance thresholds
    'small_problem_threshold': 15,    # Problems ≤15 locations = tiny
    'medium_problem_threshold': 50,   # Problems ≤50 locations = small
    'performance_mode': True,
    'skip_breaks_threshold': 10,      # Skip breaks for problems ≤10 locations
    'minimal_constraints_threshold': 15,  # Minimal constraints for tiny problems

    # Time limits by problem size (seconds)
    'time_limits': {
        'tiny': 5,        # ≤15 locations
        'small': 10,      # ≤50 locations
        'medium': 30,     # ≤100 locations
        'large': 60       # >100 locations
    },

    # Concurrent solver time limits — slightly tighter to allow batch throughput
    'concurrent_time_limits': {
        'tiny': 3,        # ≤15 locations
        'small': 8,       # ≤50 locations
        'medium': 20,     # ≤100 locations
        'large': 45       # >100 locations
    },

    # cuOpt specific settings
    'solver_settings': {
        'time_limit': 2,
        'verbose': False,         # Performance critical
        'error_logging': False    # Performance critical
    },

    # Objective types
    'objectives': {
        'COST': 'cost',
        'PRIZE': 'prize',
        'VEHICLE_COUNT': 'vehicles'
    }
}

# =============================================================================
# Business Logic Configuration
# =============================================================================

BUSINESS_CONFIG = {
    # Time units (all times should be in the same unit)
    'time_unit': 'minutes',  # 'seconds', 'minutes', 'hours'

    # Default service times per work order type (in minutes)
    'default_service_times': {
        'maintenance': 60,
        'repair': 90,
        'inspection': 30,
        'installation': 120,
        'emergency': 45
    },

    # Priority weights for work orders
    'priority_weights': {
        'low': 1,
        'medium': 2,
        'high': 5,
        'critical': 10,
        'emergency': 20
    },

    # Break configuration
    'break_config': {
        'default_duration': 30,  # minutes
        'earliest_start_offset': 240,  # 4 hours after shift start
        'latest_start_offset': 480,   # 8 hours after shift start
        'mandatory': True
    },

    # Vehicle/Technician constraints
    'technician_constraints': {
        'max_daily_working_hours': 8,  # hours
        'max_travel_time_per_day': 4,  # hours
        'max_orders_per_day': 10,
        'lunch_break_required': True
    }
}

# =============================================================================
# Data Processing Configuration
# =============================================================================

DATA_CONFIG = {
    # Coordinate system
    'coordinate_system': 'WGS84',  # lat, lon
    'coordinate_precision': 6,  # decimal places

    # Input validation
    'max_technicians': 50,
    'max_work_orders': 500,
    'max_locations_total': 550,  # max_technicians + max_work_orders

    # Concurrent processing limits with memory considerations
    'concurrent_limits': {
        'max_requests_per_minute': 360,  # 6 instances * 60 requests/min
        'max_concurrent_problems': 6,
        'queue_size': 50,
        'priority_queue_enabled': True,
        'memory_limit_per_request_mb': 1024,  # Memory limit per concurrent request
        'max_memory_usage_percent': 80        # Maximum total GPU memory usage
    },

    # Data file paths
    'input_data_path': './data/input/',
    'output_data_path': './data/output/',
    'logs_path': './logs/',

    # File formats
    'supported_input_formats': ['.csv', '.json', '.xlsx'],
    'output_format': 'csv',

    # API data validation
    'api_validation': {
        'min_technicians': 1,
        'min_work_orders': 1,
        'max_skills_per_tech': 20,
        'max_skills_per_order': 10,
        'max_name_length': 100,
        'max_description_length': 500,
        'max_address_length': 200
    },

    # Data conversion settings
    'conversion': {
        'strict_validation': True,
        'allow_partial_conversion': False,
        'default_service_time': 60,  # minutes
        'default_break_duration': 30,  # minutes
        'default_max_daily_orders': 10
    }
}

# =============================================================================
# Optimization Objectives Configuration
# =============================================================================

OPTIMIZATION_CONFIG = {
    # Primary objective weights
    'objective_weights': {
        'minimize_travel_time': 1.0,
        'maximize_priority_score': 0.5,
        'minimize_technicians_used': 0.3,
        'balance_workload': 0.2
    },

    # Optimization strategy
    'strategy': 'speed',  # Changed from 'balanced' to 'speed'

    # Advanced settings
    'allow_overtime': False,
    'allow_unassigned_orders': True,
    'prefer_skill_matching': True,

    # Performance settings
    'skip_complex_constraints_threshold': 15,  # Skip complex constraints for tiny problems
    'fast_mode_enabled': True,

    # Concurrent optimization settings
    'concurrent_optimization': {
        'enable_problem_splitting': True,      # Split large problems across solvers
        'min_problem_size_for_splitting': 100, # Minimum size to consider splitting
        'split_strategy': 'geographic',        # 'geographic', 'skills', 'random'
        'merge_results': True,                 # Merge split results back together
        'load_balancing': True                 # Balance load across available solvers
    },

    # Memory-aware optimization settings
    'memory_optimization': {
        'enable_memory_aware_scheduling': True,    # Schedule based on memory availability
        'memory_threshold_for_sequential': 0.9,   # Use sequential if memory >90% full
        'dynamic_batch_sizing': True,             # Adjust batch size based on memory
        'prefer_smaller_problems_when_low_memory': True  # Prioritize smaller problems when memory is low
    }
}

# =============================================================================
# Enhanced Logging Configuration - OPTIMIZED FOR CONCURRENT EXECUTION WITH MEMORY MONITORING
# =============================================================================

LOGGING_CONFIG = {
    'level': 'WARNING',  # Reduced from INFO to WARNING for performance
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file_path': './logs/technician_matching.log',
    'max_file_size': 10,  # MB
    'backup_count': 5,
    'console_output': True,

    # API specific logging - reduced for performance
    'api_logging': {
        'log_requests': False,        # Disabled for performance
        'log_responses': False,       # Disabled for performance
        'log_request_body': False,
        'log_response_body': False,
        'performance_logging': True   # Keep performance metrics
    },

    # Component logging levels - reduced for performance
    'component_levels': {
        'uvicorn': 'WARNING',     # Reduced from INFO
        'fastapi': 'WARNING',     # Reduced from INFO
        'osrm': 'WARNING',        # Reduced from INFO
        'solver': 'WARNING',      # Reduced from INFO
        'converter': 'WARNING',   # Reduced from INFO
        'concurrent': 'INFO',     # Concurrent execution logging
        'memory': 'INFO'          # Memory management logging
    },

    # Concurrent execution specific logging
    'concurrent_logging': {
        'log_stream_allocation': True,
        'log_memory_usage': True,
        'log_queue_status': True,
        'log_solver_performance': True,
        'performance_interval': 10  # seconds
    },

    # Memory management specific logging
    'memory_logging': {
        'log_memory_allocation': True,     # Log memory allocations
        'log_memory_cleanup': True,        # Log memory cleanup operations
        'log_memory_warnings': True,       # Log memory warnings
        'log_memory_leaks': True,          # Log potential memory leaks
        'memory_log_interval': 5,          # Log memory status every 5 seconds
        'detailed_memory_logging': False   # Enable detailed memory logging (debug only)
    }
}

# =============================================================================
# API Configuration
# =============================================================================

API_CONFIG = {
    'host': '0.0.0.0',
    'port': 8000,
    'debug': False,
    'cors_enabled': True,
    'cors_origins': ["*"],  # Configure for security in production
    'title': 'Technician WorkOrder Optimization API',
    'description': 'API for optimizing technician-workorder assignments using cuOpt and OSRM with CUDA Streams and GPU Memory Management',
    'version': '1.0.0',
    'docs_url': '/docs',
    'redoc_url': '/redoc',
    'rate_limiting': {
        'enabled': True,
        'max_requests_per_minute': 360  # Increased for concurrent processing
    },
    'request_timeout': 300,  # 5 minutes for complex optimizations
    'max_request_size': 10 * 1024 * 1024,  # 10MB

    # Concurrent API processing with memory management
    'concurrent_processing': {
        'enabled': True,
        'max_concurrent_requests': 6,
        'queue_enabled': True,
        'priority_handling': True,
        'load_balancing': 'least_loaded',
        'memory_aware_scheduling': True,      # Schedule requests based on memory availability
        'memory_threshold_rejection': 0.95   # Reject requests if memory usage >95%
    },

    # Memory monitoring for API
    'memory_monitoring': {
        'enabled': True,
        'include_in_responses': True,         # Include memory info in API responses
        'log_memory_per_request': True,       # Log memory usage per request
        'memory_alerts': True,                # Enable memory usage alerts
        'alert_threshold': 0.8               # Alert if memory usage >80%
    }
}

# =============================================================================
# Configuration Assembly
# =============================================================================

def get_config() -> Dict[str, Any]:
    """
    Get application configuration with memory management settings
    """
    config = {
        'osrm': OSRM_CONFIG.copy(),
        'cuopt': CUOPT_CONFIG.copy(),
        'business': BUSINESS_CONFIG.copy(),
        'data': DATA_CONFIG.copy(),
        'optimization': OPTIMIZATION_CONFIG.copy(),
        'logging': LOGGING_CONFIG.copy(),
        'api': API_CONFIG.copy()
    }

    # Override with environment variables if present
    if os.getenv('OSRM_HOST'):
        config['osrm']['host'] = os.getenv('OSRM_HOST')
        config['osrm']['base_url'] = f"http://{os.getenv('OSRM_HOST')}:{config['osrm']['port']}"

    if os.getenv('OSRM_PORT'):
        config['osrm']['port'] = int(os.getenv('OSRM_PORT'))
        config['osrm']['base_url'] = f"http://{config['osrm']['host']}:{os.getenv('OSRM_PORT')}"

    # Override concurrent instance count if environment variable is set
    # Support both old and new environment variable names for backward compatibility
    if os.getenv('CUOPT_CONCURRENT_INSTANCES'):
        config['cuopt']['concurrent_execution']['max_concurrent_instances'] = int(os.getenv('CUOPT_CONCURRENT_INSTANCES'))
    elif os.getenv('CUOPT_CONCURRENT_SOLVERS'):
        # Backward compatibility with old environment variable name
        config['cuopt']['concurrent_execution']['max_concurrent_instances'] = int(os.getenv('CUOPT_CONCURRENT_SOLVERS'))

    # Override memory settings if environment variables are set
    if os.getenv('CUOPT_MEMORY_PER_INSTANCE'):
        config['cuopt']['concurrent_execution']['memory_pool_per_instance'] = int(os.getenv('CUOPT_MEMORY_PER_INSTANCE'))

    if os.getenv('CUOPT_ENABLE_MEMORY_MONITORING'):
        config['cuopt']['memory_management']['enable_memory_monitoring'] = os.getenv('CUOPT_ENABLE_MEMORY_MONITORING').lower() == 'true'

    if os.getenv('CUOPT_AGGRESSIVE_CLEANUP'):
        config['cuopt']['memory_management']['aggressive_cleanup'] = os.getenv('CUOPT_AGGRESSIVE_CLEANUP').lower() == 'true'

    return config

# =============================================================================
# Enhanced Performance Helper Functions - With Memory Management
# =============================================================================

def get_optimal_time_limit(problem_size: int, concurrent_mode: bool = False) -> float:
    """
    Get optimal time limit based on problem size for maximum performance

    Args:
        problem_size: Total number of locations (technicians + work orders)
        concurrent_mode: Whether to use concurrent execution time limits

    Returns:
        float: Optimal time limit in seconds
    """
    config = get_config()

    time_limits = config['cuopt']['concurrent_time_limits'] if concurrent_mode else config['cuopt']['time_limits']

    if problem_size <= config['cuopt']['small_problem_threshold']:
        return time_limits['tiny']
    elif problem_size <= config['cuopt']['medium_problem_threshold']:
        return time_limits['small']
    elif problem_size <= 100:
        return time_limits['medium']
    else:
        return time_limits['large']

def should_skip_complex_constraints(problem_size: int) -> bool:
    """
    Determine if complex constraints should be skipped for performance

    Args:
        problem_size: Total number of locations

    Returns:
        bool: True if complex constraints should be skipped
    """
    config = get_config()
    return (problem_size <= config['optimization']['skip_complex_constraints_threshold'] and
            config['optimization']['fast_mode_enabled'])

def get_concurrent_solver_config() -> Dict[str, Any]:
    """
    Get configuration specific to concurrent solver execution

    Returns:
        dict: Concurrent solver configuration with derived values
    """
    config = get_config()
    concurrent_config = config['cuopt']['concurrent_execution'].copy()

    # Add derived values for backward compatibility
    max_instances = concurrent_config['max_concurrent_instances']
    concurrent_config['max_concurrent_solvers'] = max_instances  # For backward compatibility
    concurrent_config['cuda_streams'] = max_instances           # Same as solver count
    concurrent_config['memory_pool_per_solver'] = concurrent_config['memory_pool_per_instance']

    return concurrent_config

def should_use_concurrent_execution(problem_count: int = 1, current_memory_usage: float = 0.0) -> bool:
    """
    Determine if concurrent execution should be used based on problem count and memory usage

    Args:
        problem_count: Number of problems to solve
        current_memory_usage: Current memory usage as percentage (0.0-1.0)

    Returns:
        bool: True if concurrent execution should be used
    """
    config = get_config()
    concurrent_config = config['cuopt']['concurrent_execution']
    memory_config = config['optimization']['memory_optimization']

    # Check if concurrent execution is enabled
    if not concurrent_config['enabled']:
        return False

    # Check if we have enough instances for the problem count
    if problem_count < 1 or concurrent_config['max_concurrent_instances'] <= 1:
        return False

    # Check memory constraints
    if memory_config['enable_memory_aware_scheduling']:
        memory_threshold = memory_config['memory_threshold_for_sequential']
        if current_memory_usage > memory_threshold:
            return False

    return True

def calculate_memory_per_instance(total_gpu_memory_gb: float, safety_margin: float = 0.2) -> int:
    """
    Calculate optimal memory allocation per solver instance with safety margin

    Args:
        total_gpu_memory_gb: Total GPU memory in GB
        safety_margin: Safety margin as percentage (default 20%)

    Returns:
        int: Memory per solver instance in MB
    """
    config = get_config()
    concurrent_config = config['cuopt']['concurrent_execution']
    max_instances = concurrent_config['max_concurrent_instances']

    # Reserve safety margin for system overhead
    available_memory_gb = total_gpu_memory_gb * (1.0 - safety_margin)
    memory_per_instance_gb = available_memory_gb / max_instances

    # Convert to MB and ensure minimum allocation
    memory_per_instance_mb = max(512, int(memory_per_instance_gb * 1024))

    return min(memory_per_instance_mb, concurrent_config['memory_pool_per_instance'])

def get_memory_cleanup_config() -> Dict[str, Any]:
    """
    Get memory cleanup configuration settings

    Returns:
        dict: Memory cleanup configuration
    """
    config = get_config()
    return config['cuopt']['memory_management']

def should_force_memory_cleanup(operation_count: int) -> bool:
    """
    Determine if forced memory cleanup should be performed

    Args:
        operation_count: Number of operations performed since last cleanup

    Returns:
        bool: True if forced cleanup should be performed
    """
    config = get_config()
    memory_config = config['cuopt']['memory_management']

    return (memory_config['aggressive_cleanup'] and
            operation_count >= memory_config['force_cleanup_interval'])

def get_memory_warning_threshold() -> float:
    """
    Get memory usage threshold for warnings

    Returns:
        float: Memory warning threshold as percentage (0.0-1.0)
    """
    config = get_config()
    return config['cuopt']['memory_management']['memory_warning_threshold']

# =============================================================================
# Enhanced Validation functions with Memory Checks
# =============================================================================

def validate_config() -> bool:
    """
    Validate configuration settings including concurrent execution and memory management
    """
    config = get_config()

    # Check OSRM connectivity with a simple API test
    try:
        import requests
        # First check if server responds to root (even with error)
        response = requests.get(f"{config['osrm']['base_url']}/", timeout=5)
        if response.status_code not in [200, 400]:
            print(f"Warning: OSRM server returned unexpected status: {response.status_code}")
            return False

        # Test with a simple coordinate to verify API actually works
        test_url = f"{config['osrm']['base_url']}/table/v1/driving/103.8198,1.3521;103.8478,1.3644"
        api_response = requests.get(test_url, timeout=10)
        if api_response.status_code == 200:
            api_data = api_response.json()
            if api_data.get('code') == 'Ok':
                print("✅ OSRM server is accessible and API is working")
            else:
                print(f"Warning: OSRM API returned: {api_data.get('message', 'Unknown error')}")
        else:
            print(f"Warning: OSRM API test failed with status: {api_response.status_code}")

    except Exception as e:
        print(f"Warning: Cannot connect to OSRM server: {e}")
        return False

    # Validate concurrent execution configuration
    concurrent_config = config['cuopt']['concurrent_execution']
    if concurrent_config['enabled']:
        max_instances = concurrent_config['max_concurrent_instances']

        if max_instances <= 0:
            print("Error: max_concurrent_instances must be positive")
            return False

        if concurrent_config['memory_pool_per_instance'] <= 0:
            print("Error: memory_pool_per_instance must be positive")
            return False

        print(f"✅ Concurrent execution configured: {max_instances} solver instances (threads + CUDA streams)")

    # Validate memory management configuration
    memory_config = config['cuopt']['memory_management']
    if memory_config['enable_memory_monitoring']:
        print("✅ GPU memory monitoring enabled")

        if memory_config['aggressive_cleanup']:
            print("✅ Aggressive memory cleanup enabled")

        if memory_config['enable_context_managers']:
            print("✅ Memory context managers enabled")

    # Validate file paths
    for path_key in ['input_data_path', 'output_data_path', 'logs_path']:
        path = config['data'][path_key]
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
                print(f"Created directory: {path}")
            except Exception as e:
                print(f"Error creating directory {path}: {e}")
                return False

    # Validate data limits
    if config['data']['max_technicians'] <= 0:
        print("Error: max_technicians must be positive")
        return False

    if config['data']['max_work_orders'] <= 0:
        print("Error: max_work_orders must be positive")
        return False

    # Validate OSRM configuration
    if config['osrm']['max_locations_per_request'] > 100:
        print("Warning: OSRM max_locations_per_request is high, may cause timeouts")

    # Validate API configuration
    if config['api']['port'] < 1024 or config['api']['port'] > 65535:
        print("Warning: API port should be between 1024-65535")

    # Validate solver configuration
    if config['cuopt']['default_time_limit'] <= 0:
        print("Error: solver time_limit must be positive")
        return False

    # Validate memory thresholds
    memory_optimization = config['optimization']['memory_optimization']
    if memory_optimization['memory_threshold_for_sequential'] > 1.0:
        print("Warning: memory_threshold_for_sequential should be <= 1.0")

    api_memory = config['api']['memory_monitoring']
    if api_memory['alert_threshold'] > 1.0:
        print("Warning: memory alert_threshold should be <= 1.0")

    print("✅ Configuration validation passed")
    return True

# =============================================================================
# Helper functions
# =============================================================================

def convert_time_to_minutes(value: float, unit: str) -> float:
    """Convert time value to minutes based on unit"""
    if unit == 'seconds':
        return value / 60
    elif unit == 'minutes':
        return value
    elif unit == 'hours':
        return value * 60
    else:
        raise ValueError(f"Unsupported time unit: {unit}")

def convert_time_from_minutes(value: float, unit: str) -> float:
    """Convert time value from minutes to specified unit"""
    if unit == 'seconds':
        return value * 60
    elif unit == 'minutes':
        return value
    elif unit == 'hours':
        return value / 60
    else:
        raise ValueError(f"Unsupported time unit: {unit}")


def setup_logging(config: Optional[Dict[str, Any]] = None) -> None:
    """
    Setup logging configuration for the application with memory logging

    Args:
        config: Optional config override, uses global CONFIG if None
    """
    import logging.handlers

    log_config = (config or CONFIG)['logging']

    # Create formatter
    formatter = logging.Formatter(log_config['format'])

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_config['level']))

    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    if log_config['console_output']:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_config['file_path']:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_config['file_path'])
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_config['file_path'],
            maxBytes=log_config['max_file_size'] * 1024 * 1024,  # Convert MB to bytes
            backupCount=log_config['backup_count']
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Set component-specific log levels
    if 'component_levels' in log_config:
        for component, level in log_config['component_levels'].items():
            logging.getLogger(component).setLevel(getattr(logging, level))


def get_api_config() -> Dict[str, Any]:
    """
    Get API-specific configuration

    Returns:
        dict: API configuration settings
    """
    return CONFIG['api'].copy()


def get_solver_config() -> Dict[str, Any]:
    """
    Get solver-specific configuration

    Returns:
        dict: Solver configuration settings
    """
    return CONFIG['cuopt'].copy()

# Initialize configuration on module import
CONFIG = get_config()

if __name__ == "__main__":
    # Test configuration
    print("Configuration loaded successfully!")
    print(f"OSRM URL: {CONFIG['osrm']['base_url']}")
    concurrent_config = get_concurrent_solver_config()
    print(f"Concurrent Instances: {concurrent_config['max_concurrent_instances']}")
    print(f"Solver Threads: {concurrent_config['max_concurrent_solvers']}")
    print(f"CUDA Streams: {concurrent_config['cuda_streams']}")

    # Memory management info
    memory_config = get_memory_cleanup_config()
    print(f"Memory Management: {'enabled' if memory_config['enable_memory_monitoring'] else 'disabled'}")
    print(f"Aggressive Cleanup: {'enabled' if memory_config['aggressive_cleanup'] else 'disabled'}")
    print(f"Context Managers: {'enabled' if memory_config['enable_context_managers'] else 'disabled'}")

    # Validate configuration
    if validate_config():
        print("✅ Configuration validation passed")
    else:
        print("❌ Configuration validation failed")