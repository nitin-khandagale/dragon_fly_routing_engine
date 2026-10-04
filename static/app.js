import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";


const tabs = document.querySelectorAll(".input-tab");
const formMode = document.getElementById("form-mode");
const jsonMode = document.getElementById("json-mode");

const calculateButton = document.getElementById("calculate-route");
const requestStatus = document.getElementById("request-status");

const resultSection = document.getElementById("result-section");
const errorBox = document.getElementById("error-box");

const requestJson = document.getElementById("request-json");
const loadExampleButton = document.getElementById("load-example");

let currentMode = "form";

let scene = null;
let camera = null;
let renderer = null;
let controls = null;
let routeGroup = null;
let routeOriginPosition = null;
let routeDestinationPosition = null;

let animationFrame = null;


const exampleRequest = {
    start_lat: 37.79448372,
    start_lon: -122.40547051,
    goal_lat: 37.78695766,
    goal_lon: -122.38931347,
    start_altitude_meters: 0,
    goal_altitude_meters: 0,
    minimum_transit_altitude_meters: 30,
    max_altitude_meters: 300,
    objective: "distance",
    vehicle_profile: "default_multirotor"
};


/* ---------------------------------- */
/* INPUT MODE                         */
/* ---------------------------------- */

tabs.forEach((tab) => {

    tab.addEventListener("click", () => {

        currentMode = tab.dataset.mode;

        tabs.forEach((item) => {
            item.classList.remove("active");
        });

        tab.classList.add("active");

        formMode.classList.toggle(
            "active",
            currentMode === "form"
        );

        jsonMode.classList.toggle(
            "active",
            currentMode === "json"
        );

    });

});


/* ---------------------------------- */
/* JSON EXAMPLE                       */
/* ---------------------------------- */

loadExampleButton.addEventListener("click", () => {

    requestJson.value = JSON.stringify(
        exampleRequest,
        null,
        2
    );

});


/* ---------------------------------- */
/* FORM REQUEST                       */
/* ---------------------------------- */

function getFormRequest() {

    return {
        start_lat: Number(
            document.getElementById("start_lat").value
        ),

        start_lon: Number(
            document.getElementById("start_lon").value
        ),

        goal_lat: Number(
            document.getElementById("goal_lat").value
        ),

        goal_lon: Number(
            document.getElementById("goal_lon").value
        ),

        start_altitude_meters: Number(
            document.getElementById("start_altitude_meters").value
        ),

        goal_altitude_meters: Number(
            document.getElementById("goal_altitude_meters").value
        ),

        minimum_transit_altitude_meters: Number(
            document.getElementById(
                "minimum_transit_altitude_meters"
            ).value
        ),

        max_altitude_meters: Number(
            document.getElementById("max_altitude_meters").value
        ),

        objective: document.getElementById("objective").value,

        vehicle_profile: document.getElementById(
            "vehicle_profile"
        ).value
    };

}


/* ---------------------------------- */
/* JSON REQUEST                       */
/* ---------------------------------- */

function getJsonRequest() {

    let parsed;

    try {
        parsed = JSON.parse(requestJson.value);
    } catch (error) {
        throw new Error(
            "Invalid JSON. Please check the request body."
        );
    }

    if (
        parsed === null ||
        typeof parsed !== "object" ||
        Array.isArray(parsed)
    ) {
        throw new Error(
            "Request JSON must be a JSON object."
        );
    }

    return parsed;

}


/* ---------------------------------- */
/* CALCULATE ROUTE                    */
/* ---------------------------------- */

async function calculateRoute() {

    clearError();

    calculateButton.disabled = true;
    requestStatus.textContent = "CALCULATING...";

    try {

        const request =
            currentMode === "form"
                ? getFormRequest()
                : getJsonRequest();


        const response = await fetch("/route", {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify(request)
        });


        const data = await response.json();


        if (!response.ok) {
            throw new Error(
                data.detail || "Routing request failed."
            );
        }


        renderResult(data);

        requestStatus.textContent = "ROUTE VALIDATED";

    } catch (error) {

        showError(error.message);

        requestStatus.textContent = "REQUEST FAILED";

    } finally {

        calculateButton.disabled = false;

    }

}


/* ---------------------------------- */
/* RESULT                             */
/* ---------------------------------- */

function renderResult(data) {

    const metrics = data.metrics;

    document.getElementById(
        "metric-distance"
    ).textContent = formatNumber(
        metrics.distance_meters
    );

    document.getElementById(
        "metric-3d-distance"
    ).textContent = formatNumber(
        metrics["3d_distance_meters"]
    );

    document.getElementById(
        "metric-energy"
    ).textContent = formatNumber(
        metrics.energy_wh
    );

    document.getElementById(
        "metric-flight-time"
    ).textContent = formatNumber(
        metrics.flight_time_seconds
    );

    document.getElementById(
        "metric-battery"
    ).textContent =
        formatNumber(metrics.battery_percent) + "%";


    const maxAltitude = data.waypoints.length
        ? Math.max(
            ...data.waypoints.map(
                waypoint => waypoint.altitude_meters
            )
        )
        : 0;


    document.getElementById(
        "metric-max-altitude"
    ).textContent =
        formatNumber(maxAltitude);


    document.getElementById(
        "result-objective"
    ).textContent =
        data.objective.toUpperCase();


    document.getElementById(
        "result-vehicle"
    ).textContent =
        data.vehicle.profile;


    document.getElementById(
        "result-climb"
    ).textContent =
        formatNumber(metrics.total_climb_meters) + " M";


    document.getElementById(
        "result-descent"
    ).textContent =
        formatNumber(metrics.total_descent_meters) + " M";


    document.getElementById(
        "route-3d-info"
    ).textContent =
        `${data.waypoints.length} WAYPOINTS / 3D`;


    renderChart(data.waypoints);

    resultSection.classList.add("visible");

    render3DRoute(data.waypoints);

    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
    }


/* ---------------------------------- */
/* ALTITUDE CHART                     */
/* ---------------------------------- */

function renderChart(waypoints) {

    const svg =
        document.getElementById("altitude-chart");

    svg.innerHTML = "";

    if (!waypoints.length) {
        return;
    }


    const width = 1000;
    const height = 300;

    const paddingLeft = 50;
    const paddingRight = 20;
    const paddingTop = 25;
    const paddingBottom = 35;


    const chartWidth =
        width - paddingLeft - paddingRight;

    const chartHeight =
        height - paddingTop - paddingBottom;


    const altitudes = waypoints.map(
        waypoint => waypoint.altitude_meters
    );


    const minAltitude = Math.min(...altitudes);
    const maxAltitude = Math.max(...altitudes);

    const range =
        Math.max(maxAltitude - minAltitude, 1);


    function x(index) {

        if (waypoints.length === 1) {
            return paddingLeft;
        }

        return paddingLeft +
            (index / (waypoints.length - 1)) *
            chartWidth;

    }


    function y(altitude) {

        return paddingTop +
            chartHeight -
            ((altitude - minAltitude) / range) *
            chartHeight;

    }


    for (let i = 0; i <= 4; i++) {

        const gridY =
            paddingTop +
            (chartHeight / 4) * i;


        const line =
            document.createElementNS(
                "http://www.w3.org/2000/svg",
                "line"
            );

        line.setAttribute("x1", paddingLeft);
        line.setAttribute(
            "x2",
            width - paddingRight
        );

        line.setAttribute("y1", gridY);
        line.setAttribute("y2", gridY);

        line.setAttribute("class", "chart-grid");

        svg.appendChild(line);


        const altitude =
            maxAltitude -
            (range / 4) * i;


        const label =
            document.createElementNS(
                "http://www.w3.org/2000/svg",
                "text"
            );

        label.setAttribute("x", 8);
        label.setAttribute(
            "y",
            gridY + 4
        );

        label.setAttribute(
            "class",
            "chart-label"
        );

        label.textContent =
            Math.round(altitude) + "m";

        svg.appendChild(label);

    }


    let pathData = "";

    waypoints.forEach((waypoint, index) => {

        const command =
            index === 0 ? "M" : "L";

        pathData +=
            `${command} ${x(index)} ${y(
                waypoint.altitude_meters
            )} `;

    });


    const path =
        document.createElementNS(
            "http://www.w3.org/2000/svg",
            "path"
        );

    path.setAttribute(
        "d",
        pathData
    );

    path.setAttribute(
        "class",
        "chart-line"
    );

    svg.appendChild(path);


    [0, waypoints.length - 1].forEach(
        (index) => {

            const circle =
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    "circle"
                );

            circle.setAttribute(
                "cx",
                x(index)
            );

            circle.setAttribute(
                "cy",
                y(
                    waypoints[index].altitude_meters
                )
            );

            circle.setAttribute(
                "r",
                4
            );

            circle.setAttribute(
                "fill",
                "#f4f4f0"
            );

            svg.appendChild(circle);

        }
    );

}


/* ---------------------------------- */
/* THREE.JS ROUTE VIEW                */
/* ---------------------------------- */

function init3DScene() {

    const container =
        document.getElementById("route-3d-view");

    if (!container) {
        return;
    }

    scene = new THREE.Scene();

    scene.background =
        new THREE.Color(0x080808);


    camera =
        new THREE.PerspectiveCamera(
            45,
            container.clientWidth /
                container.clientHeight,
            0.1,
            100000
        );


    renderer =
        new THREE.WebGLRenderer({
            antialias: true
        });


    renderer.setPixelRatio(
        Math.min(window.devicePixelRatio, 2)
    );


    renderer.setSize(
        container.clientWidth,
        container.clientHeight
    );


    container.appendChild(
        renderer.domElement
    );


    controls =
        new OrbitControls(
            camera,
            renderer.domElement
        );


    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    controls.minDistance = 10;
    controls.maxDistance = 10000;


    /* ---------------------------------- */
    /* Lighting                           */
    /* ---------------------------------- */

    scene.add(
        new THREE.AmbientLight(
            0xffffff,
            1.5
        )
    );


    const light =
        new THREE.DirectionalLight(
            0xffffff,
            2
        );

    light.position.set(
        200,
        500,
        200
    );

    scene.add(light);


    /* ---------------------------------- */
    /* Ground grid                        */
    /* ---------------------------------- */

    const grid =
        new THREE.GridHelper(
            2000,
            40,
            0x333333,
            0x181818
        );

    scene.add(grid);


    window.addEventListener(
        "resize",
        resize3DScene
    );


    animate3D();
}


/* ---------------------------------- */
/* RENDER 3D ROUTE                    */
/* ---------------------------------- */

function render3DRoute(waypoints) {

    if (!waypoints || waypoints.length < 2) {
        return;
    }

    // The results section must be visible before Three.js
    // measures the container.
    resultSection.classList.add("visible");

    if (!scene) {
        init3DScene();
    }

    // The browser may not have completed layout yet.
    // Re-measure the renderer after the results section is visible.
    resize3DScene();


    /* Remove previous route */

    if (routeGroup) {
        scene.remove(routeGroup);
    }


    routeGroup =
        new THREE.Group();


    /*
     * Geographic origin.
     *
     * Everything is converted into a local
     * coordinate system around the first point.
     */

    const origin =
        waypoints[0];


    const metersPerLatitude =
        111320;


    const metersPerLongitude =
        111320 *
        Math.cos(
            origin.latitude *
            Math.PI /
            180
        );


    /*
     * Convert every API waypoint into
     * Three.js coordinates.
     */

    const positions =
        waypoints.map((waypoint) => {

            const x =
                (
                    waypoint.longitude -
                    origin.longitude
                ) *
                metersPerLongitude;


            const z =
                -(
                    waypoint.latitude -
                    origin.latitude
                ) *
                metersPerLatitude;


            /*
             * Exaggerate altitude so that
             * the 3D route is visually clear.
             */

            const y =
                Number(
                    waypoint.altitude_meters
                ) * 1.8;


            return new THREE.Vector3(
                x,
                y,
                z
            );

        });


    /* ---------------------------------- */
    /* ROUTE LINE                         */
    /* ---------------------------------- */

    const routeGeometry =
        new THREE.BufferGeometry();

    routeGeometry.setFromPoints(
        positions
    );


    const routeMaterial =
        new THREE.LineBasicMaterial({
            color: 0xffffff,
            transparent: false
        });


    const routeLine =
        new THREE.Line(
            routeGeometry,
            routeMaterial
        );


    routeGroup.add(
        routeLine
    );


    /* ---------------------------------- */
    /* GROUND PROJECTION                  */
    /* ---------------------------------- */

    const groundPositions =
        positions.map(
            (point) =>
                new THREE.Vector3(
                    point.x,
                    0,
                    point.z
                )
        );


    const groundGeometry =
        new THREE.BufferGeometry();

    groundGeometry.setFromPoints(
        groundPositions
    );


    const groundMaterial =
        new THREE.LineDashedMaterial({
            color: 0x777777,
            dashSize: 5,
            gapSize: 5
        });


    const groundLine =
        new THREE.Line(
            groundGeometry,
            groundMaterial
        );


    groundLine.computeLineDistances();


    routeGroup.add(
        groundLine
    );


    /* ---------------------------------- */
    /* ALTITUDE GUIDES                    */
    /* ---------------------------------- */

    positions.forEach((point) => {

        const geometry =
            new THREE.BufferGeometry();

        geometry.setFromPoints([
            new THREE.Vector3(
                point.x,
                0,
                point.z
            ),

            point
        ]);


        const material =
            new THREE.LineBasicMaterial({
                color: 0x555555,
                transparent: true,
                opacity: 0.45
            });


        const line =
            new THREE.Line(
                geometry,
                material
            );


        routeGroup.add(line);

    });


    /* ---------------------------------- */
    /* ADD ROUTE TO SCENE                 */
    /* ---------------------------------- */

    scene.add(
        routeGroup
    );


    /* ---------------------------------- */
    /* FIT CAMERA TO ROUTE                */
    /* ---------------------------------- */

    const box =
        new THREE.Box3();

    positions.forEach(
        (point) => {
            box.expandByPoint(point);
        }
    );


    const center =
        new THREE.Vector3();

    box.getCenter(center);


    const size =
        new THREE.Vector3();

    box.getSize(size);


    const maxDimension =
        Math.max(
            size.x,
            size.y,
            size.z,
            100
        );

    routeOriginPosition = positions[0].clone();
    routeDestinationPosition = positions[positions.length - 1].clone();

    const endpointRadius = Math.max(
        maxDimension * 0.012,
        3
    );

    const endpointGeometry = new THREE.SphereGeometry(
        endpointRadius,
        16,
        12
    );

    const originMarker = new THREE.Mesh(
        endpointGeometry,
        new THREE.MeshBasicMaterial({ color: 0x72e0a2 })
    );
    originMarker.position.copy(routeOriginPosition);
    routeGroup.add(originMarker);

    const destinationMarker = new THREE.Mesh(
        endpointGeometry,
        new THREE.MeshBasicMaterial({ color: 0xffb86b })
    );
    destinationMarker.position.copy(routeDestinationPosition);
    routeGroup.add(destinationMarker);

    /*
     * Fit the camera to the complete route.
     * Use the bounding sphere so long routes are not
     * clipped by the camera field of view.
     */

    const radius = Math.max(
        box.getBoundingSphere(
            new THREE.Sphere()
        ).radius,
        50
    );

    const fovRadians =
        camera.fov * Math.PI / 180;

    const cameraDistance =
        (radius / Math.sin(fovRadians / 2)) * 1.35;

    const direction =
        new THREE.Vector3(
            1,
            0.75,
            1
        ).normalize();

    camera.position.copy(
        center
    ).add(
        direction.multiplyScalar(
            cameraDistance
        )
    );

    camera.near = 0.1;
    camera.far = Math.max(
        100000,
        cameraDistance * 10
    );

    camera.updateProjectionMatrix();

    controls.target.copy(
        center
    );

    controls.update();


    /* ---------------------------------- */
    /* UI                                  */
    /* ---------------------------------- */

    const maxAltitude =
        Math.max(
            ...waypoints.map(
                waypoint =>
                    Number(
                        waypoint.altitude_meters
                    )
            )
        );


    document.getElementById(
        "route-start-altitude"
    ).textContent =
        formatNumber(
            waypoints[0].altitude_meters
        ) + " M";


    document.getElementById(
        "route-view-max-altitude"
    ).textContent =
        formatNumber(
            maxAltitude
        ) + " M";


    document.getElementById(
        "route-goal-altitude"
    ).textContent =
        formatNumber(
            waypoints[
                waypoints.length - 1
            ].altitude_meters
        ) + " M";


    document.getElementById(
        "route-3d-info"
    ).textContent =
        `${waypoints.length} WAYPOINTS / 3D`;
}


/* ---------------------------------- */
/* ANIMATION                          */
/* ---------------------------------- */

function animate3D() {

    animationFrame =
        requestAnimationFrame(
            animate3D
        );


    if (controls) {
        controls.update();
    }


    updateRoutePointLabels();


    if (
        renderer &&
        scene &&
        camera
    ) {

        renderer.render(
            scene,
            camera
        );

    }
}


function updateRoutePointLabels() {

    if (!camera || !renderer || !routeOriginPosition || !routeDestinationPosition) {
        return;
    }

    const container = document.getElementById("route-3d-view");
    const labels = [
        ["route-origin-label", routeOriginPosition],
        ["route-destination-label", routeDestinationPosition]
    ];

    camera.updateMatrixWorld();

    labels.forEach(([id, position]) => {
        const label = document.getElementById(id);
        const projected = position.clone().project(camera);
        const visible = projected.z >= -1 && projected.z <= 1;

        label.style.display = visible ? "block" : "none";

        if (!visible) {
            return;
        }

        label.style.left = `${(projected.x + 1) * 0.5 * container.clientWidth}px`;
        label.style.top = `${(1 - projected.y) * 0.5 * container.clientHeight}px`;
        label.style.transform = "translate(-50%, -130%)";
    });
}


/* ---------------------------------- */
/* RESIZE                             */
/* ---------------------------------- */

function resize3DScene() {

    const container =
        document.getElementById(
            "route-3d-view"
        );


    if (
        !container ||
        !camera ||
        !renderer
    ) {
        return;
    }


    const width =
        container.clientWidth;


    const height =
        container.clientHeight;


    camera.aspect =
        width / height;


    camera.updateProjectionMatrix();


    renderer.setSize(
        width,
        height
    );
}


/* ---------------------------------- */
/* HELPERS                             */
/* ---------------------------------- */

function formatNumber(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "—";
    }


    return Number(value).toLocaleString(
        undefined,
        {
            maximumFractionDigits: 2
        }
    );

}


function showError(message) {

    errorBox.textContent =
        message;

    errorBox.classList.add(
        "visible"
    );


    errorBox.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });

}


function clearError() {

    errorBox.textContent = "";

    errorBox.classList.remove(
        "visible"
    );

}


/* ---------------------------------- */
/* EVENTS                             */
/* ---------------------------------- */

calculateButton.addEventListener(
    "click",
    calculateRoute
);


/* ---------------------------------- */
/* INITIALIZE 3D VIEW                 */
/* ---------------------------------- */