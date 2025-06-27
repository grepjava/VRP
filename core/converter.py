"""
JSON conversion utilities for converting between JSON and our model objects
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from core.models import (
    Technician, WorkOrder, OptimizationProblem, OptimizationSolution,
    TechnicianRoute, Assignment, Location, TimeWindow, Priority, WorkOrderType,
    SolutionStatus, DistanceMatrix, create_technician_from_dict, create_work_order_from_dict
)

logger = logging.getLogger(__name__)


class ConversionError(Exception):
    """Custom exception for conversion errors"""
    pass


# =============================================================================
# JSON to Model Object Conversions
# =============================================================================

def json_to_location(data: Dict[str, Any]) -> Location:
    """
    Convert JSON data to Location object

    Args:
        data: JSON data containing latitude, longitude, optional address

    Returns:
        Location: Location object

    Raises:
        ConversionError: If required fields are missing or invalid
    """
    try:
        return Location(
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            address=data.get('address')
        )
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(f"Invalid location data: {e}")


def json_to_time_window(data: Dict[str, Any]) -> TimeWindow:
    """
    Convert JSON data to TimeWindow object

    Args:
        data: JSON data containing earliest and latest times

    Returns:
        TimeWindow: TimeWindow object
    """
    try:
        return TimeWindow(
            earliest=int(data['earliest']),
            latest=int(data['latest'])
        )
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(f"Invalid time window data: {e}")


def json_to_technician(data: Dict[str, Any]) -> Technician:
    """
    Convert JSON data to Technician object

    Args:
        data: JSON data for technician

    Returns:
        Technician: Technician object
    """
    try:
        return create_technician_from_dict(data)
    except Exception as e:
        raise ConversionError(f"Invalid technician data: {e}")


def json_to_work_order(data: Dict[str, Any]) -> WorkOrder:
    """
    Convert JSON data to WorkOrder object

    Args:
        data: JSON data for work order

    Returns:
        WorkOrder: WorkOrder object
    """
    try:
        return create_work_order_from_dict(data)
    except Exception as e:
        raise ConversionError(f"Invalid work order data: {e}")


def json_to_optimization_problem(data: Dict[str, Any]) -> OptimizationProblem:
    """
    Convert JSON data to OptimizationProblem object

    Args:
        data: JSON data containing technicians and work_orders lists

    Returns:
        OptimizationProblem: Complete optimization problem
    """
    try:
        problem = OptimizationProblem()

        # Convert technicians
        if 'technicians' in data:
            for tech_data in data['technicians']:
                technician = json_to_technician(tech_data)
                problem.add_technician(technician)

        # Convert work orders
        if 'work_orders' in data:
            for wo_data in data['work_orders']:
                work_order = json_to_work_order(wo_data)
                problem.add_work_order(work_order)

        # Add config if provided
        if 'config' in data:
            problem.config = data['config']

        return problem

    except Exception as e:
        raise ConversionError(f"Invalid optimization problem data: {e}")


# =============================================================================
# Model Object to JSON Conversions
# =============================================================================

def location_to_json(location: Location) -> Dict[str, Any]:
    """
    Convert Location object to JSON data

    Args:
        location: Location object

    Returns:
        dict: JSON-serializable dictionary
    """
    return {
        'latitude': location.latitude,
        'longitude': location.longitude,
        'address': location.address
    }


def time_window_to_json(time_window: TimeWindow) -> Dict[str, Any]:
    """
    Convert TimeWindow object to JSON data

    Args:
        time_window: TimeWindow object

    Returns:
        dict: JSON-serializable dictionary
    """
    return {
        'earliest': time_window.earliest,
        'latest': time_window.latest
    }


def technician_to_json(technician: Technician) -> Dict[str, Any]:
    """
    Convert Technician object to JSON data

    Args:
        technician: Technician object

    Returns:
        dict: JSON-serializable dictionary
    """
    return technician.to_dict()


def work_order_to_json(work_order: WorkOrder) -> Dict[str, Any]:
    """
    Convert WorkOrder object to JSON data

    Args:
        work_order: WorkOrder object

    Returns:
        dict: JSON-serializable dictionary
    """
    return work_order.to_dict()


def assignment_to_json(assignment: Assignment) -> Dict[str, Any]:
    """
    Convert Assignment object to JSON data

    Args:
        assignment: Assignment object

    Returns:
        dict: JSON-serializable dictionary
    """
    return {
        'technician_id': assignment.technician_id,
        'work_order_id': assignment.work_order_id,
        'arrival_time': assignment.arrival_time,
        'start_time': assignment.start_time,
        'finish_time': assignment.finish_time,
        'travel_time_to': assignment.travel_time_to,
        'sequence_order': assignment.sequence_order
    }


def technician_route_to_json(route: TechnicianRoute) -> Dict[str, Any]:
    """
    Convert TechnicianRoute object to JSON data

    Args:
        route: TechnicianRoute object

    Returns:
        dict: JSON-serializable dictionary
    """
    return {
        'technician_id': route.technician_id,
        'assignments': [assignment_to_json(a) for a in route.assignments],
        'total_travel_time': route.total_travel_time,
        'total_service_time': route.total_service_time,
        'total_time': route.total_time,
        'work_order_count': route.get_work_order_count(),
        'break_assignment': assignment_to_json(route.break_assignment) if route.break_assignment else None
    }


def optimization_solution_to_json(solution: OptimizationSolution) -> Dict[str, Any]:
    """
    Convert OptimizationSolution object to JSON data

    Args:
        solution: OptimizationSolution object

    Returns:
        dict: JSON-serializable dictionary
    """
    return {
        'status': solution.status.value,
        'routes': [technician_route_to_json(route) for route in solution.routes],
        'unassigned_orders': solution.unassigned_orders,
        'total_travel_time': solution.total_travel_time,
        'total_service_time': solution.total_service_time,
        'objective_value': solution.objective_value,
        'solve_time': solution.solve_time,
        'technicians_used': solution.technicians_used,
        'orders_completed': solution.orders_completed,
        'summary': solution.to_summary_dict()
    }


def optimization_problem_to_json(problem: OptimizationProblem) -> Dict[str, Any]:
    """
    Convert OptimizationProblem object to JSON data

    Args:
        problem: OptimizationProblem object

    Returns:
        dict: JSON-serializable dictionary
    """
    return {
        'technicians': [technician_to_json(tech) for tech in problem.technicians],
        'work_orders': [work_order_to_json(wo) for wo in problem.work_orders],
        'config': problem.config,
        'summary': problem.to_summary_dict()
    }


def distance_matrix_to_json(matrix: DistanceMatrix) -> Dict[str, Any]:
    """
    Convert DistanceMatrix object to JSON data

    Args:
        matrix: DistanceMatrix object

    Returns:
        dict: JSON-serializable dictionary
    """
    return {
        'locations': [location_to_json(loc) for loc in matrix.locations],
        'durations': matrix.durations,
        'distances': matrix.distances
    }


# =============================================================================
# Utility Functions
# =============================================================================

def validate_json_structure(data: Dict[str, Any], required_fields: List[str]) -> None:
    """
    Validate that JSON data contains required fields

    Args:
        data: JSON data to validate
        required_fields: List of required field names

    Raises:
        ConversionError: If any required fields are missing
    """
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        raise ConversionError(f"Missing required fields: {missing_fields}")


def safe_convert(converter_func, data: Any, default_value: Any = None) -> Any:
    """
    Safely convert data using converter function with fallback

    Args:
        converter_func: Function to use for conversion
        data: Data to convert
        default_value: Value to return if conversion fails

    Returns:
        Converted data or default value
    """
    try:
        return converter_func(data)
    except Exception as e:
        logger.warning(f"Conversion failed: {e}, using default value: {default_value}")
        return default_value


def convert_times_to_minutes(data: Dict[str, Any], time_fields: List[str]) -> Dict[str, Any]:
    """
    Convert time fields from various formats to minutes

    Args:
        data: Dictionary containing time fields
        time_fields: List of field names that contain time values

    Returns:
        dict: Data with time fields converted to minutes
    """
    from config import convert_time_to_minutes, CONFIG

    converted_data = data.copy()
    time_unit = CONFIG['business']['time_unit']

    for field in time_fields:
        if field in converted_data and converted_data[field] is not None:
            try:
                converted_data[field] = int(convert_time_to_minutes(converted_data[field], time_unit))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to convert time field {field}: {e}")

    return converted_data


# =============================================================================
# Batch Conversion Functions
# =============================================================================

def json_to_technicians_list(data: List[Dict[str, Any]]) -> List[Technician]:
    """
    Convert list of JSON objects to list of Technician objects

    Args:
        data: List of JSON objects for technicians

    Returns:
        list: List of Technician objects
    """
    technicians = []
    for i, tech_data in enumerate(data):
        try:
            technician = json_to_technician(tech_data)
            technicians.append(technician)
        except ConversionError as e:
            logger.error(f"Failed to convert technician {i}: {e}")
            # Continue with other technicians

    return technicians


def json_to_work_orders_list(data: List[Dict[str, Any]]) -> List[WorkOrder]:
    """
    Convert list of JSON objects to list of WorkOrder objects

    Args:
        data: List of JSON objects for work orders

    Returns:
        list: List of WorkOrder objects
    """
    work_orders = []
    for i, wo_data in enumerate(data):
        try:
            work_order = json_to_work_order(wo_data)
            work_orders.append(work_order)
        except ConversionError as e:
            logger.error(f"Failed to convert work order {i}: {e}")
            # Continue with other work orders

    return work_orders


def technicians_list_to_json(technicians: List[Technician]) -> List[Dict[str, Any]]:
    """
    Convert list of Technician objects to list of JSON objects

    Args:
        technicians: List of Technician objects

    Returns:
        list: List of JSON-serializable dictionaries
    """
    return [technician_to_json(tech) for tech in technicians]


def work_orders_list_to_json(work_orders: List[WorkOrder]) -> List[Dict[str, Any]]:
    """
    Convert list of WorkOrder objects to list of JSON objects

    Args:
        work_orders: List of WorkOrder objects

    Returns:
        list: List of JSON-serializable dictionaries
    """
    return [work_order_to_json(wo) for wo in work_orders]


# =============================================================================
# File I/O Functions
# =============================================================================

def load_optimization_problem_from_file(file_path: str) -> OptimizationProblem:
    """
    Load OptimizationProblem from JSON file

    Args:
        file_path: Path to JSON file

    Returns:
        OptimizationProblem: Loaded optimization problem
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return json_to_optimization_problem(data)
    except FileNotFoundError:
        raise ConversionError(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ConversionError(f"Invalid JSON in file {file_path}: {e}")


def save_optimization_solution_to_file(solution: OptimizationSolution, file_path: str) -> None:
    """
    Save OptimizationSolution to JSON file

    Args:
        solution: OptimizationSolution to save
        file_path: Path to output JSON file
    """
    try:
        data = optimization_solution_to_json(solution)
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Solution saved to {file_path}")
    except Exception as e:
        raise ConversionError(f"Failed to save solution to {file_path}: {e}")


def save_optimization_problem_to_file(problem: OptimizationProblem, file_path: str) -> None:
    """
    Save OptimizationProblem to JSON file

    Args:
        problem: OptimizationProblem to save
        file_path: Path to output JSON file
    """
    try:
        data = optimization_problem_to_json(problem)
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Problem saved to {file_path}")
    except Exception as e:
        raise ConversionError(f"Failed to save problem to {file_path}: {e}")


# =============================================================================
# Example JSON Schemas
# =============================================================================

def get_technician_json_schema() -> Dict[str, Any]:
    """
    Get example JSON schema for technician

    Returns:
        dict: Example technician JSON structure
    """
    return {
        "id": "TECH001",
        "name": "John Smith",
        "start_location": {
            "latitude": 1.3521,
            "longitude": 103.8198,
            "address": "Marina Bay, Singapore"
        },
        "work_shift": {
            "earliest": 480,  # 8:00 AM in minutes
            "latest": 1020  # 5:00 PM in minutes
        },
        "break_window": {
            "earliest": 720,  # 12:00 PM in minutes
            "latest": 780  # 1:00 PM in minutes
        },
        "break_duration": 30,
        "skills": ["electrical", "plumbing"],
        "max_daily_orders": 8,
        "max_travel_time": 240,
        "hourly_rate": 50.0,
        "vehicle_type": "van",
        "drop_return_trip": False
    }


def get_work_order_json_schema() -> Dict[str, Any]:
    """
    Get example JSON schema for work order

    Returns:
        dict: Example work order JSON structure
    """
    return {
        "id": "WO001",
        "location": {
            "latitude": 1.2966,
            "longitude": 103.8067,
            "address": "Jurong East, Singapore"
        },
        "priority": "high",
        "work_type": "repair",
        "service_time": 90,
        "time_window": {
            "earliest": 540,  # 9:00 AM in minutes
            "latest": 960  # 4:00 PM in minutes
        },
        "required_skills": ["electrical"],
        "customer_name": "ABC Company",
        "description": "Emergency electrical repair",
        "estimated_value": 500.0
    }


def get_optimization_problem_json_schema() -> Dict[str, Any]:
    """
    Get example JSON schema for optimization problem

    Returns:
        dict: Example optimization problem JSON structure
    """
    return {
        "technicians": [get_technician_json_schema()],
        "work_orders": [get_work_order_json_schema()],
        "config": {
            "time_limit": 60,
            "verbose": True
        }
    }


# Testing functions

def test_json_conversion():
    """Test JSON conversion functions"""
    try:
        # Test technician conversion
        tech_json = get_technician_json_schema()
        technician = json_to_technician(tech_json)
        tech_json_back = technician_to_json(technician)

        print("✅ Technician JSON conversion successful")

        # Test work order conversion
        wo_json = get_work_order_json_schema()
        work_order = json_to_work_order(wo_json)
        wo_json_back = work_order_to_json(work_order)

        print("✅ Work order JSON conversion successful")

        # Test optimization problem conversion
        problem_json = get_optimization_problem_json_schema()
        problem = json_to_optimization_problem(problem_json)
        problem_json_back = optimization_problem_to_json(problem)

        print("✅ Optimization problem JSON conversion successful")

        return True

    except Exception as e:
        print(f"❌ JSON conversion test failed: {e}")
        return False


if __name__ == "__main__":
    print("Testing JSON conversion...")
    test_json_conversion()