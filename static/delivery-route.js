/* ==========================================================
   DELIVERY ROUTE & LIVE TRACKING (NO GOOGLE)
   Uses: Leaflet + Leaflet Routing Machine + OSRM
========================================================== */


let map;
let routingControl;
let deliveryMarker;

/* ==========================================================
   INIT MAP
========================================================== */
function initDeliveryMap(customerLat, customerLng) {

    map = L.map("map").setView([customerLat, customerLng], 14);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap"
    }).addTo(map);

    // Customer marker
    L.marker([customerLat, customerLng])
        .addTo(map)
        .bindPopup("🏠 Customer Location")
        .openPopup();

    // Start tracking delivery boy
    trackDeliveryBoy(customerLat, customerLng);
}

/* ==========================================================
   TRACK DELIVERY BOY LOCATION
========================================================== */
function trackDeliveryBoy(customerLat, customerLng) {

    if (!navigator.geolocation) {
        alert("Geolocation not supported");
        return;
    }

    navigator.geolocation.watchPosition(
        position => {

            const dLat = position.coords.latitude;
            const dLng = position.coords.longitude;

            updateRoute(dLat, dLng, customerLat, customerLng);
        },
        error => {
            console.error("GPS error:", error);
        },
        {
            enableHighAccuracy: true,
            maximumAge: 3000,
            timeout: 10000
        }
    );
}

/* ==========================================================
   UPDATE ROUTE
========================================================== */
function updateRoute(dLat, dLng, cLat, cLng) {

    const deliveryLatLng = L.latLng(dLat, dLng);
    const customerLatLng = L.latLng(cLat, cLng);

    // Remove old route
    if (routingControl) {
        map.removeControl(routingControl);
    }

    routingControl = L.Routing.control({
        waypoints: [
            deliveryLatLng,
            customerLatLng
        ],
        routeWhileDragging: false,
        draggableWaypoints: false,
        addWaypoints: false,
        show: false,
        lineOptions: {
            styles: [{ color: "#1e88e5", weight: 5 }]
        },
        createMarker: function (i, wp) {
            if (i === 0) {
                if (!deliveryMarker) {
                    deliveryMarker = L.marker(wp.latLng)
                        .addTo(map)
                        .bindPopup("🛵 Delivery Boy");
                } else {
                    deliveryMarker.setLatLng(wp.latLng);
                }
                return deliveryMarker;
            }

            if (i === 1) {
                return L.marker(wp.latLng)
                    .bindPopup("🏠 Customer");
            }
        }
    }).addTo(map);

    routingControl.on("routesfound", e => {
        const route = e.routes[0];
        const distanceKm = (route.summary.totalDistance / 1000).toFixed(2);
        const timeMin = Math.round(route.summary.totalTime / 60);

        console.log(`🚚 Distance: ${distanceKm} km | ⏱ ETA: ${timeMin} min`);
    });
}

/* ==========================================================
   AUTO START (CALL THIS FROM HTML)
========================================================== */
// Example usage:
// initDeliveryMap(CUSTOMER_LAT, CUSTOMER_LNG);
