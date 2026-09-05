from dataclasses import dataclass
from typing import Dict, Tuple

# A 3D Voxel Coordinate: (H3_Hex_Index, Altitude_Layer_Int)
Voxel3D = Tuple[str, int]

@dataclass
class EnvironmentalCostMap:
    """
    Decoupled data container. 
    The pathfinder ONLY reads this object. It has no idea whether 
    this data came from an API, a database, or a mock test file.
    """
    blocked_voxels: set[Voxel3D]          # Buildings / No-fly zones (Cost = Infinity)
    wind_costs: Dict[Voxel3D, float]      # Wind penalty multipliers