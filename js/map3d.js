/* ============ 3D pohled — MapLibre GL: terén + ortofoto ============
   Lazy modul: MapLibre (vendor/maplibre) se načte až při prvním zapnutí 3D.
   Terén: lokální DMR 5G dlaždice (terrain/, pokud jsou vygenerované CI bake),
   jinak AWS Terrain Tiles (Terrarium, Mapzen/USGS/EU-DEM). */
const Map3D = (() => {
  let map = null;          // maplibregl.Map
  let ready = false;
  let loading = null;      // Promise načítání skriptu
  let boatMarker = null;
  let poiMarkers = [];
  let localTerrain = null; // meta.json lokálních dlaždic, nebo false

  const AWS_DEM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
  const ORTO = "https://ags.cuzk.gov.cz/arcgis1/rest/services/ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}";

  function loadScript() {
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "vendor/maplibre/maplibre-gl.css";
      document.head.appendChild(css);
      const s = document.createElement("script");
      s.src = "vendor/maplibre/maplibre-gl.js";
      s.onload = resolve;
      s.onerror = () => reject(new Error("maplibre load failed"));
      document.head.appendChild(s);
    });
    return loading;
  }

  async function detectLocalTerrain() {
    if (localTerrain !== null) return localTerrain;
    try {
      const r = await fetch("terrain/meta.json", { cache: "no-cache" });
      localTerrain = r.ok ? await r.json() : false;
    } catch (e) { localTerrain = false; }
    return localTerrain;
  }

  /* převod existujících dat na GeoJSON */
  function axisGeoJSON() {
    return { type: "Feature", geometry: { type: "LineString",
      coordinates: RIVER_AXIS.map(p => [p[1], p[0]]) } };
  }
  function zonesGeoJSON() {
    return { type: "FeatureCollection", features: ZONES.filter(z => z.poly).map(z => ({
      type: "Feature",
      properties: { kind: z.kind, name: z.name },
      geometry: { type: "Polygon", coordinates: [z.poly.map(p => [p[1], p[0]])] },
    })) };
  }
  function isobathsGeoJSON() {
    return (typeof ISOBATHS !== "undefined") ? ISOBATHS : null;
  }

  const ZONE_COLORS = { danger: "#ff5a6a", ski: "#ffb63d", swim: "#38dc94", info: "#24c6dc" };

  async function build(container, view) {
    await loadScript();
    const meta = await detectLocalTerrain();
    const demSource = meta ? {
      type: "raster-dem",
      tiles: [location.pathname.replace(/[^/]*$/, "") + "terrain/{z}/{x}/{y}.png"],
      encoding: "terrarium",
      tileSize: 256,
      minzoom: meta.minzoom, maxzoom: meta.maxzoom,
      bounds: meta.bounds,
      attribution: "výškopis © ČÚZK DMR 5G (CC BY 4.0)",
    } : {
      type: "raster-dem",
      tiles: [AWS_DEM],
      encoding: "terrarium",
      tileSize: 256,
      maxzoom: 14,
      attribution: "terén: Mapzen/AWS Terrain Tiles",
    };

    map = new maplibregl.Map({
      container,
      center: [view.lng, view.lat],
      zoom: Math.min(view.zoom, 16),
      pitch: 62,
      bearing: view.bearing || 0,
      maxBounds: [[13.85, 49.45], [14.80, 50.00]],
      maxPitch: 75,
      attributionControl: { compact: true },
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        sources: {
          orto: { type: "raster", tiles: [ORTO], tileSize: 256, maxzoom: 19,
                  attribution: "© ČÚZK ortofoto" },
          dem: demSource,
          axis: { type: "geojson", data: axisGeoJSON() },
          zones: { type: "geojson", data: zonesGeoJSON() },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0a1a28" } },
          { id: "orto", type: "raster", source: "orto",
            paint: { "raster-saturation": 0.05, "raster-contrast": 0.04 } },
          { id: "zones-fill", type: "fill", source: "zones",
            paint: { "fill-color": ["match", ["get", "kind"],
              "danger", ZONE_COLORS.danger, "ski", ZONE_COLORS.ski,
              "swim", ZONE_COLORS.swim, ZONE_COLORS.info],
              "fill-opacity": 0.18 } },
          { id: "zones-line", type: "line", source: "zones",
            paint: { "line-color": ["match", ["get", "kind"],
              "danger", ZONE_COLORS.danger, "ski", ZONE_COLORS.ski,
              "swim", ZONE_COLORS.swim, ZONE_COLORS.info],
              "line-width": 1.6, "line-dasharray": [3, 2] } },
          { id: "axis", type: "line", source: "axis",
            paint: { "line-color": "#24c6dc", "line-width": 1.4,
                     "line-opacity": 0.55, "line-dasharray": [4, 5] } },
        ],
        sky: {
          "sky-color": "#0e2a44",
          "horizon-color": "#3d6a8a",
          "fog-color": "#0a1a28",
          "sky-horizon-blend": 0.6,
          "horizon-fog-blend": 0.7,
        },
      },
    });

    /* setTerrain a vrstvy až po načtení stylu (jinak „Style is not done loading") */
    await new Promise(resolve => {
      if (map.isStyleLoaded()) resolve();
      else map.once("style.load", resolve);
    });

    map.setTerrain({ source: "dem", exaggeration: 1.35 });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

    /* izobaty (pokud jsou vygenerované) */
    const iso = isobathsGeoJSON();
    if (iso) {
      map.addSource("isobaths", { type: "geojson", data: iso });
      map.addLayer({ id: "isobaths", type: "line", source: "isobaths",
        paint: { "line-color": "#7fd4ff",
                 "line-width": ["interpolate", ["linear"], ["get", "depth"], 5, 0.8, 50, 2.2],
                 "line-opacity": 0.75 } });
      map.addLayer({ id: "isobath-labels", type: "symbol", source: "isobaths",
        layout: { "symbol-placement": "line", "text-field": ["concat", ["get", "depth"], " m"],
                  "text-size": 10, "text-font": ["Noto Sans Regular"] },
        paint: { "text-color": "#bfe6ff", "text-halo-color": "#06263c", "text-halo-width": 1.4 } });
    }

    /* POI markery (HTML, stejný vzhled jako v 2D) */
    POIS.forEach(p => {
      const el = document.createElement("div");
      el.className = "poi-pin";
      el.innerHTML = `<div>${({marina:"⚓",fuel:"⛽",food:"🍽",camp:"🏕",ferry:"⛴",rescue:"🚑",dam:"🧱",rental:"🛥",beach:"🏖",sight:"🏰"})[p.type] || "📍"}</div>`;
      el.style.cursor = "pointer";
      const mk = new maplibregl.Marker({ element: el })
        .setLngLat([p.lon, p.lat])
        .setPopup(new maplibregl.Popup({ offset: 14 })
          .setHTML(`<b>${p.name}</b><br><span class="muted">${p.desc || ""}${p.km ? ` · ř. km ${p.km}` : ""}</span>`))
        .addTo(map);
      poiMarkers.push(mk);
    });

    ready = true;
    return map;
  }

  return {
    get active() { return ready && map && map.getContainer().style.display !== "none"; },

    /* zapnout 3D: container = DOM element, view = {lat,lng,zoom,bearing} */
    async show(container, view) {
      container.style.display = "block";
      if (!ready) {
        await build(container, view);
      } else {
        map.jumpTo({ center: [view.lng, view.lat], zoom: Math.min(view.zoom, 16) });
        map.resize();
      }
      return map;
    },
    hide(container) {
      if (container) container.style.display = "none";
    },
    /* aktuální pohled pro synchronizaci zpět do 2D */
    view() {
      if (!map) return null;
      const c = map.getCenter();
      return { lat: c.lat, lng: c.lng, zoom: map.getZoom() };
    },
    /* GPS fix z app.js */
    updateBoat(lat, lon, course) {
      if (!ready || !map) return;
      if (!boatMarker) {
        const el = document.createElement("div");
        el.className = "boat-marker3d";
        el.innerHTML = `<svg width="42" height="42" viewBox="-21 -21 42 42">
          <circle r="19" fill="rgba(36,198,220,.16)"/>
          <path d="M0,-13 L7,9 L0,4.5 L-7,9 Z" fill="#24c6dc" stroke="#eef6fb" stroke-width="1.5"/>
        </svg>`;
        boatMarker = new maplibregl.Marker({ element: el, rotationAlignment: "map" })
          .setLngLat([lon, lat]).addTo(map);
      } else {
        boatMarker.setLngLat([lon, lat]);
      }
      boatMarker.setRotation(course || 0);
    },
    follow(lat, lon) {
      if (ready && map) map.easeTo({ center: [lon, lat], duration: 500 });
    },
  };
})();
