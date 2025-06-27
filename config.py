"""
Configuration file for Technician-WorkOrder Matching Application
using cuOpt and OSRM for route optimization
OPTIMIZED FOR HIGH PERFORMANCE WITH CUDA STREAMS
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
# cuOpt Solver Configuration - PERFORMANCE OPTIMIZED WITH CUDA STREAMS
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
        'max_concurrent_instances': 6,        # Single setting for both threads and CUDA streams
        'memory_pool_per_instance': 1024,     # MB per solver instance
        'queue_timeout': 30,                  # Timeout for solver queue in seconds
        'batch_processing': True,             # Enable batch processing mode
        'load_balancing': 'round_robin'       # 'round_robin', 'least_loaded', 'memory_based'
    },

    # GPU Memory Management
    'memory_management': {
        'initial_pool_size': 2**30,       # 1GB initial pool
        'maximum_pool_size': 8*2**30,     # 8GB maximum pool
        'per_solver_limit': 1.2*2**30,    # 1.2GB per solver max
        'enable_memory_pool': True,
        'auto_defragment': True,
        'memory_growth_strategy': 'linear'  # 'linear', 'exponential'
    },

    # Performance thresholds
    'small_problem_threshold': 15,    # Problems ≤15 locations = tiny
    'medium_problem_threshold': 50,   # Problems ≤50 locations = small
    'performance_mode': True,
    'skip_breaks_threshold': 10,      # Skip breaks for problems ≤10 locations
    'minimal_constraints_threshold': 15,  # Minimal constraints for tiny problems

    # ULTRA-aggressive time limits by problem size
    'time_limits': {
        'tiny': 0.1,      # ≤15 locations: 100ms (was 300ms)
        'small': 0.3,     # ≤50 locations: 300ms (was 800ms)
        'medium': 1.0,    # ≤100 locations: 1s (was 2s)
        'large': 3.0      # >100 locations: 3s (was 5s)
    },

    # Concurrent solver time limits (more aggressive for concurrent execution)
    'concurrent_time_limits': {
        'tiny': 0.05,     # ≤15 locations: 50ms
        'small': 0.15,    # ≤50 locations: 150ms
        'medium': 0.5,    # ≤100 locations: 500ms
        'large': 1.5      # >100 locations: 1.5s
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

    # Concurrent processing limits
    'concurrent_limits': {
        'max_requests_per_minute': 360,  # 6 instances * 60 requests/min
        'max_concurrent_problems': 6,
        'queue_size': 50,
        'priority_queue_enabled': True
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
    }
}

# =============================================================================
# Logging Configuration - OPTIMIZED FOR CONCURRENT EXECUTION
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
        'concurrent': 'INFO'      # New: Concurrent execution logging
    },

    # Concurrent execution specific logging
    'concurrent_logging': {
        'log_stream_allocation': True,
        'log_memory_usage': True,
        'log_queue_status': True,
        'log_solver_performance': True,
        'performance_interval': 10  # seconds
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
    'description': 'API for optimizing technician-workorder assignments using cuOpt and OSRM with CUDA Streams',
    'version': '1.0.0',
    'docs_url': '/docs',
    'redoc_url': '/redoc',
    'rate_limiting': {
        'enabled': True,
        'max_requests_per_minute': 360  # Increased for concurrent processing
    },
    'request_timeout': 300,  # 5 minutes for complex optimizations
    'max_request_size': 10 * 1024 * 1024,  # 10MB

    # Concurrent API processing
    'concurrent_processing': {
        'enabled': True,
        'max_concurrent_requests': 6,
        'queue_enabled': True,
        'priority_handling': True,
        'load_balancing': 'least_loaded'
    }
}

# =============================================================================
# Configuration Assembly
# =============================================================================

def get_config() -> Dict[str, Any]:
    """
    Get application configuration
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

    return config

# =============================================================================
# Performance Helper Functions - Enhanced for Concurrent Execution
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

def should_use_concurrent_execution(problem_count: int = 1) -> bool:
    """
    Determine if concurrent execution should be used

    Args:
        problem_count: Number of problems to solve

    Returns:
        bool: True if concurrent execution should be used
    """
    config = get_config()
    concurrent_config = config['cuopt']['concurrent_execution']

    return (concurrent_config['enabled'] and
            problem_count >= 1 and
            concurrent_config['max_concurrent_instances'] > 1)

def calculate_memory_per_instance(total_gpu_memory_gb: float) -> int:
    """
    Calculate optimal memory allocation per solver instance

    Args:
        total_gpu_memory_gb: Total GPU memory in GB

    Returns:
        int: Memory per solver instance in MB
    """
    config = get_config()
    concurrent_config = config['cuopt']['concurrent_execution']
    max_instances = concurrent_config['max_concurrent_instances']

    # Reserve 20% of memory for system overhead
    available_memory_gb = total_gpu_memory_gb * 0.8
    memory_per_instance_gb = available_memory_gb / max_instances

    # Convert to MB and ensure minimum allocation
    memory_per_instance_mb = max(512, int(memory_per_instance_gb * 1024))

    return min(memory_per_instance_mb, concurrent_config['memory_pool_per_instance'])

# =============================================================================
# Validation functions
# =============================================================================

def validate_config() -> bool:
    """
    Validate configuration settings including concurrent execution
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
    Setup logging configuration for the application

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

    # Validate configuration
    if validate_config():
        print("✅ Configuration validation passed")
    else:
        print("❌ Configuration validation failed")