from pathlib import Path

import geopandas as gpd
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent

DATASETS = {
    "Existing OSM": (
        BASE_DIR
        / "building_service"
        / "artifacts"
        / "sf_buildings.geojson"
    ),
    "Overture Buildings": (
        BASE_DIR
        / "building_service"
        / "artifacts"
        / "sf_overture_buildings.geojson"
    ),
}

# Common possible height attributes.
HEIGHT_FIELDS = [
    "height",
    "height_m",
    "render_height",
    "num_floors",
    "num_floors",
    "roof_height",
]


def evaluate_dataset(name: str, path: Path) -> dict:
    print(f"\nLoading {name}: {path}")

    if not path.exists():
        print("  FILE NOT FOUND")
        return {"Dataset": name, "Error": "File not found"}

    gdf = gpd.read_file(path)

    if gdf.empty:
        return {"Dataset": name, "Error": "No features found"}

    if gdf.crs is None:
        raise ValueError(
            f"{name} has no CRS. Determine its coordinate system first."
        )

    # Evaluate geometry in a projected CRS suitable for San Francisco.
    projected = gdf.to_crs("EPSG:32610")

    non_empty = projected.geometry.notna() & ~projected.geometry.is_empty
    valid = projected.geometry.is_valid

    polygon_count = projected.geom_type.isin(
        ["Polygon", "MultiPolygon"]
    ).sum()

    height_fields = [
        field
        for field in HEIGHT_FIELDS
        if field in gdf.columns
    ]

    print(f"  Features: {len(gdf):,}")
    print(f"  Geometry types: {gdf.geom_type.value_counts().to_dict()}")
    print(f"  Polygon features: {polygon_count:,}")
    print(f"  Empty/null geometries: {(~non_empty).sum():,}")
    print(f"  Invalid geometries: {(~valid & non_empty).sum():,}")
    print(f"  Available height-related fields: {height_fields}")
    print(f"  All fields: {list(gdf.columns)}")

    result = {
        "Dataset": name,
        "Feature count": len(gdf),
        "Polygon count": int(polygon_count),
        "Empty/null geometries": int((~non_empty).sum()),
        "Invalid geometries": int((~valid & non_empty).sum()),
        "Height-related fields": ", ".join(height_fields),
    }

    # Report how many features have values in each candidate field.
    for field in height_fields:
        values = pd.to_numeric(gdf[field], errors="coerce")
        usable = values.notna() & (values > 0)

        result[f"{field}: positive values"] = int(usable.sum())
        result[f"{field}: coverage %"] = round(
            100 * usable.sum() / len(gdf), 2
        )

        if usable.any():
            result[f"{field}: median"] = round(
                float(values[usable].median()), 2
            )

    return result


if __name__ == "__main__":
    results = []

    for name, path in DATASETS.items():
        results.append(evaluate_dataset(name, path))

    report = pd.DataFrame(results)
    output = BASE_DIR / "building_service" / "artifacts" / "building_quality_report.csv"

    output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output, index=False)

    print(f"\nReport saved to: {output}")