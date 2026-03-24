// ── State ────────────────────────────────────────────────────
let map, marker, routeLine, routeDisplayLine;
let routePoints = [];
let routeMarkers = [];
let routePolling = null;
let searchTimeout = null;
let selectedSpeed = 15;
let darkTiles = true;

const TILES = {
    dark: {
        url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://osm.org/">OSM</a>',
    },
    light: {
        url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://osm.org/">OSM</a>',
    },
};

let tileLayer;

// ── Init ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    // Load default location FIRST so the map opens on the user's real location
    let startLat = 40.7128, startLon = -74.006;
    try {
        const r = await fetch("/api/default-location");
        const d = await r.json();
        if (d.lat && d.lon) { startLat = d.lat; startLon = d.lon; }
    } catch (e) { /* NYC fallback */ }

    map = L.map("map", { zoomControl: false }).setView([startLat, startLon], 13);
    tileLayer = L.tileLayer(TILES.dark.url, {
        attribution: TILES.dark.attr,
        maxZoom: 19,
        subdomains: "abcd",
    }).addTo(map);

    map.on("click", onMapClick);

    // Bind events
    $("btn-set").addEventListener("click", setLocation);
    $("btn-clear").addEventListener("click", clearLocation);
    $("btn-save").addEventListener("click", saveLocation);
    $("btn-route-start").addEventListener("click", startRoute);
    $("btn-route-stop").addEventListener("click", stopRoute);
    $("btn-route-clear").addEventListener("click", clearRoutePoints);
    $("sidebar-toggle").addEventListener("click", toggleSidebar);
    $("btn-layer").addEventListener("click", toggleTiles);
    $("search-input").addEventListener("input", onSearchInput);
    $("search-input").addEventListener("focus", () => {
        if ($("search-results").children.length > 0)
            $("search-results").classList.add("visible");
    });

    document.querySelectorAll(".seg-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            selectedSpeed = parseInt(btn.dataset.speed);
            $("speed-input").value = selectedSpeed;
        });
    });

    $("speed-input").addEventListener("change", (e) => {
        selectedSpeed = parseInt(e.target.value) || 15;
        document.querySelectorAll(".seg-btn").forEach((b) =>
            b.classList.toggle("active", parseInt(b.dataset.speed) === selectedSpeed)
        );
    });

    // Close search on outside click
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".search-container"))
            $("search-results").classList.remove("visible");
    });

    // Load data
    pollDevice();
    loadSaved();
    setInterval(pollDevice, 5000);
});

function $(id) { return document.getElementById(id); }

// ── Toasts ───────────────────────────────────────────────────
function toast(msg, type = "success") {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    $("toasts").appendChild(el);
    setTimeout(() => {
        el.classList.add("out");
        setTimeout(() => el.remove(), 300);
    }, 3000);
}

// ── Map ──────────────────────────────────────────────────────
function onMapClick(e) {
    if (e.originalEvent.shiftKey || routePoints.length > 0) {
        addRoutePoint(e.latlng.lat, e.latlng.lng);
    } else {
        placeMarker(e.latlng.lat, e.latlng.lng);
    }
}

function placeMarker(lat, lng) {
    if (marker) {
        marker.setLatLng([lat, lng]);
    } else {
        marker = L.circleMarker([lat, lng], {
            radius: 8, color: "#58a6ff", fillColor: "#58a6ff",
            fillOpacity: 1, weight: 2, opacity: 0.6,
        }).addTo(map);
        // Pulsing ring
        const pulse = L.circleMarker([lat, lng], {
            radius: 16, color: "#58a6ff", fillOpacity: 0,
            weight: 1.5, opacity: 0.3, className: "pulse-ring",
        }).addTo(map);
        marker._pulse = pulse;
    }
    if (marker._pulse) marker._pulse.setLatLng([lat, lng]);
    $("lat-input").value = lat.toFixed(6);
    $("lon-input").value = lng.toFixed(6);
}

function toggleTiles() {
    darkTiles = !darkTiles;
    const t = darkTiles ? TILES.dark : TILES.light;
    map.removeLayer(tileLayer);
    tileLayer = L.tileLayer(t.url, { attribution: t.attr, maxZoom: 19, subdomains: "abcd" }).addTo(map);
}

function toggleSidebar() {
    $("sidebar").classList.toggle("collapsed");
    setTimeout(() => map.invalidateSize(), 350);
}

// ── Location ─────────────────────────────────────────────────
async function setLocation() {
    const lat = parseFloat($("lat-input").value);
    const lon = parseFloat($("lon-input").value);
    if (isNaN(lat) || isNaN(lon)) return toast("Place a marker on the map first", "error");

    try {
        const r = await fetch("/api/location/set", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lat, lon }),
        });
        const d = await r.json();
        if (r.ok) {
            toast(`Location set: ${lat.toFixed(4)}, ${lon.toFixed(4)}`);
            placeMarker(lat, lon);
        } else toast(d.error || "Failed", "error");
    } catch (e) { toast("Connection error", "error"); }
}

async function clearLocation() {
    try {
        const r = await fetch("/api/location/clear", { method: "POST" });
        if (r.ok) {
            toast("Reset to real GPS");
            if (marker) { map.removeLayer(marker); if (marker._pulse) map.removeLayer(marker._pulse); marker = null; }
            $("lat-input").value = "";
            $("lon-input").value = "";
        }
    } catch (e) { toast("Connection error", "error"); }
}

// ── Search ───────────────────────────────────────────────────
function onSearchInput(e) {
    const q = e.target.value.trim();
    clearTimeout(searchTimeout);
    if (q.length < 2) { $("search-results").classList.remove("visible"); return; }
    searchTimeout = setTimeout(() => doSearch(q), 250);
}

async function doSearch(q) {
    try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const results = await r.json();
        const c = $("search-results");
        if (!Array.isArray(results) || !results.length) { c.classList.remove("visible"); return; }

        c.innerHTML = results.map((r) => `
            <div class="search-item" data-lat="${r.lat}" data-lon="${r.lon}">
                <div class="search-item-icon">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
                </div>
                <div class="search-item-text">${r.display_name}</div>
            </div>
        `).join("");

        c.classList.add("visible");
        c.querySelectorAll(".search-item").forEach((item) => {
            item.addEventListener("click", () => {
                const lat = parseFloat(item.dataset.lat);
                const lon = parseFloat(item.dataset.lon);
                map.flyTo([lat, lon], 16, { duration: 1.2 });
                placeMarker(lat, lon);
                c.classList.remove("visible");
                $("search-input").value = item.querySelector(".search-item-text").textContent.trim();
            });
        });
    } catch (e) { /* silent */ }
}

// ── Device polling ───────────────────────────────────────────
async function pollDevice() {
    try {
        const r = await fetch("/api/device");
        const d = await r.json();
        const dot = $("device-dot");
        if (d.connected) {
            dot.classList.add("connected");
            $("device-label").textContent = d.name || "iPhone";
            $("dev-name").textContent = d.name || "iPhone";
            $("dev-ios").textContent = d.ios_version || "--";
            $("dev-model").textContent = d.model || "--";
            $("dev-udid").textContent = d.udid || "--";
        } else {
            dot.classList.remove("connected");
            $("device-label").textContent = "Disconnected";
        }
    } catch (e) { /* server down */ }
}

// ── Saved locations ──────────────────────────────────────────
async function loadSaved() {
    try {
        const r = await fetch("/api/saved");
        const locs = await r.json();
        const c = $("saved-list");
        if (!locs.length) { c.innerHTML = '<div class="empty-state">No saved locations</div>'; return; }

        c.innerHTML = locs.map((l) => `
            <div class="saved-item" data-lat="${l.lat}" data-lon="${l.lon}">
                <span class="saved-name">${l.name}</span>
                <span class="saved-coords">${l.lat.toFixed(2)}, ${l.lon.toFixed(2)}</span>
                <button class="saved-del" data-name="${l.name}" title="Delete">&times;</button>
            </div>
        `).join("");

        c.querySelectorAll(".saved-item").forEach((item) => {
            item.addEventListener("click", (e) => {
                if (e.target.classList.contains("saved-del")) return;
                const lat = parseFloat(item.dataset.lat), lon = parseFloat(item.dataset.lon);
                map.flyTo([lat, lon], 15, { duration: 1 });
                placeMarker(lat, lon);
            });
        });

        c.querySelectorAll(".saved-del").forEach((btn) => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                await fetch(`/api/saved/${encodeURIComponent(btn.dataset.name)}`, { method: "DELETE" });
                loadSaved();
                toast(`Deleted "${btn.dataset.name}"`);
            });
        });
    } catch (e) { /* silent */ }
}

async function saveLocation() {
    const lat = parseFloat($("lat-input").value), lon = parseFloat($("lon-input").value);
    if (isNaN(lat) || isNaN(lon)) return toast("Place a marker first", "error");
    const name = prompt("Name this location:");
    if (!name?.trim()) return;
    await fetch("/api/saved", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), lat, lon }),
    });
    loadSaved();
    toast(`Saved "${name.trim()}"`);
}

// ── Route / Movement ─────────────────────────────────────────
function addRoutePoint(lat, lng) {
    routePoints.push({ lat, lng });
    const m = L.circleMarker([lat, lng], {
        radius: 7, color: "#a78bfa", fillColor: "#a78bfa", fillOpacity: 1, weight: 0,
    }).addTo(map);
    m.bindTooltip(String(routePoints.length), {
        permanent: true, direction: "center", className: "route-label",
    });
    routeMarkers.push(m);

    if (routePoints.length >= 2) {
        if (routeLine) map.removeLayer(routeLine);
        routeLine = L.polyline(routePoints.map((p) => [p.lat, p.lng]), {
            color: "#a78bfa", weight: 2, dashArray: "8 6", opacity: 0.6,
        }).addTo(map);
    }
    updateRouteUI();
}

function clearRoutePoints() {
    routePoints = [];
    routeMarkers.forEach((m) => map.removeLayer(m));
    routeMarkers = [];
    if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
    if (routeDisplayLine) { map.removeLayer(routeDisplayLine); routeDisplayLine = null; }
    updateRouteUI();
    $("route-progress").classList.add("hidden");
}

function updateRouteUI() {
    $("btn-route-start").disabled = routePoints.length < 2;
    $("route-hint").textContent = routePoints.length > 0
        ? `${routePoints.length} point${routePoints.length > 1 ? "s" : ""} -- shift+click to add more`
        : "Shift+click map to add route points";
}

async function startRoute() {
    if (routePoints.length < 2) return;
    const speed = parseInt($("speed-input").value) || selectedSpeed;
    try {
        const r = await fetch("/api/route/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ waypoints: routePoints, speed }),
        });
        const d = await r.json();
        if (!r.ok) return toast(d.error || "Route failed", "error");

        if (d.coordinates) {
            if (routeLine) map.removeLayer(routeLine);
            routeDisplayLine = L.polyline(d.coordinates.map((c) => [c[1], c[0]]), {
                color: "#a78bfa", weight: 3, opacity: 0.8,
            }).addTo(map);
        }

        $("btn-route-start").disabled = true;
        $("btn-route-stop").disabled = false;
        $("route-progress").classList.remove("hidden");
        toast(`Route started: ${d.distance_km} km`);
        routePolling = setInterval(pollRoute, 1000);
    } catch (e) { toast("Route error", "error"); }
}

async function stopRoute() {
    await fetch("/api/route/stop", { method: "POST" });
    endRoute();
    toast("Route stopped");
}

async function pollRoute() {
    try {
        const r = await fetch("/api/route/status");
        if (!r.ok) { endRoute(); return; }
        const d = await r.json();
        $("progress-bar").style.width = d.progress_pct + "%";
        $("route-pct").textContent = Math.round(d.progress_pct) + "%";

        // Update marker to current position
        const lr = await fetch("/api/location/current");
        if (lr.ok) {
            const loc = await lr.json();
            placeMarker(loc.lat, loc.lon);
        }

        if (!d.active) { endRoute(); toast("Route completed"); }
    } catch (e) { /* silent */ }
}

function endRoute() {
    clearInterval(routePolling);
    routePolling = null;
    $("btn-route-start").disabled = false;
    $("btn-route-stop").disabled = true;
}
