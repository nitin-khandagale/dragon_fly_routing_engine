from fastapi import APIRouter, HTTPException

from api.models import RouteRequest
from engine.routing_engine import RouteComputationError, RoutingEngine


router = APIRouter()
routing_engine = RoutingEngine()


@router.post("/route")
def calculate_route(req: RouteRequest):
    try:
        return routing_engine.compute_route(req)
    except RouteComputationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
