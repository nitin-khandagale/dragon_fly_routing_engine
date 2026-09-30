# DragonFly UTM Routing Engine

A 3D drone routing engine that computes collision-free routes through
building-constrained environments using H3 spatial cells, altitude
layers, and A* pathfinding.

## V1 Capability

DragonFly accepts a routing request and returns a validated 3D route
with:

- Exact start and goal coordinates
- Building-aware collision avoidance
- 3D altitude routing
- Distance or energy optimization
- Vehicle profile selection
- Route distance and 3D distance
- Climb and descent totals
- Estimated flight time
- Estimated energy consumption
- Estimated battery usage

The current V1 uses a defined `default_multirotor` vehicle profile and
a practical model-based energy estimate.

## Architecture

```text
Client
  |
  v
FastAPI
  |
  v
RoutingEngine
  |
  +--> Building Service
  |      |
  |      +--> SF building GeoJSON
  |      +--> Building heights
  |      +--> Blocked 3D voxels
  |
  +--> Pathfinder3D
  |      |
  |      +--> H3 resolution 11
  |      +--> 15 m altitude layers
  |      +--> A* search
  |
  +--> Cost Model
  |      |
  |      +--> Distance
  |      +--> Energy
  |
  +--> Vehicle Profile
  |
  v
Validated 3D Route
  |
  +--> Waypoints
  +--> Route metrics
  +--> Energy metrics
````

## Project Structure

```text
dragon_fly/
├── main.py
├── api/
│   ├── models.py
│   └── routes.py
├── engine/
│   ├── routing_engine.py
│   ├── vehicle_energy.py
│   ├── vehicle_profile.py
│   └── cost_models/
├── building_service/
│   ├── building_service.py
│   └── artifacts/
│       └── sf_buildings.geojson
├── weather_service/
├── src/
├── dragonfly_test/
├── requirements.txt
├── Dockerfile
└── .dockerignore
```

## Routing Model

DragonFly represents each routing state as:

```text
(H3 cell, altitude layer)
```

Current configuration:

| Parameter                     |    V1 |
| ----------------------------- | ----: |
| H3 resolution                 |    11 |
| Altitude layer                |  15 m |
| Maximum altitude              | 300 m |
| Horizontal building clearance |  15 m |
| Vertical building clearance   |  15 m |

Building heights are derived from:

1. `height`
2. `num_floors × 3.5 m`
3. 15 m fallback

## Optimization

The API supports two objectives:

### Distance

Minimizes the routing cost based on horizontal and vertical movement.

### Energy

Uses the selected vehicle profile to estimate energy required for
horizontal flight, climbing, and descending.

The two objectives can produce different 3D routes. For the current
San Francisco baseline, the energy objective selects a lower-altitude,
longer-horizontal route while consuming less estimated energy than the
distance-optimized route.

## Vehicle Profile

Current V1 profile:

```text
default_multirotor
```

Key parameters include:

* Mass
* Cruise speed
* Climb speed
* Descent speed
* Horizontal power
* Climb power
* Descent power
* Battery capacity
* Maximum altitude
* Maximum climb/descent rate

The current energy model is intended for V1 route optimization and
estimation. It is not a certified aircraft performance or flight-safety
model.

## API

### Health Check

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "service": "dragonfly-routing-engine",
  "version": "1.2"
}
```

### Route

```http
POST /route
```

Example:

```json
{
  "start_lat": 37.79448372,
  "start_lon": -122.40547051,
  "goal_lat": 37.78695766,
  "goal_lon": -122.38931347,
  "start_altitude_meters": 0,
  "goal_altitude_meters": 0,
  "minimum_transit_altitude_meters": 30,
  "max_altitude_meters": 300,
  "objective": "energy",
  "vehicle_profile": "default_multirotor"
}
```

The response contains:

```text
status
objective
vehicle
metrics
waypoints
```

### Metrics

The route response currently reports:

```text
distance_meters
3d_distance_meters
total_climb_meters
total_descent_meters
flight_time_seconds
energy_joules
energy_wh
battery_percent
```

## Running Locally

### Create environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Start the API

```bash
uvicorn main:app --reload
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Docker

Build:

```bash
docker build -t dragonfly-routing-engine .
```

Run:

```bash
docker run --rm -p 8000:8000 dragonfly-routing-engine
```

Then:

```text
http://localhost:8000/docs
http://localhost:8000/health
```

## Testing

The project includes automated tests covering:

* Vehicle energy calculations
* Route request validation
* Routing regression
* Distance vs energy objectives
* Route metric consistency
* API response behavior
* Health endpoint

Run all tests:

```bash
pytest -v
```

## Working Routing Demonstration

The following test demonstrates the current 3D routing behaviour in a
dense San Francisco building area.

### Request

```json
{
  "start_lat": 37.79448372,
  "start_lon": -122.40547051,
  "goal_lat": 37.78695766,
  "goal_lon": -122.38931347,
  "start_altitude_meters": 0,
  "goal_altitude_meters": 0,
  "minimum_transit_altitude_meters": 30,
  "max_altitude_meters": 300,
  "objective": "energy",
  "vehicle_profile": "default_multirotor"
}
```

### Result

The generated route navigates through the building-constrained
environment using available horizontal and altitude layers.

![Working 3D routing result](docs/images/routing-result.png)

## V1 Validation

The current V1 baseline has automated regression coverage for:

* Exact endpoint preservation
* Altitude bounds
* Successful 3D routing
* Distance optimization
* Energy optimization
* Energy metric consistency
* API validation
* Health endpoint

The Docker image has also been verified by running both `/health` and
`/route` successfully inside the container.

## Development Principle

DragonFly is developed incrementally from a known-good routing baseline.

When changing routing behaviour:

1. Reproduce the baseline.
2. Change one component.
3. Run the regression tests.
4. Compare the resulting route and metrics.
5. Keep the change only when the baseline remains valid.

## Scope

The current V1 focuses on single-route 3D path planning with building
constraints, vehicle-aware cost models, and route metrics.

Advanced UTM capabilities, multi-drone coordination, weather/wind
optimization, restricted airspace integration, and production flight
certification are outside the current V1 scope.

```

**I would use this as the README update.** It accurately reflects what you've actually built now, rather than presenting completed work as “Next.”

One important wording choice: I used **“validated 3D route”** in the context of your implemented routing/collision validation, while explicitly avoiding any claim that this is a **flight-certified safety system**.

If you want, I can next turn this exact content into the actual `README.md` file for you.
```
