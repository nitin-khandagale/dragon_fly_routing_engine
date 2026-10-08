from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


KML_NAMESPACE = "http://www.opengis.net/kml/2.2"


def generate_route_kml(
    waypoints: list,
    route_name: str = "DragonFly Route",
) -> str:
    """
    Generate a KML document containing the 3D route.

    Each waypoint must provide:
        latitude
        longitude
        altitude_meters
    """

    kml = Element(
        "kml",
        {
            "xmlns": KML_NAMESPACE,
        },
    )

    document = SubElement(kml, "Document")

    name = SubElement(document, "name")
    name.text = route_name

    # Route style
    style = SubElement(document, "Style", {"id": "routeStyle"})

    line_style = SubElement(style, "LineStyle")

    color = SubElement(line_style, "color")
    color.text = "ff00ffff"

    width = SubElement(line_style, "width")
    width.text = "5"

    # Route
    route_placemark = SubElement(document, "Placemark")

    route_name_element = SubElement(route_placemark, "name")
    route_name_element.text = route_name

    style_url = SubElement(route_placemark, "styleUrl")
    style_url.text = "#routeStyle"

    line_string = SubElement(
        route_placemark,
        "LineString",
    )

    altitude_mode = SubElement(
        line_string,
        "altitudeMode",
    )
    altitude_mode.text = "absolute"

    tessellate = SubElement(
        line_string,
        "tessellate",
    )
    tessellate.text = "1"

    coordinates = SubElement(
        line_string,
        "coordinates",
    )

    coordinate_values = []

    for waypoint in waypoints:
        coordinate_values.append(
            f"{waypoint.longitude},"
            f"{waypoint.latitude},"
            f"{waypoint.altitude_meters}"
        )

    coordinates.text = " ".join(coordinate_values)

    # Start marker
    if waypoints:
        start = waypoints[0]

        start_placemark = SubElement(
            document,
            "Placemark",
        )

        start_name = SubElement(start_placemark, "name")
        start_name.text = "Start"

        point = SubElement(
            start_placemark,
            "Point",
        )

        start_altitude_mode = SubElement(
            point,
            "altitudeMode",
        )
        start_altitude_mode.text = "absolute"

        start_coordinates = SubElement(
            point,
            "coordinates",
        )
        start_coordinates.text = (
            f"{start.longitude},"
            f"{start.latitude},"
            f"{start.altitude_meters}"
        )

    # Goal marker
    if waypoints:
        goal = waypoints[-1]

        goal_placemark = SubElement(
            document,
            "Placemark",
        )

        goal_name = SubElement(goal_placemark, "name")
        goal_name.text = "Goal"

        point = SubElement(
            goal_placemark,
            "Point",
        )

        goal_altitude_mode = SubElement(
            point,
            "altitudeMode",
        )
        goal_altitude_mode.text = "absolute"

        goal_coordinates = SubElement(
            point,
            "coordinates",
        )
        goal_coordinates.text = (
            f"{goal.longitude},"
            f"{goal.latitude},"
            f"{goal.altitude_meters}"
        )

    # Pretty-print XML
    raw_xml = tostring(
        kml,
        encoding="utf-8",
        xml_declaration=True,
    )

    parsed = minidom.parseString(raw_xml)

    return parsed.toprettyxml(
        indent="  ",
        encoding="utf-8",
    ).decode("utf-8")