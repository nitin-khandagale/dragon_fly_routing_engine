import math

import geopandas as gpd
import pandas as pd
import h3
from shapely.geometry import LineString

from src.utm_interfaces import Voxel3D


class LocalBuildingService:
    def __init__(
        self,
        geojson_path: str,
        layer_height_meters: float = 15.0,
        safety_margin_meters: float = 15.0,
        vertical_clearance_meters: float = 15.0,
    ):
        self.layer_height = layer_height_meters
        self.safety_margin_meters = safety_margin_meters
        self.vertical_clearance_meters = vertical_clearance_meters

        self.gdf = gpd.read_file(geojson_path)

        if self.gdf.crs is None:
            self.gdf = self.gdf.set_crs(epsg=4326)
        else:
            self.gdf = self.gdf.to_crs(epsg=4326)

        # Metric CRS is needed because building buffers are specified in metres.
        self.metric_crs = self.gdf.estimate_utm_crs()
        self.metric_gdf = self.gdf.to_crs(self.metric_crs)

        # Pre-calculate buffered building footprints.
        #
        # These are used by the precise edge collision checker.
        self.buffered_metric_gdf = self.metric_gdf.copy()
        self.buffered_metric_gdf["geometry"] = (
            self.metric_gdf.geometry.buffer(self.safety_margin_meters)
        )

        # Store effective obstacle height:
        # roof height + required vertical clearance.
        self.buffered_metric_gdf["_obstacle_height"] = [
            self._building_height_meters(row)
            + self.vertical_clearance_meters
            for _, row in self.gdf.iterrows()
        ]

    @staticmethod
    def _value_or_none(value: object) -> float | None:
        if value is None or pd.isna(value):
            return None

        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None

        return numeric_value if numeric_value > 0 else None

    def _building_height_meters(self, row: pd.Series) -> float:
        height = self._value_or_none(row.get("height"))

        if height is not None:
            return height

        floors = self._value_or_none(row.get("num_floors"))

        if floors is not None:
            return floors * 3.5

        return self.layer_height

    def get_blocked_voxels(
        self,
        bbox: tuple[float, float, float, float] | None = None,
        resolution: int = 11,
    ) -> set[Voxel3D]:

        blocked_voxels = set()

        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            filtered_gdf = self.gdf.cx[
                min_lon:max_lon,
                min_lat:max_lat
            ]
        else:
            filtered_gdf = self.gdf

        # Buffered footprints in WGS84 for H3 conversion.
        buffered_geometries = (
            self.buffered_metric_gdf
            .loc[filtered_gdf.index]
            .geometry
            .to_crs(epsg=4326)
        )

        for index, row in filtered_gdf.iterrows():

            geom = row.geometry

            is_underground = row.get("is_underground", False)

            if pd.notna(is_underground) and bool(is_underground):
                continue

            height = self._building_height_meters(row)

            effective_height = (
                height + self.vertical_clearance_meters
            )

            max_blocked_layer = math.floor(
                effective_height / self.layer_height
            )

            buffered_geom = buffered_geometries.loc[index]

            building_cells = h3.geo_to_cells(
                buffered_geom.__geo_interface__,
                resolution,
            )

            # Conservative fallback for tiny polygons.
            if not building_cells:
                centroid = geom.centroid

                building_cells = {
                    h3.latlng_to_cell(
                        centroid.y,
                        centroid.x,
                        resolution,
                    )
                }

            for alt_layer in range(max_blocked_layer + 1):

                blocked_voxels.update(
                    (hex_code, alt_layer)
                    for hex_code in building_cells
                )

        return blocked_voxels

    # ---------------------------------------------------------
    # PRECISE EDGE COLLISION CHECKING
    # ---------------------------------------------------------

    def edge_is_clear(
        self,
        from_voxel: Voxel3D,
        to_voxel: Voxel3D,
    ) -> bool:

        from_hex, from_layer = from_voxel
        to_hex, to_layer = to_voxel

        # ========================================================
        # PURE VERTICAL MOVEMENT
        # ========================================================
        #
        # No horizontal segment exists.
        #
        # The blocked-voxel model already protects the building
        # column.
        # ========================================================

        if from_hex == to_hex:
            return True


        # ========================================================
        # H3 CENTRES
        # ========================================================

        from_lat, from_lon = h3.cell_to_latlng(
            from_hex
        )

        to_lat, to_lon = h3.cell_to_latlng(
            to_hex
        )


        # ========================================================
        # ALTITUDES
        # ========================================================

        from_altitude = (
            from_layer
            * self.layer_height
        )

        to_altitude = (
            to_layer
            * self.layer_height
        )


        # ========================================================
        # CREATE HORIZONTAL FLIGHT SEGMENT
        # ========================================================

        line_wgs84 = gpd.GeoSeries(
            [
                LineString(
                    [
                        (
                            from_lon,
                            from_lat,
                        ),
                        (
                            to_lon,
                            to_lat,
                        ),
                    ]
                )
            ],
            crs="EPSG:4326",
        )

        line_metric = (
            line_wgs84
            .to_crs(self.metric_crs)
            .iloc[0]
        )

        line_length = line_metric.length

        if line_length <= 0:
            return True


        # ========================================================
        # FIND POSSIBLE BUILDINGS
        # ========================================================

        candidate_indexes = list(
            self.buffered_metric_gdf.sindex.query(
                line_metric,
                predicate="intersects",
            )
        )

        if not candidate_indexes:
            return True


        # ========================================================
        # CHECK EACH BUILDING
        # ========================================================

        for positional_index in candidate_indexes:

            building = (
                self.buffered_metric_gdf.iloc[
                    positional_index
                ]
            )

            is_underground = building.get(
                "is_underground",
                False,
            )

            if (
                pd.notna(is_underground)
                and bool(is_underground)
            ):
                continue


            footprint = building.geometry

            intersection = (
                line_metric.intersection(
                    footprint
                )
            )

            if intersection.is_empty:
                continue


            obstacle_height = float(
                building[
                    "_obstacle_height"
                ]
            )


            # ====================================================
            # GET ALL INTERSECTION LINE PARTS
            # ====================================================

            intersection_lines = []

            intersection_points = []


            if intersection.geom_type == "LineString":

                intersection_lines.append(
                    intersection
                )


            elif intersection.geom_type == "MultiLineString":

                intersection_lines.extend(
                    intersection.geoms
                )


            elif intersection.geom_type == "Point":

                intersection_points.append(
                    intersection
                )


            elif intersection.geom_type == "MultiPoint":

                intersection_points.extend(
                    intersection.geoms
                )


            elif intersection.geom_type == "GeometryCollection":

                for geom in intersection.geoms:

                    if geom.geom_type == "LineString":

                        intersection_lines.append(
                            geom
                        )

                    elif geom.geom_type == "Point":

                        intersection_points.append(
                            geom
                        )


            # ====================================================
            # CHECK LINE INTERSECTIONS
            # ====================================================
            #
            # The drone altitude changes linearly from:
            #
            #     from_altitude -> to_altitude
            #
            # We calculate the altitude at both points where the
            # route enters/leaves the building.
            #
            # The LOWER altitude is what matters.
            # ====================================================

            for intersection_line in intersection_lines:

                coords = list(
                    intersection_line.coords
                )

                if not coords:
                    continue

                from shapely.geometry import Point

                entry_point = Point(
                    coords[0]
                )

                exit_point = Point(
                    coords[-1]
                )


                entry_distance = (
                    line_metric.project(
                        entry_point
                    )
                )

                exit_distance = (
                    line_metric.project(
                        exit_point
                    )
                )


                entry_fraction = max(
                    0.0,
                    min(
                        1.0,
                        entry_distance
                        / line_length,
                    ),
                )

                exit_fraction = max(
                    0.0,
                    min(
                        1.0,
                        exit_distance
                        / line_length,
                    ),
                )


                entry_altitude = (
                    from_altitude
                    +
                    (
                        to_altitude
                        - from_altitude
                    )
                    * entry_fraction
                )

                exit_altitude = (
                    from_altitude
                    +
                    (
                        to_altitude
                        - from_altitude
                    )
                    * exit_fraction
                )


                lowest_altitude = min(
                    entry_altitude,
                    exit_altitude,
                )


                # ================================================
                # COLLISION
                # ================================================

                if lowest_altitude <= obstacle_height:

                    return False


            # ====================================================
            # POINT TOUCH
            # ====================================================
            #
            # Even if the line only touches the buffered building
            # boundary at one point, verify clearance there.
            # ====================================================

            for point in intersection_points:

                distance = (
                    line_metric.project(
                        point
                    )
                )

                fraction = max(
                    0.0,
                    min(
                        1.0,
                        distance
                        / line_length,
                    ),
                )


                altitude = (
                    from_altitude
                    +
                    (
                        to_altitude
                        - from_altitude
                    )
                    * fraction
                )


                if altitude <= obstacle_height:

                    return False


        return True

    # ---------------------------------------------------------
    # FINAL ROUTE VALIDATION
    # ---------------------------------------------------------

    def validate_route_edges(
        self,
        route: list[Voxel3D],
    ) -> tuple[bool, int | None]:

        for index in range(len(route) - 1):

            current = route[index]
            next_voxel = route[index + 1]

            if not self.edge_is_clear(
                current,
                next_voxel,
            ):
                return False, index

        return True, None

    def coordinate_edge_is_clear(
        self,
        from_lat: float,
        from_lon: float,
        from_altitude_meters: float,
        to_lat: float,
        to_lon: float,
        to_altitude_meters: float,
    ) -> bool:
        """
        Check a continuous 3D segment between two arbitrary geographic
        coordinates against buffered building footprints.

        Unlike edge_is_clear(), this method does NOT require H3 cells.

        Used primarily for:

            exact requested start -> H3 routing graph

            H3 routing graph -> exact requested goal
        """

        from shapely.geometry import LineString, Point

        # --------------------------------------------------------
        # Convert geographic segment into the metric CRS used by
        # our buffered building geometries.
        # --------------------------------------------------------

        line_wgs84 = gpd.GeoSeries(
            [
                LineString(
                    [
                        (from_lon, from_lat),
                        (to_lon, to_lat),
                    ]
                )
            ],
            crs="EPSG:4326",
        )

        line_metric = (
            line_wgs84
            .to_crs(self.metric_crs)
            .iloc[0]
        )

        line_length = line_metric.length

        if line_length <= 0:
            return True

        # --------------------------------------------------------
        # Find only buildings intersecting this short connector.
        # --------------------------------------------------------

        candidate_indexes = list(
            self.buffered_metric_gdf.sindex.query(
                line_metric,
                predicate="intersects",
            )
        )

        if not candidate_indexes:
            return True

        # --------------------------------------------------------
        # Test each intersecting building.
        # --------------------------------------------------------

        for positional_index in candidate_indexes:

            building = self.buffered_metric_gdf.iloc[
                positional_index
            ]

            is_underground = building.get(
                "is_underground",
                False,
            )

            if (
                pd.notna(is_underground)
                and bool(is_underground)
            ):
                continue

            footprint = building.geometry

            intersection = line_metric.intersection(
                footprint
            )

            if intersection.is_empty:
                continue

            obstacle_height = float(
                building["_obstacle_height"]
            )

            # ----------------------------------------------------
            # Helper:
            # calculate drone altitude at an arbitrary point along
            # the horizontal segment.
            # ----------------------------------------------------

            def altitude_at_point(point):

                distance = line_metric.project(
                    point
                )

                fraction = max(
                    0.0,
                    min(
                        1.0,
                        distance / line_length,
                    ),
                )

                return (
                    from_altitude_meters
                    +
                    (
                        to_altitude_meters
                        - from_altitude_meters
                    )
                    * fraction
                )

            # ----------------------------------------------------
            # Line intersection
            # ----------------------------------------------------

            if intersection.geom_type == "LineString":

                coords = list(
                    intersection.coords
                )

                if coords:

                    entry = Point(coords[0])
                    exit_point = Point(coords[-1])

                    lowest_altitude = min(
                        altitude_at_point(entry),
                        altitude_at_point(exit_point),
                    )

                    if lowest_altitude <= obstacle_height:
                        return False

            # ----------------------------------------------------
            # Multiple line intersections
            # ----------------------------------------------------

            elif intersection.geom_type == "MultiLineString":

                for part in intersection.geoms:

                    coords = list(part.coords)

                    if not coords:
                        continue

                    entry = Point(coords[0])
                    exit_point = Point(coords[-1])

                    lowest_altitude = min(
                        altitude_at_point(entry),
                        altitude_at_point(exit_point),
                    )

                    if lowest_altitude <= obstacle_height:
                        return False

            # ----------------------------------------------------
            # Boundary touch
            # ----------------------------------------------------

            elif intersection.geom_type == "Point":

                altitude = altitude_at_point(
                    intersection
                )

                if altitude <= obstacle_height:
                    return False

            elif intersection.geom_type == "MultiPoint":

                for point in intersection.geoms:

                    altitude = altitude_at_point(
                        point
                    )

                    if altitude <= obstacle_height:
                        return False

            # ----------------------------------------------------
            # GeometryCollection fallback
            # ----------------------------------------------------

            else:

                representative_point = (
                    intersection.representative_point()
                )

                altitude = altitude_at_point(
                    representative_point
                )

                if altitude <= obstacle_height:
                    return False

        return True