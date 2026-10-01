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
/* REQUEST                            */
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
    ).textContent = formatNumber(
        metrics.battery_percent
    ) + "%";

    const maxAltitude = data.waypoints.length
        ? Math.max(
            ...data.waypoints.map(
                waypoint => waypoint.altitude_meters
            )
        )
        : 0;

    document.getElementById(
        "metric-max-altitude"
    ).textContent = formatNumber(maxAltitude);


    document.getElementById(
        "result-objective"
    ).textContent = data.objective.toUpperCase();

    document.getElementById(
        "result-vehicle"
    ).textContent = data.vehicle.profile;

    document.getElementById(
        "result-climb"
    ).textContent =
        formatNumber(metrics.total_climb_meters) + " M";

    document.getElementById(
        "result-descent"
    ).textContent =
        formatNumber(metrics.total_descent_meters) + " M";


    document.getElementById(
        "waypoint-count"
    ).textContent =
        `${data.waypoints.length} POINTS`;


    renderChart(data.waypoints);
    renderWaypoints(data.waypoints);


    resultSection.classList.add("visible");

    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });

}


/* ---------------------------------- */
/* ALTITUDE CHART                     */
/* ---------------------------------- */

function renderChart(waypoints) {

    const svg = document.getElementById("altitude-chart");

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


    /* Grid */

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
        line.setAttribute("x2", width - paddingRight);
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
        label.setAttribute("y", gridY + 4);

        label.setAttribute("class", "chart-label");

        label.textContent =
            Math.round(altitude) + "m";

        svg.appendChild(label);

    }


    /* Route line */

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

    path.setAttribute("d", pathData);
    path.setAttribute("class", "chart-line");

    svg.appendChild(path);


    /* Start / end markers */

    [0, waypoints.length - 1].forEach((index) => {

        const circle =
            document.createElementNS(
                "http://www.w3.org/2000/svg",
                "circle"
            );

        circle.setAttribute("cx", x(index));
        circle.setAttribute(
            "cy",
            y(waypoints[index].altitude_meters)
        );

        circle.setAttribute("r", 4);
        circle.setAttribute("fill", "#f4f4f0");

        svg.appendChild(circle);

    });

}


/* ---------------------------------- */
/* WAYPOINT TABLE                     */
/* ---------------------------------- */

function renderWaypoints(waypoints) {

    const table =
        document.getElementById("waypoint-table");

    table.innerHTML = "";


    waypoints.forEach((waypoint) => {

        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${waypoint.step}</td>
            <td>${formatCoordinate(waypoint.latitude)}</td>
            <td>${formatCoordinate(waypoint.longitude)}</td>
            <td>${formatNumber(waypoint.altitude_meters)}</td>
            <td>${waypoint.altitude_layer}</td>
            <td>${waypoint.type}</td>
        `;

        table.appendChild(row);

    });

}


/* ---------------------------------- */
/* HELPERS                            */
/* ---------------------------------- */

function formatNumber(value) {

    if (value === null || value === undefined) {
        return "—";
    }

    return Number(value).toLocaleString(
        undefined,
        {
            maximumFractionDigits: 2
        }
    );

}


function formatCoordinate(value) {

    if (value === null || value === undefined) {
        return "—";
    }

    return Number(value).toFixed(6);

}


function showError(message) {

    errorBox.textContent = message;
    errorBox.classList.add("visible");

    errorBox.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });

}


function clearError() {

    errorBox.textContent = "";
    errorBox.classList.remove("visible");

}


/* ---------------------------------- */
/* EVENTS                             */
/* ---------------------------------- */

calculateButton.addEventListener(
    "click",
    calculateRoute
);