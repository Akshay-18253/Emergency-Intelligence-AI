/**
 * Emergency Intelligence AI - CAD Terminal & 5-Stage Statutory AI Policy Controller
 * Handles 911 caller intake, presets, audio chimes, and policy report card visualization.
 */

import { api } from './api.js';
import { audioSynth } from './audio.js';

export const CAD_PRESETS = [
  {
    id: 'cardiac',
    label: '❤️ Cardiac Arrest',
    text: 'Caller reports 58yo male collapsed on waterfront sidewalk near Pier 54, unresponsive, agonal breathing, bystander CPR in progress.',
    priorityHint: 'ECHO',
  },
  {
    id: 'pileup',
    label: '🚗 Highway Pileup',
    text: 'High-speed 3-vehicle collision on Central Parkway, heavy extrication needed, driver trapped, fuel leaking on roadway.',
    priorityHint: 'DELTA',
  },
  {
    id: 'fire',
    label: '🔥 Warehouse Fire',
    text: '3-alarm structure fire showing from warehouse roof on 4th Ave, toxic chemical drums burning, smoke plume spreading.',
    priorityHint: 'DELTA',
  },
  {
    id: 'pediatric',
    label: '🧒 Pediatric Trauma',
    text: '8yo child fell from 2nd story playground deck, altered mental status, severe head trauma.',
    priorityHint: 'CHARLIE',
  },
];

export class CadTerminal {
  constructor(options = {}) {
    this.container = options.container || document.getElementById('cadTerminalPanel');
    this.onIncidentDispatched = options.onIncidentDispatched || (() => {});
    this.audioSynth = options.audioSynth || audioSynth;
    this.isSubmitting = false;

    this._initElements();
    this._bindEvents();
  }

  _initElements() {
    this.presetBar = document.getElementById('cadPresetBar');
    this.narrativeInput = document.getElementById('cadNarrativeInput');
    this.submitBtn = document.getElementById('cadSubmitBtn');
    this.policyCard = document.getElementById('policyReportCard');
    this.audioToggleBtn = document.getElementById('audioToggleBtn');

    // Populate preset buttons if container exists
    if (this.presetBar) {
      this.presetBar.innerHTML = '';
      CAD_PRESETS.forEach(preset => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'cad-preset-btn';
        btn.dataset.presetId = preset.id;
        btn.textContent = preset.label;
        btn.addEventListener('click', () => this.applyPreset(preset));
        this.presetBar.appendChild(btn);
      });
    }
  }

  _bindEvents() {
    if (this.submitBtn) {
      this.submitBtn.addEventListener('click', () => this.submitIntake());
    }

    if (this.audioToggleBtn) {
      this.audioToggleBtn.addEventListener('click', () => {
        const isMuted = this.audioSynth.toggleMute();
        this.updateAudioButtonState(isMuted);
      });
    }

    if (this.narrativeInput) {
      this.narrativeInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          this.submitIntake();
        }
      });
    }
  }

  updateAudioButtonState(isMuted) {
    if (!this.audioToggleBtn) return;
    if (isMuted) {
      this.audioToggleBtn.classList.add('muted');
      this.audioToggleBtn.innerHTML = `<span>🔇</span> Audio Muted`;
    } else {
      this.audioToggleBtn.classList.remove('muted');
      this.audioToggleBtn.innerHTML = `<span>🔔</span> Audio Alert`;
    }
  }

  applyPreset(preset) {
    if (this.narrativeInput) {
      this.narrativeInput.value = preset.text;
      this.narrativeInput.focus();
    }
  }

  async submitIntake() {
    if (this.isSubmitting) return;
    const rawText = this.narrativeInput ? this.narrativeInput.value.trim() : '';
    if (!rawText) {
      alert('Please enter a 911 caller narrative or select a preset.');
      return;
    }

    this.isSubmitting = true;
    if (this.submitBtn) {
      this.submitBtn.disabled = true;
      this.submitBtn.textContent = 'Evaluating Policy...';
    }

    try {
      const response = await api.processIntake({ raw_text: rawText });
      this.renderPolicyReport(response);

      // Play audio notification based on priority
      const priority = response.triage ? response.triage.clinical_priority : 'CHARLIE';
      if (priority === 'ECHO' || priority === 'DELTA') {
        this.audioSynth.playDispatchChime();
        // Trigger subtle emergency siren after short delay
        setTimeout(() => this.audioSynth.playEmergencySiren(1.2), 650);
      } else {
        this.audioSynth.playDispatchChime();
      }

      // Notify map & dashboard
      this.onIncidentDispatched(response);
    } catch (err) {
      console.error('[CadTerminal] Intake submission error:', err);
      alert(`Dispatch Error: ${err.message}`);
    } finally {
      this.isSubmitting = false;
      if (this.submitBtn) {
        this.submitBtn.disabled = false;
        this.submitBtn.textContent = 'Dispatch 911 Incident';
      }
    }
  }

  renderPolicyReport(data) {
    if (!this.policyCard) return;

    const triage = data.triage || {};
    const priority = triage.clinical_priority || 'UNKNOWN';
    const badgesClass = priority.toLowerCase();
    const sanitization = data.sanitization || {};
    const mandates = data.mandates || {};
    const apparatus = data.assigned_apparatus || [];
    const auditHash = data.audit_hash || 'SHA256:PENDING';

    const apparatusList = apparatus.length > 0
      ? apparatus.map(a => `<span class="policy-badge pass">${a.callsign || a.apparatus_type || a}</span>`).join(' ')
      : '<span class="text-muted">Standby / None Required</span>';

    const mandatesText = mandates.statutory_dual_response_required
      ? 'AHA Dual-Response (ALS + BLS/Engine) Active'
      : (mandates.rule_identifier || 'NFPA Standard Guidelines');

    this.policyCard.style.display = 'flex';
    this.policyCard.innerHTML = `
      <div class="policy-stage-row">
        <span class="policy-stage-title">Stage 1: PII Sanitization</span>
        <span class="policy-badge pass">HIPAA MASKED (${sanitization.redacted_entities_count || 0} tokens)</span>
      </div>
      <div class="policy-stage-row">
        <span class="policy-stage-title">Stage 2: Clinical Triage</span>
        <span class="policy-badge ${badgesClass}">${priority} (${triage.primary_protocol || 'GENERAL'})</span>
      </div>
      <div class="policy-stage-row">
        <span class="policy-stage-title">Stage 3: Statutory Mandates</span>
        <span style="font-size:0.7rem; color:var(--text-main);">${mandatesText}</span>
      </div>
      <div class="policy-stage-row">
        <span class="policy-stage-title">Stage 4: Apparatus Assigned</span>
        <div style="display:flex; gap:0.25rem; flex-wrap:wrap;">${apparatusList}</div>
      </div>
      <div class="policy-stage-row">
        <span class="policy-stage-title">Stage 5: Audit Ledger</span>
        <span class="audit-hash-code" title="${auditHash}">${auditHash.substring(0, 16)}...</span>
      </div>
    `;
  }
}
