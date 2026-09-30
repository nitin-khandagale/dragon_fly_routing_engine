import heapq
import math
from itertools import count

import h3
from engine.cost_models import CostModel, DistanceCost
from src.utm_interfaces import EnvironmentalCostMap, Voxel3D


class Pathfinder3D:

    def __init__(
        self,
        cost_map: EnvironmentalCostMap,
        max_altitude_layer: int = 20,
        min_altitude_layer: int = 0,
        bounds=None,
        max_expansions: int = 50_000,
        edge_validator=None,
        cost_model: CostModel | None = None,
    ):
        self.blocked = cost_map.blocked_voxels
        self.wind_costs = cost_map.wind_costs

        self.max_alt = max_altitude_layer
        self.min_alt = min_altitude_layer

        self.bounds = bounds
        self.max_expansions = max_expansions

        self.edge_validator = edge_validator
        self.cost_model = cost_model or DistanceCost()

        # ====================================================
        # PHYSICAL COST MODEL
        # ====================================================

        # Horizontal movement uses actual distance in meters.
        self.HORIZONTAL_WEIGHT = 1.0

        # Vertical movement is more expensive than horizontal
        # movement because climbing requires additional energy.
        self.CLIMB_WEIGHT = 1.5

        # Descent is cheaper than climbing.
        self.DESCENT_WEIGHT = 1.0

        # Each altitude layer represents 15 meters.
        self.ALTITUDE_LAYER_HEIGHT_METERS = 15.0

        self.WIND_WEIGHT = 1.0

        self.AWAY_FROM_GOAL_PENALTY = 5.0

        self.IMMEDIATE_REVERSAL_PENALTY = 50.0

        


    # ========================================================
    # BOUNDS
    # ========================================================

    def _within_bounds(self, hex_code: str) -> bool:

        if self.bounds is None:
            return True

        min_lon, min_lat, max_lon, max_lat = self.bounds

        lat, lon = h3.cell_to_latlng(hex_code)

        return (
            min_lat <= lat <= max_lat
            and min_lon <= lon <= max_lon
        )


    # ========================================================
    # HORIZONTAL DISTANCE
    # ========================================================

    def _horizontal_distance(
        self,
        hex_a: str,
        hex_b: str,
    ) -> float:

        lat1, lon1 = h3.cell_to_latlng(hex_a)
        lat2, lon2 = h3.cell_to_latlng(hex_b)

        radius = 6_371_000.0

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad)
            * math.cos(lat2_rad)
            * math.sin(dlon / 2) ** 2
        )

        return (
            2
            * radius
            * math.atan2(
                math.sqrt(a),
                math.sqrt(1 - a),
            )
        )


    # ========================================================
    # HEURISTIC
    # ========================================================

    def _heuristic(self, current, goal) -> float:
        current_hex, current_layer = current
        goal_hex, goal_layer = goal

        horizontal_distance = self._horizontal_distance(
            current_hex,
            goal_hex,
        )

        current_altitude = (
            current_layer * self.ALTITUDE_LAYER_HEIGHT_METERS
        )

        goal_altitude = (
            goal_layer * self.ALTITUDE_LAYER_HEIGHT_METERS
        )

        altitude_difference = abs(
            goal_altitude - current_altitude
        )

        return self.cost_model.heuristic(
            horizontal_distance_meters=horizontal_distance,
            altitude_change_meters=altitude_difference,
        )


    # ========================================================
    # NEIGHBORS
    # ========================================================

    def _get_neighbors(
        self,
        current: Voxel3D,
    ):

        current_hex, altitude = current

        neighbors = []

        adjacent_cells = h3.grid_disk(
            current_hex,
            1,
        )

        adjacent_cells = [
            cell
            for cell in adjacent_cells
            if cell != current_hex
        ]

        # ====================================================
        # HORIZONTAL + DIAGONAL 3D MOVEMENT
        # ====================================================

        for neighbor_hex in adjacent_cells:

            # -----------------------------------------------
            # Same altitude
            # -----------------------------------------------

            neighbors.append(
                (
                    neighbor_hex,
                    altitude,
                )
            )

            # -----------------------------------------------
            # Move + climb
            # -----------------------------------------------

            if altitude < self.max_alt:

                neighbors.append(
                    (
                        neighbor_hex,
                        altitude + 1,
                    )
                )

            # -----------------------------------------------
            # Move + descend
            # -----------------------------------------------

            if altitude > self.min_alt:

                neighbors.append(
                    (
                        neighbor_hex,
                        altitude - 1,
                    )
                )


        # ====================================================
        # PURE VERTICAL MOVEMENT
        # ====================================================

        if altitude < self.max_alt:

            neighbors.append(
                (
                    current_hex,
                    altitude + 1,
                )
            )

        if altitude > self.min_alt:

            neighbors.append(
                (
                    current_hex,
                    altitude - 1,
                )
            )

        return neighbors


    # ========================================================
    # MOVEMENT COST
    # ========================================================

    def _movement_cost(self, current, neighbor) -> float:
        horizontal_distance = self._horizontal_distance(
            current[0],
            neighbor[0],
        )

        current_altitude = current[1] * self.ALTITUDE_LAYER_HEIGHT_METERS
        neighbor_altitude = neighbor[1] * self.ALTITUDE_LAYER_HEIGHT_METERS

        altitude_change = neighbor_altitude - current_altitude

        current_hex, current_alt = current
        neighbor_hex, neighbor_alt = neighbor

        # Horizontal distance in metres.
        horizontal_distance = 0.0

        if current_hex != neighbor_hex:
            horizontal_distance = self._horizontal_distance(
                current_hex,
                neighbor_hex,
            )

        # Vertical distance in metres.
        vertical_distance = (
            abs(neighbor_alt - current_alt)
            * self.ALTITUDE_LAYER_HEIGHT_METERS
        )

        cost = (
            horizontal_distance
            * self.HORIZONTAL_WEIGHT
        )

        # Climbing.
        if neighbor_alt > current_alt:
            cost += (
                vertical_distance
                * self.CLIMB_WEIGHT
            )

        # Descending.
        elif neighbor_alt < current_alt:
            cost += (
                vertical_distance
                * self.DESCENT_WEIGHT
            )

        return self.cost_model.edge_cost(
        horizontal_distance_meters=horizontal_distance,
        altitude_change_meters=altitude_change,
    )


    # ========================================================
    # PATH RECONSTRUCTION
    # ========================================================

    def _reconstruct_path(
        self,
        came_from,
        current,
    ):

        path = [current]

        while current in came_from:

            current = came_from[current]
            path.append(current)

        path.reverse()

        return path


    # ========================================================
    # A*
    # ========================================================

    def find_route(
        self,
        start: Voxel3D,
        goal: Voxel3D,
    ):

        if start in self.blocked:
            return None

        if goal in self.blocked:
            return None

        open_heap = []

        sequence = count()

        heapq.heappush(
            open_heap,
            (
                self._heuristic(
                    start,
                    goal,
                ),
                next(sequence),
                start,
            ),
        )

        came_from = {}

        g_score = {
            start: 0.0
        }

        closed = set()

        expansions = 0


        # ====================================================
        # SEARCH
        # ====================================================

        while open_heap:

            _, _, current = heapq.heappop(
                open_heap
            )

            if current in closed:
                continue


            # =================================================
            # GOAL
            # =================================================

            if current == goal:

                return self._reconstruct_path(
                    came_from,
                    current,
                )


            closed.add(current)

            expansions += 1

            if expansions > self.max_expansions:
                return None

            # =================================================
            # EXPAND
            # =================================================

            for neighbor in self._get_neighbors(
                current
            ):

                neighbor_hex, neighbor_alt = (
                    neighbor
                )


                # =============================================
                # ALTITUDE
                # =============================================

                if (
                    neighbor_alt < self.min_alt
                    or neighbor_alt > self.max_alt
                ):
                    continue


                # =============================================
                # BOUNDS
                # =============================================

                if not self._within_bounds(
                    neighbor_hex
                ):
                    continue


                # =============================================
                # FAST VOXEL COLLISION
                # =============================================

                if neighbor in self.blocked:
                    continue


                # =============================================
                # PRECISE 3D EDGE COLLISION
                # =============================================
                #
                # IMPORTANT:
                #
                # Run this for horizontal AND diagonal edges.
                #
                # For example:
                #
                # A @ 45m
                #       ↗
                #        B @ 60m
                #
                # The validator determines the actual drone
                # altitude where the segment crosses a
                # building footprint.
                # =============================================

                if (
                    current[0] != neighbor[0]
                    and self.edge_validator is not None
                ):

                    if not self.edge_validator(
                        current,
                        neighbor,
                    ):
                        continue


                if neighbor in closed:
                    continue


                # =============================================
                # MOVEMENT COST
                # =============================================

                movement_cost = self._movement_cost(
                    current=current,
                    neighbor=neighbor,
                )

                tentative_g = (
                    g_score[current]
                    + movement_cost
                )

                existing_g = g_score.get(
                    neighbor,
                    float("inf"),
                )

                if tentative_g >= existing_g:
                    continue


                # =============================================
                # RECORD
                # =============================================

                came_from[neighbor] = current

                g_score[neighbor] = (
                    tentative_g
                )

                f_score = (
                    tentative_g
                    + self._heuristic(
                        neighbor,
                        goal,
                    )
                )

                heapq.heappush(
                    open_heap,
                    (
                        f_score,
                        next(sequence),
                        neighbor,
                    ),
                )


        return None