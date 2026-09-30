import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from api.models import RouteRequest


def test_default_vehicle_profile():
    request = RouteRequest(
        start_lat=37.79448372,
        start_lon=-122.40547051,
        goal_lat=37.78695766,
        goal_lon=-122.38931347,
        start_altitude_meters=0,
        goal_altitude_meters=0,
        minimum_transit_altitude_meters=30,
        max_altitude_meters=300,
    )

    assert request.vehicle_profile == "default_multirotor"


def test_explicit_vehicle_profile():
    request = RouteRequest(
        start_lat=37.79448372,
        start_lon=-122.40547051,
        goal_lat=37.78695766,
        goal_lon=-122.38931347,
        start_altitude_meters=0,
        goal_altitude_meters=0,
        minimum_transit_altitude_meters=30,
        max_altitude_meters=300,
        vehicle_profile="default_multirotor",
    )

    assert request.vehicle_profile == "default_multirotor"