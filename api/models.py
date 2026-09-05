from pydantic import BaseModel, Field


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
