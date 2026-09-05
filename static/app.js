// Telecom Network Incident Triage Assistant - Production UI Logic
// Track: TRACK_ID=PS07

let appState = {
  scenarios: [],
  selectedScenario: null,
  currentAlerts: [],
  triageResult: null,
  topology: null,
  runbooks: [],
  streamFilter: 'all'
};

document.addEventListener('DOMContentLoaded', () => {
  initLiveClock();
  initModals();
  initCopilotChat();
  initStreamTabs();
  loadInitialData();
});

// 1. Live Clock
function initLiveClock() {
  const clockEl = document.getElementById('live-clock');
  function update() {
    const now = new Date();
    clockEl.textContent = now.toISOString().substring(11, 19) + ' UTC';
  }
  update();
  setInterval(update, 1000);
}

// 2. Load Core Data
async function loadInitialData() {
  try {
    // Health check
    const healthRes = await fetch('/api/health');
    const healthData = await healthRes.json();
    const dot = document.getElementById('gemini-status-dot');
    const text = document.getElementById('gemini-status-text');
    if (healthData.gemini_api_key_configured) {
      dot.className = 'status-dot pulsing';
      text.textContent = 'Gemini Active (Grounded)';
    } else {
      dot.className = 'status-dot';
      dot.style.background = '#38bdf8';
      text.textContent = 'Deterministic Local Engine';
    }

    // Scenarios
    const scRes = await fetch('/api/scenarios');
    appState.scenarios = await scRes.json();
    populateScenarioDropdown();

    // Topology
    const topoRes = await fetch('/api/topology');
    appState.topology = await topoRes.json();
    renderMiniTopology();

    // Runbooks
    const rbRes = await fetch('/api/runbooks');
    appState.runbooks = await rbRes.json();

    // Auto-select and run scenario 1 by default
    if (appState.scenarios.length > 0) {
      document.getElementById('scenario-dropdown').value = appState.scenarios[0].file;
      await selectScenario(appState.scenarios[0].file);
      await executeTriage();
    }
  } catch (err) {
    console.error('Failed to load initial data:', err);
  }
}

// 3. Scenario Selector
function populateScenarioDropdown() {
  const select = document.getElementById('scenario-dropdown');
  select.innerHTML = '';
  appState.scenarios.forEach(sc => {
    const opt = document.createElement('option');
    opt.value = sc.file;
    opt.textContent = `${sc.file.replace('.json', '')}: ${sc.title} (${sc.alert_count} alarms)`;
    select.appendChild(opt);
  });

  select.addEventListener('change', async (e) => {
    await selectScenario(e.target.value);
  });

  document.getElementById('btn-run-triage').addEventListener('click', async () => {
    await executeTriage();
  });
}

async function selectScenario(filename) {
  try {
    const res = await fetch(`/api/scenarios/${filename}`);
    const data = await res.json();
    appState.selectedScenario = data;
    appState.currentAlerts = data.alerts || [];

    // Reset results view before running triage
    renderRawStream();
    renderMiniTopology();
  } catch (err) {
    console.error(`Failed to load scenario ${filename}:`, err);
  }
}

// 4. Run Triage Engine
async function executeTriage() {
  if (!appState.currentAlerts || appState.currentAlerts.length === 0) return;

  const btn = document.getElementById('btn-run-triage');
  btn.disabled = true;
  btn.innerHTML = `<span class="status-dot pulsing"></span> Correlating...`;

  try {
    const res = await fetch('/api/triage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alerts: appState.currentAlerts })
    });
    const triageData = await res.json();
    appState.triageResult = triageData;

    // Render components
    renderKPIs(triageData);
    renderIncidents(triageData.incidents);
    renderRawStream();
    renderMiniTopology();
    generateHandoverText(triageData);

  } catch (err) {
    console.error('Triage execution failed:', err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
      Run Triage Engine
    `;
  }
}

// 5. Render KPIs
function renderKPIs(res) {
  document.getElementById('kpi-total-alerts').textContent = res.total_raw_alerts;
  document.getElementById('kpi-incidents').textContent = res.incident_count;
  document.getElementById('kpi-noise').textContent = res.noise_count;
  document.getElementById('kpi-latency').textContent = `${res.execution_time_ms} ms`;

  let totalSubs = 0;
  res.incidents.forEach(inc => totalSubs += (inc.blast_radius_subscribers || 0));
  document.getElementById('kpi-subscribers').textContent = totalSubs.toLocaleString();

  // Priority count badges
  let p1 = 0, p2 = 0, p3 = 0;
  res.incidents.forEach(inc => {
    if (inc.priority === 'P1') p1++;
    else if (inc.priority === 'P2') p2++;
    else if (inc.priority === 'P3') p3++;
  });
  document.getElementById('badge-p1-count').textContent = `${p1} P1`;
  document.getElementById('badge-p2-count').textContent = `${p2} P2`;
  document.getElementById('badge-p3-count').textContent = `${p3} P3`;
}

// 6. Mini Topology Visualizer
function renderMiniTopology() {
  const container = document.getElementById('topology-grid');
  if (!appState.topology || !appState.topology.nodes) return;

  container.innerHTML = '';
  const affectedDevices = new Set();
  const rootDevices = new Set();

  if (appState.triageResult && appState.triageResult.incidents) {
    appState.triageResult.incidents.forEach(inc => {
      rootDevices.add(inc.root_cause_device);
      (inc.affected_devices || []).forEach(d => affectedDevices.add(d));
    });
  }

  appState.topology.nodes.slice(0, 9).forEach(node => {
    const chip = document.createElement('div');
    chip.className = 'node-chip';

    let status = 'status-healthy';
    let statusText = 'OK';
    if (rootDevices.has(node.id)) {
      status = 'status-critical';
      statusText = 'ROOT';
    } else if (affectedDevices.has(node.id)) {
      status = 'status-warning';
      statusText = 'ALM';
    }

    chip.classList.add(status);
    chip.innerHTML = `<span>${node.id}</span> <strong>${statusText}</strong>`;
    container.appendChild(chip);
  });

  const badge = document.getElementById('topo-status-badge');
  if (rootDevices.size > 0) {
    badge.className = 'badge badge-p1';
    badge.textContent = `${rootDevices.size} Active Root Faults`;
  } else {
    badge.className = 'badge badge-sm';
    badge.textContent = 'Nominal';
  }
}

// 7. Stream Feed Rendering
function initStreamTabs() {
  const tabs = document.querySelectorAll('.stream-tabs .tab-btn');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      appState.streamFilter = tab.getAttribute('data-filter');
      renderRawStream();
    });
  });
}

function renderRawStream() {
  const container = document.getElementById('stream-feed');
  const alerts = appState.currentAlerts || [];

  const noiseIds = new Set();
  if (appState.triageResult && appState.triageResult.noise_alerts) {
    appState.triageResult.noise_alerts.forEach(a => noiseIds.add(a.id));
  }

  let filtered = alerts;
  if (appState.streamFilter === 'signal') {
    filtered = alerts.filter(a => !noiseIds.has(a.id));
  } else if (appState.streamFilter === 'noise') {
    filtered = alerts.filter(a => noiseIds.has(a.id));
  }

  // Update counts
  document.getElementById('count-all').textContent = alerts.length;
  document.getElementById('count-signal').textContent = alerts.length - noiseIds.size;
  document.getElementById('count-noise').textContent = noiseIds.size;

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">No alerts match the selected filter.</div>';
    return;
  }

  container.innerHTML = '';
  filtered.forEach(a => {
    const isNoise = noiseIds.has(a.id);
    const item = document.createElement('div');
    item.className = `alert-item sev-${(a.severity || 'info').toLowerCase()} ${isNoise ? 'is-noise-item' : ''}`;

    const sevBadge = `<span class="badge badge-sm">${a.severity}</span>`;
    const noiseBadge = isNoise ? `<span class="badge badge-noise">ISOLATED NOISE</span>` : '';

    item.innerHTML = `
      <div class="alert-top">
        <span class="alert-dev">${a.device_id}</span>
        <span class="alert-time">${a.timestamp.substring(11, 19)} UTC</span>
      </div>
      <div class="alert-type">${a.event_type}</div>
      <div class="alert-msg">${a.message}</div>
      <div class="alert-tags">
        ${sevBadge}
        ${noiseBadge}
        <span class="badge badge-sm">${a.device_tier || 'Tier'}</span>
      </div>
    `;
    container.appendChild(item);
  });
}

// 8. Render Incidents & Grounded Triage
function renderIncidents(incidents) {
  const container = document.getElementById('incidents-container');
  if (!incidents || incidents.length === 0) {
    container.innerHTML = '<div class="empty-state">No active incidents detected.</div>';
    return;
  }

  container.innerHTML = '';
  incidents.forEach(inc => {
    const card = document.createElement('div');
    card.className = `incident-card priority-${inc.priority}`;

    const priorityClass = `badge-${inc.priority.toLowerCase()}`;
    const statusBadge = inc.is_escalated
      ? `<span class="badge badge-escalated">DISCIPLINED ESCALATION</span>`
      : `<span class="badge badge-ai">GROUNDED NOC RUNBOOK</span>`;

    // Action items HTML
    let actionsHtml = '';
    if (inc.recommended_actions && inc.recommended_actions.length > 0) {
      actionsHtml = `
        <div class="action-steps-group">
          <div class="subcard-title">${inc.is_escalated ? 'Mandated Evidence Capture Steps:' : 'Recommended Triage Actions:'}</div>
          ${inc.recommended_actions.map(act => `
            <div class="action-step-item">
              <div class="action-step-title">${act.step || ''}. ${act.title}</div>
              <div style="font-size:0.75rem; color:#94a3b8; margin-bottom:4px;">${act.purpose || ''}</div>
              ${act.command ? `
                <div class="action-cmd-box">
                  <code>${act.command}</code>
                  <button class="btn-copy" onclick="copyText('${act.command.replace(/'/g, "\\'")}')">Copy CLI</button>
                </div>
              ` : ''}
            </div>
          `).join('')}
        </div>
      `;
    }

    // Safety Warnings
    let warningsHtml = '';
    if (inc.safety_warnings && inc.safety_warnings.length > 0) {
      warningsHtml = `
        <div class="safety-warning-banner">
          <div class="safety-title">⚠️ Operational Safety Precautions:</div>
          <div>${inc.safety_warnings.join(' ')}</div>
        </div>
      `;
    }

    // Citations / Grounding
    let citationCardHtml = '';
    if (inc.matched_runbook_id) {
      citationCardHtml = `
        <div class="citation-card">
          <div class="citation-header">
            <span class="citation-tag">Ground Truth Source: ${inc.matched_runbook_id}</span>
            <span class="confidence-meter">Retrieval Confidence: ${Math.round((inc.runbook_confidence || 0) * 100)}%</span>
          </div>
          <div class="citation-list">
            ${(inc.citations || [inc.matched_runbook_id]).map(c => `<span class="citation-badge">📌 ${c}</span>`).join('')}
          </div>
        </div>
      `;
    } else if (inc.is_escalated && inc.escalation_package) {
      const pkg = inc.escalation_package;
      citationCardHtml = `
        <div class="escalation-detail-card">
          <div class="citation-header">
            <span class="text-rose font-mono" style="font-weight:700;">Zero-Day / Uncovered Anomaly Escalation</span>
            <span class="badge badge-p1">${pkg.urgency} URGENT</span>
          </div>
          <div style="font-size:0.78rem; color:#f87171; margin-bottom:6px;">
            ${pkg.reason}
          </div>
          <div class="escalation-grid">
            <div class="escalation-item">
              <span class="escalation-label">Target Tier 3/4 Team:</span>
              <strong>${pkg.target_team}</strong>
            </div>
            <div class="escalation-item">
              <span class="escalation-label">Ruled Out Runbooks:</span>
              <span>${(pkg.ruled_out_runbooks || []).join(', ')}</span>
            </div>
          </div>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="incident-header">
        <div class="incident-title-block">
          <h3>${inc.title}</h3>
          <div class="incident-meta-chips">
            <span class="badge ${priorityClass}">${inc.priority} (${inc.severity})</span>
            <span class="badge badge-root">Root: ${inc.root_cause_device}</span>
            <span class="badge badge-sm">Impact Score: ${inc.impact_score}</span>
            <span class="badge badge-sm">${(inc.blast_radius_subscribers || 0).toLocaleString()} Subs</span>
            ${statusBadge}
          </div>
        </div>
      </div>

      <div class="triage-summary-box ${inc.is_escalated ? 'escalation-box' : ''}">
        ${inc.triage_summary || 'Incident correlated by NOC pipeline.'}
      </div>

      ${citationCardHtml}
      ${actionsHtml}
      ${warningsHtml}
    `;

    container.appendChild(card);
  });
}

// 9. Instant Handover Generator
function generateHandoverText(res) {
  const handoverEl = document.getElementById('handover-preview');
  if (!res.incidents || res.incidents.length === 0) {
    handoverEl.textContent = 'No active incidents to report for shift handover.';
    return;
  }

  const lines = [
    `=== TELECOM NOC SHIFT HANDOVER BRIEF ===`,
    `Timestamp: ${new Date().toISOString()} | Track: TRACK_ID=PS07`,
    `Total Telemetry Events: ${res.total_raw_alerts} | Active Incidents: ${res.incident_count} | Noise Isolated: ${res.noise_count}`,
    ``
  ];

  res.incidents.forEach(inc => {
    lines.push(`[${inc.priority}] ${inc.id}: ${inc.title}`);
    lines.push(` - Root Device: ${inc.root_cause_device}`);
    lines.push(` - Affected Nodes (${inc.affected_devices.length}): ${inc.affected_devices.join(', ')}`);
    lines.push(` - Blast Radius: ${(inc.blast_radius_subscribers || 0).toLocaleString()} subscribers`);
    if (inc.is_escalated) {
      lines.push(` - STATUS: ESCALATED to ${inc.escalation_package ? inc.escalation_package.target_team : 'L3 Team'}`);
      lines.push(` - Escalation Reason: Uncatalogued anomaly with no approved runbook. Evidence preserved.`);
    } else {
      lines.push(` - Grounded Runbook: ${inc.matched_runbook_id} (${inc.citations ? inc.citations.join(', ') : ''})`);
      lines.push(` - First Action: ${inc.recommended_actions[0] ? inc.recommended_actions[0].command || inc.recommended_actions[0].title : 'In progress'}`);
    }
    lines.push(``);
  });

  handoverEl.textContent = lines.join('\n');
}

// 10. Copilot Chat Interactive
function initCopilotChat() {
  const form = document.getElementById('copilot-form');
  const input = document.getElementById('copilot-input');
  const history = document.getElementById('copilot-chat-history');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;

    // Append user message
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-bubble user';
    userMsg.textContent = query;
    history.appendChild(userMsg);
    input.value = '';
    history.scrollTop = history.scrollHeight;

    // Loading indicator
    const aiLoading = document.createElement('div');
    aiLoading.className = 'chat-bubble ai';
    aiLoading.innerHTML = `<strong>NOC Copilot:</strong> Thinking with grounded runbooks...`;
    history.appendChild(aiLoading);
    history.scrollTop = history.scrollHeight;

    // Active incident context
    const activeInc = (appState.triageResult && appState.triageResult.incidents)
      ? appState.triageResult.incidents[0]
      : {};

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, incident_context: activeInc })
      });
      const data = await res.json();
      aiLoading.innerHTML = `<strong>NOC Copilot (${data.engine}):</strong> ${data.reply}`;
    } catch (err) {
      aiLoading.innerHTML = `<strong>NOC Copilot:</strong> Request failed: ${err.message}`;
    }
    history.scrollTop = history.scrollHeight;
  });

  document.getElementById('btn-copy-handover').addEventListener('click', () => {
    const text = document.getElementById('handover-preview').textContent;
    navigator.clipboard.writeText(text);
    alert('Shift Handover Brief copied to clipboard!');
  });
}

// 11. Modals (Runbooks and Full Topology)
function initModals() {
  const rbModal = document.getElementById('runbooks-modal');
  const topoModal = document.getElementById('topology-modal');

  document.getElementById('btn-view-runbooks').addEventListener('click', () => {
    renderRunbooksModal();
    rbModal.classList.add('active');
  });

  document.getElementById('btn-close-runbooks').addEventListener('click', () => {
    rbModal.classList.remove('active');
  });

  document.getElementById('btn-view-topology').addEventListener('click', () => {
    renderFullTopologyModal();
    topoModal.classList.add('active');
  });

  document.getElementById('btn-close-topology').addEventListener('click', () => {
    topoModal.classList.remove('active');
  });

  [rbModal, topoModal].forEach(m => {
    m.addEventListener('click', (e) => {
      if (e.target === m) m.classList.remove('active');
    });
  });
}

function renderRunbooksModal() {
  const body = document.getElementById('runbooks-modal-body');
  if (!appState.runbooks || appState.runbooks.length === 0) {
    body.innerHTML = '<div>No runbooks found.</div>';
    return;
  }

  body.innerHTML = appState.runbooks.map(rb => `
    <div class="incident-card" style="margin-bottom:12px;">
      <div class="incident-header">
        <div>
          <h3>${rb.id}: ${rb.title}</h3>
          <div class="incident-meta-chips" style="margin-top:4px;">
            <span class="badge badge-sm text-cyan">${rb.domain}</span>
            <span class="badge badge-sm">${rb.severity}</span>
            <span class="badge badge-sm">Applies: ${(rb.applies_to || []).join(', ')}</span>
          </div>
        </div>
      </div>
      <div style="font-size:0.78rem; color:#94a3b8; margin-top:6px;">
        <strong>Symptoms:</strong> ${(rb.symptoms || []).join(' • ')}
      </div>
      <div style="margin-top:8px;">
        <div class="subcard-title">Mitigation Procedures:</div>
        ${(rb.mitigation_sections || []).map(s => `
          <div style="background:#0f172a; padding:6px 10px; border-radius:4px; margin-top:4px; font-size:0.76rem;">
            <strong>${s.title}</strong>
            ${s.commands && s.commands.length > 0 ? `<div class="font-mono text-cyan" style="margin-top:2px;">$ ${s.commands[0]}</div>` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function renderFullTopologyModal() {
  const treeView = document.getElementById('topology-tree-view');
  if (!appState.topology || !appState.topology.nodes) return;

  const nodes = appState.topology.nodes;
  treeView.innerHTML = '';

  // Group by tier
  const tierOrder = ['Core', 'Aggregation', 'Edge', 'Access', 'Facility'];
  tierOrder.forEach(tier => {
    const tierNodes = nodes.filter(n => n.tier === tier);
    if (tierNodes.length > 0) {
      const tierHeader = document.createElement('div');
      tierHeader.style.cssText = 'font-weight:700; color:#38bdf8; margin-top:12px; margin-bottom:4px; font-size:0.85rem;';
      tierHeader.textContent = `=== ${tier.toUpperCase()} TIER NODES (${tierNodes.length}) ===`;
      treeView.appendChild(tierHeader);

      tierNodes.forEach(node => {
        const item = document.createElement('div');
        item.className = 'tree-node';
        item.innerHTML = `
          <div>
            <strong style="color:#fff;">${node.id}</strong> - ${node.name}
            <div style="font-size:0.7rem; color:#64748b;">Location: ${node.location} | Type: ${node.type} ${node.parent ? '| Uplink: ' + node.parent : ''}</div>
          </div>
          <span class="badge badge-sm font-mono">${(node.subscribers_impacted || 0).toLocaleString()} Subs</span>
        `;
        treeView.appendChild(item);
      });
    }
  });
}

function copyText(text) {
  navigator.clipboard.writeText(text);
  alert(`Command copied: ${text}`);
}
