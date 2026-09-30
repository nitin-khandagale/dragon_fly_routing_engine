import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


BASELINE_REQUEST = {
    "start_lat": 37.79448372,
    "start_lon": -122.40547051,
    "goal_lat": 37.78695766,
    "goal_lon": -122.38931347,
    "start_altitude_meters": 0,
    "goal_altitude_meters": 0,
    "minimum_transit_altitude_meters": 30,
    "max_altitude_meters": 300,
    "objective": "distance",
    "vehicle_profile": "default_multirotor",
}


def test_route_api_success():
    response = client.post("/route", json=BASELINE_REQUEST)

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "success"
    assert data["objective"] == "distance"
    assert data["vehicle"]["profile"] == "default_multirotor"

    assert "metrics" in data
    assert "waypoints" in data
    assert data["waypoints"]


def test_route_api_rejects_missing_coordinates():
    request = BASELINE_REQUEST.copy()
    del request["start_lat"]

    response = client.post("/route", json=request)

    assert response.status_code == 422

def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data == {
        "status": "ok",
        "service": "dragonfly-routing-engine",
        "version": "1.2",
    }