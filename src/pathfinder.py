import heapq
import math
from itertools import count

import h3

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
    ):
        self.blocked = cost_map.blocked_voxels
        self.wind_costs = cost_map.wind_costs

        self.max_alt = max_altitude_layer
        self.min_alt = min_altitude_layer

        self.bounds = bounds
        self.max_expansions = max_expansions

        self.edge_validator = edge_validator

        # ====================================================
        # COST MODEL
        # ====================================================

        # Horizontal movement to an adjacent H3 cell.
        self.HORIZONTAL_COST = 1.0

        # Diagonal altitude change is relatively cheap because the
        # drone is already travelling horizontally.
        self.CLIMB_COST = 0.15
        self.DESCENT_COST = 0.08

        # Pure vertical movement remains more expensive.
        self.VERTICAL_CLIMB_COST = 0.55
        self.VERTICAL_DESCENT_COST = 0.35

        self.WIND_WEIGHT = 1.0

        # Small penalty for a move that increases horizontal
        # distance from the destination.
        #
        # This is deliberately SMALL because legitimate building
        # avoidance may require temporarily moving away.
        self.AWAY_FROM_GOAL_PENALTY = 0.12

        # Stronger penalty for immediately returning to the
        # horizontal H3 cell we just came from.
        #
        # This targets:
        #
        #     A -> B -> A
        #
        # without banning it.
        self.IMMEDIATE_REVERSAL_PENALTY = 1.25


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

        try:
            return float(
                h3.grid_distance(hex_a, hex_b)
            )

        except Exception:
            lat1, lon1 = h3.cell_to_latlng(hex_a)
            lat2, lon2 = h3.cell_to_latlng(hex_b)

            # Approximate distance.
            lat_scale = 111_320.0

            avg_lat = math.radians(
                (lat1 + lat2) / 2.0
            )

            dx = (
                (lon2 - lon1)
                * lat_scale
                * math.cos(avg_lat)
            )

            dy = (
                (lat2 - lat1)
                * lat_scale
            )

            # Convert approximately into H3-step units.
            return math.hypot(dx, dy) / 50.0


    # ========================================================
    # HEURISTIC
    # ========================================================

    def _heuristic(
        self,
        current: Voxel3D,
        goal: Voxel3D,
    ) -> float:

        current_hex, current_alt = current
        goal_hex, goal_alt = goal

        horizontal = self._horizontal_distance(
            current_hex,
            goal_hex,
        )

        vertical = abs(
            current_alt - goal_alt
        )

        # Keep the heuristic conservative.
        #
        # Horizontal movement costs at least 1.
        # Vertical movement costs at least ~0.65.
        return (
            horizontal * self.HORIZONTAL_COST
            + vertical * 0.35
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

    def _movement_cost(
        self,
        previous: Voxel3D | None,
        current: Voxel3D,
        neighbor: Voxel3D,
        goal: Voxel3D,
    ) -> float:

        current_hex, current_alt = current
        neighbor_hex, neighbor_alt = neighbor

        horizontal_move = (
            current_hex != neighbor_hex
        )

        altitude_change = (
            neighbor_alt - current_alt
        )

        cost = 0.0


        # ====================================================
        # BASE MOVEMENT COST
        # ====================================================

        if horizontal_move:

            cost += self.HORIZONTAL_COST

            if altitude_change > 0:
                cost += self.CLIMB_COST

            elif altitude_change < 0:
                cost += self.DESCENT_COST

        else:

            if altitude_change > 0:
                cost += self.VERTICAL_CLIMB_COST

            elif altitude_change < 0:
                cost += self.VERTICAL_DESCENT_COST


        # ====================================================
        # WIND
        # ====================================================

        if horizontal_move:

            wind_cost = self.wind_costs.get(
                neighbor,
                0.0,
            )

            cost += (
                wind_cost
                * self.WIND_WEIGHT
            )


        # ====================================================
        # PROGRESS PENALTY
        # ====================================================
        #
        # Don't prohibit moving away from the goal.
        #
        # Just make it slightly more expensive when there is
        # another equally safe route that moves forward.
        # ====================================================

        if horizontal_move:

            current_distance = (
                self._horizontal_distance(
                    current_hex,
                    goal[0],
                )
            )

            neighbor_distance = (
                self._horizontal_distance(
                    neighbor_hex,
                    goal[0],
                )
            )

            if neighbor_distance > current_distance:

                amount_away = (
                    neighbor_distance
                    - current_distance
                )

                cost += (
                    self.AWAY_FROM_GOAL_PENALTY
                    * amount_away
                )


        # ====================================================
        # IMMEDIATE HORIZONTAL REVERSAL
        # ====================================================
        #
        # Detect:
        #
        #       previous horizontal cell = A
        #       current horizontal cell  = B
        #       next horizontal cell     = A
        #
        # Example from your route:
        #
        #       A @ 105
        #          ↘
        #           B @ 120
        #          ↙
        #       A @ 135
        #
        # We don't ban this because there may be a rare
        # legitimate reason for it.
        #
        # We simply make it unattractive.
        # ====================================================

        if previous is not None:

            previous_hex = previous[0]

            if (
                horizontal_move
                and neighbor_hex == previous_hex
                and current_hex != previous_hex
            ):
                cost += (
                    self.IMMEDIATE_REVERSAL_PENALTY
                )


        return cost


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
            # PREVIOUS STATE
            # =================================================

            previous = came_from.get(
                current
            )


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

                movement_cost = (
                    self._movement_cost(
                        previous=previous,
                        current=current,
                        neighbor=neighbor,
                        goal=goal,
                    )
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