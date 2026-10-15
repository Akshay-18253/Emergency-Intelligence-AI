/**
 * Emergency Intelligence AI - Simulation Timeline Transport Controller
 * Controls discrete-event simulation playback, speed multipliers, scrubber, and vehicle stepping.
 */

import { api } from './api.js';

export class TimelineController {
  constructor(options = {}) {
    this.onSimulationUpdate = options.onSimulationUpdate || (() => {});
    this.currentSpeed = 1;
    this.isPlaying = false;
    this.timerId = null;
    this.currentSimTime = 0;
    this.maxDuration = 3600;
    this.stepSize = 5.0; // 5 seconds per simulation step

    this._initElements();
    this._bindEvents();
    this.syncStatus();
  }

  _initElements() {
    this.playBtn = document.getElementById('btnSimPlay');
    this.stepBtn = document.getElementById('btnSimStep');
    this.resetBtn = document.getElementById('btnSimReset');
    this.scrubber = document.getElementById('timelineScrubber');
    this.clockDisplay = document.getElementById('simClockDisplay');
    this.speedChips = document.querySelectorAll('.speed-chip');
  }

  _bindEvents() {
    if (this.playBtn) {
      this.playBtn.addEventListener('click', () => this.togglePlay());
    }

    if (this.stepBtn) {
      this.stepBtn.addEventListener('click', () => this.stepForward());
    }

    if (this.resetBtn) {
      this.resetBtn.addEventListener('click', () => this.resetSimulation());
    }

    if (this.scrubber) {
      this.scrubber.addEventListener('change', (e) => {
        const targetTime = parseFloat(e.target.value);
        this.seekTo(targetTime);
      });
      this.scrubber.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        this._updateClockDisplay(val);
      });
    }

    if (this.speedChips) {
      this.speedChips.forEach(chip => {
        chip.addEventListener('click', () => {
          const speed = parseFloat(chip.dataset.speed || '1');
          this.setSpeed(speed);
        });
      });
    }
  }

  formatTime(seconds) {
    const totalSecs = Math.max(0, Math.floor(seconds));
    const hrs = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;
    const hh = String(hrs).padStart(2, '0');
    const mm = String(mins).padStart(2, '0');
    const ss = String(secs).padStart(2, '0');
    return `T+${hh}:${mm}:${ss}`;
  }

  _updateClockDisplay(timeSec) {
    if (this.clockDisplay) {
      this.clockDisplay.textContent = this.formatTime(timeSec);
    }
  }

  setSpeed(speed) {
    this.currentSpeed = speed;
    if (this.speedChips) {
      this.speedChips.forEach(chip => {
        if (parseFloat(chip.dataset.speed) === speed) {
          chip.classList.add('active');
        } else {
          chip.classList.remove('active');
        }
      });
    }

    if (this.isPlaying) {
      this._stopLoop();
      this._startLoop();
    }
  }

  togglePlay() {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
  }

  play() {
    if (this.isPlaying) return;
    this.isPlaying = true;
    if (this.playBtn) {
      this.playBtn.innerHTML = `<span>⏸</span> Pause`;
      this.playBtn.classList.add('playing');
    }
    this._startLoop();
  }

  pause() {
    if (!this.isPlaying) return;
    this.isPlaying = false;
    if (this.playBtn) {
      this.playBtn.innerHTML = `<span>▶</span> Play`;
      this.playBtn.classList.remove('playing');
    }
    this._stopLoop();
  }

  _startLoop() {
    // Tick interval: base 500ms divided by current speed multiplier
    const intervalMs = Math.max(80, Math.floor(500 / this.currentSpeed));
    this.timerId = setInterval(async () => {
      try {
        await this.stepForward();
      } catch (err) {
        console.error('[Timeline] Step failed during playback loop:', err);
        this.pause();
      }
    }, intervalMs);
  }

  _stopLoop() {
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  async stepForward(stepSeconds = null) {
    const dt = stepSeconds !== null ? stepSeconds : this.stepSize;
    try {
      const data = await api.stepSimulation({ step_seconds: dt });
      this.updateStateFromData(data);
    } catch (err) {
      console.error('[Timeline] Step error:', err);
    }
  }

  async seekTo(targetTime) {
    try {
      const data = await api.stepSimulation({ target_time: targetTime });
      this.updateStateFromData(data);
    } catch (err) {
      console.error('[Timeline] Seek error:', err);
    }
  }

  async resetSimulation() {
    this.pause();
    try {
      const data = await api.resetSimulation();
      this.updateStateFromData(data);
    } catch (err) {
      console.error('[Timeline] Reset error:', err);
    }
  }

  async syncStatus() {
    try {
      const status = await api.getSimulationStatus();
      this.updateStateFromData(status);
    } catch (err) {
      console.warn('[Timeline] Could not sync initial simulation status:', err);
    }
  }

  updateStateFromData(data) {
    if (!data) return;
    this.currentSimTime = data.current_sim_time !== undefined ? data.current_sim_time : (data.sim_time || 0);
    this.maxDuration = data.max_duration_seconds || this.maxDuration;

    if (this.scrubber) {
      this.scrubber.max = this.maxDuration;
      this.scrubber.value = this.currentSimTime;
    }
    this._updateClockDisplay(this.currentSimTime);

    // If max duration reached, stop playback
    if (this.currentSimTime >= this.maxDuration && this.isPlaying) {
      this.pause();
    }

    // Trigger visual updates on the map
    this.onSimulationUpdate(data);
  }
}
