
const API_BASE = "";

const els = {
    statusBadge: document.getElementById('statusIndicator'),
    startBtn: document.getElementById('startBtn'),
    stopBtn: document.getElementById('stopBtn'),
    saveBtn: document.getElementById('saveBtn'),
    configForm: document.getElementById('configForm'),
    instrument: document.getElementById('instrument'),
    expiryType: document.getElementById('expiry_type'),
    lots: document.getElementById('lots'),
    legsContainer: document.getElementById('legsContainer'),
    legsTableBody: document.getElementById('legsTableBody'),
    currentPhase: document.getElementById('currentPhase'),
    selectedExpiry: document.getElementById('selectedExpiry'),
    spotPrice: document.getElementById('spotPrice'),
    countdown: document.getElementById('countdown'),
    countdownContainer: document.getElementById('countdownContainer'),
    logs: document.getElementById('logs'),
    paperTradingBadge: document.getElementById('paperTradingBadge')
};

let currentConfig = {};
let isRunning = false;

async function fetchStatus() {
    try {
        const res = await fetch(`${API_BASE}/status`);
        const data = await res.json();
        updateUI(data);
    } catch (e) {
        console.error("Status fetch failed", e);
    }
}

function updateUI(data) {
    currentConfig = data.config;
    const strategyState = data.strategy_state;

    // Paper Trading Badge
    if (currentConfig.strategy_settings && currentConfig.strategy_settings.paper_trading) {
        els.paperTradingBadge.style.display = 'inline-block';
    } else {
        els.paperTradingBadge.style.display = 'none';
    }

    isRunning = currentConfig.is_running;

    // Status Badge
    if (isRunning) {
        els.statusBadge.textContent = "RUNNING";
        els.statusBadge.className = "status-badge status-running";
        els.startBtn.classList.add('hidden');
        els.stopBtn.classList.remove('hidden');
        els.configForm.querySelectorAll('input, select').forEach(el => el.disabled = true);
        els.saveBtn.disabled = true;
    } else {
        els.statusBadge.textContent = "STOPPED";
        els.statusBadge.className = "status-badge status-stopped";
        els.startBtn.classList.remove('hidden');
        els.stopBtn.classList.add('hidden');
        els.configForm.querySelectorAll('input, select').forEach(el => el.disabled = false);
        els.saveBtn.disabled = false;
    }

    // Config inputs (only update if not focused to avoid typing jump, purely simplified here)
    if (!document.activeElement.tagName.match(/INPUT|SELECT/)) {
        els.instrument.value = currentConfig.strategy_settings?.instrument || "BANKNIFTY";
        els.expiryType.value = currentConfig.strategy_settings?.expiry_type || "current";
        els.lots.value = currentConfig.strategy_settings?.lots || 1;
        els.paperTrading.checked = currentConfig.strategy_settings?.paper_trading !== false; // Default true
        renderLegsConfig(currentConfig.strategy_settings?.legs || {});
    }

    // Dashboard Info
    els.currentPhase.textContent = strategyState.status || "IDLE";
    els.selectedExpiry.textContent = strategyState.selected_expiry || "Not Selected";

    // Spot Price Display
    updateSpotPrice(currentConfig.strategy_settings?.instrument || "BANKNIFTY");

    // Countdown Timer
    updateCountdown(strategyState.status, currentConfig.strategy_settings);

    // Table
    renderTable(strategyState.legs || {});
}

// Fetch and display spot price
async function updateSpotPrice(instrument) {
    const spotPriceEl = document.getElementById('spotPrice');
    try {
        const res = await fetch(`${API_BASE}/spot_price?instrument=${instrument}`);
        if (res.ok) {
            const data = await res.json();
            if (data.spot_price) {
                spotPriceEl.textContent = `₹${data.spot_price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                spotPriceEl.style.color = '#4CAF50';
            } else {
                spotPriceEl.textContent = 'No Data';
                spotPriceEl.style.color = '#FF5252';
            }
        } else {
            spotPriceEl.textContent = 'Error';
            spotPriceEl.style.color = '#FF5252';
        }
    } catch (e) {
        spotPriceEl.textContent = 'Offline';
        spotPriceEl.style.color = '#999';
    }
}

// Update countdown timer
function updateCountdown(status, settings) {
    const countdownContainer = document.getElementById('countdownContainer');
    const countdownEl = document.getElementById('countdown');

    const now = new Date();
    const currentTime = now.getHours() * 60 + now.getMinutes();

    // Parse start time from config (default 10:00)
    const startTime = settings?.time_range?.start || "10:00";
    const [startHour, startMin] = startTime.split(':').map(Number);
    const startTimeMinutes = startHour * 60 + startMin;

    // Range end time (default 10:30)
    const endTime = settings?.time_range?.end || "10:30";
    const [endHour, endMin] = endTime.split(':').map(Number);
    const endTimeMinutes = endHour * 60 + endMin;

    let showCountdown = false;
    let targetTime = null;
    let label = '';

    if (status === 'IDLE' && currentTime < startTimeMinutes) {
        // Waiting for start time
        showCountdown = true;
        targetTime = startTimeMinutes;
        label = 'Strike Selection In';
    } else if (status === 'MONITORING_RANGE' && currentTime < endTimeMinutes) {
        // Waiting for range finalization
        showCountdown = true;
        targetTime = endTimeMinutes;
        label = 'Range Finalization In';
    }

    if (showCountdown && targetTime) {
        const minutesRemaining = targetTime - currentTime;
        const hours = Math.floor(minutesRemaining / 60);
        const mins = minutesRemaining % 60;

        countdownContainer.style.display = 'block';
        countdownContainer.querySelector('label').textContent = label;

        if (hours > 0) {
            countdownEl.textContent = `${hours}h ${mins}m`;
        } else {
            countdownEl.textContent = `${mins}m`;
        }
        countdownEl.style.color = minutesRemaining < 5 ? '#FF5252' : '#FF9800';
    } else {
        countdownContainer.style.display = 'none';
    }
}

function renderLegsConfig(legs) {
    els.legsContainer.innerHTML = '';
    for (const [key, val] of Object.entries(legs)) {
        const div = document.createElement('div');
        div.className = `leg-item ${key.includes('ce') ? 'ce' : 'pe'}`;
        div.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <strong>${key.toUpperCase()}</strong>
                <span style="font-size:0.8rem; opacity:0.7;">StopLoss: ${val.sl_percentage}%</span>
            </div>
            <div style="margin-top:0.5rem; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem;">
                <div>
                   <label style="font-size:0.7rem;">Entry %</label>
                   <input type="number" value="${val.entry_trigger_percentage}" data-leg="${key}" class="leg-entry-input" ${isRunning ? 'disabled' : ''}>
                </div>
                <div>
                   <label style="font-size:0.7rem;">Re-entry %</label>
                   <input type="number" value="${val.reentry_trigger_percentage}" data-leg="${key}" class="leg-reentry-input" ${isRunning ? 'disabled' : ''}>
                </div>
                 <div>
                   <label style="font-size:0.7rem;">Lots</label>
                   <input type="number" value="${val.lots}" data-leg="${key}" class="leg-lots-input" ${isRunning ? 'disabled' : ''}>
                </div>
            </div>
            
        `;
        els.legsContainer.appendChild(div);
    }
}

function renderTable(legs) {
    if (Object.keys(legs).length === 0) {
        els.legsTableBody.innerHTML = '<tr><td colspan="6" style="text-align:center; opacity:0.5; padding: 2rem;">No Active Legs</td></tr>';
        return;
    }

    els.legsTableBody.innerHTML = '';
    for (const [key, val] of Object.entries(legs)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${key.toUpperCase()}</td>
            <td>${val.strike || '-'}</td>
            <td><span class="status-badge" style="font-size:0.7rem;">${val.status}</span></td>
            <td>${val.range_high ? val.range_high.toFixed(2) : '-'}</td>
            <td>Pending...</td>
            <td>Ent: ${val.entry_price ? val.entry_price.toFixed(2) : '-'} <br> SL: ${val.sl_price ? val.sl_price.toFixed(2) : '-'}</td>
        `;
        els.legsTableBody.appendChild(tr);
    }
}

// Actions
els.startBtn.onclick = async () => {
    await fetch(`${API_BASE}/control/start`, { method: 'POST' });
    fetchStatus();
};

els.stopBtn.onclick = async () => {
    await fetch(`${API_BASE}/control/stop`, { method: 'POST' });
    fetchStatus();
};

els.saveBtn.onclick = async () => {
    // Collect JSON
    const newSettings = {
        instrument: els.instrument.value,
        expiry_type: els.expiryType.value,
        lots: parseInt(els.lots.value),
        paper_trading: els.paperTrading.checked,
        legs: {}
    };

    // Collect from inputs
    document.querySelectorAll('.leg-entry-input').forEach(input => {
        const key = input.dataset.leg;
        if (!newSettings.legs[key]) newSettings.legs[key] = { ...currentConfig.strategy_settings.legs[key] };
        newSettings.legs[key].entry_trigger_percentage = parseFloat(input.value);
    });

    document.querySelectorAll('.leg-reentry-input').forEach(input => {
        const key = input.dataset.leg;
        if (!newSettings.legs[key]) newSettings.legs[key] = { ...currentConfig.strategy_settings.legs[key] };
        newSettings.legs[key].reentry_trigger_percentage = parseFloat(input.value);
    });

    document.querySelectorAll('.leg-lots-input').forEach(input => {
        const key = input.dataset.leg;
        if (!newSettings.legs[key]) newSettings.legs[key] = { ...currentConfig.strategy_settings.legs[key] };
        newSettings.legs[key].lots = parseInt(input.value);
    });

    const fullConfig = {
        ...currentConfig,
        strategy_settings: {
            ...currentConfig.strategy_settings,
            ...newSettings
        }
    };

    await fetch(`${API_BASE}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fullConfig)
    });
    alert("Configuration Saved!");
    fetchStatus();
};

// Polling
setInterval(fetchStatus, 2000);
fetchStatus();
