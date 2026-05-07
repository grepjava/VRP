from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict


class LocationModel(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = None


class TimeWindowModel(BaseModel):
    earliest: int = Field(..., ge=0)
    latest: int = Field(..., ge=0)

    @model_validator(mode='after')
    def validate_time_window(self):
        if self.latest < self.earliest:
            raise ValueError('Latest time must be >= earliest time')
        return self


class TechnicianModel(BaseModel):
    id: str
    name: str
    start_location: LocationModel
    work_shift: TimeWindowModel
    break_window: TimeWindowModel
    break_duration: int = Field(30, ge=1)
    skills: List[str] = []
    max_daily_orders: int = Field(10, ge=1)
    max_travel_time: int = Field(240, ge=1)
    hourly_rate: float = Field(0.0, ge=0)
    vehicle_type: str = "standard"
    drop_return_trip: Optional[bool] = False


class WorkOrderModel(BaseModel):
    id: str
    location: LocationModel
    priority: str = Field(..., pattern="^(low|medium|high|critical|emergency)$")
    work_type: str = Field(..., pattern="^(maintenance|repair|inspection|installation|emergency)$")
    service_time: int = Field(60, ge=1)
    time_window: Optional[TimeWindowModel] = None
    required_skills: List[str] = []
    customer_name: Optional[str] = None
    description: Optional[str] = None
    estimated_value: float = Field(0.0, ge=0)


class OptimizationRequestModel(BaseModel):
    technicians: List[TechnicianModel] = Field(..., min_length=1)
    work_orders: List[WorkOrderModel] = Field(..., min_length=1)
    config: Optional[Dict[str, Any]] = None
    use_concurrent: Optional[bool] = None
    priority: Optional[int] = 1

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "technicians": [
                    {
                        "id": "TECH001",
                        "name": "John Smith",
                        "start_location": {"latitude": 3.1073, "longitude": 101.6067, "address": "Petaling Jaya"},
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
                        "location": {"latitude": 3.1478, "longitude": 101.6159, "address": "Damansara Heights"},
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
    problems: List[OptimizationRequestModel] = Field(..., min_length=1, max_length=10)
    timeout: Optional[float] = None

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
    technician_id: str
    work_order_id: str
    arrival_time: int
    start_time: int
    finish_time: int
    travel_time_to: int
    sequence_order: int


class TechnicianRouteModel(BaseModel):
    technician_id: str
    assignments: List[AssignmentModel]
    total_travel_time: int
    total_service_time: int
    total_time: int
    work_order_count: int
    break_assignment: Optional[AssignmentModel]


class MemoryInfoModel(BaseModel):
    gpu_used_mb: float
    gpu_total_mb: float
    gpu_usage_percent: float
    pinned_used_mb: Optional[float] = None
    pinned_total_mb: Optional[float] = None


class OptimizationResponseModel(BaseModel):
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
    concurrent_execution: Optional[bool] = None
    solver_id: Optional[int] = None
    memory_info: Optional[MemoryInfoModel] = None


class BatchOptimizationResponseModel(BaseModel):
    results: List[OptimizationResponseModel]
    total_time: float
    concurrent_execution: bool
    success_count: int
    failure_count: int
    statistics: Dict[str, Any]
    memory_summary: Optional[MemoryInfoModel] = None


class ErrorResponseModel(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: str
    request_id: Optional[str] = None


class HealthResponseModel(BaseModel):
    status: str
    timestamp: str
    version: str
    services: Dict[str, str]
    concurrent_execution: Dict[str, Any]
    memory_info: Optional[MemoryInfoModel] = None


class SaveScenarioRequestModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    technicians: List[Dict[str, Any]]
    work_orders: List[Dict[str, Any]]
    city: str = ""
    source: str = "manual"


class DemoGenerateRequestModel(BaseModel):
    city: str = Field("Kuala Lumpur", description="City name for geocoding")
    num_orders: int = Field(15, ge=1, le=50)
    num_technicians: int = Field(4, ge=1, le=15)
