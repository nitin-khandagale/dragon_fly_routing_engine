from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleProfile:
    """
    Physical and operational parameters for a drone.

    V1 uses a practical parameterized model.
    """

    name: str

    mass_kg: float

    cruise_speed_mps: float
    climb_speed_mps: float
    descent_speed_mps: float

    horizontal_power_watts: float
    climb_power_watts: float
    descent_power_watts: float

    battery_capacity_wh: float

    max_altitude_meters: float
    max_climb_rate_mps: float
    max_descent_rate_mps: float

    def __post_init__(self):
        if self.mass_kg <= 0:
            raise ValueError("mass_kg must be greater than zero")

        if self.cruise_speed_mps <= 0:
            raise ValueError("cruise_speed_mps must be greater than zero")

        if self.climb_speed_mps <= 0:
            raise ValueError("climb_speed_mps must be greater than zero")

        if self.descent_speed_mps <= 0:
            raise ValueError("descent_speed_mps must be greater than zero")

        if self.horizontal_power_watts <= 0:
            raise ValueError(
                "horizontal_power_watts must be greater than zero"
            )

        if self.climb_power_watts <= 0:
            raise ValueError(
                "climb_power_watts must be greater than zero"
            )

        if self.descent_power_watts <= 0:
            raise ValueError(
                "descent_power_watts must be greater than zero"
            )

        if self.battery_capacity_wh <= 0:
            raise ValueError(
                "battery_capacity_wh must be greater than zero"
            )

        if self.max_altitude_meters <= 0:
            raise ValueError(
                "max_altitude_meters must be greater than zero"
            )

        if self.max_climb_rate_mps <= 0:
            raise ValueError(
                "max_climb_rate_mps must be greater than zero"
            )

        if self.max_descent_rate_mps <= 0:
            raise ValueError(
                "max_descent_rate_mps must be greater than zero"
            )


DEFAULT_MULTIROTOR = VehicleProfile(
    name="default_multirotor",

    mass_kg=2.0,

    cruise_speed_mps=10.0,
    climb_speed_mps=2.0,
    descent_speed_mps=2.0,

    horizontal_power_watts=250.0,
    climb_power_watts=450.0,
    descent_power_watts=100.0,

    battery_capacity_wh=150.0,

    max_altitude_meters=300.0,
    max_climb_rate_mps=2.0,
    max_descent_rate_mps=2.0,
)