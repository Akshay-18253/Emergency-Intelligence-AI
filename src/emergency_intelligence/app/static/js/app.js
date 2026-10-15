/**
 * Emergency Intelligence AI - Tactical Operations Center Coordinator
 * Connects UI panels, REST API, Leaflet GIS Map, and SSE Telemetry Stream.
 */

import { api } from './api.js';
import { sse } from './sse.js';
import { TacticalMap } from './map.js';
import { CadTerminal } from './cad.js';
import { TimelineController } from './timeline.js';

let tacticalMap = null;
let cadTerminal = null;
let timelineController = null;
let currentNetwork = null;
let currentRouteData = null;
let activeHazardsList = [];

// Format helper for timestamps in log
function getTimestamp() {
  const now = new Date();
  return now.toTimeString().split(' ')[0];
}

// Append log to terminal feed
function appendLog(message, cssClass = '') {
  const terminal = document.getElementById('terminal-feed');
  if (!terminal) return;

  const line = document.createElement('div');
  line.className = 'terminal-line';

  const timeSpan = document.createElement('span');
  timeSpan.className = 'terminal-time';
  timeSpan.textContent = `[${getTimestamp()}]`;

  const msgSpan = document.createElement('span');
  msgSpan.className = `terminal-msg ${cssClass}`;
  msgSpan.textContent = message;

  line.appendChild(timeSpan);
  line.appendChild(msgSpan);
  terminal.appendChild(line);

  // Auto-scroll to bottom
  terminal.scrollTop = terminal.scrollHeight;
}

// Update top telemetry bar metrics
async function refreshTelemetry() {
  try {
    const health = await api.getHealth();
    const upEl = document.getElementById('telemetry-uptime');
    if (upEl && health.uptime_seconds !== undefined) {
      const mins = Math.floor(health.uptime_seconds / 60);
      const secs = Math.floor(health.uptime_seconds % 60);
      upEl.textContent = `${mins}m ${secs}s`;
    }

    const nodesEl = document.getElementById('telemetry-nodes');
    if (nodesEl && health.graph_nodes !== undefined) {
      nodesEl.textContent = health.graph_nodes;
    }

    const edgesEl = document.getElementById('telemetry-edges');
    if (edgesEl && health.graph_edges !== undefined) {
      edgesEl.textContent = health.graph_edges;
    }

    const hazardsEl = document.getElementById('telemetry-hazards');
    if (hazardsEl && health.active_hazards !== undefined) {
      hazardsEl.textContent = health.active_hazards;
    }

    const severedEl = document.getElementById('telemetry-severed');
    if (severedEl && health.severed_edges !== undefined) {
      severedEl.textContent = health.severed_edges;
    }
  } catch (err) {
    console.warn('[App] Telemetry refresh failed:', err);
  }
}

// Load road network and populate origin/destination selects
async function loadNetwork() {
  try {
    const network = await api.getNetwork();
    currentNetwork = network;
    tacticalMap.renderNetwork(network);

    const originSelect = document.getElementById('select-origin');
    const destSelect = document.getElementById('select-destination');

    if (originSelect && destSelect && network.features) {
      const nodeSet = new Set();
      network.features.forEach((feat) => {
        if (feat.properties) {
          if (feat.properties.source) nodeSet.add(feat.properties.source);
          if (feat.properties.target) nodeSet.add(feat.properties.target);
        }
      });

      const sortedNodes = Array.from(nodeSet).sort();
      const currentOrigin = originSelect.value;
      const currentDest = destSelect.value;

      originSelect.innerHTML = '<option value="">-- Select Origin --</option>';
      destSelect.innerHTML = '<option value="">-- Select Destination --</option>';

      sortedNodes.forEach((nodeId) => {
        const optA = document.createElement('option');
        optA.value = nodeId;
        optA.textContent = `Intersection: ${nodeId}`;
        originSelect.appendChild(optA);

        const optB = document.createElement('option');
        optB.value = nodeId;
        optB.textContent = `Intersection: ${nodeId}`;
        destSelect.appendChild(optB);
      });

      // Restore values or defaults
      if (currentOrigin && sortedNodes.includes(currentOrigin)) {
        originSelect.value = currentOrigin;
      } else if (sortedNodes.length > 0) {
        originSelect.value = sortedNodes[0];
      }

      if (currentDest && sortedNodes.includes(currentDest)) {
        destSelect.value = currentDest;
      } else if (sortedNodes.length > 1) {
        destSelect.value = sortedNodes[sortedNodes.length - 1];
      }
    }
  } catch (err) {
    appendLog(`Network load error: ${err.message}`, 'event-hazard');
  }
}

// Load emergency facilities POIs
async function loadFacilities() {
  try {
    const facilities = await api.getFacilities();
    tacticalMap.renderFacilities(facilities);
  } catch (err) {
    console.warn('[App] Facilities load error:', err);
  }
}

// Calculate route handler
async function handleCalculateRoute() {
  const originSelect = document.getElementById('select-origin');
  const destSelect = document.getElementById('select-destination');
  const elevToggle = document.getElementById('toggle-elevation');
  const calculateBtn = document.getElementById('btn-calculate-route');

  const origin = originSelect ? originSelect.value : '';
  const destination = destSelect ? destSelect.value : '';

  if (!origin || !destination) {
    appendLog('Route aborted: Origin or Destination not selected.', 'event-hazard');
    return;
  }

  // Selected apparatus radio
  const selectedApparatusInput = document.querySelector('input[name="apparatus"]:checked');
  const apparatus_type = selectedApparatusInput ? selectedApparatusInput.value : 'AMBULANCE_ALS';
  const elevation_aware = elevToggle ? elevToggle.checked : false;

  try {
    if (calculateBtn) {
      calculateBtn.disabled = true;
      calculateBtn.innerHTML = 'Computing Route...';
    }

    const result = await api.calculateRoute({
      origin,
      destination,
      apparatus_type,
      elevation_aware,
    });

    if (!result.path_found) {
      appendLog(`NO ROUTE FOUND: All corridors severed between ${origin} and ${destination}!`, 'event-hazard');
      tacticalMap.clearRoute();
      currentRouteData = null;
      return;
    }

    currentRouteData = result;
    tacticalMap.renderRoute(result);

    // Update telemetry metrics
    const durEl = document.getElementById('metric-duration');
    if (durEl) {
      durEl.textContent = `${result.duration_seconds.toFixed(1)} s`;
    }

    const distEl = document.getElementById('metric-distance');
    if (distEl) {
      distEl.textContent = `${Math.round(result.distance_2d_meters)} m / ${Math.round(result.distance_3d_meters)} m`;
    }

    const elevEl = document.getElementById('metric-elevation');
    if (elevEl) {
      elevEl.textContent = `+${result.elevation_gain_meters.toFixed(1)} m`;
    }

    const gradeEl = document.getElementById('metric-grade');
    if (gradeEl) {
      gradeEl.textContent = `${result.max_grade_percent.toFixed(1)} %`;
    }

    // Populate turn maneuvers
    const maneuverList = document.getElementById('maneuver-list');
    if (maneuverList && Array.isArray(result.maneuvers)) {
      maneuverList.innerHTML = '';
      result.maneuvers.forEach((m) => {
        const item = document.createElement('div');
        item.className = 'maneuver-item';

        const textDiv = document.createElement('div');
        textDiv.textContent = m.instruction || `${m.type} onto ${m.street_name || m.target_edge}`;

        const badge = document.createElement('span');
        badge.className = `maneuver-badge ${(m.type || '').toLowerCase()}`;
        badge.textContent = m.type || 'STEP';

        item.appendChild(textDiv);
        item.appendChild(badge);
        maneuverList.appendChild(item);
      });
    }

    appendLog(
      `ROUTE COMPUTED: ${origin} &rarr; ${destination} (${result.duration_seconds.toFixed(1)}s, ${result.nodes.length} nodes)`,
      'event-intake'
    );
  } catch (err) {
    appendLog(`Route calculation error: ${err.message}`, 'event-hazard');
  } finally {
    if (calculateBtn) {
      calculateBtn.disabled = false;
      calculateBtn.innerHTML = 'Calculate Optimal Route &raquo;';
    }
  }
}

// Global quick selector helper for POI popups
window.__selectOriginDestination = function (nodeId, role) {
  const originSelect = document.getElementById('select-origin');
  const destSelect = document.getElementById('select-destination');

  if (role === 'origin' && originSelect) {
    originSelect.value = nodeId;
    appendLog(`Selected origin facility node: ${nodeId}`);
  } else if (role === 'destination' && destSelect) {
    destSelect.value = nodeId;
    appendLog(`Selected destination facility node: ${nodeId}`);
  }

  // If both selected, auto-calculate
  if (originSelect && destSelect && originSelect.value && destSelect.value && originSelect.value !== destSelect.value) {
    handleCalculateRoute();
  }
};

// Initialize Application
document.addEventListener('DOMContentLoaded', async () => {
  // 1. Initialize Leaflet Map Canvas
  tacticalMap = new TacticalMap('map').init();

  // Handle map node clicks
  tacticalMap.onNodeClick((nodeId) => {
    const originSelect = document.getElementById('select-origin');
    const destSelect = document.getElementById('select-destination');

    if (!originSelect.value) {
      originSelect.value = nodeId;
      appendLog(`Picked origin node from map: ${nodeId}`);
    } else if (!destSelect.value || destSelect.value === originSelect.value) {
      destSelect.value = nodeId;
      appendLog(`Picked destination node from map: ${nodeId}`);
      handleCalculateRoute();
    } else {
      originSelect.value = nodeId;
      appendLog(`Updated origin node from map: ${nodeId}`);
    }
  });

  // 2. Connect SSE Real-Time Telemetry Stream
  sse.onStatusChange((status) => {
    const pulseDot = document.getElementById('sse-status-dot');
    const statusText = document.getElementById('sse-status-text');

    if (status === 'connected') {
      if (pulseDot) pulseDot.className = 'pulse-dot';
      if (statusText) statusText.textContent = 'ONLINE';
    } else {
      if (pulseDot) pulseDot.className = 'pulse-dot disconnected';
      if (statusText) statusText.textContent = status.toUpperCase();
    }
  });

  sse.on('connected', (data) => {
    appendLog(`SSE Connected: Session ${data.client_id || 'active'}`, 'event-clear');
    refreshTelemetry();
  });

  sse.on('incident_intake', (data) => {
    appendLog(
      `INCIDENT INTAKE: ${data.intake_id || 'INC'} (${data.urgency || data.call_type || 'EMERGENCY'})`,
      'event-intake'
    );
  });

  sse.on('cad_dispatch', (data) => {
    appendLog(
      `CAD DISPATCH BROADCAST: ${data.intake_id || data.incident_id || 'INC'} (${data.urgency || 'DISPATCHED'})`,
      'event-intake'
    );
    if (tacticalMap) {
      tacticalMap.addIncidentBeacon(data);
    }
    if (cadTerminal) {
      cadTerminal.renderPolicyReport(data);
    }
    if (timelineController) {
      timelineController.syncStatus();
    }
  });

  sse.on('simulation_step', (data) => {
    if (timelineController) {
      timelineController.updateStateFromData(data);
    }
  });

  sse.on('simulation_reset', (data) => {
    appendLog(`SIMULATION RESET: Clock reset to T+00:00:00`, 'event-clear');
    if (timelineController) {
      timelineController.updateStateFromData(data);
    }
  });

  sse.on('hazard_injected', async (data) => {
    appendLog(
      `DISASTER HAZARD INJECTED: ${data.hazard_id || 'HZ'} (${data.edges_closed || 0} edges severed)`,
      'event-hazard'
    );
    await refreshTelemetry();
    await loadNetwork();

    // Reroute active trajectory if in-flight
    if (currentRouteData) {
      appendLog('Reactive in-flight rerouting triggered by dynamic mutation...', 'event-hazard');
      handleCalculateRoute();
    }
  });

  sse.on('hazard_cleared', async (data) => {
    appendLog(`HAZARD CLEARED: ${data.hazard_id || ''}`, 'event-clear');
    await refreshTelemetry();
    await loadNetwork();
    if (currentRouteData) handleCalculateRoute();
  });

  sse.on('hazards_reset', async (data) => {
    appendLog(`HAZARDS RESET: All ${data.cleared_count || 0} disaster polygons cleared.`, 'event-clear');
    activeHazardsList = [];
    tacticalMap.renderHazards([]);
    await refreshTelemetry();
    await loadNetwork();
    if (currentRouteData) handleCalculateRoute();
  });

  sse.connect();

  // 3. Initialize CAD Terminal & Timeline Controller
  cadTerminal = new CadTerminal({
    onIncidentDispatched: (data) => {
      tacticalMap.addIncidentBeacon(data);
      appendLog(
        `CAD DISPATCH: ${data.intake_id} (${data.urgency || data.triage?.clinical_priority}) - Apparatus Assigned`,
        'event-intake'
      );
      if (timelineController) {
        timelineController.syncStatus();
      }
    },
  });

  timelineController = new TimelineController({
    onSimulationUpdate: (data) => {
      if (data.vehicles && tacticalMap) {
        tacticalMap.renderVehicles(data.vehicles);
      }
      if (data.active_incidents && tacticalMap) {
        tacticalMap.renderIncidents(data.active_incidents);
      }
    },
  });

  // 4. Load Base District Topology & Facilities
  await refreshTelemetry();
  await loadNetwork();
  await loadFacilities();

  // 5. Attach UI Event Listeners
  const calculateBtn = document.getElementById('btn-calculate-route');
  if (calculateBtn) {
    calculateBtn.addEventListener('click', handleCalculateRoute);
  }

  // Preset Disaster Hazard Injections
  const btnFlood = document.getElementById('btn-flood');
  if (btnFlood) {
    btnFlood.addEventListener('click', async () => {
      try {
        appendLog('Injecting USGS Major River Flood inundation...', 'event-hazard');
        const floodCoords = [
          [-122.332, 47.595],
          [-122.327, 47.595],
          [-122.327, 47.615],
          [-122.332, 47.615],
        ];
        const res = await api.injectHazard({
          polygon_coords: floodCoords,
          hazard_type: 'RIVER_FLOOD',
          speed_multiplier: 0.0,
          severity: 1.0,
        });
        activeHazardsList.push({
          polygon_coords: floodCoords,
          hazard_type: 'RIVER_FLOOD',
          severity: 1.0,
        });
        tacticalMap.renderHazards(activeHazardsList);
      } catch (err) {
        appendLog(`Flood injection error: ${err.message}`, 'event-hazard');
      }
    });
  }

  const btnCollapse = document.getElementById('btn-collapse');
  if (btnCollapse) {
    btnCollapse.addEventListener('click', async () => {
      try {
        appendLog('Injecting Central Structural Arterial Collapse...', 'event-hazard');
        const collapseCoords = [
          [-122.335, 47.603],
          [-122.325, 47.603],
          [-122.325, 47.608],
          [-122.335, 47.608],
        ];
        const res = await api.injectHazard({
          polygon_coords: collapseCoords,
          hazard_type: 'STRUCTURAL_COLLAPSE',
          speed_multiplier: 0.0,
          severity: 1.0,
        });
        activeHazardsList.push({
          polygon_coords: collapseCoords,
          hazard_type: 'STRUCTURAL_COLLAPSE',
          severity: 1.0,
        });
        tacticalMap.renderHazards(activeHazardsList);
      } catch (err) {
        appendLog(`Collapse injection error: ${err.message}`, 'event-hazard');
      }
    });
  }

  const btnWildfire = document.getElementById('btn-wildfire');
  if (btnWildfire) {
    btnWildfire.addEventListener('click', async () => {
      try {
        appendLog('Injecting Wildfire Perimeter with thermal smoke buffer...', 'event-hazard');
        const fireCoords = [
          [-122.325, 47.608],
          [-122.316, 47.608],
          [-122.316, 47.618],
          [-122.325, 47.618],
        ];
        const res = await api.injectHazard({
          polygon_coords: fireCoords,
          hazard_type: 'WILDFIRE',
          speed_multiplier: 0.2,
          severity: 0.8,
        });
        activeHazardsList.push({
          polygon_coords: fireCoords,
          hazard_type: 'WILDFIRE',
          severity: 0.8,
        });
        tacticalMap.renderHazards(activeHazardsList);
      } catch (err) {
        appendLog(`Wildfire injection error: ${err.message}`, 'event-hazard');
      }
    });
  }

  const btnReset = document.getElementById('btn-reset-hazards');
  if (btnReset) {
    btnReset.addEventListener('click', async () => {
      try {
        appendLog('Clearing and resetting all active hazards...', 'event-clear');
        await api.resetHazards();
        activeHazardsList = [];
        tacticalMap.renderHazards([]);
      } catch (err) {
        appendLog(`Reset error: ${err.message}`, 'event-hazard');
      }
    });
  }

  // Auto-run first route after 500ms
  setTimeout(() => {
    handleCalculateRoute();
  }, 500);
});
