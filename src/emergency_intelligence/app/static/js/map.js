/**
 * Emergency Intelligence AI - Interactive GIS Map Canvas (Leaflet)
 * Orchestrates tactical road networks, emergency facilities, dynamic hazards,
 * and calculated vehicle trajectories.
 */

export class TacticalMap {
  constructor(containerId = 'map') {
    this.containerId = containerId;
    this.map = null;
    this.networkLayer = null;
    this.facilityLayer = null;
    this.hazardLayer = null;
    this.routeLayer = null;
    this.nodeClickCallbacks = new Set();
    this.selectedOrigin = null;
    this.selectedDestination = null;
  }

  /**
   * Initialize Leaflet map and tile basemap
   */
  init() {
    if (this.map) return this;

    // Center on default Pacific Northwest / Seattle metropolitan grid
    this.map = L.map(this.containerId, {
      center: [47.6062, -122.3321],
      zoom: 13,
      zoomControl: true,
      preferCanvas: true,
    });

    // CartoDB Dark Matter Base Tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(this.map);

    // Layer groups for tactical features
    this.networkLayer = L.featureGroup().addTo(this.map);
    this.hazardLayer = L.featureGroup().addTo(this.map);
    this.routeLayer = L.featureGroup().addTo(this.map);
    this.facilityLayer = L.featureGroup().addTo(this.map);

    return this;
  }

  /**
   * Subscribe to node click events
   */
  onNodeClick(callback) {
    this.nodeClickCallbacks.add(callback);
    return () => this.nodeClickCallbacks.delete(callback);
  }

  _notifyNodeClick(nodeId, coordinates) {
    for (const cb of this.nodeClickCallbacks) {
      try {
        cb(nodeId, coordinates);
      } catch (err) {
        console.error('[TacticalMap] Node click callback error:', err);
      }
    }
  }

  /**
   * Render road network topology GeoJSON
   * @param {Object} geoJson - GeoJSON FeatureCollection of edges
   */
  renderNetwork(geoJson) {
    this.networkLayer.clearLayers();

    if (!geoJson || !geoJson.features) return;

    const layer = L.geoJSON(geoJson, {
      style: (feature) => {
        const props = feature.properties || {};
        if (props.is_severed) {
          return {
            color: '#ef4444',
            weight: 4,
            opacity: 0.9,
            dashArray: '6, 6',
          };
        }
        if (props.is_bridge) {
          return {
            color: '#38bdf8',
            weight: 3.5,
            opacity: 0.85,
          };
        }
        return {
          color: '#475569',
          weight: 2.5,
          opacity: 0.7,
        };
      },
      onEachFeature: (feature, layer) => {
        const props = feature.properties || {};
        const statusLabel = props.is_severed ? '<span style="color:#ef4444; font-weight:700;">[SEVERED / BLOCKED]</span>' : '<span style="color:#10b981;">[OPEN]</span>';
        const bridgeLabel = props.is_bridge ? ' | <strong>Bridge Link</strong>' : '';
        
        layer.bindTooltip(`
          <div style="font-family: -apple-system, sans-serif; font-size: 0.75rem;">
            <div><strong>${props.source} &rarr; ${props.target}</strong></div>
            <div>${statusLabel}${bridgeLabel}</div>
            <div>Length: ${Math.round(props.length_m || 0)} m | Max: ${props.maxspeed_kmh || 50} km/h</div>
          </div>
        `, { sticky: true, opacity: 0.95 });

        // Node click triggers
        layer.on('click', (e) => {
          // Trigger nearest vertex click
          const coords = feature.geometry.coordinates;
          if (coords && coords.length >= 2) {
            this._notifyNodeClick(props.source, coords[0]);
          }
        });
      },
    });

    this.networkLayer.addLayer(layer);

    // If initial load and network has bbox, fit bounds
    if (geoJson.bbox && geoJson.bbox.length === 4) {
      const [minX, minY, maxX, maxY] = geoJson.bbox;
      this.map.fitBounds([
        [minY, minX],
        [maxY, maxX],
      ], { padding: [24, 24] });
    }
  }

  /**
   * Render emergency facility POIs
   * @param {Array<Object>} facilities - Array of POI objects
   */
  renderFacilities(facilities) {
    this.facilityLayer.clearLayers();
    if (!Array.isArray(facilities)) return;

    facilities.forEach((facility) => {
      const [lon, lat] = facility.coordinates || [0, 0];
      const isHospital = facility.poi_type === 'HOSPITAL';
      
      const iconHtml = isHospital
        ? `<div class="poi-marker poi-hospital" style="width:28px;height:28px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 10.5h-5.5V5c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v5.5H5c-.83 0-1.5.67-1.5 1.5s.67 1.5 1.5 1.5h5.5V19c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5v-5.5H19c.83 0 1.5-.67 1.5-1.5s-.67-1.5-1.5-1.5z"/></svg></div>`
        : `<div class="poi-marker poi-fire" style="width:28px;height:28px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M13.5.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.61 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67zM11.71 19c-1.78 0-3.22-1.4-3.22-3.14 0-1.62 1.05-2.76 2.81-3.12 1.77-.36 3.6-1.21 4.62-2.58.39 1.29.59 2.65.59 4.04 0 2.65-2.15 4.8-4.8 4.8z"/></svg></div>`;

      const customIcon = L.divIcon({
        className: 'custom-poi-wrapper',
        html: iconHtml,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
      });

      const marker = L.marker([lat, lon], { icon: customIcon });

      // Build popup content
      let badgesHtml = '';
      if (isHospital) {
        if (facility.trauma_level) {
          badgesHtml += `<span class="popup-badge hospital">Trauma Level ${facility.trauma_level}</span>`;
        }
        if (facility.has_helipad) {
          badgesHtml += `<span class="popup-badge helipad">Helipad</span>`;
        }
        if (facility.capabilities) {
          facility.capabilities.forEach((cap) => {
            badgesHtml += `<span class="popup-badge">${cap}</span>`;
          });
        }
      } else {
        if (facility.apparatus_bays) {
          badgesHtml += `<span class="popup-badge fire">${facility.apparatus_bays} Apparatus Bays</span>`;
        }
      }

      const popupHtml = `
        <div style="min-width: 200px;">
          <div class="popup-title">
            <span>${facility.name || facility.id}</span>
          </div>
          <div class="popup-subtitle">Node: <code>${facility.id}</code></div>
          <div class="popup-badges">${badgesHtml}</div>
          <button class="popup-action-btn" onclick="window.__selectOriginDestination('${facility.id}', 'origin')">&bull; Set as Origin</button>
          <button class="popup-action-btn" onclick="window.__selectOriginDestination('${facility.id}', 'destination')">&bull; Set as Destination</button>
        </div>
      `;

      marker.bindPopup(popupHtml);
      this.facilityLayer.addLayer(marker);
    });
  }

  /**
   * Render dynamic hazard polygons
   * @param {Array<Object>} hazards - Array of hazard objects
   */
  renderHazards(hazards) {
    this.hazardLayer.clearLayers();
    if (!Array.isArray(hazards)) return;

    hazards.forEach((hazard) => {
      if (!hazard.polygon_coords || hazard.polygon_coords.length < 3) return;

      // Leaflet expects [lat, lon]
      const latLngs = hazard.polygon_coords.map(([lon, lat]) => [lat, lon]);

      const isFire = (hazard.hazard_type || '').includes('FIRE');
      const strokeColor = isFire ? '#f97316' : '#ef4444';
      const fillColor = isFire ? '#ea580c' : '#dc2626';

      const polygon = L.polygon(latLngs, {
        color: strokeColor,
        weight: 2,
        fillColor: fillColor,
        fillOpacity: 0.35,
        className: 'hazard-pulse-polygon',
      });

      polygon.bindTooltip(`
        <div style="font-size: 0.75rem;">
          <strong style="color: ${strokeColor};">${hazard.hazard_type || 'HAZARD'}</strong>
          <div>Severity: ${hazard.severity || 1.0} | Speed Multiplier: ${hazard.speed_multiplier || 0.0}</div>
        </div>
      `, { sticky: true });

      this.hazardLayer.addLayer(polygon);
    });
  }

  /**
   * Render calculated emergency vehicle route
   * @param {Object} routeData - Route response containing geojson, maneuvers, etc.
   */
  renderRoute(routeData) {
    this.routeLayer.clearLayers();
    if (!routeData || !routeData.geojson) return;

    // Extract the primary LineString trajectory from FeatureCollection or Feature
    let lineFeature = null;
    if (routeData.geojson.type === 'FeatureCollection' && Array.isArray(routeData.geojson.features)) {
      lineFeature = routeData.geojson.features.find((f) => f.geometry && f.geometry.type === 'LineString');
    } else if (routeData.geojson.type === 'Feature' && routeData.geojson.geometry?.type === 'LineString') {
      lineFeature = routeData.geojson;
    } else if (routeData.geojson.type === 'LineString') {
      lineFeature = { type: 'Feature', geometry: routeData.geojson, properties: {} };
    }

    if (!lineFeature) return;

    // Outer glow track
    const glowTrack = L.geoJSON(lineFeature, {
      style: {
        color: '#0284c7',
        weight: 8,
        opacity: 0.45,
        lineCap: 'round',
        lineJoin: 'round',
      },
    });

    // Inner bright cyan siren line
    const sirenLine = L.geoJSON(lineFeature, {
      style: {
        color: '#38bdf8',
        weight: 4,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
        className: 'animated-route-line',
      },
    });

    this.routeLayer.addLayer(glowTrack);
    this.routeLayer.addLayer(sirenLine);

    // Add origin and destination pins
    const coords = lineFeature.geometry?.coordinates || lineFeature.coordinates;
    if (coords && coords.length >= 2) {
      const startCoord = coords[0];
      const endCoord = coords[coords.length - 1];

      const startMarker = L.marker([startCoord[1], startCoord[0]], {
        icon: L.divIcon({
          className: 'origin-marker',
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
      }).bindTooltip(`<strong>ORIGIN</strong>: ${routeData.origin_node}`, { permanent: false });

      const endMarker = L.marker([endCoord[1], endCoord[0]], {
        icon: L.divIcon({
          className: 'destination-marker',
          iconSize: [14, 14],
          iconAnchor: [7, 7],
        }),
      }).bindTooltip(`<strong>DESTINATION</strong>: ${routeData.destination_node}`, { permanent: false });

      this.routeLayer.addLayer(startMarker);
      this.routeLayer.addLayer(endMarker);
    }

    // Add turn maneuvers pins
    if (Array.isArray(routeData.maneuvers)) {
      routeData.maneuvers.forEach((m, idx) => {
        if (!m.type || m.type === 'START' || m.type === 'ARRIVE') return;
        if (!m.node) return;
        
        // Find coordinate for maneuver node if available
        // Simple maneuver icon
        const iconHtml = `<div class="turn-marker" style="width:20px;height:20px;">#${idx}</div>`;
        // Coordinates can be extracted from route if matched
      });
    }

    // Fit map bounds to show complete route
    try {
      this.map.fitBounds(sirenLine.getBounds(), { padding: [40, 40] });
    } catch {
      // Bounds error fallback
    }
  }

  /**
   * Clear active route layer
   */
  clearRoute() {
    this.routeLayer.clearLayers();
  }
}
