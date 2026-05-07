"""
Integration tests for scenario CRUD routes.
Uses a tmp_path-isolated SCENARIOS_DIR — no real filesystem side-effects.
"""
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app():
    with patch("main.validate_config", return_value=True), \
         patch("main.validate_osrm_connection", return_value=False):
        from main import app as _app
        from api.routers.health import _osrm_health_cache
        _osrm_health_cache.update({"ok": False, "ts": float("inf")})
        return _app


@pytest.fixture
def client(app, tmp_path, monkeypatch):
    """Fresh client with an empty tmp SCENARIOS_DIR for each test."""
    monkeypatch.setattr("api.routers.scenarios.SCENARIOS_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def scenario_payload():
    return {
        "name": "Test Scenario",
        "technicians": [{"id": "T1", "name": "Alice"}],
        "work_orders": [{"id": "WO1", "description": "Fix it"}],
        "city": "Kuala Lumpur",
        "source": "manual"
    }


# ── POST /vrp/scenarios ───────────────────────────────────────────────────────

class TestSaveScenario:
    def test_creates_scenario(self, client, scenario_payload):
        r = client.post("/vrp/scenarios", json=scenario_payload)
        assert r.status_code == 201

    def test_returns_slug_and_name(self, client, scenario_payload):
        data = client.post("/vrp/scenarios", json=scenario_payload).json()
        assert data["slug"] == "test-scenario"
        assert data["name"] == "Test Scenario"

    def test_returns_created_at(self, client, scenario_payload):
        data = client.post("/vrp/scenarios", json=scenario_payload).json()
        assert "created_at" in data

    def test_slug_collision_returns_409(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        r = client.post("/vrp/scenarios", json=scenario_payload)
        assert r.status_code == 409

    def test_different_name_same_slug_returns_409(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        payload2 = {**scenario_payload, "name": "Test  Scenario"}  # extra space → same slug
        r = client.post("/vrp/scenarios", json=payload2)
        assert r.status_code == 409

    def test_empty_name_returns_422(self, client, scenario_payload):
        r = client.post("/vrp/scenarios", json={**scenario_payload, "name": ""})
        assert r.status_code == 422

    def test_name_too_long_returns_422(self, client, scenario_payload):
        r = client.post("/vrp/scenarios", json={**scenario_payload, "name": "x" * 81})
        assert r.status_code == 422

    def test_invalid_name_only_special_chars_returns_400(self, client, scenario_payload):
        r = client.post("/vrp/scenarios", json={**scenario_payload, "name": "!!!"})
        assert r.status_code == 400


# ── GET /vrp/scenarios ────────────────────────────────────────────────────────

class TestListScenarios:
    def test_empty_list_when_no_scenarios(self, client):
        r = client.get("/vrp/scenarios")
        assert r.status_code == 200
        assert r.json() == []

    def test_lists_saved_scenario(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        data = client.get("/vrp/scenarios").json()
        assert len(data) == 1
        assert data[0]["slug"] == "test-scenario"
        assert data[0]["name"] == "Test Scenario"

    def test_metadata_only_no_full_data(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        item = client.get("/vrp/scenarios").json()[0]
        assert "technicians" not in item
        assert "work_orders" not in item

    def test_tech_and_order_counts(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        item = client.get("/vrp/scenarios").json()[0]
        assert item["tech_count"] == 1
        assert item["order_count"] == 1

    def test_lists_multiple_scenarios(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        client.post("/vrp/scenarios", json={**scenario_payload, "name": "Second"})
        data = client.get("/vrp/scenarios").json()
        assert len(data) == 2


# ── GET /vrp/scenarios/{slug} ─────────────────────────────────────────────────

class TestLoadScenario:
    def test_loads_saved_scenario(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        r = client.get("/vrp/scenarios/test-scenario")
        assert r.status_code == 200

    def test_full_data_returned(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        data = client.get("/vrp/scenarios/test-scenario").json()
        assert "technicians" in data
        assert "work_orders" in data

    def test_technician_data_intact(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        data = client.get("/vrp/scenarios/test-scenario").json()
        assert data["technicians"][0]["id"] == "T1"

    def test_not_found_returns_404(self, client):
        assert client.get("/vrp/scenarios/does-not-exist").status_code == 404

    def test_path_traversal_blocked(self, client):
        # Starlette normalises `..` in the URL path before routing; either 400
        # (our guard) or 404 (never matched) is a safe outcome.
        assert client.get("/vrp/scenarios/../etc/passwd").status_code in (400, 404)

    def test_path_traversal_with_dots_blocked(self, client):
        assert client.get("/vrp/scenarios/..%2Fetc%2Fpasswd").status_code in (400, 404)


# ── DELETE /vrp/scenarios/{slug} ─────────────────────────────────────────────

class TestDeleteScenario:
    def test_deletes_scenario(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        r = client.delete("/vrp/scenarios/test-scenario")
        assert r.status_code == 200

    def test_deleted_scenario_no_longer_listable(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        client.delete("/vrp/scenarios/test-scenario")
        assert client.get("/vrp/scenarios").json() == []

    def test_deleted_scenario_not_loadable(self, client, scenario_payload):
        client.post("/vrp/scenarios", json=scenario_payload)
        client.delete("/vrp/scenarios/test-scenario")
        assert client.get("/vrp/scenarios/test-scenario").status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        assert client.delete("/vrp/scenarios/does-not-exist").status_code == 404

    def test_delete_path_traversal_blocked(self, client):
        assert client.delete("/vrp/scenarios/../etc/passwd").status_code in (400, 404)
