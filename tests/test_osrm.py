import pytest
from unittest.mock import patch, Mock

from core.osrm import OSRMClient, OSRMError
from core.models import Location


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    cfg = {
        "base_url": "http://localhost:5000",
        "table_endpoint": "/table/v1/driving/",
        "timeout": 10,
        "max_locations_per_request": 500,
        "annotations": ["duration"],
    }
    return OSRMClient(cfg)


@pytest.fixture
def two_locs():
    return [
        Location(latitude=3.1073, longitude=101.6067),
        Location(latitude=3.1478, longitude=101.6159),
    ]


def _ok_response(durations, distances=None):
    """Build a mock requests.Response for a successful OSRM table call."""
    m = Mock()
    m.status_code = 200
    payload = {"code": "Ok", "durations": durations}
    if distances is not None:
        payload["distances"] = distances
    m.json.return_value = payload
    return m


# ── health_check ──────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_returns_true_when_ok(self, client):
        with patch("requests.get", return_value=_ok_response([[0.0]])):
            assert client.health_check() is True

    def test_returns_false_when_code_not_ok(self, client):
        m = Mock()
        m.status_code = 200
        m.json.return_value = {"code": "Error"}
        with patch("requests.get", return_value=m):
            assert client.health_check() is False

    def test_returns_false_on_connection_error(self, client):
        with patch("requests.get", side_effect=ConnectionError()):
            assert client.health_check() is False

    def test_returns_false_on_non_200_status(self, client):
        m = Mock()
        m.status_code = 500
        with patch("requests.get", return_value=m):
            assert client.health_check() is False


# ── build_table_url ───────────────────────────────────────────────────────────

class TestBuildTableUrl:
    def test_contains_coordinates(self, client, two_locs):
        url = client.build_table_url(two_locs)
        assert "101.606700" in url
        assert "3.107300" in url

    def test_contains_base_url(self, client, two_locs):
        url = client.build_table_url(two_locs)
        assert url.startswith("http://localhost:5000")

    def test_sources_and_destinations_in_params(self, client, two_locs):
        url = client.build_table_url(two_locs, sources=[0], destinations=[1])
        assert "sources=0" in url
        assert "destinations=1" in url

    def test_too_many_locations_raises(self, client):
        locs = [Location(latitude=3.1, longitude=101.6)] * 501
        with pytest.raises(OSRMError, match="Too many locations"):
            client.build_table_url(locs)

    def test_invalid_latitude_raises(self, client):
        # Location validates coordinates in __post_init__ before the client sees them
        with pytest.raises(ValueError, match="latitude"):
            Location(latitude=91.0, longitude=101.6)

    def test_invalid_longitude_raises(self, client):
        with pytest.raises(ValueError, match="longitude"):
            Location(latitude=3.1, longitude=181.0)


# ── call_table_api ────────────────────────────────────────────────────────────

class TestCallTableApi:
    def test_returns_data_on_success(self, client, two_locs):
        durations = [[0.0, 120.0], [130.0, 0.0]]
        with patch("requests.get", return_value=_ok_response(durations)):
            data = client.call_table_api(two_locs)
        assert data["code"] == "Ok"
        assert data["durations"] == durations

    def test_raises_on_non_200(self, client, two_locs):
        m = Mock()
        m.status_code = 503
        m.text = "Service Unavailable"
        with patch("requests.get", return_value=m):
            with pytest.raises(OSRMError, match="503"):
                client.call_table_api(two_locs)

    def test_raises_on_osrm_error_code(self, client, two_locs):
        m = Mock()
        m.status_code = 200
        m.json.return_value = {"code": "InvalidQuery", "message": "bad input"}
        with patch("requests.get", return_value=m):
            with pytest.raises(OSRMError, match="bad input"):
                client.call_table_api(two_locs)

    def test_raises_on_timeout(self, client, two_locs):
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.Timeout()):
            with pytest.raises(OSRMError, match="timeout"):
                client.call_table_api(two_locs)

    def test_raises_on_connection_error(self, client, two_locs):
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError()):
            with pytest.raises(OSRMError, match="Cannot connect"):
                client.call_table_api(two_locs)

    def test_raises_on_invalid_json(self, client, two_locs):
        import json
        m = Mock()
        m.status_code = 200
        m.json.side_effect = json.JSONDecodeError("", "", 0)
        with patch("requests.get", return_value=m):
            with pytest.raises(OSRMError, match="Invalid JSON"):
                client.call_table_api(two_locs)


# ── create_distance_matrix ────────────────────────────────────────────────────

class TestCreateDistanceMatrix:
    def test_single_location_returns_identity(self, client):
        locs = [Location(latitude=3.1, longitude=101.6)]
        matrix = client.create_distance_matrix(locs)
        assert matrix.durations == [[0.0]]

    def test_empty_locations_raises(self, client):
        with pytest.raises(ValueError):
            client.create_distance_matrix([])

    def test_two_locations_returns_matrix(self, client, two_locs):
        durations_s = [[0.0, 120.0], [130.0, 0.0]]
        with patch("requests.get", return_value=_ok_response(durations_s)):
            matrix = client.create_distance_matrix(two_locs)
        # durations converted from seconds to minutes (÷60)
        assert matrix.durations[0][1] == pytest.approx(2.0)
        assert matrix.durations[1][0] == pytest.approx(130.0 / 60.0)

    def test_null_cells_become_nan(self, client, two_locs):
        import math
        durations_s = [[0.0, None], [None, 0.0]]
        with patch("requests.get", return_value=_ok_response(durations_s)):
            matrix = client.create_distance_matrix(two_locs)
        assert math.isnan(matrix.durations[0][1])
        assert math.isnan(matrix.durations[1][0])
