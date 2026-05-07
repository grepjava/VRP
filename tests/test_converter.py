import pytest
from core.converter import (
    json_to_location, json_to_time_window, json_to_technician,
    json_to_work_order, json_to_optimization_problem, ConversionError,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_location():
    return {"latitude": 3.1073, "longitude": 101.6067, "address": "Petaling Jaya"}


@pytest.fixture
def valid_technician():
    return {
        "id": "T1",
        "name": "Alice",
        "start_location": {"latitude": 3.1073, "longitude": 101.6067},
        "work_shift": {"earliest": 480, "latest": 1020},
        "break_window": {"earliest": 720, "latest": 780},
        "break_duration": 60,
        "skills": ["electrical"],
        "max_daily_orders": 8,
        "max_travel_time": 300,
        "hourly_rate": 50.0,
        "vehicle_type": "van",
    }


@pytest.fixture
def valid_work_order():
    return {
        "id": "WO1",
        "location": {"latitude": 3.1478, "longitude": 101.6159},
        "priority": "high",
        "work_type": "repair",
        "service_time": 90,
        "required_skills": ["electrical"],
        "customer_name": "Acme",
        "estimated_value": 200.0,
    }


# ── json_to_location ──────────────────────────────────────────────────────────

class TestJsonToLocation:
    def test_valid_with_address(self, valid_location):
        loc = json_to_location(valid_location)
        assert loc.latitude == 3.1073
        assert loc.longitude == 101.6067
        assert loc.address == "Petaling Jaya"

    def test_valid_without_address(self):
        loc = json_to_location({"latitude": 1.0, "longitude": 2.0})
        assert loc.address is None

    def test_missing_latitude(self):
        with pytest.raises(ConversionError):
            json_to_location({"longitude": 101.6})

    def test_missing_longitude(self):
        with pytest.raises(ConversionError):
            json_to_location({"latitude": 3.1})

    def test_invalid_latitude_type(self):
        with pytest.raises(ConversionError):
            json_to_location({"latitude": "not_a_number", "longitude": 101.6})

    def test_empty_dict(self):
        with pytest.raises(ConversionError):
            json_to_location({})


# ── json_to_time_window ───────────────────────────────────────────────────────

class TestJsonToTimeWindow:
    def test_valid(self):
        tw = json_to_time_window({"earliest": 480, "latest": 1020})
        assert tw.earliest == 480
        assert tw.latest == 1020

    def test_equal_bounds(self):
        tw = json_to_time_window({"earliest": 720, "latest": 720})
        assert tw.earliest == tw.latest

    def test_missing_earliest(self):
        with pytest.raises(ConversionError):
            json_to_time_window({"latest": 1020})

    def test_missing_latest(self):
        with pytest.raises(ConversionError):
            json_to_time_window({"earliest": 480})

    def test_invalid_type(self):
        with pytest.raises(ConversionError):
            json_to_time_window({"earliest": "eight", "latest": 1020})


# ── json_to_technician ────────────────────────────────────────────────────────

class TestJsonToTechnician:
    def test_valid(self, valid_technician):
        tech = json_to_technician(valid_technician)
        assert tech.id == "T1"
        assert tech.name == "Alice"
        assert "electrical" in tech.skills

    def test_missing_id(self, valid_technician):
        del valid_technician["id"]
        with pytest.raises(ConversionError):
            json_to_technician(valid_technician)

    def test_missing_start_location(self, valid_technician):
        del valid_technician["start_location"]
        with pytest.raises(ConversionError):
            json_to_technician(valid_technician)

    def test_missing_work_shift(self, valid_technician):
        del valid_technician["work_shift"]
        with pytest.raises(ConversionError):
            json_to_technician(valid_technician)


# ── json_to_work_order ────────────────────────────────────────────────────────

class TestJsonToWorkOrder:
    def test_valid(self, valid_work_order):
        wo = json_to_work_order(valid_work_order)
        assert wo.id == "WO1"
        assert wo.service_time == 90

    def test_missing_id(self, valid_work_order):
        del valid_work_order["id"]
        with pytest.raises(ConversionError):
            json_to_work_order(valid_work_order)

    def test_missing_location(self, valid_work_order):
        del valid_work_order["location"]
        with pytest.raises(ConversionError):
            json_to_work_order(valid_work_order)

    def test_missing_priority(self, valid_work_order):
        del valid_work_order["priority"]
        with pytest.raises(ConversionError):
            json_to_work_order(valid_work_order)

    def test_missing_work_type(self, valid_work_order):
        del valid_work_order["work_type"]
        with pytest.raises(ConversionError):
            json_to_work_order(valid_work_order)


# ── json_to_optimization_problem ─────────────────────────────────────────────

class TestJsonToOptimizationProblem:
    def test_valid(self, valid_technician, valid_work_order):
        data = {"technicians": [valid_technician], "work_orders": [valid_work_order]}
        problem = json_to_optimization_problem(data)
        assert len(problem.technicians) == 1
        assert len(problem.work_orders) == 1

    def test_multiple_entries(self, valid_technician, valid_work_order):
        t2 = {**valid_technician, "id": "T2", "name": "Bob"}
        wo2 = {**valid_work_order, "id": "WO2"}
        data = {"technicians": [valid_technician, t2], "work_orders": [valid_work_order, wo2]}
        problem = json_to_optimization_problem(data)
        assert len(problem.technicians) == 2
        assert len(problem.work_orders) == 2

    def test_empty_lists(self):
        problem = json_to_optimization_problem({"technicians": [], "work_orders": []})
        assert len(problem.technicians) == 0
        assert len(problem.work_orders) == 0

    def test_config_passed_through(self, valid_technician, valid_work_order):
        cfg = {"time_limit": 30}
        data = {"technicians": [valid_technician], "work_orders": [valid_work_order], "config": cfg}
        problem = json_to_optimization_problem(data)
        assert problem.config == cfg

    def test_invalid_technician_raises(self, valid_work_order):
        with pytest.raises(ConversionError):
            json_to_optimization_problem({"technicians": [{"bad": "data"}], "work_orders": [valid_work_order]})
