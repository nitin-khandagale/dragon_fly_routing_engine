import os
import math
import time
import h3

from building_service.building_service import LocalBuildingService
from weather_service.get_weather_data import LiveWeatherService
from src.pathfinder import Pathfinder3D
from src.utm_interfaces import EnvironmentalCostMap
from engine.cost_models import DistanceCost, EnergyCost
from engine.cost_models.distance import DistanceCost
from engine.cost_models.energy import EnergyCost
from engine.vehicle_profile import (
    DEFAULT_MULTIROTOR,
    VehicleProfile,
)

from api.models import RouteRequest
from engine.route_metrics import RouteMetrics


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
    def _log_timing(label: str, started: float) -> None:
        print(f"[DragonFly timing] {label}: {time.perf_counter() - started:.3f}s")

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
        self,
        exact_lat,
        exact_lon,
        altitude_layer,
        blocked_voxels,
        search_radius=None,
        transit_altitude_layer=None,
        max_altitude_layer=None,
    ):
        """
        Find a safe H3 routing node for an exact geographic endpoint.

        The endpoint is connected to the routing graph at the minimum
        safe transit altitude rather than necessarily at the endpoint's
        original altitude.

        This allows an endpoint at ground level to climb vertically first
        and then connect horizontally to the H3 graph.
        """

        if search_radius is None:
            search_radius = self.ENDPOINT_CONNECTOR_SEARCH_RADIUS

        if transit_altitude_layer is None:
            transit_altitude_layer = altitude_layer

        minimum_connector_layer = max(
            altitude_layer,
            transit_altitude_layer,
        )

        if max_altitude_layer is None:
            max_altitude_layer = minimum_connector_layer

        # The connector altitude must be at least the endpoint altitude
        # and at least the requested minimum transit altitude.
        connector_altitude_layer = max(
            altitude_layer,
            transit_altitude_layer,
        )

        endpoint_altitude_meters = (
            altitude_layer * self.LAYER_HEIGHT_METERS
        )

        connector_altitude_meters = (
            connector_altitude_layer
            * self.LAYER_HEIGHT_METERS
        )

        endpoint_altitude_meters = (
            altitude_layer * self.LAYER_HEIGHT_METERS
        )

        minimum_connector_layer = max(
            altitude_layer,
            transit_altitude_layer,
        )

        if max_altitude_layer is None:
            max_altitude_layer = minimum_connector_layer

        containing_hex = h3.latlng_to_cell(
            exact_lat,
            exact_lon,
            self.H3_RESOLUTION,
        )

        candidate_cells = h3.grid_disk(
            containing_hex,
            search_radius,
        )

        for connector_altitude_layer in range(
            minimum_connector_layer,
            max_altitude_layer + 1,
        ):

            connector_altitude_meters = (
                connector_altitude_layer
                * self.LAYER_HEIGHT_METERS
            )

            # --------------------------------------------------------
            # 1. Validate vertical climb/descent at exact endpoint
            # --------------------------------------------------------

            vertical_connector_is_clear = (
                self.building_service.coordinate_edge_is_clear(
                    from_lat=exact_lat,
                    from_lon=exact_lon,
                    from_altitude_meters=endpoint_altitude_meters,
                    to_lat=exact_lat,
                    to_lon=exact_lon,
                    to_altitude_meters=connector_altitude_meters,
                )
            )

            if not vertical_connector_is_clear:
                continue

            candidates = []

            # --------------------------------------------------------
            # 2. Search nearby H3 cells at this altitude
            # --------------------------------------------------------

            for hex_code in candidate_cells:

                voxel = (
                    hex_code,
                    connector_altitude_layer,
                )

                if voxel in blocked_voxels:
                    continue

                cell_lat, cell_lon = h3.cell_to_latlng(
                    hex_code
                )

                connector_is_clear = (
                    self.building_service.coordinate_edge_is_clear(
                        from_lat=exact_lat,
                        from_lon=exact_lon,
                        from_altitude_meters=connector_altitude_meters,
                        to_lat=cell_lat,
                        to_lon=cell_lon,
                        to_altitude_meters=connector_altitude_meters,
                    )
                )

                if not connector_is_clear:
                    continue

                distance = self.approximate_distance_meters(
                    exact_lat,
                    exact_lon,
                    cell_lat,
                    cell_lon,
                )

                candidates.append(
                    (distance, voxel)
                )

            # --------------------------------------------------------
            # 3. Use the lowest altitude that has a safe connector
            # --------------------------------------------------------

            if candidates:
                candidates.sort(
                    key=lambda item: item[0]
                )

                return candidates[0][1]

        return None

    def get_vehicle_profile(
        self,
        vehicle_profile_name: str,
    ) -> VehicleProfile:
        profiles = {
            "default_multirotor": DEFAULT_MULTIROTOR,
        }

        vehicle = profiles.get(vehicle_profile_name)

        if vehicle is None:
            raise RouteComputationError(
                status_code=422,
                detail=(
                    f"Unsupported vehicle profile: "
                    f"{vehicle_profile_name}"
                ),
            )

        return vehicle

    def compute_route(self, req: RouteRequest):

        total_started = time.perf_counter()

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

        
        objective = req.objective

        vehicle = self.get_vehicle_profile(
            req.vehicle_profile
        )

        if req.max_altitude_meters > vehicle.max_altitude_meters:
            raise RouteComputationError(
                status_code=422,
                detail=(
                    f"Requested maximum altitude "
                    f"{req.max_altitude_meters:g} m exceeds "
                    f"vehicle maximum altitude "
                    f"{vehicle.max_altitude_meters:g} m."
                ),
            )

        if objective == "energy":
            cost_model = EnergyCost(
                vehicle=vehicle
            )
        else:
            cost_model = DistanceCost()


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

        stage_started = time.perf_counter()
        blocked_voxels = (
            self.building_service.get_blocked_voxels(
                bbox=flight_bbox,
                resolution=self.H3_RESOLUTION,
            )
        )
        self._log_timing(f"building obstacles ({len(blocked_voxels)} voxels)", stage_started)


        # ========================================================
        # 6. FIND SAFE H3 START CONNECTOR
        # ========================================================

        stage_started = time.perf_counter()
        start_connector_voxel = (
            self.find_safe_endpoint_connector(
                exact_lat=req.start_lat,
                exact_lon=req.start_lon,
                altitude_layer=start_altitude_layer,
                transit_altitude_layer=minimum_transit_altitude_layer,
                max_altitude_layer=max_altitude_layer,
                blocked_voxels=blocked_voxels,
                search_radius=(
                    self.ENDPOINT_CONNECTOR_SEARCH_RADIUS
                ),
            )
        )

        self._log_timing("start endpoint connector", stage_started)

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

        stage_started = time.perf_counter()
        goal_connector_voxel = (
            self.find_safe_endpoint_connector(
                exact_lat=req.goal_lat,
                exact_lon=req.goal_lon,
                altitude_layer=goal_altitude_layer,
                transit_altitude_layer=minimum_transit_altitude_layer,
                max_altitude_layer=max_altitude_layer,
                blocked_voxels=blocked_voxels,
                search_radius=(
                    self.ENDPOINT_CONNECTOR_SEARCH_RADIUS
                ),
            )
        )

        self._log_timing("goal endpoint connector", stage_started)

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

        start_voxel = start_connector_voxel
        goal_voxel = goal_connector_voxel


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

        stage_started = time.perf_counter()
        wind_costs = (
            weather_service.get_wind_penalties(
                sample_voxels
            )
        )
        self._log_timing(f"weather/wind ({len(sample_voxels)} samples)", stage_started)


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
        # 13. ENDPOINT TAKEOFF / LANDING
        # ========================================================

        # Endpoint connectors were already validated at the safe
        # transit altitude by find_safe_endpoint_connector().
        #
        # Do not model takeoff/landing as H3 vertical columns because
        # the containing H3 cell can contain a building even when the
        # exact requested coordinate is clear.

        takeoff = [
            start_connector_voxel,
        ]

        landing = [
            goal_connector_voxel,
        ]


        # ========================================================
        # 14. VALIDATE TAKEOFF / LANDING
        # ========================================================

        # self.ensure_clear(
        #     takeoff,
        #     blocked_voxels,
        #     "Takeoff path",
        # )

        # self.ensure_clear(
        #     landing,
        #     blocked_voxels,
        #     "Landing path",
        # )


        # ========================================================
        # 15. CREATE 3D PATHFINDER
        # ========================================================

        engine = Pathfinder3D(
            cost_map=environment,
            cost_model= cost_model,

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

        stage_started = time.perf_counter()

        transit_route = engine.find_route(
            takeoff[-1],
            landing[0],
        )
        self._log_timing("A* transit search", stage_started)

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

        route = transit_route


        # ========================================================
        # 18. FINAL H3 EDGE VALIDATION
        # ========================================================

        stage_started = time.perf_counter()
        route_is_safe, failed_edge_index = (
            self.building_service.validate_route_edges(
                route
            )
        )
        self._log_timing(f"final route edge validation ({len(route)} voxels)", stage_started)

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

        connector_altitude = (
            first_route_voxel[1] * self.LAYER_HEIGHT_METERS
        )

        vertical_start_safe = (
            self.building_service.coordinate_edge_is_clear(
                from_lat=req.start_lat,
                from_lon=req.start_lon,
                from_altitude_meters=req.start_altitude_meters,
                to_lat=req.start_lat,
                to_lon=req.start_lon,
                to_altitude_meters=connector_altitude,
            )
        )

        horizontal_start_safe = (
            self.building_service.coordinate_edge_is_clear(
                from_lat=req.start_lat,
                from_lon=req.start_lon,
                from_altitude_meters=connector_altitude,
                to_lat=first_route_lat,
                to_lon=first_route_lon,
                to_altitude_meters=connector_altitude,
            )
        )

        exact_start_connector_safe = (
            vertical_start_safe and horizontal_start_safe
        )

        if not exact_start_connector_safe:


            print("\n[DEBUG FINAL START CONNECTOR]")

            first_hex, first_layer = route[0]
            first_lat, first_lon = h3.cell_to_latlng(first_hex)
            first_altitude = first_layer * self.LAYER_HEIGHT_METERS

            print(
                f"START: "
                f"lat={req.start_lat}, "
                f"lon={req.start_lon}, "
                f"alt={req.start_altitude_meters}"
            )

            print(
                f"FIRST: "
                f"lat={first_lat}, "
                f"lon={first_lon}, "
                f"alt={first_altitude}"
            )

            connector_clear = self.building_service.coordinate_edge_is_clear(
                from_lat=req.start_lat,
                from_lon=req.start_lon,
                from_altitude_meters=req.start_altitude_meters,
                to_lat=first_lat,
                to_lon=first_lon,
                to_altitude_meters=first_altitude,
            )

            print(f"CONNECTOR CLEAR: {connector_clear}")

            print("[DEBUG FINAL START CONNECTOR END]\n")

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

        route_metrics = RouteMetrics.calculate(
        waypoints=waypoints,
        vehicle=vehicle,
        )


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

        self._log_timing("TOTAL route computation", total_started)

        return {
            "status": "success",
            "objective": objective,
            "vehicle": {
                "profile": vehicle.name,
                "battery_capacity_wh": vehicle.battery_capacity_wh,
            },

            "metrics": route_metrics,

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