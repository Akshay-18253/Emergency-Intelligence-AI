/**
 * Emergency Intelligence AI - REST API Gateway Client
 * Zero-dependency pure ES6 fetch client for all backend endpoints.
 */

export class ApiClient {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Internal helper for JSON requests
   */
  async _request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const defaultHeaders = {
      'Accept': 'application/json',
    };

    if (options.body && typeof options.body === 'object') {
      options.body = JSON.stringify(options.body);
      defaultHeaders['Content-Type'] = 'application/json';
    }

    const config = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...(options.headers || {}),
      },
    };

    try {
      const response = await fetch(url, config);
      if (!response.ok) {
        let errorDetails = `HTTP ${response.status} ${response.statusText}`;
        try {
          const errJson = await response.json();
          if (errJson.error) {
            errorDetails = `${errJson.error}: ${errJson.details || ''}`;
          }
        } catch {
          // Response body was not JSON
        }
        throw new Error(errorDetails);
      }
      const json = await response.json();
      if (json && typeof json === 'object' && json.data !== undefined) {
        return json.data;
      }
      return json;
    } catch (err) {
      console.error(`[ApiClient] Request to ${endpoint} failed:`, err);
      throw err;
    }
  }

  /**
   * Health & telemetry status
   * GET /api/health
   */
  async getHealth() {
    return this._request('/api/health');
  }

  /**
   * Road network topology GeoJSON
   * GET /api/network
   */
  async getNetwork() {
    return this._request('/api/network');
  }

  /**
   * Emergency Facilities POIs
   * GET /api/facilities
   */
  async getFacilities() {
    return this._request('/api/facilities');
  }

  /**
   * Calculate emergency apparatus route
   * POST /api/route
   * @param {Object} params
   * @param {string} params.origin - Origin node ID
   * @param {string} params.destination - Destination node ID
   * @param {string} [params.apparatus_type='AMBULANCE_ALS']
   * @param {boolean} [params.elevation_aware=false]
   */
  async calculateRoute({ origin, destination, apparatus_type = 'AMBULANCE_ALS', elevation_aware = false }) {
    return this._request('/api/route', {
      method: 'POST',
      body: {
        origin,
        destination,
        apparatus_type,
        elevation_aware,
      },
    });
  }

  /**
   * Inject dynamic hazard polygon
   * POST /api/hazards
   * @param {Object} params
   * @param {Array<[number, number]>} params.polygon_coords - Array of [lon, lat] pairs
   * @param {string} [params.hazard_type='FLOOD']
   * @param {number} [params.speed_multiplier=0.0]
   * @param {number} [params.severity=1.0]
   */
  async injectHazard({ polygon_coords, hazard_type = 'FLOOD', speed_multiplier = 0.0, severity = 1.0 }) {
    return this._request('/api/hazards', {
      method: 'POST',
      body: {
        polygon_coords,
        hazard_type,
        speed_multiplier,
        severity,
      },
    });
  }

  /**
   * Reset all active hazards
   * POST /api/hazards/reset
   */
  async resetHazards() {
    return this._request('/api/hazards/reset', {
      method: 'POST',
      body: {},
    });
  }
}

// Global default export instance
export const api = new ApiClient();
