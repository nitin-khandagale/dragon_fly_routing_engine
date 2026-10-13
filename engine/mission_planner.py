"""Ordered multi-waypoint mission orchestration for DragonFly.

This module deliberately delegates each leg to the existing RoutingEngine.
It does not implement waypoint-order optimization or battery feasibility;
those belong to later milestones.
"""

from typing import Literal

from pydantic import BaseModel, Field

from api.models import RouteRequest
from engine.routing_engine import RouteComputationError, RoutingEngine

MAX_ALTITUDE_METERS = 300.0
MIN_TRANSIT_ALTITUDE_METERS = 15.0


class MissionPoint(BaseModel):
    """A required mission stop in geographic coordinates."""

    id: str | None = Field(default=None, min_length=1, max_length=80)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    altitude_meters: float = Field(default=0.0, ge=0.0, le=MAX_ALTITUDE_METERS)


class MissionRequest(BaseModel):
    """A mission with a fixed, customer-defined waypoint order."""

    start: MissionPoint
    waypoints: list[MissionPoint] = Field(min_length=1, max_length=25)
    destination: MissionPoint
    return_to_start: bool = False
    objective: Literal["distance", "energy"] = "distance"
    vehicle_profile: Literal["default_multirotor"] = "default_multirotor"
    minimum_transit_altitude_meters: float = Field(
        default=30.0,
        ge=MIN_TRANSIT_ALTITUDE_METERS,
        le=MAX_ALTITUDE_METERS,
    )
    max_altitude_meters: float = Field(default=MAX_ALTITUDE_METERS, ge=15.0, le=MAX_ALTITUDE_METERS)


class MissionPlanner:
    """Plan ordered missions by routing each consecutive pair of stops."""

    def __init__(self, routing_engine: RoutingEngine):
        self.routing_engine = routing_engine

    @staticmethod
    def _route_request(
        origin: MissionPoint,
        destination: MissionPoint,
        mission: MissionRequest,
    ) -> RouteRequest:
        """Translate a mission leg into the existing point-to-point contract."""
        return RouteRequest(
            start_lat=origin.latitude,
            start_lon=origin.longitude,
            goal_lat=destination.latitude,
            goal_lon=destination.longitude,
            start_altitude_meters=origin.altitude_meters,
            goal_altitude_meters=destination.altitude_meters,
            minimum_transit_altitude_meters=mission.minimum_transit_altitude_meters,
            max_altitude_meters=mission.max_altitude_meters,
            objective=mission.objective,
            vehicle_profile=mission.vehicle_profile,
        )

    def plan_mission(self, mission: MissionRequest) -> dict:
        """Calculate all legs, then return a mission-level aggregate.

        A mission is successful only when every required leg succeeds. The
        response includes per-leg route data and a combined trajectory. The
        duplicate boundary point between adjacent legs is omitted from the
        combined trajectory, while every leg's original route is preserved.
        """
        stops: list[tuple[str, MissionPoint]] = [("start", mission.start)]
        for index, point in enumerate(mission.waypoints, start=1):
            stops.append((point.id or f"waypoint_{index}", point))
        stops.append(("destination", mission.destination))
        if mission.return_to_start:
            stops.append(("return_to_start", mission.start))

        segments: list[dict] = []
        combined_waypoints: list[dict] = []
        totals = {
            "distance_meters": 0.0,
            "3d_distance_meters": 0.0,
            "total_climb_meters": 0.0,
            "total_descent_meters": 0.0,
            "flight_time_seconds": 0.0,
            "energy_joules": 0.0,
            "energy_wh": 0.0,
        }
        battery_capacity_wh = None

        for segment_index, ((from_id, origin), (to_id, target)) in enumerate(
            zip(stops, stops[1:]), start=1
        ):
            segment_id = f"segment_{segment_index}"
            try:
                result = self.routing_engine.compute_route(
                    self._route_request(origin, target, mission)
                )
            except RouteComputationError as exc:
                detail = {
                    "message": "Mission could not be completed because a required segment failed.",
                    "failed_segment": segment_id,
                    "from_stop": from_id,
                    "to_stop": to_id,
                    "route_error": exc.detail,
                }
                raise RouteComputationError(exc.status_code, detail) from exc

            metrics = result.get("metrics") or {}
            for key in totals:
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    totals[key] += float(value)
            if battery_capacity_wh is None:
                battery_capacity_wh = (result.get("vehicle") or {}).get("battery_capacity_wh")

            route_waypoints = result.get("waypoints") or []
            tagged_waypoints = []
            for waypoint in route_waypoints:
                tagged = dict(waypoint)
                tagged["segment_id"] = segment_id
                tagged_waypoints.append(tagged)

            segments.append(
                {
                    "segment_id": segment_id,
                    "from_stop": from_id,
                    "to_stop": to_id,
                    "status": result.get("status", "success"),
                    "metrics": metrics,
                    "total_waypoints": len(route_waypoints),
                    "waypoints": tagged_waypoints,
                    "safety": result.get("safety"),
                }
            )

            if tagged_waypoints:
                # Keep the first point of the first leg, then skip the first
                # point on each later leg to avoid duplicated stop coordinates.
                points_to_add = tagged_waypoints if not combined_waypoints else tagged_waypoints[1:]
                combined_waypoints.extend(points_to_add)

        if battery_capacity_wh:
            totals["battery_percent"] = totals["energy_wh"] / battery_capacity_wh * 100.0
        else:
            totals["battery_percent"] = None

        for step, waypoint in enumerate(combined_waypoints, start=1):
            waypoint["step"] = step

        return {
            "status": "success",
            "mission_type": "ordered_multi_waypoint",
            "objective": mission.objective,
            "vehicle": {
                "profile": mission.vehicle_profile,
                "battery_capacity_wh": battery_capacity_wh,
            },
            "return_to_start": mission.return_to_start,
            "stop_sequence": [
                {
                    "id": stop_id,
                    "latitude": point.latitude,
                    "longitude": point.longitude,
                    "altitude_meters": point.altitude_meters,
                }
                for stop_id, point in stops
            ],
            "total_segments": len(segments),
            "metrics": totals,
            "safety": {
                "all_segments_succeeded": True,
                "all_segments_returned_existing_route_safety_checks": True,
                "note": "Route checks are inherited from the point-to-point engine; this is not a real-world flight authorization or safety guarantee.",
            },
            "segments": segments,
            "total_waypoints": len(combined_waypoints),
            "waypoints": combined_waypoints,
        }
