// ========== Dashboard ==========

async function loadDashboard() {
    try {
        const resp = await fetch('/api/dashboard');
        const companies = await resp.json();
        const tbody = document.getElementById('companies-body');
        const emptyState = document.getElementById('empty-state');

        if (!companies.length) {
            tbody.closest('table').closest('div').classList.add('hidden');
            emptyState.classList.remove('hidden');
            return;
        }

        let totalRed = 0, totalAmber = 0;
        companies.forEach(c => {
            totalRed += (c.alert_counts.red || 0);
            totalAmber += (c.alert_counts.amber || 0);
        });

        if (totalRed || totalAmber) {
            const bar = document.getElementById('alerts-bar');
            bar.classList.remove('hidden');
            if (totalRed) {
                const el = document.getElementById('red-alerts');
                el.classList.remove('hidden');
                el.querySelector('span').textContent = `${totalRed} red alert${totalRed > 1 ? 's' : ''}`;
            }
            if (totalAmber) {
                const el = document.getElementById('amber-alerts');
                el.classList.remove('hidden');
                el.querySelector('span').textContent = `${totalAmber} amber alert${totalAmber > 1 ? 's' : ''}`;
            }
        }

        tbody.innerHTML = companies.map(c => `
            <tr class="hover:bg-gray-50">
                <td class="px-4 py-3 font-medium text-gray-900">
                    <a href="/company/${c.id}" class="hover:text-blue-600">${esc(c.name)}</a>
                </td>
                <td class="px-4 py-3 text-gray-600">${esc(c.ticker)}${c.exchange ? '.' + esc(c.exchange) : ''}</td>
                <td class="px-4 py-3"><span class="rating-badge rating-${c.current_rating.toLowerCase().replace(' ', '-')}">${esc(c.current_rating)}</span></td>
                <td class="px-4 py-3 text-right font-mono">${c.currency === 'JPY' ? '¥' : '$'}${formatNum(c.current_price)}</td>
                <td class="px-4 py-3 text-right font-mono">${c.currency === 'JPY' ? '¥' : '$'}${formatNum(c.blended_price_target)}</td>
                <td class="px-4 py-3 text-right font-mono ${c.upside >= 0 ? 'text-green-600' : 'text-red-600'}">${c.upside != null ? (c.upside * 100).toFixed(1) + '%' : '—'}</td>
                <td class="px-4 py-3 text-center">
                    ${c.suggested_rating ? `<span class="rating-badge rating-${c.suggested_rating.toLowerCase().replace(' ', '-')}">${esc(c.suggested_rating)}</span>` : '—'}
                    ${c.suggested_rating && c.suggested_rating !== c.current_rating ? '<span class="ml-1 text-amber-500" title="Divergence">⚠</span>' : ''}
                </td>
                <td class="px-4 py-3 text-center">
                    ${alertBadges(c.alert_counts)}
                </td>
                <td class="px-4 py-3 text-center">
                    <a href="/company/${c.id}" class="text-blue-600 hover:text-blue-700 text-sm">View</a>
                </td>
            </tr>
        `).join('');

        document.getElementById('last-updated').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    } catch (e) {
        console.error('Failed to load dashboard:', e);
    }
}

function alertBadges(counts) {
    if (!counts || (!counts.red && !counts.amber && !counts.green)) return '<span class="text-gray-300">—</span>';
    let html = '';
    if (counts.red) html += `<span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium tier-red">${counts.red}</span> `;
    if (counts.amber) html += `<span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium tier-amber">${counts.amber}</span> `;
    return html;
}

// ========== Company Detail ==========

async function loadCompanyDetail(id) {
    try {
        const resp = await fetch(`/api/companies/${id}`);
        if (!resp.ok) { document.getElementById('company-detail').innerHTML = '<p class="text-red-500">Company not found.</p>'; return; }
        const c = await resp.json();
        const el = document.getElementById('company-detail');

        el.innerHTML = `
            <div class="flex items-center justify-between mb-6">
                <div>
                    <h2 class="text-2xl font-semibold text-gray-800">${esc(c.name)}</h2>
                    <p class="text-gray-500">${esc(c.ticker)}${c.exchange ? '.' + esc(c.exchange) : ''} · ${esc(c.currency)}</p>
                </div>
                <div class="text-right">
                    <p class="text-sm text-gray-500">Current Rating</p>
                    <span class="rating-badge rating-${c.current_rating.toLowerCase().replace(' ', '-')}">${esc(c.current_rating)}</span>
                    ${c.suggested_rating && c.suggested_rating !== c.current_rating
                        ? `<span class="ml-2 text-sm text-amber-600">Suggested: ${esc(c.suggested_rating)}</span>` : ''}
                </div>
            </div>

            <div class="grid grid-cols-3 gap-4 mb-6">
                <div class="bg-white rounded-lg shadow p-4">
                    <p class="text-sm text-gray-500">Price</p>
                    <p class="text-2xl font-mono font-bold">${c.currency === 'JPY' ? '¥' : '$'}${formatNum(c.current_price)}</p>
                </div>
                <div class="bg-white rounded-lg shadow p-4">
                    <p class="text-sm text-gray-500">Blended Target</p>
                    <p class="text-2xl font-mono font-bold">${c.currency === 'JPY' ? '¥' : '$'}${formatNum(c.blended_price_target)}</p>
                </div>
                <div class="bg-white rounded-lg shadow p-4">
                    <p class="text-sm text-gray-500">Upside</p>
                    <p class="text-2xl font-mono font-bold ${c.upside >= 0 ? 'text-green-600' : 'text-red-600'}">${c.upside != null ? (c.upside * 100).toFixed(1) + '%' : '—'}</p>
                </div>
            </div>

            ${c.alerts.length ? `
                <div class="mb-6">
                    <h3 class="text-lg font-semibold mb-3">Active Alerts</h3>
                    <div class="space-y-2">
                        ${c.alerts.map(a => `
                            <div class="bg-white rounded-lg shadow p-3 border-l-4 ${a.tier === 'red' ? 'border-red-500' : a.tier === 'amber' ? 'border-amber-500' : 'border-green-500'}">
                                <div class="flex justify-between items-start">
                                    <div>
                                        <span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium tier-${a.tier}">${a.tier}</span>
                                        <span class="font-medium ml-2">${esc(a.title)}</span>
                                        <p class="text-sm text-gray-600 mt-1">${esc(a.description)}</p>
                                    </div>
                                    <button onclick="acknowledgeAlert(${a.id}, ${id})" class="text-xs text-gray-400 hover:text-gray-600">Dismiss</button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}

            <div class="mb-6">
                <h3 class="text-lg font-semibold mb-3">Upload Materials</h3>
                <div class="bg-white rounded-lg shadow p-4">
                    <form id="materials-form" onsubmit="return false;">
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Scenario PDF <span class="text-red-500">*</span></label>
                                <input type="file" accept=".pdf" id="mat-scenario" class="block w-full text-sm text-gray-500 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Thesis PDF</label>
                                <input type="file" accept=".pdf" id="mat-thesis" class="block w-full text-sm text-gray-500 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-gray-50 file:text-gray-700 hover:file:bg-gray-100">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Model XLSX</label>
                                <input type="file" accept=".xlsx,.xls" id="mat-model" class="block w-full text-sm text-gray-500 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-medium file:bg-gray-50 file:text-gray-700 hover:file:bg-gray-100">
                            </div>
                        </div>
                        <button onclick="uploadMaterials(${id})" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium">Upload</button>
                    </form>
                    <div id="materials-status" class="mt-3 hidden"></div>
                    <div id="materials-results" class="mt-4 hidden"></div>
                </div>
            </div>

            <div class="mb-6">
                <h3 class="text-lg font-semibold mb-3">Scenarios</h3>
                ${c.scenarios.length ? `
                    <div class="bg-white rounded-lg shadow overflow-hidden">
                        <table class="w-full text-sm">
                            <thead class="bg-gray-50 border-b">
                                <tr>
                                    <th class="px-3 py-2 text-left">Scenario</th>
                                    <th class="px-3 py-2 text-right">Raw Wt</th>
                                    <th class="px-3 py-2 text-right">Eff. Wt</th>
                                    <th class="px-3 py-2 text-right">Implied Price</th>
                                    <th class="px-3 py-2 text-right">Contribution</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y">
                                ${c.scenarios.map(s => `
                                    <tr>
                                        <td class="px-3 py-2 font-medium">${esc(s.name)}</td>
                                        <td class="px-3 py-2 text-right font-mono">${s.raw_weight != null ? (s.raw_weight * 100).toFixed(1) + '%' : '—'}</td>
                                        <td class="px-3 py-2 text-right font-mono">${s.effective_weight != null ? (s.effective_weight * 100).toFixed(1) + '%' : '—'}</td>
                                        <td class="px-3 py-2 text-right font-mono">${c.currency === 'JPY' ? '¥' : '$'}${formatNum(s.implied_price)}</td>
                                        <td class="px-3 py-2 text-right font-mono">${s.contribution != null ? (c.currency === 'JPY' ? '¥' : '$') + formatNum(s.contribution) : '—'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : '<p class="text-gray-400">No scenarios defined.</p>'}
            </div>

            <div>
                <h3 class="text-lg font-semibold mb-3">Indicators</h3>
                ${c.indicators.length ? `
                    <div class="bg-white rounded-lg shadow overflow-hidden">
                        <table class="w-full text-sm">
                            <thead class="bg-gray-50 border-b">
                                <tr>
                                    <th class="px-3 py-2 text-left">Indicator</th>
                                    <th class="px-3 py-2 text-left">Current</th>
                                    <th class="px-3 py-2 text-left">Bear Thr.</th>
                                    <th class="px-3 py-2 text-left">Bull Thr.</th>
                                    <th class="px-3 py-2 text-left">Freq.</th>
                                    <th class="px-3 py-2 text-left">Source</th>
                                    <th class="px-3 py-2 text-center">Status</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y">
                                ${c.indicators.map(ind => `
                                    <tr>
                                        <td class="px-3 py-2 font-medium">${esc(ind.name)}</td>
                                        <td class="px-3 py-2 font-mono">${esc(ind.current_value || '—')}</td>
                                        <td class="px-3 py-2 font-mono text-red-600">${esc(ind.bear_threshold || '—')}</td>
                                        <td class="px-3 py-2 font-mono text-green-600">${esc(ind.bull_threshold || '—')}</td>
                                        <td class="px-3 py-2">${esc(ind.check_frequency)}</td>
                                        <td class="px-3 py-2">${esc(ind.data_source)}</td>
                                        <td class="px-3 py-2 text-center"><span class="inline-block w-3 h-3 rounded-full bg-${ind.status === 'red' ? 'red' : ind.status === 'amber' ? 'amber' : 'green'}-500"></span></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : '<p class="text-gray-400">No indicators defined.</p>'}
            </div>
        `;
    } catch (e) {
        console.error('Failed to load company:', e);
    }
}

async function acknowledgeAlert(alertId, companyId) {
    await fetch(`/api/alerts/${alertId}/acknowledge`, { method: 'PUT' });
    loadCompanyDetail(companyId);
}

async function uploadMaterials(companyId) {
    const scenarioFile = document.getElementById('mat-scenario').files[0];
    if (!scenarioFile) { alert('Scenario PDF is required.'); return; }

    const statusDiv = document.getElementById('materials-status');
    const resultsDiv = document.getElementById('materials-results');
    statusDiv.className = 'mt-3 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-sm text-blue-800';
    statusDiv.textContent = 'Uploading and processing...';
    resultsDiv.classList.add('hidden');

    const formData = new FormData();
    formData.append('scenario_pdf', scenarioFile);
    const thesisFile = document.getElementById('mat-thesis').files[0];
    if (thesisFile) formData.append('thesis_pdf', thesisFile);
    const modelFile = document.getElementById('mat-model').files[0];
    if (modelFile) formData.append('model_xlsx', modelFile);

    try {
        const resp = await fetch(`/api/companies/${companyId}/materials`, { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.detail) {
            statusDiv.className = 'mt-3 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-800';
            statusDiv.textContent = data.detail;
            return;
        }

        statusDiv.className = 'mt-3 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm text-green-800';
        statusDiv.textContent = `Files saved: ${data.files_saved.join(', ')}`;

        let html = '';

        if (data.indicators_updated.length) {
            html += `<div class="mb-3"><h4 class="font-medium text-sm text-gray-700 mb-1">Updated Indicators (${data.indicators_updated.length})</h4>
                <ul class="text-sm text-gray-600 list-disc ml-5">${data.indicators_updated.map(u =>
                    `<li>${esc(u.name)}: ${Object.entries(u.changes).map(([k,v]) => `${k}=${esc(v)}`).join(', ')}</li>`
                ).join('')}</ul></div>`;
        }

        if (data.new_indicators.length) {
            window._pendingNewIndicators = data.new_indicators;
            window._pendingCompanyId = companyId;
            html += `<div class="mb-3"><h4 class="font-medium text-sm text-amber-700 mb-1">New Indicators Found (${data.new_indicators.length}) — review and confirm</h4>
                <table class="w-full text-sm border rounded"><thead class="bg-gray-50"><tr>
                    <th class="px-2 py-1 text-left"><input type="checkbox" checked onchange="toggleAllNewInd(this)"></th>
                    <th class="px-2 py-1 text-left">Name</th><th class="px-2 py-1 text-left">Bear</th>
                    <th class="px-2 py-1 text-left">Bull</th><th class="px-2 py-1 text-left">Freq</th>
                    <th class="px-2 py-1 text-left">Source</th></tr></thead>
                <tbody>${data.new_indicators.map((ind, i) => `<tr>
                    <td class="px-2 py-1"><input type="checkbox" checked class="new-ind-check" data-idx="${i}"></td>
                    <td class="px-2 py-1">${esc(ind.name)}</td>
                    <td class="px-2 py-1 text-red-600">${esc(ind.bear_threshold || '—')}</td>
                    <td class="px-2 py-1 text-green-600">${esc(ind.bull_threshold || '—')}</td>
                    <td class="px-2 py-1">${esc(ind.check_frequency)}</td>
                    <td class="px-2 py-1">${esc(ind.data_source)}</td></tr>`).join('')}</tbody></table>
                <button onclick="confirmNewIndicators()" class="mt-2 bg-green-600 text-white px-4 py-1.5 rounded hover:bg-green-700 text-sm font-medium">Confirm New Indicators</button></div>`;
        }

        if (data.possibly_removed.length) {
            html += `<div class="mb-3"><h4 class="font-medium text-sm text-red-700 mb-1">Possibly Removed (${data.possibly_removed.length})</h4>
                <ul class="text-sm text-gray-600 list-disc ml-5">${data.possibly_removed.map(r =>
                    `<li>${esc(r.name)} (status: ${r.status})</li>`
                ).join('')}</ul>
                <p class="text-xs text-gray-500 mt-1">These indicators are in the database but were not found in the PDF. No action taken.</p></div>`;
        }

        if (data.extraction_errors.length) {
            html += `<div class="mb-3"><h4 class="font-medium text-sm text-red-700 mb-1">Extraction Errors</h4>
                <ul class="text-sm text-red-600 list-disc ml-5">${data.extraction_errors.map(e =>
                    `<li>${esc(e)}</li>`
                ).join('')}</ul></div>`;
        }

        if (!html) html = '<p class="text-sm text-gray-500">No indicator changes detected.</p>';

        resultsDiv.innerHTML = html;
        resultsDiv.classList.remove('hidden');

        if (data.indicators_updated.length) loadCompanyDetail(companyId);
    } catch (err) {
        statusDiv.className = 'mt-3 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-800';
        statusDiv.textContent = 'Upload failed: ' + err.message;
    }
}

function toggleAllNewInd(master) {
    document.querySelectorAll('.new-ind-check').forEach(cb => cb.checked = master.checked);
}

async function confirmNewIndicators() {
    if (!window._pendingNewIndicators || !window._pendingCompanyId) return;
    const checks = document.querySelectorAll('.new-ind-check');
    const selected = [];
    checks.forEach(cb => {
        if (cb.checked) selected.push(window._pendingNewIndicators[parseInt(cb.dataset.idx)]);
    });
    if (!selected.length) { alert('No indicators selected.'); return; }

    const indicators = selected.map(ind => ({
        name: ind.name,
        current_value: ind.current_value || null,
        bear_threshold: ind.bear_threshold || null,
        bull_threshold: ind.bull_threshold || null,
        check_frequency: ind.check_frequency || 'Monthly',
        data_source: ind.data_source || 'Unknown',
        added_from: ind.added_from || 'scenario_pdf',
    }));

    try {
        const resp = await fetch(`/api/companies/${window._pendingCompanyId}/materials/confirm-new`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ indicators }),
        });
        const data = await resp.json();
        const statusDiv = document.getElementById('materials-status');
        statusDiv.className = 'mt-3 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm text-green-800';
        statusDiv.textContent = data.message;
        document.getElementById('materials-results').classList.add('hidden');
        window._pendingNewIndicators = null;
        loadCompanyDetail(window._pendingCompanyId);
    } catch (err) {
        alert('Failed to confirm indicators: ' + err.message);
    }
}

// ========== Onboarding ==========

let currentStep = 1;
let onboardData = { scenarios: [], indicators: [] };
let createdCompanyId = null;

function initOnboarding() {
    // Pre-populate with Bear/Base/Bull scenarios
    addScenarioRow('Bear');
    addScenarioRow('Base');
    addScenarioRow('Bull');
}

function goToStep(step) {
    currentStep = step;
    for (let i = 1; i <= 5; i++) {
        document.getElementById(`step-${i}`).classList.toggle('hidden', i !== step);
        const btn = document.getElementById(`step-btn-${i}`);
        if (i === step) {
            btn.classList.add('bg-blue-600', 'text-white');
            btn.classList.remove('bg-gray-200', 'text-gray-600');
        } else {
            btn.classList.remove('bg-blue-600', 'text-white');
            btn.classList.add('bg-gray-200', 'text-gray-600');
        }
    }
    if (step === 5) buildReview();
}

function nextStep() { goToStep(Math.min(currentStep + 1, 5)); }
function prevStep() { goToStep(Math.max(currentStep - 1, 1)); }

function addScenarioRow(name = '') {
    const container = document.getElementById('scenarios-container');
    const idx = container.children.length;
    const div = document.createElement('div');
    div.className = 'scenario-row border rounded-lg p-4 mb-3 bg-gray-50';
    div.innerHTML = `
        <div class="flex items-center justify-between mb-2">
            <span class="font-medium text-sm text-gray-700">Scenario ${idx + 1}</span>
            <button onclick="this.closest('.scenario-row').remove()" class="text-red-400 hover:text-red-600 text-sm">Remove</button>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
                <label class="block text-xs text-gray-500 mb-0.5">Name *</label>
                <input type="text" class="sc-name w-full" value="${esc(name)}" placeholder="Bear / Base / Bull / Custom">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-0.5">Raw Weight (%)</label>
                <input type="number" step="0.1" class="sc-raw w-full" placeholder="30">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-0.5">Effective Weight (%)</label>
                <input type="number" step="0.1" class="sc-eff w-full" placeholder="30">
            </div>
            <div>
                <label class="block text-xs text-gray-500 mb-0.5">Implied Price *</label>
                <input type="number" step="0.01" class="sc-price w-full" placeholder="15.88">
            </div>
        </div>
        <div class="mt-2">
            <label class="block text-xs text-gray-500 mb-0.5">Narrative Summary</label>
            <input type="text" class="sc-narrative w-full" placeholder="Brief scenario description...">
        </div>
    `;
    container.appendChild(div);
}

function collectScenarios() {
    const rows = document.querySelectorAll('.scenario-row');
    const scenarios = [];
    let order = 0;
    rows.forEach(row => {
        const name = row.querySelector('.sc-name').value.trim();
        const price = parseFloat(row.querySelector('.sc-price').value);
        if (!name || isNaN(price)) return;
        const rawPct = parseFloat(row.querySelector('.sc-raw').value);
        const effPct = parseFloat(row.querySelector('.sc-eff').value);
        scenarios.push({
            name,
            raw_weight: isNaN(rawPct) ? null : rawPct / 100,
            effective_weight: isNaN(effPct) ? null : effPct / 100,
            implied_price: price,
            narrative_summary: row.querySelector('.sc-narrative').value.trim() || null,
            sort_order: order++,
        });
    });
    return scenarios;
}

// PDF upload
async function handlePdfUpload() {
    const fileInput = document.getElementById('pdf-file');
    const file = fileInput.files[0];
    if (!file) return;

    document.getElementById('upload-status').textContent = `Uploading ${file.name}...`;

    // We need a company ID first — create a temp one or just extract locally
    // For now, show extraction after company is created. Use a placeholder approach:
    // store file for later upload
    onboardData._pdfFile = file;
    document.getElementById('upload-status').textContent = `Selected: ${file.name} (will extract after company is created)`;
    document.getElementById('upload-status').className = 'text-sm text-green-600 mt-2';
}

async function uploadAndExtractPdf(companyId) {
    if (!onboardData._pdfFile) return [];
    const formData = new FormData();
    formData.append('file', onboardData._pdfFile);
    try {
        const resp = await fetch(`/api/companies/${companyId}/upload-scenario-doc`, {
            method: 'POST',
            body: formData,
        });
        const data = await resp.json();
        if (data.indicators && data.indicators.length) {
            showExtractedIndicators(data.indicators);
            return data.indicators;
        }
    } catch (e) {
        console.error('PDF extraction failed:', e);
    }
    return [];
}

function showExtractedIndicators(indicators) {
    const container = document.getElementById('extracted-data');
    const tbody = document.getElementById('extracted-body');
    container.classList.remove('hidden');
    tbody.innerHTML = indicators.map((ind, i) => `
        <tr>
            <td class="px-2 py-1"><input type="checkbox" checked class="ext-include" data-idx="${i}"></td>
            <td class="px-2 py-1"><input type="text" class="ext-name" value="${esc(ind.name || '')}" data-idx="${i}"></td>
            <td class="px-2 py-1"><input type="text" class="ext-current" value="${esc(ind.current_value || '')}" data-idx="${i}"></td>
            <td class="px-2 py-1"><input type="text" class="ext-bear" value="${esc(ind.bear_threshold || '')}" data-idx="${i}"></td>
            <td class="px-2 py-1"><input type="text" class="ext-bull" value="${esc(ind.bull_threshold || '')}" data-idx="${i}"></td>
            <td class="px-2 py-1"><input type="text" class="ext-freq" value="${esc(ind.check_frequency || 'Monthly')}" data-idx="${i}"></td>
            <td class="px-2 py-1"><input type="text" class="ext-source" value="${esc(ind.data_source || '')}" data-idx="${i}"></td>
        </tr>
    `).join('');
    onboardData._extractedIndicators = indicators;
}

function confirmExtracted() {
    if (!onboardData._extractedIndicators) return;
    const rows = document.querySelectorAll('#extracted-body tr');
    rows.forEach((row, i) => {
        const include = row.querySelector('.ext-include').checked;
        if (!include) return;
        const ind = {
            name: row.querySelector('.ext-name').value,
            current_value: row.querySelector('.ext-current').value,
            bear_threshold: row.querySelector('.ext-bear').value,
            bull_threshold: row.querySelector('.ext-bull').value,
            check_frequency: row.querySelector('.ext-freq').value || 'Monthly',
            data_source: row.querySelector('.ext-source').value || 'Unknown',
            added_from: '',
        };
        addIndicatorRowWithData(ind);
    });
    document.getElementById('extracted-data').classList.add('hidden');
    goToStep(4); // jump to indicators step
}

function addIndicatorRow() {
    addIndicatorRowWithData({});
}

function addIndicatorRowWithData(data = {}) {
    const tbody = document.getElementById('indicators-body');
    const tr = document.createElement('tr');
    tr.className = 'indicator-row';
    tr.innerHTML = `
        <td class="px-2 py-1"><input type="text" class="ind-name" value="${esc(data.name || '')}"></td>
        <td class="px-2 py-1"><input type="text" class="ind-current" value="${esc(data.current_value || '')}"></td>
        <td class="px-2 py-1"><input type="text" class="ind-bear" value="${esc(data.bear_threshold || '')}"></td>
        <td class="px-2 py-1"><input type="text" class="ind-bull" value="${esc(data.bull_threshold || '')}"></td>
        <td class="px-2 py-1">
            <select class="ind-freq">
                ${['Daily','Weekly','Monthly','Quarterly','Semiannual','Annual','Once','Pre-earnings','Event'].map(f =>
                    `<option ${f === (data.check_frequency || 'Monthly') ? 'selected' : ''}>${f}</option>`
                ).join('')}
            </select>
        </td>
        <td class="px-2 py-1"><input type="text" class="ind-source" value="${esc(data.data_source || '')}"></td>
        <td class="px-2 py-1"><input type="text" class="ind-added" value="${esc(data.added_from || '')}"></td>
        <td class="px-2 py-1"><button onclick="this.closest('tr').remove()" class="text-red-400 hover:text-red-600">×</button></td>
    `;
    tbody.appendChild(tr);
}

function collectIndicators() {
    const rows = document.querySelectorAll('.indicator-row');
    const indicators = [];
    rows.forEach(row => {
        const name = row.querySelector('.ind-name').value.trim();
        if (!name) return;
        indicators.push({
            name,
            current_value: row.querySelector('.ind-current').value.trim() || null,
            bear_threshold: row.querySelector('.ind-bear').value.trim() || null,
            bull_threshold: row.querySelector('.ind-bull').value.trim() || null,
            check_frequency: row.querySelector('.ind-freq').value,
            data_source: row.querySelector('.ind-source').value.trim() || 'Unknown',
            added_from: row.querySelector('.ind-added').value.trim() || null,
        });
    });
    return indicators;
}

function buildReview() {
    const name = document.getElementById('company-name').value;
    const ticker = document.getElementById('company-ticker').value;
    const exchange = document.getElementById('company-exchange').value;
    const currency = document.getElementById('company-currency').value;
    const rating = document.getElementById('company-rating').value;
    const price = document.getElementById('company-price').value;
    const target = document.getElementById('company-target').value;

    const scenarios = collectScenarios();
    const indicators = collectIndicators();

    let html = `
        <div class="space-y-4">
            <div>
                <h4 class="font-medium text-gray-700 mb-2">Company</h4>
                <p><strong>${esc(name)}</strong> (${esc(ticker)}${exchange ? '.' + esc(exchange) : ''}) · ${esc(currency)}</p>
                <p>Rating: ${esc(rating)} · Price: ${price || '—'} · Target: ${target}</p>
            </div>
            <div>
                <h4 class="font-medium text-gray-700 mb-2">Scenarios (${scenarios.length})</h4>
                ${scenarios.length ? `<table class="w-full text-sm bg-gray-50 rounded">
                    <thead><tr><th class="px-2 py-1 text-left">Name</th><th class="px-2 py-1 text-right">Raw Wt</th><th class="px-2 py-1 text-right">Eff. Wt</th><th class="px-2 py-1 text-right">Price</th></tr></thead>
                    <tbody>${scenarios.map(s => `<tr><td class="px-2 py-1">${esc(s.name)}</td><td class="px-2 py-1 text-right">${s.raw_weight != null ? (s.raw_weight*100).toFixed(1)+'%' : '—'}</td><td class="px-2 py-1 text-right">${s.effective_weight != null ? (s.effective_weight*100).toFixed(1)+'%' : '—'}</td><td class="px-2 py-1 text-right">${formatNum(s.implied_price)}</td></tr>`).join('')}</tbody>
                </table>` : '<p class="text-gray-400">No scenarios.</p>'}
            </div>
            <div>
                <h4 class="font-medium text-gray-700 mb-2">Indicators (${indicators.length})</h4>
                ${indicators.length ? `<table class="w-full text-sm bg-gray-50 rounded">
                    <thead><tr><th class="px-2 py-1 text-left">Name</th><th class="px-2 py-1">Current</th><th class="px-2 py-1">Bear</th><th class="px-2 py-1">Bull</th><th class="px-2 py-1">Freq</th></tr></thead>
                    <tbody>${indicators.map(ind => `<tr><td class="px-2 py-1">${esc(ind.name)}</td><td class="px-2 py-1">${esc(ind.current_value||'—')}</td><td class="px-2 py-1">${esc(ind.bear_threshold||'—')}</td><td class="px-2 py-1">${esc(ind.bull_threshold||'—')}</td><td class="px-2 py-1">${esc(ind.check_frequency)}</td></tr>`).join('')}</tbody>
                </table>` : '<p class="text-gray-400">No indicators.</p>'}
            </div>
        </div>
    `;
    document.getElementById('review-content').innerHTML = html;
}

async function submitOnboarding() {
    const btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const errorDiv = document.getElementById('save-error');
    errorDiv.classList.add('hidden');

    try {
        // 1. Create company
        const companyPayload = {
            name: document.getElementById('company-name').value.trim(),
            ticker: document.getElementById('company-ticker').value.trim(),
            exchange: document.getElementById('company-exchange').value.trim() || null,
            currency: document.getElementById('company-currency').value,
            current_rating: document.getElementById('company-rating').value,
            current_price: parseFloat(document.getElementById('company-price').value) || null,
            blended_price_target: parseFloat(document.getElementById('company-target').value),
            notes: document.getElementById('company-notes').value.trim() || null,
        };

        if (!companyPayload.name || !companyPayload.ticker || !companyPayload.blended_price_target) {
            throw new Error('Name, ticker, and blended price target are required.');
        }

        const compResp = await fetch('/api/companies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(companyPayload),
        });
        if (!compResp.ok) throw new Error('Failed to create company');
        const compData = await compResp.json();
        createdCompanyId = compData.id;

        // 2. Upload PDF if present
        if (onboardData._pdfFile) {
            await uploadAndExtractPdf(createdCompanyId);
        }

        // 3. Create scenarios
        const scenarios = collectScenarios();
        for (const sc of scenarios) {
            await fetch(`/api/companies/${createdCompanyId}/scenarios`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(sc),
            });
        }

        // 4. Create indicators
        const indicators = collectIndicators();
        for (const ind of indicators) {
            await fetch(`/api/companies/${createdCompanyId}/indicators`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(ind),
            });
        }

        // Success — redirect to company page
        window.location.href = `/company/${createdCompanyId}`;
    } catch (e) {
        errorDiv.textContent = e.message;
        errorDiv.classList.remove('hidden');
        btn.disabled = false;
        btn.textContent = 'Save Company';
    }
}

// ========== Utilities ==========

function esc(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function formatNum(n) {
    if (n == null) return '—';
    if (Math.abs(n) >= 1000) return Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    return Number(n).toFixed(2);
}
