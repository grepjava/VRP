"""
Data models for Technician-WorkOrder Matching Application
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime, time
import json
from enum import Enum


class Priority(Enum):
    """Work order priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class WorkOrderType(Enum):
    """Types of work orders"""
    MAINTENANCE = "maintenance"
    REPAIR = "repair"
    INSPECTION = "inspection"
    INSTALLATION = "installation"
    EMERGENCY = "emergency"


class SolutionStatus(Enum):
    """Solution status from cuOpt solver"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    INFEASIBLE = "infeasible"
    ERROR = "error"


@dataclass
class Location:
    """Geographic location with latitude and longitude"""
    latitude: float
    longitude: float
    address: Optional[str] = None

    def __post_init__(self):
        """Validate coordinates"""
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Invalid longitude: {self.longitude}")

    def to_osrm_format(self) -> str:
        """Convert to OSRM coordinate format (lon,lat)"""
        return f"{self.longitude},{self.latitude}"

    def __str__(self) -> str:
        return f"({self.latitude}, {self.longitude})"


@dataclass
class TimeWindow:
    """Time window with earliest and latest times"""
    earliest: int  # minutes from start of day
    latest: int  # minutes from start of day

    def __post_init__(self):
        """Validate time window"""
        if self.earliest < 0 or self.latest < 0:
            raise ValueError("Time values must be non-negative")
        if self.earliest > self.latest:
            raise ValueError("Earliest time must be <= latest time")

    def duration(self) -> int:
        """Get duration of time window in minutes"""
        return self.latest - self.earliest

    def __str__(self) -> str:
        return f"[{self.earliest}-{self.latest}]"


@dataclass
class Technician:
    """Represents a field technician"""
    id: str
    name: str
    start_location: Location
    work_shift: TimeWindow
    break_window: TimeWindow
    break_duration: int = 30  # minutes
    skills: Set[str] = field(default_factory=set)
    max_daily_orders: int = 10
    max_travel_time: int = 240  # minutes (4 hours)
    hourly_rate: float = 0.0
    vehicle_type: str = "standard"

    def __post_init__(self):
        """Validate technician data"""
        if self.break_duration <= 0:
            raise ValueError("Break duration must be positive")
        if self.max_daily_orders <= 0:
            raise ValueError("Max daily orders must be positive")
        if not self.work_shift.earliest <= self.break_window.earliest <= self.break_window.latest <= self.work_shift.latest:
            raise ValueError("Break window must be within work shift")

    def available_work_time(self) -> int:
        """Calculate available work time excluding break"""
        return self.work_shift.duration() - self.break_duration

    def can_handle_order(self, work_order: 'WorkOrder') -> bool:
        """Check if technician can handle the work order based on skills"""
        if work_order.required_skills:
            return work_order.required_skills.issubset(self.skills)
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'start_location': {
                'latitude': self.start_location.latitude,
                'longitude': self.start_location.longitude,
                'address': self.start_location.address
            },
            'work_shift': {'earliest': self.work_shift.earliest, 'latest': self.work_shift.latest},
            'break_window': {'earliest': self.break_window.earliest, 'latest': self.break_window.latest},
            'break_duration': self.break_duration,
            'skills': list(self.skills),
            'max_daily_orders': self.max_daily_orders,
            'max_travel_time': self.max_travel_time,
            'hourly_rate': self.hourly_rate,
            'vehicle_type': self.vehicle_type
        }


@dataclass
class WorkOrder:
    """Represents a work order/task"""
    id: str
    location: Location
    priority: Priority
    work_type: WorkOrderType
    service_time: int = 60  # minutes
    time_window: Optional[TimeWindow] = None
    required_skills: Set[str] = field(default_factory=set)
    customer_name: Optional[str] = None
    description: Optional[str] = None
    estimated_value: float = 0.0

    def __post_init__(self):
        """Validate work order data"""
        if self.service_time <= 0:
            raise ValueError("Service time must be positive")

    def get_priority_weight(self, weights: Dict[str, float]) -> float:
        """Get priority weight from configuration"""
        return weights.get(self.priority.value, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'location': {
                'latitude': self.location.latitude,
                'longitude': self.location.longitude,
                'address': self.location.address
            },
            'priority': self.priority.value,
            'work_type': self.work_type.value,
            'service_time': self.service_time,
            'time_window': {
                'earliest': self.time_window.earliest,
                'latest': self.time_window.latest
            } if self.time_window else None,
            'required_skills': list(self.required_skills),
            'customer_name': self.customer_name,
            'description': self.description,
            'estimated_value': self.estimated_value
        }


@dataclass
class Assignment:
    """Represents assignment of a work order to a technician"""
    technician_id: str
    work_order_id: str
    arrival_time: int  # minutes from start of day
    start_time: int  # minutes from start of day
    finish_time: int  # minutes from start of day
    travel_time_to: int = 0  # minutes to reach this location
    sequence_order: int = 0  # order in technician's route

    def total_time(self) -> int:
        """Total time for this assignment including travel and service"""
        return self.travel_time_to + (self.finish_time - self.start_time)


@dataclass
class TechnicianRoute:
    """Represents a complete route for one technician"""
    technician_id: str
    assignments: List[Assignment] = field(default_factory=list)
    total_travel_time: int = 0
    total_service_time: int = 0
    total_time: int = 0
    break_assignment: Optional[Assignment] = None

    def add_assignment(self, assignment: Assignment):
        """Add assignment to route"""
        self.assignments.append(assignment)
        assignment.sequence_order = len(self.assignments)

    def calculate_totals(self):
        """Calculate total times for the route"""
        self.total_service_time = sum(
            (a.finish_time - a.start_time) for a in self.assignments
        )
        self.total_travel_time = sum(a.travel_time_to for a in self.assignments)
        self.total_time = self.total_travel_time + self.total_service_time

    def get_work_order_count(self) -> int:
        """Get number of work orders in this route"""
        return len(self.assignments)


@dataclass
class OptimizationSolution:
    """Complete solution from the optimization"""
    status: SolutionStatus
    routes: List[TechnicianRoute] = field(default_factory=list)
    unassigned_orders: List[str] = field(default_factory=list)
    total_travel_time: int = 0
    total_service_time: int = 0
    objective_value: float = 0.0
    solve_time: float = 0.0  # seconds
    technicians_used: int = 0
    orders_completed: int = 0

    def calculate_summary_stats(self):
        """Calculate summary statistics"""
        self.technicians_used = len([r for r in self.routes if r.assignments])
        self.orders_completed = sum(len(r.assignments) for r in self.routes)
        self.total_travel_time = sum(r.total_travel_time for r in self.routes)
        self.total_service_time = sum(r.total_service_time for r in self.routes)

    def get_completion_rate(self, total_orders: int) -> float:
        """Calculate percentage of orders completed"""
        if total_orders == 0:
            return 100.0
        return (self.orders_completed / total_orders) * 100

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary"""
        return {
            'status': self.status.value,
            'technicians_used': self.technicians_used,
            'orders_completed': self.orders_completed,
            'unassigned_orders_count': len(self.unassigned_orders),
            'total_travel_time_hours': round(self.total_travel_time / 60, 2),
            'total_service_time_hours': round(self.total_service_time / 60, 2),
            'objective_value': round(self.objective_value, 2),
            'solve_time_seconds': round(self.solve_time, 2)
        }


@dataclass
class DistanceMatrix:
    """Distance/time matrix between locations"""
    locations: List[Location]
    durations: List[List[float]]  # seconds
    distances: Optional[List[List[float]]] = None  # meters

    def __post_init__(self):
        """Validate matrix dimensions"""
        n = len(self.locations)
        if len(self.durations) != n:
            raise ValueError("Duration matrix rows must match location count")
        for row in self.durations:
            if len(row) != n:
                raise ValueError("Duration matrix must be square")

    def get_duration(self, from_idx: int, to_idx: int) -> float:
        """Get duration between two location indices"""
        return self.durations[from_idx][to_idx]

    def get_distance(self, from_idx: int, to_idx: int) -> Optional[float]:
        """Get distance between two location indices"""
        if self.distances:
            return self.distances[from_idx][to_idx]
        return None


@dataclass
class OptimizationProblem:
    """Complete problem definition for optimization"""
    technicians: List[Technician] = field(default_factory=list)
    work_orders: List[WorkOrder] = field(default_factory=list)
    distance_matrix: Optional[DistanceMatrix] = None
    config: Optional[Dict[str, Any]] = None

    def add_technician(self, technician: Technician):
        """Add a technician to the problem"""
        if any(t.id == technician.id for t in self.technicians):
            raise ValueError(f"Technician with ID {technician.id} already exists")
        self.technicians.append(technician)

    def add_work_order(self, work_order: WorkOrder):
        """Add a work order to the problem"""
        if any(w.id == work_order.id for w in self.work_orders):
            raise ValueError(f"Work order with ID {work_order.id} already exists")
        self.work_orders.append(work_order)

    def get_all_locations(self) -> List[Location]:
        """Get all unique locations (technician starts + work order locations)"""
        locations = []

        # Add technician start locations
        for tech in self.technicians:
            locations.append(tech.start_location)

        # Add work order locations
        for order in self.work_orders:
            locations.append(order.location)

        return locations

    def validate(self) -> List[str]:
        """Validate problem and return list of issues"""
        issues = []

        if not self.technicians:
            issues.append("No technicians defined")

        if not self.work_orders:
            issues.append("No work orders defined")

        # Check for skill mismatches
        all_required_skills = set()
        for order in self.work_orders:
            all_required_skills.update(order.required_skills)

        all_tech_skills = set()
        for tech in self.technicians:
            all_tech_skills.update(tech.skills)

        missing_skills = all_required_skills - all_tech_skills
        if missing_skills:
            issues.append(f"No technicians have required skills: {missing_skills}")

        return issues

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary"""
        return {
            'technician_count': len(self.technicians),
            'work_order_count': len(self.work_orders),
            'total_locations': len(self.get_all_locations()),
            'validation_issues': self.validate()
        }


# Helper functions for creating instances from data

def create_technician_from_dict(data: Dict[str, Any]) -> Technician:
    """Create Technician from dictionary data"""
    location_data = data['start_location']
    location = Location(
        latitude=location_data['latitude'],
        longitude=location_data['longitude'],
        address=location_data.get('address')
    )

    work_shift = TimeWindow(
        earliest=data['work_shift']['earliest'],
        latest=data['work_shift']['latest']
    )

    break_window = TimeWindow(
        earliest=data['break_window']['earliest'],
        latest=data['break_window']['latest']
    )

    return Technician(
        id=data['id'],
        name=data['name'],
        start_location=location,
        work_shift=work_shift,
        break_window=break_window,
        break_duration=data.get('break_duration', 30),
        skills=set(data.get('skills', [])),
        max_daily_orders=data.get('max_daily_orders', 10),
        max_travel_time=data.get('max_travel_time', 240),
        hourly_rate=data.get('hourly_rate', 0.0),
        vehicle_type=data.get('vehicle_type', 'standard')
    )


def create_work_order_from_dict(data: Dict[str, Any]) -> WorkOrder:
    """Create WorkOrder from dictionary data"""
    location_data = data['location']
    location = Location(
        latitude=location_data['latitude'],
        longitude=location_data['longitude'],
        address=location_data.get('address')
    )

    time_window = None
    if data.get('time_window'):
        time_window = TimeWindow(
            earliest=data['time_window']['earliest'],
            latest=data['time_window']['latest']
        )

    return WorkOrder(
        id=data['id'],
        location=location,
        priority=Priority(data['priority']),
        work_type=WorkOrderType(data['work_type']),
        service_time=data.get('service_time', 60),
        time_window=time_window,
        required_skills=set(data.get('required_skills', [])),
        customer_name=data.get('customer_name'),
        description=data.get('description'),
        estimated_value=data.get('estimated_value', 0.0)
    )