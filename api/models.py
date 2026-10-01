from pydantic import BaseModel, Field
from typing import Literal


LAYER_HEIGHT_METERS = 15.0
MAX_ALTITUDE_METERS = 300.0


class RouteRequest(BaseModel):
    start_lat: float
    start_lon: float

    goal_lat: float
    goal_lon: float

    start_altitude_meters: float = Field(
        default=0.0,
        ge=0.0,
        le=MAX_ALTITUDE_METERS,
    )

    goal_altitude_meters: float = Field(
        default=0.0,
        ge=0.0,
        le=MAX_ALTITUDE_METERS,
    )

    max_altitude_meters: float = Field(
        default=MAX_ALTITUDE_METERS,
        ge=0.0,
        le=MAX_ALTITUDE_METERS,
    )

    minimum_transit_altitude_meters: float = Field(
        default=LAYER_HEIGHT_METERS,
        ge=LAYER_HEIGHT_METERS,
        le=MAX_ALTITUDE_METERS,
    )

    objective: Literal["distance", "energy"] = "distance"
    vehicle_profile: Literal["default_multirotor"] = "default_multirotor"



class VehicleInfo(BaseModel):
    profile: str
    battery_capacity_wh: float


class RouteMetrics(BaseModel):
    distance_meters: float
    model_config = {"populate_by_name": True}

    three_d_distance_meters: float = Field(
        alias="3d_distance_meters"
    )

    total_climb_meters: float
    total_descent_meters: float
    flight_time_seconds: float
    energy_joules: float
    energy_wh: float
    battery_percent: float


class RouteWaypoint(BaseModel):
    step: int
    latitude: float
    longitude: float
    altitude_layer: int
    altitude_meters: float
    type: str


class RouteResponse(BaseModel):
    status: str
    objective: Literal["distance", "energy"]
    vehicle: VehicleInfo
    metrics: RouteMetrics
    waypoints: list[RouteWaypoint]


class ErrorResponse(BaseModel):
    detail: str