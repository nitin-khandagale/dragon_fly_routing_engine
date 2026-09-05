import requests
from src.utm_interfaces import Voxel3D

class LiveWeatherService:
    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon
        # Free Open-Meteo REST Endpoint
        self.api_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current=wind_speed_10m,wind_direction_10m"
        )

    def get_wind_penalties(self, active_voxels: set[Voxel3D]) -> dict[Voxel3D, float]:
        """
        Fetches live wind speed and applies cost penalties to higher altitude layers.
        """
        try:
            response = requests.get(self.api_url, timeout=3)
            data = response.json()
            # Wind speed in km/h
            wind_speed = data["current"]["wind_speed_10m"] 
            print(f"🌐 Live Wind Speed fetched: {wind_speed} km/h")
        except Exception as e:
            print(f"⚠️ Weather API failed ({e}). Falling back to 0 wind penalty.")
            wind_speed = 0.0

        wind_penalties = {}
        # Calculate wind penalty multiplier (e.g. 20 km/h wind adds cost at higher layers)
        penalty_factor = wind_speed / 10.0

        for hex_code, alt_layer in active_voxels:
            if alt_layer >= 2:  # Altitude Layer 2+ (100ft+) feels wind resistance
                wind_penalties[(hex_code, alt_layer)] = penalty_factor * alt_layer

        return wind_penalties