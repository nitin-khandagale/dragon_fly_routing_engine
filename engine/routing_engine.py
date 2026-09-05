import os
import math
import h3

from building_service.building_service import LocalBuildingService
from weather_service.get_weather_data import LiveWeatherService
from src.pathfinder import Pathfinder3D
from src.utm_interfaces import EnvironmentalCostMap

from api.models import RouteRequest


class RouteComputationError(Exception):
    """Expected routing failure that the API layer can expose to clients."""

    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class RoutingEngine:
    """Core DragonFly route-computation engine.

    This class contains routing orchestration and does not define HTTP
    endpoints. The API layer is responsible only for translating HTTP
    requests into engine calls.
    """

    LAYER_HEIGHT_METERS = 15.0
    MAX_ALTITUDE_LAYER = 20
    H3_RESOLUTION = 11
    ENDPOINT_CONNECTOR_SEARCH_RADIUS = 3

    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        geojson_path = os.path.join(
            base_dir,
            "building_service",
            "artifacts",
            "sf_buildings.geojson",
        )

        self.building_service = LocalBuildingService(
            geojson_path=geojson_path,
            layer_height_meters=self.LAYER_HEIGHT_METERS,
            safety_margin_meters=15.0,
            vertical_clearance_meters=15.0,
        )

    @staticmethod
    def meters_to_layer(altitude_meters: float) -> int:
        """Convert metres to an internal altitude layer, rounding upward."""
        if altitude_meters <= 0:
            return 0
        return math.ceil(altitude_meters / RoutingEngine.LAYER_HEIGHT_METERS)

    @staticmethod
    def vertical_segment(hex_code: str, from_altitude: int, to_altitude: int) -> list[tuple[str, int]]:
        """Create an inclusive vertical movement inside one H3 cell."""
        step = 1 if to_altitude >= from_altitude else -1
        return [
            (hex_code, altitude)
            for altitude in range(from_altitude, to_altitude + step, step)
        ]

    @staticmethod
    def ensure_clear(segment, blocked_voxels, label: str) -> None:
        """Verify that every voxel in a vertical segment is clear."""
        blocked = next((voxel for voxel in segment if voxel in blocked_voxels), None)
        if blocked is None:
            return

        blocked_altitude_meters = blocked[1] * RoutingEngine.LAYER_HEIGHT_METERS
        raise RouteComputationError(
            status_code=422,
            detail=(
                f"{label} is blocked at "
                f"{blocked_altitude_meters:g} m "
                f"(internal layer {blocked[1]})."
            ),
        )

    @staticmethod
    def approximate_distance_meters(lat1, lon1, lat2, lon2) -> float:
        """Approximate local distance in metres."""
        lat_scale = 111_320.0
        avg_lat = math.radians((lat1 + lat2) / 2.0)
        dx = (lon2 - lon1) * lat_scale * math.cos(avg_lat)
        dy = (lat2 - lat1) * lat_scale
        return math.hypot(dx, dy)

    def find_safe_endpoint_connector(
        self, exact_lat, exact_lon, altitude_layer, blocked_voxels,
        search_radius=None,
    ):
        """Find a safe H3 routing node for an exact geographic endpoint."""
        if search_radius is None:
            search_radius = self.ENDPOINT_CONNECTOR_SEARCH_RADIUS

        altitude_meters = altitude_layer * self.LAYER_HEIGHT_METERS
        containing_hex = h3.latlng_to_cell(exact_lat, exact_lon, self.H3_RESOLUTION)
        candidate_cells = h3.grid_disk(containing_hex, search_radius)
        candidates = []

        for hex_code in candidate_cells:
            voxel = (hex_code, altitude_layer)
            if voxel in blocked_voxels:
                continue

            cell_lat, cell_lon = h3.cell_to_latlng(hex_code)
            connector_is_clear = self.building_service.coordinate_edge_is_clear(
                from_lat=exact_lat,
                from_lon=exact_lon,
                from_altitude_meters=altitude_meters,
                to_lat=cell_lat,
                to_lon=cell_lon,
                to_altitude_meters=altitude_meters,
            )
            if not connector_is_clear:
                continue

            distance = self.approximate_distance_meters(
                exact_lat, exact_lon, cell_lat, cell_lon
            )
            candidates.append((distance, voxel))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def compute_route(self, req: RouteRequest):

        # ========================================================
        # 1. CONVERT ALTITUDES TO INTERNAL LAYERS
        # ========================================================

        start_altitude_layer = self.meters_to_layer(
            req.start_altitude_meters
        )

        goal_altitude_layer = self.meters_to_layer(
            req.goal_altitude_meters
        )

        max_altitude_layer = self.meters_to_layer(
            req.max_altitude_meters
        )

        minimum_transit_altitude_layer = self.meters_to_layer(
            req.minimum_transit_altitude_meters
        )


        # ========================================================
        # 2. VALIDATE ALTITUDE CONFIGURATION
        # ========================================================

        required_maximum = max(
            start_altitude_layer,
            goal_altitude_layer,
            minimum_transit_altitude_layer,
        )

        if max_altitude_layer < required_maximum:

            raise RouteComputationError(
                status_code=422,
                detail=(
                    "Maximum altitude must be at least the "
                    "start, goal, and minimum transit altitudes."
                ),
            )


        # ========================================================
        # 3. ORIGINAL CONTAINING H3 CELLS
        # ========================================================

        original_start_hex = h3.latlng_to_cell(
            req.start_lat,
            req.start_lon,
            self.H3_RESOLUTION,
        )

        original_goal_hex = h3.latlng_to_cell(
            req.goal_lat,
            req.goal_lon,
            self.H3_RESOLUTION,
        )


        # ========================================================
        # 4. FLIGHT SEARCH BOUNDING BOX
        # ========================================================

        min_lat = (
            min(
                req.start_lat,
                req.goal_lat,
            )
            - 0.005
        )

        max_lat = (
            max(
                req.start_lat,
                req.goal_lat,
            )
            + 0.005
        )

        min_lon = (
            min(
                req.start_lon,
                req.goal_lon,
            )
            - 0.005
        )

        max_lon = (
            max(
                req.start_lon,
                req.goal_lon,
            )
            + 0.005
        )

        flight_bbox = (
            min_lon,
            min_lat,
            max_lon,
            max_lat,
        )


        # ========================================================
        # 5. LOAD BUILDING OBSTACLES
        # ========================================================

        blocked_voxels = (
            self.building_service.get_blocked_voxels(
                bbox=flight_bbox,
                resolution=self.H3_RESOLUTION,
            )
        )


        # ========================================================
        # 6. FIND SAFE H3 START CONNECTOR
        # ========================================================

        start_connector_voxel = (
            self.find_safe_endpoint_connector(
                exact_lat=req.start_lat,
                exact_lon=req.start_lon,

                altitude_layer=(
                    start_altitude_layer
                ),

                blocked_voxels=blocked_voxels,

                search_radius=(
                    self.ENDPOINT_CONNECTOR_SEARCH_RADIUS
                ),
            )
        )

        if start_connector_voxel is None:

            raise RouteComputationError(
                status_code=422,
                detail=(
                    "Could not safely connect the exact start "
                    "coordinate to the H3 routing graph."
                ),
            )


        # ========================================================
        # 7. FIND SAFE H3 GOAL CONNECTOR
        # ========================================================

        goal_connector_voxel = (
            self.find_safe_endpoint_connector(
                exact_lat=req.goal_lat,
                exact_lon=req.goal_lon,

                altitude_layer=(
                    goal_altitude_layer
                ),

                blocked_voxels=blocked_voxels,

                search_radius=(
                    self.ENDPOINT_CONNECTOR_SEARCH_RADIUS
                ),
            )
        )

        if goal_connector_voxel is None:

            raise RouteComputationError(
                status_code=422,
                detail=(
                    "Could not safely connect the exact goal "
                    "coordinate to the H3 routing graph."
                ),
            )


        # ========================================================
        # 8. ROUTING CELLS
        # ========================================================

        start_hex = (
            start_connector_voxel[0]
        )

        goal_hex = (
            goal_connector_voxel[0]
        )

        start_voxel = (
            start_hex,
            start_altitude_layer,
        )

        goal_voxel = (
            goal_hex,
            goal_altitude_layer,
        )


        # ========================================================
        # 9. VERIFY CONNECTOR VOXELS
        # ========================================================

        self.ensure_clear(
            [start_voxel],
            blocked_voxels,
            "Start H3 connector",
        )

        self.ensure_clear(
            [goal_voxel],
            blocked_voxels,
            "Goal H3 connector",
        )


        # ========================================================
        # 10. WEATHER / WIND COSTS
        # ========================================================

        weather_service = LiveWeatherService(
            req.start_lat,
            req.start_lon,
        )

        sample_voxels = {
            (hex_code, altitude)
            for hex_code in h3.grid_disk(
                start_hex,
                4,
            )
            for altitude in range(
                max_altitude_layer + 1
            )
        }

        wind_costs = (
            weather_service.get_wind_penalties(
                sample_voxels
            )
        )


        # ========================================================
        # 11. ENVIRONMENT
        # ========================================================

        environment = EnvironmentalCostMap(
            blocked_voxels=blocked_voxels,
            wind_costs=wind_costs,
        )


        # ========================================================
        # 12. TRANSIT ALTITUDES
        # ========================================================

        transit_start_altitude = max(
            start_altitude_layer,
            minimum_transit_altitude_layer,
        )

        transit_goal_altitude = max(
            goal_altitude_layer,
            minimum_transit_altitude_layer,
        )


        # ========================================================
        # 13. TAKEOFF / LANDING SEGMENTS
        # ========================================================

        takeoff = self.vertical_segment(
            start_hex,
            start_altitude_layer,
            transit_start_altitude,
        )

        landing = self.vertical_segment(
            goal_hex,
            transit_goal_altitude,
            goal_altitude_layer,
        )


        # ========================================================
        # 14. VALIDATE TAKEOFF / LANDING
        # ========================================================

        self.ensure_clear(
            takeoff,
            blocked_voxels,
            "Takeoff path",
        )

        self.ensure_clear(
            landing,
            blocked_voxels,
            "Landing path",
        )


        # ========================================================
        # 15. CREATE 3D PATHFINDER
        # ========================================================

        engine = Pathfinder3D(
            cost_map=environment,

            max_altitude_layer=(
                max_altitude_layer
            ),

            min_altitude_layer=(
                minimum_transit_altitude_layer
            ),

            bounds=flight_bbox,

            max_expansions=50_000,

            # Precise 3D building collision validator.
            edge_validator=(
                self.building_service.edge_is_clear
            ),
        )


        # ========================================================
        # 16. FIND TRANSIT ROUTE
        # ========================================================

        transit_route = engine.find_route(
            takeoff[-1],
            landing[0],
        )

        if not transit_route:

            raise RouteComputationError(
                status_code=404,
                detail=(
                    "No safe route found between coordinates."
                ),
            )


        # ========================================================
        # 17. COMBINE H3 ROUTE
        # ========================================================

        route = (
            takeoff[:-1]
            + transit_route
            + landing[1:]
        )


        # ========================================================
        # 18. FINAL H3 EDGE VALIDATION
        # ========================================================

        route_is_safe, failed_edge_index = (
            self.building_service.validate_route_edges(
                route
            )
        )

        if not route_is_safe:

            current_voxel = route[
                failed_edge_index
            ]

            next_voxel = route[
                failed_edge_index + 1
            ]

            current_lat, current_lon = (
                h3.cell_to_latlng(
                    current_voxel[0]
                )
            )

            next_lat, next_lon = (
                h3.cell_to_latlng(
                    next_voxel[0]
                )
            )

            raise RouteComputationError(
                status_code=500,
                detail={
                    "message": (
                        "Generated H3 route failed final "
                        "building collision validation."
                    ),

                    "failed_edge": (
                        failed_edge_index + 1
                    ),

                    "from": {
                        "latitude": current_lat,
                        "longitude": current_lon,

                        "altitude_layer": (
                            current_voxel[1]
                        ),

                        "altitude_meters": (
                            current_voxel[1]
                            * self.LAYER_HEIGHT_METERS
                        ),
                    },

                    "to": {
                        "latitude": next_lat,
                        "longitude": next_lon,

                        "altitude_layer": (
                            next_voxel[1]
                        ),

                        "altitude_meters": (
                            next_voxel[1]
                            * self.LAYER_HEIGHT_METERS
                        ),
                    },
                },
            )


        # ========================================================
        # 19. VALIDATE EXACT START CONNECTOR AGAIN
        # ========================================================

        first_route_voxel = route[0]

        first_route_lat, first_route_lon = (
            h3.cell_to_latlng(
                first_route_voxel[0]
            )
        )

        exact_start_connector_safe = (
            self.building_service.coordinate_edge_is_clear(
                from_lat=req.start_lat,
                from_lon=req.start_lon,

                from_altitude_meters=(
                    req.start_altitude_meters
                ),

                to_lat=first_route_lat,
                to_lon=first_route_lon,

                to_altitude_meters=(
                    first_route_voxel[1]
                    * self.LAYER_HEIGHT_METERS
                ),
            )
        )

        if not exact_start_connector_safe:

            raise RouteComputationError(
                status_code=500,
                detail=(
                    "Final exact-start connector failed "
                    "building collision validation."
                ),
            )


        # ========================================================
        # 20. VALIDATE EXACT GOAL CONNECTOR AGAIN
        # ========================================================

        last_route_voxel = route[-1]

        last_route_lat, last_route_lon = (
            h3.cell_to_latlng(
                last_route_voxel[0]
            )
        )

        exact_goal_connector_safe = (
            self.building_service.coordinate_edge_is_clear(
                from_lat=last_route_lat,
                from_lon=last_route_lon,

                from_altitude_meters=(
                    last_route_voxel[1]
                    * self.LAYER_HEIGHT_METERS
                ),

                to_lat=req.goal_lat,
                to_lon=req.goal_lon,

                to_altitude_meters=(
                    req.goal_altitude_meters
                ),
            )
        )

        if not exact_goal_connector_safe:

            raise RouteComputationError(
                status_code=500,
                detail=(
                    "Final exact-goal connector failed "
                    "building collision validation."
                ),
            )


        # ========================================================
        # 21. FORMAT WAYPOINTS
        # ========================================================

        waypoints = []


        # --------------------------------------------------------
        # EXACT REQUESTED START
        # --------------------------------------------------------

        waypoints.append(
            {
                "step": 0,

                "latitude": req.start_lat,
                "longitude": req.start_lon,

                "altitude_layer": (
                    start_altitude_layer
                ),

                "altitude_meters": (
                    req.start_altitude_meters
                ),

                "type": "exact_start",
            }
        )


        # --------------------------------------------------------
        # H3 ROUTING POINTS
        # --------------------------------------------------------

        for (
            hex_code,
            altitude_layer,
        ) in route:

            latitude, longitude = (
                h3.cell_to_latlng(
                    hex_code
                )
            )

            # Don't add an effectively identical duplicate.
            if waypoints:

                previous_waypoint = (
                    waypoints[-1]
                )

                same_location = (
                    abs(
                        latitude
                        - previous_waypoint["latitude"]
                    ) < 1e-10
                    and
                    abs(
                        longitude
                        - previous_waypoint["longitude"]
                    ) < 1e-10
                )

                same_altitude = (
                    abs(
                        (
                            altitude_layer
                            * self.LAYER_HEIGHT_METERS
                        )
                        - previous_waypoint[
                            "altitude_meters"
                        ]
                    ) < 1e-9
                )

                if (
                    same_location
                    and same_altitude
                ):
                    continue

            waypoints.append(
                {
                    "step": 0,

                    "latitude": latitude,
                    "longitude": longitude,

                    "altitude_layer": (
                        altitude_layer
                    ),

                    "altitude_meters": (
                        altitude_layer
                        * self.LAYER_HEIGHT_METERS
                    ),

                    "type": "h3_route",
                }
            )


        # --------------------------------------------------------
        # EXACT REQUESTED GOAL
        # --------------------------------------------------------

        last_waypoint = waypoints[-1]

        exact_goal_already_present = (
            abs(
                last_waypoint["latitude"]
                - req.goal_lat
            ) < 1e-10
            and
            abs(
                last_waypoint["longitude"]
                - req.goal_lon
            ) < 1e-10
            and
            abs(
                last_waypoint["altitude_meters"]
                - req.goal_altitude_meters
            ) < 1e-9
        )

        if not exact_goal_already_present:

            waypoints.append(
                {
                    "step": 0,

                    "latitude": req.goal_lat,
                    "longitude": req.goal_lon,

                    "altitude_layer": (
                        goal_altitude_layer
                    ),

                    "altitude_meters": (
                        req.goal_altitude_meters
                    ),

                    "type": "exact_goal",
                }
            )


        # --------------------------------------------------------
        # RE-NUMBER
        # --------------------------------------------------------

        for index, waypoint in enumerate(
            waypoints,
            start=1,
        ):
            waypoint["step"] = index


        # ========================================================
        # 22. CONNECTOR INFORMATION
        # ========================================================

        start_connector_lat, start_connector_lon = (
            h3.cell_to_latlng(
                start_hex
            )
        )

        goal_connector_lat, goal_connector_lon = (
            h3.cell_to_latlng(
                goal_hex
            )
        )

        start_connector_distance = (
            self.approximate_distance_meters(
                req.start_lat,
                req.start_lon,
                start_connector_lat,
                start_connector_lon,
            )
        )

        goal_connector_distance = (
            self.approximate_distance_meters(
                req.goal_lat,
                req.goal_lon,
                goal_connector_lat,
                goal_connector_lon,
            )
        )


        # ========================================================
        # 23. RESPONSE
        # ========================================================

        return {
            "status": "success",

            "altitude_layer_height_meters": (
                self.LAYER_HEIGHT_METERS
            ),

            "requested_altitudes_meters": {
                "start": (
                    req.start_altitude_meters
                ),

                "goal": (
                    req.goal_altitude_meters
                ),

                "maximum": (
                    req.max_altitude_meters
                ),

                "minimum_transit": (
                    req.minimum_transit_altitude_meters
                ),
            },

            "safety": {
                "horizontal_building_clearance_meters": (
                    self.building_service.safety_margin_meters
                ),

                "vertical_building_clearance_meters": (
                    self.building_service.vertical_clearance_meters
                ),

                "precise_edge_collision_check": True,

                "exact_endpoint_collision_check": True,

                "final_route_validation": True,
            },

            # Useful while debugging endpoint behaviour.
            "endpoint_connectors": {
                "start": {
                    "requested": {
                        "latitude": req.start_lat,
                        "longitude": req.start_lon,
                    },

                    "original_containing_h3": (
                        original_start_hex
                    ),

                    "selected_h3": (
                        start_hex
                    ),

                    "selected_h3_center": {
                        "latitude": (
                            start_connector_lat
                        ),
                        "longitude": (
                            start_connector_lon
                        ),
                    },

                    "connector_distance_meters": (
                        start_connector_distance
                    ),
                },

                "goal": {
                    "requested": {
                        "latitude": req.goal_lat,
                        "longitude": req.goal_lon,
                    },

                    "original_containing_h3": (
                        original_goal_hex
                    ),

                    "selected_h3": (
                        goal_hex
                    ),

                    "selected_h3_center": {
                        "latitude": (
                            goal_connector_lat
                        ),
                        "longitude": (
                            goal_connector_lon
                        ),
                    },

                    "connector_distance_meters": (
                        goal_connector_distance
                    ),
                },
            },

            "total_waypoints": len(
                waypoints
            ),

            "waypoints": waypoints,
        }