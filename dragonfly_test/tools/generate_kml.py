from __future__ import annotations

import html
from pathlib import Path


def generate_kml(route_data, output_path: Path, name: str):
    waypoints = route_data.get("waypoints", [])

    coordinates = "\n".join(
        f"{waypoint['longitude']},{waypoint['latitude']},"
        f"{waypoint.get('altitude_meters', 0)}"
        for waypoint in waypoints
    )

    placemarks = []

    for waypoint in waypoints:
        step = waypoint.get("step")
        altitude = waypoint.get("altitude_meters", 0)

        label = html.escape(
            f"Step {step} | {altitude} m"
        )

        placemarks.append(
            f"""
            <Placemark>
                <name>{label}</name>
                <Point>
                    <altitudeMode>absolute</altitudeMode>
                    <coordinates>
                        {waypoint['longitude']},
                        {waypoint['latitude']},
                        {altitude}
                    </coordinates>
                </Point>
            </Placemark>
            """
        )

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <name>{html.escape(name)}</name>

        <Style id="route">
            <LineStyle>
                <width>4</width>
            </LineStyle>
        </Style>

        <Placemark>
            <name>DragonFly Route</name>
            <styleUrl>#route</styleUrl>
            <LineString>
                <altitudeMode>absolute</altitudeMode>
                <tessellate>1</tessellate>
                <coordinates>
                    {coordinates}
                </coordinates>
            </LineString>
        </Placemark>

        {''.join(placemarks)}
    </Document>
</kml>
"""

    output_path.write_text(kml, encoding="utf-8")