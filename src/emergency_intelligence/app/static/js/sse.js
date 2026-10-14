/**
 * Emergency Intelligence AI - Server-Sent Events (SSE) Client
 * Manages resilient real-time telemetry stream from /api/simulation/stream.
 */

export class SSEClient {
  constructor(url = '/api/simulation/stream') {
    this.url = url;
    this.eventSource = null;
    this.listeners = new Map();
    this.statusListeners = new Set();
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.reconnectTimer = null;
    this.shouldReconnect = true;
  }

  /**
   * Subscribe to specific event type ('connected', 'incident_intake', 'hazard_injected', etc.)
   */
  on(eventType, callback) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType).add(callback);
    return () => this.off(eventType, callback);
  }

  /**
   * Unsubscribe from event type
   */
  off(eventType, callback) {
    if (this.listeners.has(eventType)) {
      this.listeners.get(eventType).delete(callback);
    }
  }

  /**
   * Subscribe to connection status changes ('connected', 'disconnected', 'reconnecting')
   */
  onStatusChange(callback) {
    this.statusListeners.add(callback);
    return () => this.statusListeners.delete(callback);
  }

  _notifyStatus(status) {
    for (const callback of this.statusListeners) {
      try {
        callback(status);
      } catch (err) {
        console.error('[SSEClient] Status listener error:', err);
      }
    }
  }

  _dispatch(eventType, data) {
    if (this.listeners.has(eventType)) {
      for (const callback of this.listeners.get(eventType)) {
        try {
          callback(data);
        } catch (err) {
          console.error(`[SSEClient] Error in listener for "${eventType}":`, err);
        }
      }
    }
  }

  /**
   * Connect to SSE endpoint
   */
  connect() {
    if (this.eventSource) {
      this.disconnect();
    }

    this.shouldReconnect = true;
    try {
      this.eventSource = new EventSource(this.url);

      this.eventSource.onopen = () => {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this._notifyStatus('connected');
      };

      this.eventSource.onerror = (err) => {
        this.isConnected = false;
        this._notifyStatus('disconnected');
        this.eventSource.close();
        this.eventSource = null;

        if (this.shouldReconnect) {
          const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
          this.reconnectAttempts++;
          this._notifyStatus('reconnecting');
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = setTimeout(() => {
            this.connect();
          }, delay);
        }
      };

      // Listen for registered event types
      const knownEvents = [
        'connected',
        'incident_intake',
        'hazard_injected',
        'hazard_cleared',
        'hazards_reset',
      ];

      for (const eventName of knownEvents) {
        this.eventSource.addEventListener(eventName, (e) => {
          let parsedData = e.data;
          try {
            parsedData = JSON.parse(e.data);
          } catch {
            // Keep as string if not JSON
          }
          this._dispatch(eventName, parsedData);
        });
      }

      // Also listen for generic messages
      this.eventSource.onmessage = (e) => {
        let parsedData = e.data;
        try {
          parsedData = JSON.parse(e.data);
        } catch {
          // Keep as string
        }
        this._dispatch('message', parsedData);
      };

    } catch (err) {
      console.error('[SSEClient] Connection initiation failed:', err);
      this._notifyStatus('disconnected');
    }
  }

  /**
   * Gracefully close connection
   */
  disconnect() {
    this.shouldReconnect = false;
    clearTimeout(this.reconnectTimer);
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.isConnected = false;
    this._notifyStatus('disconnected');
  }
}

// Global default export instance
export const sse = new SSEClient();
