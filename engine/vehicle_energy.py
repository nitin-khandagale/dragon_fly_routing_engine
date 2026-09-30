from engine.vehicle_profile import (
    DEFAULT_MULTIROTOR,
    VehicleProfile,
)


class VehicleEnergyModel:
    """
    V1 vehicle energy model.

    Energy is returned in Joules.

    The model is intentionally parameterized by VehicleProfile so that
    different drone configurations can use the same routing engine.
    """

    def __init__(
        self,
        vehicle: VehicleProfile | None = None,
    ):
        self.vehicle = vehicle or DEFAULT_MULTIROTOR

    def horizontal_energy(
        self,
        distance_meters: float,
    ) -> float:
        if distance_meters < 0:
            raise ValueError(
                "distance_meters cannot be negative"
            )

        flight_time_seconds = (
            distance_meters
            / self.vehicle.cruise_speed_mps
        )

        return (
            self.vehicle.horizontal_power_watts
            * flight_time_seconds
        )

    def vertical_energy(
        self,
        altitude_change_meters: float,
    ) -> float:
        if altitude_change_meters == 0:
            return 0.0

        if altitude_change_meters > 0:
            power = self.vehicle.climb_power_watts
            speed = self.vehicle.climb_speed_mps
        else:
            power = self.vehicle.descent_power_watts
            speed = self.vehicle.descent_speed_mps

        flight_time_seconds = (
            abs(altitude_change_meters)
            / speed
        )

        return power * flight_time_seconds

    def edge_energy(
        self,
        horizontal_distance_meters: float,
        altitude_change_meters: float,
    ) -> float:
        return (
            self.horizontal_energy(
                distance_meters=horizontal_distance_meters,
            )
            + self.vertical_energy(
                altitude_change_meters=altitude_change_meters,
            )
        )

    def joules_to_wh(
        self,
        energy_joules: float,
    ) -> float:
        return energy_joules / 3600.0

    def battery_percentage(
        self,
        energy_joules: float,
    ) -> float:
        energy_wh = self.joules_to_wh(energy_joules)

        return (
            energy_wh
            / self.vehicle.battery_capacity_wh
        ) * 100.0