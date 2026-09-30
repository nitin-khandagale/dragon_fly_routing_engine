from engine.cost_models.base import CostModel


class DistanceCost(CostModel):

    def edge_cost(
        self,
        horizontal_distance_meters: float,
        altitude_change_meters: float,
    ) -> float:
        return (
            horizontal_distance_meters
            + abs(altitude_change_meters)
        )

    def heuristic(
        self,
        horizontal_distance_meters: float,
        altitude_change_meters: float,
    ) -> float:
        return (
            horizontal_distance_meters
            + abs(altitude_change_meters)
        )