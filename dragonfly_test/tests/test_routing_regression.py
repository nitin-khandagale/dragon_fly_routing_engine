from pathlib import Path
import sys

TEST_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEST_ROOT.parent))

from api.models import RouteRequest
from engine.routing_engine import RoutingEngine


BASELINE = {
    "start_lat": 37.79448372,
    "start_lon": -122.40547051,
    "goal_lat": 37.78695766,
    "goal_lon": -122.38931347,
    "start_altitude_meters": 0,
    "goal_altitude_meters": 0,
    "minimum_transit_altitude_meters": 30,
    "max_altitude_meters": 300,
}


def get(objective="distance"):
    request = RouteRequest(
        **BASELINE,
        objective=objective,
        vehicle_profile="default_multirotor",
    )

    result = RoutingEngine().compute_route(request)

    if hasattr(result, "model_dump"):
        return result.model_dump()

    if hasattr(result, "dict"):
        return result.dict()

    return result


def test_sf_baseline_success():
    result = get()

    assert result["status"] == "success"
    assert result["waypoints"]


def test_exact_endpoints():
    waypoints = get()["waypoints"]

    assert waypoints[0]["type"] == "exact_start"
    assert waypoints[-1]["type"] == "exact_goal"

    assert waypoints[0]["latitude"] == BASELINE["start_lat"]
    assert waypoints[0]["longitude"] == BASELINE["start_lon"]

    assert waypoints[-1]["latitude"] == BASELINE["goal_lat"]
    assert waypoints[-1]["longitude"] == BASELINE["goal_lon"]


def test_altitude_bounds():
    altitudes = [
        waypoint["altitude_meters"]
        for waypoint in get()["waypoints"]
    ]

    assert min(altitudes) >= BASELINE["start_altitude_meters"]
    assert max(altitudes) <= BASELINE["max_altitude_meters"]


def test_energy_objective_produces_energy_optimized_route():
    result = get(objective="energy")

    assert result["objective"] == "energy"
    assert result["vehicle"]["profile"] == "default_multirotor"

    metrics = result["metrics"]

    assert metrics["energy_joules"] > 0
    assert metrics["energy_wh"] > 0
    assert metrics["battery_percent"] > 0

    # Current known-good behavior:
    # energy routing stays at the minimum transit altitude.
    assert max(
        waypoint["altitude_meters"]
        for waypoint in result["waypoints"]
    ) == 30.0


def test_distance_and_energy_objectives_produce_different_routes():
    distance_result = get(objective="distance")
    energy_result = get(objective="energy")

    distance_metrics = distance_result["metrics"]
    energy_metrics = energy_result["metrics"]

    # Distance objective finds a shorter horizontal route.
    assert (
        distance_metrics["distance_meters"]
        < energy_metrics["distance_meters"]
    )

    # Energy objective consumes less modeled energy.
    assert (
        energy_metrics["energy_joules"]
        < distance_metrics["energy_joules"]
    )

    # The objectives make different altitude decisions.
    assert (
        max(
            waypoint["altitude_meters"]
            for waypoint in distance_result["waypoints"]
        )
        >
        max(
            waypoint["altitude_meters"]
            for waypoint in energy_result["waypoints"]
        )
    )


def test_energy_metrics_are_consistent():
    result = get(objective="energy")
    metrics = result["metrics"]

    assert abs(
        metrics["energy_wh"] * 3600
        - metrics["energy_joules"]
    ) < 1e-6

    assert abs(
        metrics["battery_percent"]
        - (
            metrics["energy_wh"]
            / 150.0
            * 100.0
        )
    ) < 1e-6

    assert (
        metrics["3d_distance_meters"]
        >= metrics["distance_meters"]
    )