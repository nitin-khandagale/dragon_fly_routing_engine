import math

from engine.vehicle_energy import VehicleEnergyModel
from engine.vehicle_profile import VehicleProfile


class RouteMetrics:
    """
    Calculates metrics from the final returned route.

    Metrics are calculated from the actual validated waypoints,
    not from the A* search cost.
    """

    @staticmethod
    def calculate(
        waypoints: list[dict],
        vehicle: VehicleProfile,
    ) -> dict:
        vehicle_model = VehicleEnergyModel(vehicle=vehicle)

        horizontal_distance_meters = 0.0
        three_d_distance_meters = 0.0
        total_climb_meters = 0.0
        total_descent_meters = 0.0
        energy_joules = 0.0
        flight_time_seconds = 0.0

        for previous, current in zip(
            waypoints,
            waypoints[1:],
        ):
            horizontal_distance = RouteMetrics._distance(
                previous["latitude"],
                previous["longitude"],
                current["latitude"],
                current["longitude"],
            )

            altitude_change = (
                current["altitude_meters"]
                - previous["altitude_meters"]
            )

            three_d_distance = math.sqrt(
                horizontal_distance**2
                + altitude_change**2
            )

            horizontal_distance_meters += horizontal_distance
            three_d_distance_meters += three_d_distance

            if altitude_change > 0:
                total_climb_meters += altitude_change

                vertical_time = (
                    altitude_change
                    / vehicle.climb_speed_mps
                )

            elif altitude_change < 0:
                total_descent_meters += abs(altitude_change)

                vertical_time = (
                    abs(altitude_change)
                    / vehicle.descent_speed_mps
                )

            else:
                vertical_time = 0.0

            horizontal_time = (
                horizontal_distance
                / vehicle.cruise_speed_mps
            )

            flight_time_seconds += (
                horizontal_time
                + vertical_time
            )

            energy_joules += vehicle_model.edge_energy(
                horizontal_distance_meters=horizontal_distance,
                altitude_change_meters=altitude_change,
            )

        energy_wh = vehicle_model.joules_to_wh(
            energy_joules
        )

        battery_percent = vehicle_model.battery_percentage(
            energy_joules
        )

        return {
            "distance_meters": horizontal_distance_meters,
            "3d_distance_meters": three_d_distance_meters,
            "total_climb_meters": total_climb_meters,
            "total_descent_meters": total_descent_meters,
            "flight_time_seconds": flight_time_seconds,
            "energy_joules": energy_joules,
            "energy_wh": energy_wh,
            "battery_percent": battery_percent,
        }

    @staticmethod
    def _distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Local geographic distance approximation in metres.
        """

        lat_scale = 111_320.0

        average_latitude = math.radians(
            (lat1 + lat2) / 2.0
        )

        dx = (
            (lon2 - lon1)
            * lat_scale
            * math.cos(average_latitude)
        )

        dy = (
            (lat2 - lat1)
            * lat_scale
        )

        return math.hypot(dx, dy)