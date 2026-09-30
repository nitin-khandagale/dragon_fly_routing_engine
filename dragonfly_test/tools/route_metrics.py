from __future__ import annotations
import math

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.atan2(math.sqrt(a), math.sqrt(1-a))

def calculate_metrics(route_data):
    w = route_data.get("waypoints", [])
    if not w:
        return {"status": route_data.get("status","unknown"), "waypoints": 0,
                "max_altitude_m": None, "total_climb_m": 0.0,
                "total_descent_m": 0.0, "horizontal_distance_m": 0.0,
                "3d_distance_m": 0.0, "energy_j": None}
    max_alt = max(float(x.get("altitude_meters",0)) for x in w)
    climb = descent = horizontal = d3 = 0.0
    for a,b in zip(w,w[1:]):
        h = haversine_m(float(a["latitude"]),float(a["longitude"]),
                        float(b["latitude"]),float(b["longitude"]))
        dz = float(b.get("altitude_meters",0))-float(a.get("altitude_meters",0))
        climb += max(dz,0); descent += max(-dz,0)
        horizontal += h; d3 += math.hypot(h,dz)
    return {"status": route_data.get("status","unknown"), "waypoints": len(w),
            "max_altitude_m": round(max_alt,3), "total_climb_m": round(climb,3),
            "total_descent_m": round(descent,3),
            "horizontal_distance_m": round(horizontal,3),
            "3d_distance_m": round(d3,3), "energy_j": None}
