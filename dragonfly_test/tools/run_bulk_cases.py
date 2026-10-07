import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape


BASE_DIR = Path(__file__).resolve().parents[2]

SCENARIOS_FILE = BASE_DIR / "dragonfly_test" / "scenarios" / "routing_cases.json"
RESULTS_DIR = BASE_DIR / "dragonfly_test" / "results" / "routing_cases"

API_URL = "http://127.0.0.1:8000/route"


def call_api(payload):
    body = json.dumps(payload).encode("utf-8")

    request = Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()

    try:
        with urlopen(request, timeout=300) as response:
            response_body = response.read().decode("utf-8")
            status_code = response.status

    except HTTPError as exc:
        response_body = exc.read().decode("utf-8")
        status_code = exc.code

    except URLError as exc:
        elapsed = time.perf_counter() - started

        return {
            "success": False,
            "status_code": None,
            "elapsed_seconds": elapsed,
            "response": {
                "error": f"Could not connect to API: {exc.reason}"
            },
        }

    elapsed = time.perf_counter() - started

    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError:
        response_json = {"raw_response": response_body}

    return {
        "success": 200 <= status_code < 300,
        "status_code": status_code,
        "elapsed_seconds": elapsed,
        "response": response_json,
    }


def generate_kml(case_name, response):
    waypoints = response.get("waypoints", [])

    if not waypoints:
        return None

    coordinates = []

    for waypoint in waypoints:
        lon = waypoint["longitude"]
        lat = waypoint["latitude"]
        altitude = waypoint["altitude_meters"]

        coordinates.append(
            f"{lon},{lat},{altitude}"
        )

    coordinate_text = "\n".join(coordinates)

    start = waypoints[0]
    end = waypoints[-1]

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>

    <name>{escape(case_name)}</name>

    <Style id="route">
        <LineStyle>
            <color>ff0000ff</color>
            <width>4</width>
        </LineStyle>
    </Style>

    <Style id="start">
        <IconStyle>
            <scale>1.2</scale>
        </IconStyle>
    </Style>

    <Style id="end">
        <IconStyle>
            <scale>1.2</scale>
        </IconStyle>
    </Style>

    <Placemark>
        <name>{escape(case_name)} Route</name>
        <styleUrl>#route</styleUrl>

        <LineString>
            <altitudeMode>absolute</altitudeMode>
            <tessellate>1</tessellate>
            <coordinates>
{coordinate_text}
            </coordinates>
        </LineString>
    </Placemark>

    <Placemark>
        <name>Start</name>
        <styleUrl>#start</styleUrl>

        <Point>
            <altitudeMode>absolute</altitudeMode>
            <coordinates>
                {start["longitude"]},{start["latitude"]},{start["altitude_meters"]}
            </coordinates>
        </Point>
    </Placemark>

    <Placemark>
        <name>Goal</name>
        <styleUrl>#end</styleUrl>

        <Point>
            <altitudeMode>absolute</altitudeMode>
            <coordinates>
                {end["longitude"]},{end["latitude"]},{end["altitude_meters"]}
            </coordinates>
        </Point>
    </Placemark>

</Document>
</kml>
"""


def generate_combined_kml(routes):
    placemarks = []

    for index, route in enumerate(routes, start=1):
        response = route["response"]
        waypoints = response.get("waypoints", [])

        if not waypoints:
            continue

        case_name = route["name"]

        coordinates = "\n".join(
            f'{wp["longitude"]},{wp["latitude"]},{wp["altitude_meters"]}'
            for wp in waypoints
        )

        placemarks.append(
            f"""
        <Placemark>
            <name>{escape(case_name)}</name>

            <LineString>
                <altitudeMode>absolute</altitudeMode>
                <tessellate>1</tessellate>
                <coordinates>
{coordinates}
                </coordinates>
            </LineString>
        </Placemark>
"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>

    <name>DragonFly Routing Test Cases</name>

    {"".join(placemarks)}

</Document>
</kml>
"""


def main():
    if not SCENARIOS_FILE.exists():
        print(f"Scenarios file not found: {SCENARIOS_FILE}")
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with open(SCENARIOS_FILE, "r", encoding="utf-8") as file:
        cases = json.load(file)

    print(f"\nRunning {len(cases)} routing test cases...")
    print(f"API: {API_URL}")
    print("-" * 90)

    results = []
    summary = []

    for index, case in enumerate(cases, start=1):
        name = case["name"]
        payload = case["request"]

        print(f"[{index}/{len(cases)}] {name} ...", end=" ", flush=True)

        result = call_api(payload)

        response = result["response"]

        result_file = RESULTS_DIR / f"{index:03d}_{name}.json"

        output = {
            "name": name,
            "request": payload,
            **result,
        }

        with open(result_file, "w", encoding="utf-8") as file:
            json.dump(output, file, indent=2)

        if result["success"] and "waypoints" in response:
            kml = generate_kml(name, response)

            kml_file = RESULTS_DIR / f"{index:03d}_{name}.kml"

            with open(kml_file, "w", encoding="utf-8") as file:
                file.write(kml)

            metrics = response.get("metrics", {})
            waypoints = response.get("waypoints", [])

            max_altitude = max(
                wp["altitude_meters"]
                for wp in waypoints
            )

            summary_entry = {
                "name": name,
                "status": "PASS",
                "http_status": result["status_code"],
                "elapsed_seconds": round(
                    result["elapsed_seconds"], 3
                ),
                "max_altitude_meters": max_altitude,
                "distance_meters": metrics.get("distance_meters"),
                "3d_distance_meters": metrics.get("3d_distance_meters"),
                "energy_wh": metrics.get("energy_wh"),
                "battery_percent": metrics.get("battery_percent"),
                "waypoints": len(waypoints),
            }

            print(
                f"PASS | "
                f"{result['elapsed_seconds']:.2f}s | "
                f"max alt {max_altitude:g}m"
            )

        else:
            summary_entry = {
                "name": name,
                "status": "FAIL",
                "http_status": result["status_code"],
                "elapsed_seconds": round(
                    result["elapsed_seconds"], 3
                ),
                "response": response,
            }

            print(
                f"FAIL | "
                f"HTTP {result['status_code']} | "
                f"{result['elapsed_seconds']:.2f}s"
            )

        summary.append(summary_entry)

        results.append({
            "name": name,
            "response": response,
        })

    combined_kml = generate_combined_kml(results)

    combined_kml_file = RESULTS_DIR / "all_routes.kml"

    with open(combined_kml_file, "w", encoding="utf-8") as file:
        file.write(combined_kml)

    summary_file = RESULTS_DIR / "summary.json"

    with open(summary_file, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    passed = sum(
        1 for item in summary
        if item["status"] == "PASS"
    )

    failed = len(summary) - passed

    print("-" * 90)
    print(
        f"Completed: {len(summary)} | "
        f"Passed: {passed} | "
        f"Failed: {failed}"
    )

    print(f"\nResults: {RESULTS_DIR}")
    print(f"Combined KML: {combined_kml_file}")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()