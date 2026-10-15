/**
 * Emergency Intelligence AI - Zero-Dependency Web Audio API Synthesizer
 * Generates realistic CAD alerting chimes and emergency sirens directly in the browser.
 * Strictly 0 external audio files or third-party audio packages.
 */

export class AudioAlertSynthesizer {
  constructor() {
    this.audioCtx = null;
    this.muted = false;
  }

  /**
   * Lazily initialize or resume Web Audio context
   */
  _ensureContext() {
    if (this.muted) return null;

    if (!this.audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return null;
      this.audioCtx = new AudioContextClass();
    }

    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }

    return this.audioCtx;
  }

  /**
   * Toggle audio mute state
   * @returns {boolean} New muted state
   */
  toggleMute() {
    this.muted = !this.muted;
    return this.muted;
  }

  /**
   * Set mute state explicitly
   */
  setMuted(isMuted) {
    this.muted = Boolean(isMuted);
  }

  /**
   * Play classic NFPA two-tone station alerting chime (880 Hz -> 660 Hz)
   */
  playDispatchChime() {
    const ctx = this._ensureContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;

      // Tone 1: High tone (880 Hz - A5)
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(880, now);
      gain1.gain.setValueAtTime(0.15, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.3);

      // Tone 2: Low tone (659.25 Hz - E5)
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(659.25, now + 0.28);
      gain2.gain.setValueAtTime(0.18, now + 0.28);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.7);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.28);
      osc2.stop(now + 0.75);
    } catch (err) {
      console.warn('[AudioSynthesizer] Chime synthesis error:', err);
    }
  }

  /**
   * Play critical priority wailing siren tone (700 Hz <-> 1100 Hz sweep)
   * @param {number} durationSeconds - Total siren duration
   */
  playEmergencySiren(durationSeconds = 1.5) {
    const ctx = this._ensureContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'triangle';
      osc.frequency.setValueAtTime(750, now);
      osc.frequency.linearRampToValueAtTime(1100, now + durationSeconds * 0.5);
      osc.frequency.linearRampToValueAtTime(750, now + durationSeconds);

      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + durationSeconds);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + durationSeconds);
    } catch (err) {
      console.warn('[AudioSynthesizer] Siren synthesis error:', err);
    }
  }
}

// Global default export instance
export const audioSynth = new AudioAlertSynthesizer();
