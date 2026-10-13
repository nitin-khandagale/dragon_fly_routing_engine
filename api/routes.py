from fastapi import APIRouter, HTTPException

from api.models import RouteRequest
from engine.mission_planner import MissionPlanner, MissionRequest
from engine.routing_engine import RouteComputationError, RoutingEngine

router = APIRouter()
routing_engine = RoutingEngine()
mission_planner = MissionPlanner(routing_engine)


@router.post("/route")
def calculate_route(req: RouteRequest):
    """Calculate a single point-to-point route (existing API)."""
    try:
        return routing_engine.compute_route(req)
    except RouteComputationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc


@router.post("/mission")
def calculate_mission(req: MissionRequest):
    """Calculate a fixed-order multi-waypoint mission."""
    try:
        return mission_planner.plan_mission(req)
    except RouteComputationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
