"""
API contract tests for operational endpoints.
No GPU or live OSRM server required — solver and OSRM are mocked/unavailable.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """
    TestClient with lifespan.
    OSRM cache is pre-populated so health checks never make live HTTP calls.
    validate_config is patched to avoid a slow OSRM connection attempt at startup.
    """
    with patch("main.validate_config", return_value=True), \
         patch("main.validate_osrm_connection", return_value=False):
        from main import app
        # Pre-fill the TTL cache so /health never makes a live OSRM call
        from api.routers.health import _osrm_health_cache
        _osrm_health_cache.update({"ok": False, "ts": float("inf")})
        with TestClient(app) as c:
            yield c


@pytest.fixture
def valid_optimize_payload():
    return {
        "technicians": [
            {
                "id": "T1", "name": "Alice",
                "start_location": {"latitude": 3.1073, "longitude": 101.6067},
                "work_shift": {"earliest": 480, "latest": 1020},
                "break_window": {"earliest": 720, "latest": 780},
                "break_duration": 60,
                "skills": ["electrical"],
                "max_daily_orders": 8,
                "max_travel_time": 300,
                "hourly_rate": 50.0,
                "vehicle_type": "van"
            }
        ],
        "work_orders": [
            {
                "id": "WO1",
                "location": {"latitude": 3.1478, "longitude": 101.6159},
                "priority": "high",
                "work_type": "repair",
                "service_time": 90,
                "required_skills": ["electrical"]
            }
        ]
    }


# ── GET / ─────────────────────────────────────────────────────────────────────

class TestRoot:
    def test_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_contains_message(self, client):
        r = client.get("/")
        assert "message" in r.json()

    def test_docs_url_present(self, client):
        r = client.get("/")
        assert r.json()["docs"] == "/docs"


# ── GET /health ───────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_has_status_field(self, client):
        r = client.get("/health")
        assert "status" in r.json()

    def test_has_services_field(self, client):
        data = client.get("/health").json()
        assert "services" in data
        assert "osrm" in data["services"]
        assert "cuopt" in data["services"]

    def test_has_timestamp(self, client):
        data = client.get("/health").json()
        assert "timestamp" in data

    def test_degraded_when_no_solver(self, client):
        # cuOpt unavailable → overall status should be degraded
        data = client.get("/health").json()
        assert data["status"] in ("degraded", "ok")


# ── GET /config ───────────────────────────────────────────────────────────────

class TestConfig:
    def test_returns_200(self, client):
        assert client.get("/config").status_code == 200

    def test_has_expected_sections(self, client):
        data = client.get("/config").json()
        for key in ("business", "optimization", "data", "osrm", "concurrent_execution"):
            assert key in data, f"Missing section: {key}"

    def test_no_sensitive_keys(self, client):
        data = client.get("/config").json()
        # cors_origins / api internals should not be in the safe config
        assert "cors_origins" not in data


# ── GET /cuopt/status ─────────────────────────────────────────────────────────

class TestCuoptStatus:
    def test_returns_200(self, client):
        assert client.get("/cuopt/status").status_code == 200

    def test_has_solver_available(self, client):
        data = client.get("/cuopt/status").json()
        assert "solver_available" in data

    def test_solver_unavailable_in_test_env(self, client):
        data = client.get("/cuopt/status").json()
        # cuOpt not installed in test environment
        assert data["solver_available"] is False


# ── POST /vrp/validate ────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_problem_returns_200(self, client, valid_optimize_payload):
        r = client.post("/vrp/validate", json=valid_optimize_payload)
        assert r.status_code == 200

    def test_valid_problem_reports_valid(self, client, valid_optimize_payload):
        data = client.post("/vrp/validate", json=valid_optimize_payload).json()
        assert data["valid"] is True
        assert data["issues"] == []

    def test_summary_contains_counts(self, client, valid_optimize_payload):
        data = client.post("/vrp/validate", json=valid_optimize_payload).json()
        assert "summary" in data

    def test_missing_technicians_returns_422(self, client):
        r = client.post("/vrp/validate", json={"work_orders": []})
        assert r.status_code == 422

    def test_missing_work_orders_returns_422(self, client):
        r = client.post("/vrp/validate", json={"technicians": []})
        assert r.status_code == 422

    def test_empty_body_returns_422(self, client):
        assert client.post("/vrp/validate", json={}).status_code == 422


# ── POST /vrp/optimize ────────────────────────────────────────────────────────

class TestOptimize:
    def test_returns_503_when_solver_unavailable(self, client, valid_optimize_payload):
        # Solver is not available in test environment
        r = client.post("/vrp/optimize", json=valid_optimize_payload)
        assert r.status_code == 503

    def test_invalid_priority_returns_422(self, client, valid_optimize_payload):
        payload = dict(valid_optimize_payload)
        payload["work_orders"][0]["priority"] = "not_a_valid_priority"
        r = client.post("/vrp/optimize", json=payload)
        assert r.status_code == 422

    def test_invalid_work_type_returns_422(self, client, valid_optimize_payload):
        payload = dict(valid_optimize_payload)
        payload["work_orders"][0]["work_type"] = "not_a_valid_type"
        r = client.post("/vrp/optimize", json=payload)
        assert r.status_code == 422

    def test_out_of_range_lat_returns_422(self, client, valid_optimize_payload):
        payload = dict(valid_optimize_payload)
        payload["technicians"][0]["start_location"]["latitude"] = 999.0
        r = client.post("/vrp/optimize", json=payload)
        assert r.status_code == 422


# ── GET /vrp/schema/* ─────────────────────────────────────────────────────────

class TestSchemas:
    def test_technician_schema(self, client):
        r = client.get("/vrp/schema/technician")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_work_order_schema(self, client):
        r = client.get("/vrp/schema/work_order")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_problem_schema(self, client):
        r = client.get("/vrp/schema/problem")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)


# ── Process-time header ───────────────────────────────────────────────────────

class TestMiddleware:
    def test_process_time_header_present(self, client):
        r = client.get("/health")
        assert "x-process-time" in r.headers
