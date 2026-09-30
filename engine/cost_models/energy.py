from engine.cost_models.base import CostModel
from engine.vehicle_energy import VehicleEnergyModel
from engine.vehicle_profile import VehicleProfile


class EnergyCost(CostModel):

    def __init__(
        self,
        vehicle: VehicleProfile | None = None,
    ):
        self.vehicle_model = VehicleEnergyModel(
            vehicle=vehicle,
        )

    def edge_cost(
        self,
        horizontal_distance_meters: float,
        altitude_change_meters: float,
    ) -> float:
        return self.vehicle_model.edge_energy(
            horizontal_distance_meters=horizontal_distance_meters,
            altitude_change_meters=altitude_change_meters,
        )

    def heuristic(
        self,
        horizontal_distance_meters: float,
        altitude_change_meters: float,
    ) -> float:
        return self.vehicle_model.edge_energy(
            horizontal_distance_meters=horizontal_distance_meters,
            altitude_change_meters=abs(
                altitude_change_meters
            ),
        )