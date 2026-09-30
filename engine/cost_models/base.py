from abc import ABC, abstractmethod


class CostModel(ABC):

    @abstractmethod
    def edge_cost(
        self,
        horizontal_distance_meters: float,
        altitude_change_meters: float,
    ) -> float:
        """Return the cost of traversing one routing edge."""
        raise NotImplementedError

    @abstractmethod
    def heuristic(
        self,
        horizontal_distance_meters: float,
        altitude_change_meters: float,
    ) -> float:
        """Return a lower-bound estimate of remaining route cost."""
        raise NotImplementedError