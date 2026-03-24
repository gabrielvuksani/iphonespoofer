// ── State ────────────────────────────────────────────────────
let map, marker, routeLine, routeDisplayLine;
let routePoints = [];
let routeMarkers = [];
let routePolling = null;
let searchTimeout = null;
let selectedSpeed = 15;
let darkTiles = true;
let teleportMode = false;
let recentLocations = JSON.parse(localStorage.getItem("recent") || "[]");

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

const POPULAR = [
    { name: "Times Square, NYC", lat: 40.7580, lon: -73.9855 },
    { name: "Eiffel Tower, Paris", lat: 48.8584, lon: 2.2945 },
    { name: "Tokyo Tower, Japan", lat: 35.6586, lon: 139.7454 },
    { name: "Big Ben, London", lat: 51.5007, lon: -0.1246 },
    { name: "Sydney Opera House", lat: -33.8568, lon: 151.2153 },
    { name: "Statue of Liberty, NYC", lat: 40.6892, lon: -74.0445 },
    { name: "Colosseum, Rome", lat: 41.8902, lon: 12.4922 },
    { name: "Dubai Mall, UAE", lat: 25.1972, lon: 55.2744 },
];

let tileLayer;

// ── Init ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    // Show onboarding if first visit
    if (!localStorage.getItem("ob_done")) {
        $("onboarding").classList.remove("hidden");
    } else {
        $("onboarding").classList.add("hidden");
    }

    // Load default location FIRST
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

    // Bind core events
    $("btn-set").addEventListener("click", setLocation);
    $("btn-clear").addEventListener("click", clearLocation);
    $("btn-save").addEventListener("click", saveLocation);
    $("btn-paste").addEventListener("click", pasteCoords);
    $("btn-route-start").addEventListener("click", startRoute);
    $("btn-route-stop").addEventListener("click", stopRoute);
    $("btn-route-clear").addEventListener("click", clearRoutePoints);
    $("sidebar-toggle").addEventListener("click", toggleSidebar);
    $("btn-layer").addEventListener("click", toggleTiles);
    $("btn-zoom-in").addEventListener("click", () => map.zoomIn());
    $("btn-zoom-out").addEventListener("click", () => map.zoomOut());
    $("btn-teleport").addEventListener("click", toggleTeleport);
    $("btn-clear-recent").addEventListener("click", clearRecent);
    $("btn-wifi").addEventListener("click", () => switchConnection(true));
    $("btn-usb").addEventListener("click", () => switchConnection(false));
    $("btn-connect").addEventListener("click", () => connectDevice(false));
    $("btn-connect-wifi").addEventListener("click", () => connectDevice(true));
    $("search-input").addEventListener("input", onSearchInput);
    $("search-input").addEventListener("focus", () => {
        if ($("search-results").children.length > 0)
            $("search-results").classList.add("visible");
    });

    // Speed buttons
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
    renderRecent();
    renderPopular();
    setInterval(pollDevice, 5000);
});

function $(id) { return document.getElementById(id); }

// ── Onboarding ───────────────────────────────────────────────
let obPage = 1;
function obNext(page) {
    document.getElementById(`ob-page-${obPage}`).classList.add("hidden");
    document.getElementById(`ob-page-${page}`).classList.remove("hidden");
    obPage = page;
    document.querySelectorAll(".ob-dot").forEach((d, i) =>
        d.classList.toggle("active", i + 1 === page)
    );
}
function obSkip() {
    localStorage.setItem("ob_done", "1");
    document.getElementById("onboarding").classList.add("hidden");
}
function obDone() {
    if (document.getElementById("ob-dismiss").checked) localStorage.setItem("ob_done", "1");
    document.getElementById("onboarding").classList.add("hidden");
}

// ── Toasts ───────────────────────────────────────────────────
function toast(msg, type = "success") {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    $("toasts").appendChild(el);
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, 3000);
}

// ── Teleport mode ────────────────────────────────────────────
function toggleTeleport() {
    teleportMode = !teleportMode;
    $("btn-teleport").classList.toggle("active", teleportMode);
    toast(teleportMode ? "Teleport ON — click map to move instantly" : "Teleport OFF", teleportMode ? "success" : "error");
}

// ── Map ──────────────────────────────────────────────────────
function onMapClick(e) {
    if (e.originalEvent.shiftKey || routePoints.length > 0) {
        addRoutePoint(e.latlng.lat, e.latlng.lng);
    } else if (teleportMode) {
        placeMarker(e.latlng.lat, e.latlng.lng);
        teleportTo(e.latlng.lat, e.latlng.lng);
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
        const pulse = L.circleMarker([lat, lng], {
            radius: 16, color: "#58a6ff", fillOpacity: 0,
            weight: 1.5, opacity: 0.3,
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

// ── Teleport (instant set) ───────────────────────────────────
async function teleportTo(lat, lon) {
    try {
        const r = await fetch("/api/location/set", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lat, lon }),
        });
        if (r.ok) {
            toast(`Teleported to ${lat.toFixed(4)}, ${lon.toFixed(4)}`);
            addToRecent(lat, lon);
        } else {
            const d = await r.json();
            toast(d.error || "Failed", "error");
        }
    } catch (e) { toast("Connection error", "error"); }
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
            addToRecent(lat, lon);
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

// ── Paste coordinates ────────────────────────────────────────
async function pasteCoords() {
    try {
        const text = await navigator.clipboard.readText();
        // Try common formats: "lat, lon" or "lat lon" or Google Maps URL
        let lat, lon;
        const urlMatch = text.match(/@(-?\d+\.?\d*),(-?\d+\.?\d*)/);
        const coordMatch = text.match(/(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)/);
        if (urlMatch) {
            lat = parseFloat(urlMatch[1]); lon = parseFloat(urlMatch[2]);
        } else if (coordMatch) {
            lat = parseFloat(coordMatch[1]); lon = parseFloat(coordMatch[2]);
        }
        if (lat && lon && !isNaN(lat) && !isNaN(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
            $("lat-input").value = lat.toFixed(6);
            $("lon-input").value = lon.toFixed(6);
            map.flyTo([lat, lon], 15, { duration: 1 });
            placeMarker(lat, lon);
            toast(`Pasted: ${lat.toFixed(4)}, ${lon.toFixed(4)}`);
        } else {
            toast("No valid coordinates in clipboard", "error");
        }
    } catch (e) { toast("Clipboard access denied", "error"); }
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
                if (teleportMode) teleportTo(lat, lon);
            });
        });
    } catch (e) { /* silent */ }
}

// ── Device polling ───────────────────────────────────────────
let wasConnected = false;
async function pollDevice() {
    try {
        const r = await fetch("/api/device");
        const d = await r.json();
        const dot = $("device-dot");
        if (d.connected) {
            dot.classList.add("connected");
            const connType = d.connection_type || "USB";
            $("device-label").textContent = d.name || "iPhone";
            $("dev-name").textContent = d.name || "iPhone";
            $("dev-ios").textContent = d.ios_version || "--";
            $("dev-model").textContent = d.model || "--";
            $("dev-udid").textContent = d.udid || "--";
            const connBadge = $("dev-conn");
            connBadge.textContent = connType;
            connBadge.className = "conn-badge " + connType.toLowerCase();
            $("device-body").classList.remove("hidden");
            $("setup-guide").classList.add("hidden");
            // Show relevant switch button
            $("btn-wifi").classList.toggle("hidden", connType === "WiFi");
            $("btn-usb").classList.toggle("hidden", connType === "USB");
            if (!wasConnected) { wasConnected = true; toast(`iPhone connected (${connType})`); }
        } else {
            dot.classList.remove("connected");
            $("device-label").textContent = "No device";
            $("device-body").classList.add("hidden");
            $("setup-guide").classList.remove("hidden");
            wasConnected = false;
        }
    } catch (e) { /* server down */ }
}

// ── Connection switching ─────────────────────────────────────
async function switchConnection(wifi) {
    toast(wifi ? "Switching to WiFi..." : "Switching to USB...", "success");
    try {
        const r = await fetch("/api/device/switch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ wifi }),
        });
        const d = await r.json();
        if (r.ok) {
            toast(`Connected via ${d.connection_type}${wifi ? " — you can unplug the cable now" : ""}`);
            pollDevice();
        } else {
            toast(d.error || "Switch failed", "error");
        }
    } catch (e) { toast("Switch failed: " + e.message, "error"); }
}

// ── Device connect (from setup guide) ────────────────────────
async function connectDevice(wifi = false) {
    const status = $("connect-status");
    const btnUsb = $("btn-connect");
    const btnWifi = $("btn-connect-wifi");
    if (btnUsb) btnUsb.disabled = true;
    if (btnWifi) btnWifi.disabled = true;
    if (status) status.textContent = wifi ? "Connecting via WiFi..." : "Connecting via USB...";

    try {
        const r = await fetch("/api/device/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ wifi }),
        });
        const d = await r.json();
        if (r.ok) {
            toast(`Connected via ${d.connection_type}`);
            if (status) status.textContent = "";
            pollDevice();
        } else {
            toast(d.error || "Connection failed", "error");
            if (status) status.textContent = d.error || "Connection failed — check device and retry";
        }
    } catch (e) {
        toast("Connection error", "error");
        if (status) status.textContent = "Connection error — is the app running?";
    } finally {
        if (btnUsb) btnUsb.disabled = false;
        if (btnWifi) btnWifi.disabled = false;
    }
}

// ── Recent locations ─────────────────────────────────────────
function addToRecent(lat, lon) {
    const entry = { lat: +lat.toFixed(6), lon: +lon.toFixed(6), ts: Date.now() };
    // Remove if already exists nearby
    recentLocations = recentLocations.filter(r =>
        Math.abs(r.lat - entry.lat) > 0.0005 || Math.abs(r.lon - entry.lon) > 0.0005
    );
    recentLocations.unshift(entry);
    recentLocations = recentLocations.slice(0, 15);
    localStorage.setItem("recent", JSON.stringify(recentLocations));
    renderRecent();
}

function clearRecent() {
    recentLocations = [];
    localStorage.setItem("recent", "[]");
    renderRecent();
    toast("History cleared");
}

function renderRecent() {
    const c = $("recent-list");
    if (!recentLocations.length) { c.innerHTML = '<div class="empty-state">No recent locations</div>'; return; }
    c.innerHTML = recentLocations.map((r) => {
        const ago = timeAgo(r.ts);
        return `<div class="saved-item" data-lat="${r.lat}" data-lon="${r.lon}">
            <span class="saved-name">${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}</span>
            <span class="saved-coords">${ago}</span>
        </div>`;
    }).join("");
    c.querySelectorAll(".saved-item").forEach((item) => {
        item.addEventListener("click", () => {
            const lat = parseFloat(item.dataset.lat), lon = parseFloat(item.dataset.lon);
            map.flyTo([lat, lon], 15, { duration: 1 });
            placeMarker(lat, lon);
            if (teleportMode) teleportTo(lat, lon);
        });
    });
}

function timeAgo(ts) {
    const s = Math.floor((Date.now() - ts) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
}

// ── Popular spots ────────────────────────────────────────────
function renderPopular() {
    const c = $("popular-list");
    c.innerHTML = POPULAR.map((p) => `
        <div class="saved-item" data-lat="${p.lat}" data-lon="${p.lon}">
            <span class="saved-name">${p.name}</span>
        </div>
    `).join("");
    c.querySelectorAll(".saved-item").forEach((item) => {
        item.addEventListener("click", () => {
            const lat = parseFloat(item.dataset.lat), lon = parseFloat(item.dataset.lon);
            map.flyTo([lat, lon], 15, { duration: 1.2 });
            placeMarker(lat, lon);
            if (teleportMode) teleportTo(lat, lon);
        });
    });
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
                if (teleportMode) teleportTo(lat, lon);
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
        ? `${routePoints.length} point${routePoints.length > 1 ? "s" : ""} — shift+click to add more`
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
