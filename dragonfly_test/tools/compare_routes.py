from __future__ import annotations
import json,sys
from pathlib import Path
from dragonfly_test.tools.route_metrics import calculate_metrics

def main():
    if len(sys.argv)!=3:
        print("Usage: python dragonfly_test/tools/compare_routes.py <route-a.json> <route-b.json>")
        raise SystemExit(2)
    paths=[Path(sys.argv[1]),Path(sys.argv[2])]
    metrics=[calculate_metrics(json.loads(p.read_text(encoding="utf-8"))) for p in paths]
    names=[p.parent.name for p in paths]
    rows=[("Waypoints","waypoints"),("Max altitude (m)","max_altitude_m"),
          ("Total climb (m)","total_climb_m"),("Total descent (m)","total_descent_m"),
          ("Horizontal distance (m)","horizontal_distance_m"),("3D distance (m)","3d_distance_m"),
          ("Energy (J)","energy_j")]
    print(f"\n{'Metric':28} {names[0]:>18} {names[1]:>18}\n"+"-"*66)
    for label,key in rows: print(f"{label:28} {str(metrics[0][key]):>18} {str(metrics[1][key]):>18}")
if __name__=="__main__": main()
