import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from engine.vehicle_energy import VehicleEnergyModel


def main():
    vehicle = VehicleEnergyModel()

    horizontal = vehicle.horizontal_energy(
        distance_meters=1000,
        speed_mps=10,
    )

    climb = vehicle.vertical_energy(
        altitude_change_meters=30,
        vertical_speed_mps=2,
    )

    descent = vehicle.vertical_energy(
        altitude_change_meters=-30,
        vertical_speed_mps=2,
    )

    edge = vehicle.edge_energy(
        horizontal_distance_meters=1000,
        altitude_change_meters=30,
    )

    print(f"1000 m horizontal: {horizontal:.2f} J")
    print(f"30 m climb:        {climb:.2f} J")
    print(f"30 m descent:      {descent:.2f} J")
    print(f"Combined edge:     {edge:.2f} J")


if __name__ == "__main__":
    main()