from pathlib import Path
import sys
TEST_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TEST_ROOT.parent))
from api.models import RouteRequest
from engine.routing_engine import RoutingEngine

BASELINE={"start_lat":37.79448372,"start_lon":-122.40547051,
"goal_lat":37.78695766,"goal_lon":-122.38931347,"start_altitude_meters":0,
"goal_altitude_meters":0,"minimum_transit_altitude_meters":30,"max_altitude_meters":300}

def get():
    r=RoutingEngine().compute_route(RouteRequest(**BASELINE))
    if hasattr(r,"model_dump"): return r.model_dump()
    if hasattr(r,"dict"): return r.dict()
    return r

def test_sf_baseline_success():
    d=get(); assert d["status"]=="success"; assert d["waypoints"]

def test_exact_endpoints():
    w=get()["waypoints"]
    assert w[0]["type"]=="exact_start" and w[-1]["type"]=="exact_goal"
    assert w[0]["latitude"]==BASELINE["start_lat"] and w[0]["longitude"]==BASELINE["start_lon"]
    assert w[-1]["latitude"]==BASELINE["goal_lat"] and w[-1]["longitude"]==BASELINE["goal_lon"]

def test_altitude_bounds():
    a=[w["altitude_meters"] for w in get()["waypoints"]]
    assert min(a)>=BASELINE["start_altitude_meters"] and max(a)<=BASELINE["max_altitude_meters"]
