from __future__ import annotations
import json, sys
from pathlib import Path

TEST_ROOT=Path(__file__).resolve().parents[1]
DRAGONFLY_ROOT=TEST_ROOT.parent
sys.path.insert(0,str(DRAGONFLY_ROOT))

from api.models import RouteRequest
from engine.routing_engine import RoutingEngine
from dragonfly_test.tools.route_metrics import calculate_metrics
from dragonfly_test.tools.visualize_route import generate_html
from dragonfly_test.tools.generate_kml import generate_kml

SCENARIO_DIR=TEST_ROOT/"scenarios"
RESULTS_DIR=TEST_ROOT/"results"

def load_scenario(value):
    p=Path(value)
    if not p.exists(): p=SCENARIO_DIR/f"{value}.json"
    if not p.exists(): raise FileNotFoundError(f"Scenario not found: {value}")
    return json.loads(p.read_text(encoding="utf-8")),p.stem

def main():
    if len(sys.argv)!=2:
        print("Usage: python dragonfly_test/tools/run_scenario.py <scenario>")
        raise SystemExit(2)
    scenario,name=load_scenario(sys.argv[1])
    out=RESULTS_DIR/name;out.mkdir(parents=True,exist_ok=True)
    request=RouteRequest(**scenario["request"])
    result=RoutingEngine().compute_route(request)

    if hasattr(result,"model_dump"): data=result.model_dump()
    elif hasattr(result,"dict"): data=result.dict()
    elif isinstance(result,dict): data=result
    else: raise TypeError(f"Unexpected route result type: {type(result)}")

    (out/"route.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
    metrics=calculate_metrics(data);metrics["scenario"]=name
    (out/"metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")

    buildings=DRAGONFLY_ROOT/"building_service"/"artifacts"/"sf_buildings.geojson"
    generate_html(data,buildings,out/"route.html",f"DragonFly — {name}")
    generate_kml(data,out/"route.kml",name)

    print("\nRESULT\n"+"-"*40)
    for k,v in metrics.items():
        if k!="scenario": print(f"{k:28} {v}")
    print("-"*40)
    print(f"HTML:    {out/'route.html'}")
    print(f"JSON:    {out/'route.json'}")
    print(f"KML:     {out/'route.kml'}")
    print(f"Metrics: {out/'metrics.json'}")

if __name__=="__main__": main()
