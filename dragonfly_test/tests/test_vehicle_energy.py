import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from engine.vehicle_energy import VehicleEnergyModel
from engine.vehicle_profile import DEFAULT_MULTIROTOR


def test_default_vehicle_profile():
    vehicle = DEFAULT_MULTIROTOR

    assert vehicle.name == "default_multirotor"
    assert vehicle.mass_kg == 2.0
    assert vehicle.cruise_speed_mps == 10.0


def test_horizontal_energy():
    model = VehicleEnergyModel()

    energy = model.horizontal_energy(
        distance_meters=1000.0
    )

    assert energy == 25_000.0


def test_climb_energy():
    model = VehicleEnergyModel()

    energy = model.vertical_energy(
        altitude_change_meters=30.0
    )

    assert energy == 6_750.0


def test_descent_energy():
    model = VehicleEnergyModel()

    energy = model.vertical_energy(
        altitude_change_meters=-30.0
    )

    assert energy == 1_500.0


def test_battery_percentage():
    model = VehicleEnergyModel()

    energy = 36_000.0  # 10 Wh

    percentage = model.battery_percentage(
        energy
    )

    assert percentage == 100.0 / 15.0