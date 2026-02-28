/* ═══════════════════════════════════════════════════════════════
   RootWatch  —  Main App JS
   ═══════════════════════════════════════════════════════════════ */

/* ── Constants ────────────────────────────────────────────────── */
const SC_FIPS = {
  'Abbeville':45001,'Aiken':45003,'Allendale':45005,'Anderson':45007,
  'Bamberg':45009,'Barnwell':45011,'Beaufort':45013,'Berkeley':45015,
  'Calhoun':45017,'Charleston':45019,'Cherokee':45021,'Chester':45023,
  'Chesterfield':45025,'Clarendon':45027,'Colleton':45029,'Darlington':45031,
  'Dillon':45033,'Dorchester':45035,'Edgefield':45037,'Fairfield':45039,
  'Florence':45041,'Georgetown':45043,'Greenville':45045,'Greenwood':45047,
  'Hampton':45049,'Horry':45051,'Jasper':45053,'Kershaw':45055,
  'Lancaster':45057,'Laurens':45059,'Lee':45061,'Lexington':45063,
  'McCormick':45065,'Marion':45067,'Marlboro':45069,'Newberry':45071,
  'Oconee':45073,'Orangeburg':45075,'Pickens':45077,'Richland':45079,
  'Saluda':45081,'Spartanburg':45083,'Sumter':45085,'Union':45087,
  'Williamsburg':45089,'York':45091
};

/* ── Tab switching ────────────────────────────────────────────── */
function switchTab(name) {
  document.querySelectorAll('.nav-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === name)
  );
  document.querySelectorAll('.tab-section').forEach(s =>
    s.classList.toggle('active', s.id === 'tab-' + name)
  );
  if (name === 'analytics') setTimeout(renderChart, 80);
  if (name === 'map' && !mapInitialized) initMap();
}

document.querySelectorAll('.nav-tab').forEach(btn =>
  btn.addEventListener('click', () => switchTab(btn.dataset.tab))
);

/* ── Scroll reveal ────────────────────────────────────────────── */
const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      revealObserver.unobserve(e.target);
    }
  });
}, { threshold: 0.12 });

function attachReveal() {
  document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));
}
attachReveal();

/* ── Animated counters (home stats) ──────────────────────────── */
function animateCounter(id, target, prefix = '', suffix = '', duration = 1800) {
  const el = document.getElementById(id);
  if (!el) return;
  const start = performance.now();
  function step(now) {
    const progress = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - progress, 3);
    const val = Math.round(ease * target);
    el.textContent = prefix + val.toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// Trigger on home tab
const homeObserver = new IntersectionObserver(entries => {
  if (entries[0].isIntersecting) {
    animateCounter('stat-dcs',     TOTAL_DC,       '', '');
    animateCounter('stat-counties', WITH_DC_COUNT, '', '');
    animateCounter('stat-diff',    AVG_WITH - AVG_WITHOUT, '', '');
    animateCounter('stat-year',    (AVG_WITH - AVG_WITHOUT) * 12, '$', '');
    homeObserver.disconnect();
  }
}, { threshold: 0.3 });

const statsStrip = document.querySelector('.stats-strip');
if (statsStrip) homeObserver.observe(statsStrip);

/* ── Live money ticker ────────────────────────────────────────── */
// Estimate: 46 counties, avg overcharge $28/mo, ~50k affected households
const AFFECTED_HH    = 120000;
const MONTHLY_OVERCHARGE = (AVG_WITH - AVG_WITHOUT);
const YEARLY_LOSS    = AFFECTED_HH * MONTHLY_OVERCHARGE * 12;
const START_TIME     = Date.now();
const START_OF_YEAR  = new Date(new Date().getFullYear(), 0, 1).getTime();

function updateTicker() {
  const elapsed = (Date.now() - START_OF_YEAR) / 1000;
  const lost = Math.floor(YEARLY_LOSS * (elapsed / (365.25 * 24 * 3600)));
  const tickerEl = document.getElementById('ticker-val');
  if (tickerEl) tickerEl.textContent = lost.toLocaleString();
}
updateTicker();
setInterval(updateTicker, 1000);

/* ── Sound ────────────────────────────────────────────────────── */
let audioCtx = null;
let ambientNode = null;
let soundOn = false;

function toggleSound() {
  soundOn = !soundOn;
  document.getElementById('sound-toggle').textContent = soundOn ? '🔊' : '🔇';
  if (soundOn) {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    startAmbient();
  } else {
    stopAmbient();
  }
}

function startAmbient() {
  if (!audioCtx || ambientNode) return;
  // Gentle wind: layered oscillators at low freq
  ambientNode = audioCtx.createGain();
  ambientNode.gain.setValueAtTime(0.04, audioCtx.currentTime);
  ambientNode.connect(audioCtx.destination);
  [60, 90, 120].forEach((freq, i) => {
    const osc = audioCtx.createOscillator();
    osc.frequency.value = freq;
    osc.type = 'sine';
    const g = audioCtx.createGain();
    g.gain.value = 0.015;
    osc.connect(g);
    g.connect(ambientNode);
    osc.start();
  });
}

function stopAmbient() {
  if (ambientNode) { ambientNode.gain.setValueAtTime(0, audioCtx.currentTime); ambientNode = null; }
}

function playCaChingSound() {
  if (!soundOn || !audioCtx) return;
  const now = audioCtx.currentTime;
  const freqs = [880, 1100, 1320];
  freqs.forEach((freq, i) => {
    const osc  = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.type = 'triangle';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.18, now + i * 0.1);
    gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.1 + 0.4);
    osc.start(now + i * 0.1);
    osc.stop(now + i * 0.1 + 0.5);
  });
}

/* ── Leaflet Map + Timeline ───────────────────────────────────── */
let mapInitialized  = false;
let leafletMap      = null;
let geojsonLayer    = null;   // the choropleth layer (replaced on redraw)
let fipsLookup      = {};     // FIPS → county row from COUNTY_DATA
let timelineData    = null;   // fetched from /api/timeline
let timelineYears   = [2002, 2007, 2012, 2017, 2022];
let activeYearIdx   = 4;      // 0-based index into timelineYears  (default: 2022)
let mapMode         = 'dc';   // 'dc' | 'farmland'

// ── Color scales ──────────────────────────────────────────────────
function countyColorDC(dcCount) {
  if (dcCount >= 5) return '#c1121f';
  if (dcCount >= 3) return '#e07b39';
  if (dcCount >= 1) return '#f4c430';
  return '#52b788';
}

// Farmland loss as % relative to 2002 baseline → red = more loss
function countyColorFarm(county, year) {
  if (!timelineData) return '#ccc';
  const row = timelineData.counties[county];
  if (!row || !row.farmland) return '#ccc';
  const base = row.farmland['2002'];
  const cur  = row.farmland[String(year)];
  if (!base || !cur) return '#aaa';
  const pct = (base - cur) / base;   // 0 = no loss, 1 = total loss
  if (pct >= 0.30) return '#7f0000';
  if (pct >= 0.20) return '#c1121f';
  if (pct >= 0.10) return '#e07b39';
  if (pct >= 0.02) return '#f4c430';
  return '#52b788';   // farmland roughly stable
}

function getCountyColor(countyName, yearStr, dcCount) {
  if (mapMode === 'farmland') return countyColorFarm(countyName, yearStr);
  return countyColorDC(dcCount);
}

// ── Year-slider helpers ────────────────────────────────────────────
function onYearSlide(val) {
  activeYearIdx = parseInt(val);
  const year = timelineYears[activeYearIdx];
  document.getElementById('tl-year-label').textContent = year;
  updateLegend();
  if (timelineData) applyTimelineToMap();
}

function setMapMode(mode) {
  mapMode = mode;
  document.getElementById('mode-btn-dc').classList.toggle('active',   mode === 'dc');
  document.getElementById('mode-btn-farm').classList.toggle('active', mode === 'farmland');
  updateLegend();
  if (geojsonLayer) applyTimelineToMap();
}

function updateLegend() {
  const el = document.getElementById('map-legend');
  if (!el) return;
  if (mapMode === 'farmland') {
    el.innerHTML = `
      <div class="mleg-item"><span class="mleg-dot" style="background:#7f0000"></span> &gt;30% farmland lost</div>
      <div class="mleg-item"><span class="mleg-dot" style="background:#c1121f"></span> 20–30% farmland lost</div>
      <div class="mleg-item"><span class="mleg-dot" style="background:#e07b39"></span> 10–20% farmland lost</div>
      <div class="mleg-item"><span class="mleg-dot" style="background:#f4c430"></span> 2–10% farmland lost</div>
      <div class="mleg-item"><span class="mleg-dot" style="background:#52b788"></span> Stable farmland</div>`;
  } else {
    el.innerHTML = `
      <div class="mleg-item"><span class="mleg-dot" style="background:#c1121f"></span> High (5+ DCs)</div>
      <div class="mleg-item"><span class="mleg-dot" style="background:#e07b39"></span> Medium (3–4 DCs)</div>
      <div class="mleg-item"><span class="mleg-dot" style="background:#f4c430"></span> Low (1–2 DCs)</div>
      <div class="mleg-item"><span class="mleg-dot" style="background:#52b788"></span> No Data Centers</div>`;
  }
}

// Recolor every polygon in the existing layer without re-fetching GeoJSON
function applyTimelineToMap() {
  if (!geojsonLayer || !timelineData) return;
  const year = timelineYears[activeYearIdx];
  const yearStr = String(year);

  // Update header stats
  let totalDC = 0, totalFarm = 0, farmCount = 0;
  Object.entries(timelineData.counties).forEach(([name, row]) => {
    totalDC += parseInt(row.dc_count[yearStr] || 0);
    const f = row.farmland[yearStr];
    if (f) { totalFarm += f; farmCount++; }
  });
  document.getElementById('tl-dc-total').innerHTML  = `🏭 <strong>${totalDC}</strong> Data Centers`;
  document.getElementById('tl-farm-total').innerHTML = `🌾 <strong>${totalFarm.toLocaleString()}</strong> acres farmland`;

  // Recolor each layer feature
  geojsonLayer.eachLayer(layer => {
    const fips = String(layer.feature.id || '').padStart(5,'0');
    const cd   = fipsLookup[fips];
    if (!cd) return;
    const row     = timelineData.counties[cd.county];
    const dcCount = parseInt((row && row.dc_count[yearStr]) || 0);
    const color   = getCountyColor(cd.county, yearStr, dcCount);
    layer.setStyle({ fillColor: color, fillOpacity: 0.76, color: '#fff', weight: 1.5 });

    // Update tooltip
    const farmAcres = (row && row.farmland[yearStr]) ? row.farmland[yearStr].toLocaleString() + ' ac' : 'N/A';
    layer.setTooltipContent(
      `<strong>${cd.county} County — ${year}</strong><br>🏭 ${dcCount} DC(s)<br>🌾 ${farmAcres}`
    );
  });
}

// ── Map init ──────────────────────────────────────────────────────
function initMap() {
  if (mapInitialized) return;
  mapInitialized = true;

  leafletMap = L.map('sc-map', { zoomControl: true, scrollWheelZoom: false });

  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap contributors, © CARTO',
    maxZoom: 13
  }).addTo(leafletMap);

  // FIPS lookup
  COUNTY_DATA.forEach(c => {
    const fips = SC_FIPS[c.county];
    if (fips) fipsLookup[String(fips).padStart(5,'0')] = c;
  });

  // Fetch GeoJSON + timeline data in parallel
  Promise.all([
    fetch('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json').then(r => r.json()),
    fetch('/api/timeline').then(r => r.json()).catch(() => null)
  ]).then(([geojson, tlData]) => {
    if (tlData) {
      timelineData  = tlData;
      timelineYears = tlData.years || timelineYears;
      // Sync slider max to number of years available
      const slider = document.getElementById('year-slider');
      if (slider) { slider.max = timelineYears.length - 1; slider.value = timelineYears.length - 1; }
      activeYearIdx = timelineYears.length - 1;
      document.getElementById('tl-year-label').textContent = timelineYears[activeYearIdx];
    }

    const scFeatures = geojson.features.filter(f =>
      String(f.id).startsWith('45') || String(f.properties.STATE || '').startsWith('45')
    );
    const yearStr = String(timelineYears[activeYearIdx]);

    geojsonLayer = L.geoJSON({ type: 'FeatureCollection', features: scFeatures }, {
      style: feature => {
        const fips = String(feature.id || '').padStart(5,'0');
        const cd   = fipsLookup[fips];
        if (!cd) return { fillColor: '#ccc', fillOpacity: 0.5, color: '#fff', weight: 1 };
        const row     = timelineData && timelineData.counties[cd.county];
        const dcCount = parseInt((row && row.dc_count[yearStr]) || cd.dc_count || 0);
        return {
          fillColor:   getCountyColor(cd.county, yearStr, dcCount),
          fillOpacity: 0.76,
          color:       '#fff',
          weight:      1.5
        };
      },
      onEachFeature: (feature, lyr) => {
        const fips = String(feature.id || '').padStart(5,'0');
        const cd   = fipsLookup[fips];
        if (!cd) return;
        const row       = timelineData && timelineData.counties[cd.county];
        const dcCount   = parseInt((row && row.dc_count[yearStr]) || cd.dc_count || 0);
        const farmAcres = (row && row.farmland[yearStr]) ? row.farmland[yearStr].toLocaleString() + ' ac' : 'N/A';
        lyr.bindTooltip(
          `<strong>${cd.county} County — ${timelineYears[activeYearIdx]}</strong><br>🏭 ${dcCount} DC(s)<br>🌾 ${farmAcres}`,
          { className: 'map-tooltip', sticky: true }
        );
        lyr.on({
          mouseover: e => e.target.setStyle({ fillOpacity: 0.95, weight: 2.5 }),
          mouseout:  e => geojsonLayer.resetStyle(e.target),
          click:     () => showMapCounty(cd)
        });
      }
    }).addTo(leafletMap);

    leafletMap.fitBounds(geojsonLayer.getBounds(), { padding: [10, 10] });

    // Prime the summary stats
    if (timelineData) applyTimelineToMap();
  }).catch(() => {
    document.getElementById('sc-map').innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:.9rem;padding:2rem;text-align:center">Could not load map data. Check your connection.</div>';
  });
}

function showMapCounty(cd) {
  const panel   = document.getElementById('map-county-panel');
  const year    = timelineYears[activeYearIdx];
  const yearStr = String(year);
  const row     = timelineData && timelineData.counties[cd.county];
  const dcNow   = parseInt((row && row.dc_count[yearStr]) || cd.dc_count || 0);
  const dc2002  = parseInt((row && row.dc_count['2002']) || 0);
  const farm2002 = (row && row.farmland['2002']) || null;
  const farmNow  = (row && row.farmland[yearStr]) || null;
  const farmLoss = (farm2002 && farmNow) ? Math.round(farm2002 - farmNow) : null;
  const farmLossPct = (farm2002 && farmNow) ? ((farm2002 - farmNow) / farm2002 * 100).toFixed(1) : null;

  const tier      = dcNow >= 5 ? 'high' : dcNow > 0 ? 'med' : 'none';
  const tierLabel = dcNow >= 5 ? '🔴 High Impact' : dcNow > 0 ? '🟠 Medium Impact' : '🟢 No Data Centers';

  const diff    = cd.avg_monthly_cost - AVG_WITHOUT;
  const diffStr = diff > 0 ? `+$${diff}` : `$${Math.abs(diff)} below`;

  const adjHtml = cd.adjacent.map(a => {
    const adj = COUNTY_DATA.find(x => x.county === a);
    const hasDC = adj && adj.dc_count > 0;
    return `<span class="mcp-adj-tag${hasDC?' has-dc':''}">${a}${hasDC?' ('+adj.dc_count+'DC)':''}</span>`;
  }).join('');

  panel.innerHTML = `
    <div class="mcp-county-name">${cd.county} County <small style="font-weight:400;font-size:.75rem;color:#888">${year}</small></div>
    <span class="mcp-tier-badge ${tier}">${tierLabel}</span>
    <div class="mcp-grid">
      <div class="mcp-item"><div class="mcp-label">Data Centers (${year})</div><div class="mcp-val">${dcNow}</div></div>
      <div class="mcp-item"><div class="mcp-label">DCs in 2002</div><div class="mcp-val">${dc2002}</div></div>
      <div class="mcp-item"><div class="mcp-label">Monthly Cost</div><div class="mcp-val">$${cd.avg_monthly_cost}</div></div>
      <div class="mcp-item"><div class="mcp-label">vs. SC Avg (no DC)</div><div class="mcp-val" style="color:${diff>0?'#c1121f':'#2d6a4f'}">${diffStr}/mo</div></div>
      ${farmNow ? `<div class="mcp-item"><div class="mcp-label">Farmland (${year})</div><div class="mcp-val">${farmNow.toLocaleString()} ac</div></div>` : ''}
      ${farmLoss !== null ? `<div class="mcp-item"><div class="mcp-label">Farmland Lost</div><div class="mcp-val" style="color:#c1121f">-${farmLoss.toLocaleString()} ac (${farmLossPct}%)</div></div>` : ''}
    </div>
    <div class="mcp-adj-label">Adjacent Counties</div>
    <div class="mcp-adj-tags">${adjHtml}</div>
  `;
}

/* ── Farm Calculator ──────────────────────────────────────────── */
function runCalculator() {
  const countyEl  = document.getElementById('calc-county');
  const kwhEl     = document.getElementById('calc-kwh');
  const billEl    = document.getElementById('calc-bill');

  const countyName = countyEl.value;
  if (!countyName) { countyEl.focus(); return; }

  const cd = COUNTY_DATA.find(c => c.county === countyName);
  if (!cd) return;

  const kwh  = parseFloat(kwhEl.value)  || 0;
  const bill = parseFloat(billEl.value) || cd.avg_monthly_cost;

  const rateYour = cd.avg_monthly_cost / 1100; // $/kWh estimate
  const rateBase = AVG_WITHOUT / 1100;
  const kwhUsed  = kwh || 1100;

  const monthlyOvercharge = Math.max(0, Math.round(bill - AVG_WITHOUT));
  const annual  = monthlyOvercharge * 12;
  const decade  = annual * 10;

  const result = document.getElementById('calc-result');
  result.classList.remove('hidden');

  document.getElementById('calc-county-name').textContent = countyName + ' County';

  // Animate numbers
  animateCounter('calc-monthly', monthlyOvercharge, '$', '/mo');
  animateCounter('calc-annual',  annual,  '$', '/yr');
  animateCounter('calc-decade',  decade,  '$', '/10yr');

  // Cost comparison bars
  const maxCost = 250;
  const yourPct = Math.min(100, Math.round(cd.avg_monthly_cost / maxCost * 100));
  const basePct = Math.min(100, Math.round(AVG_WITHOUT / maxCost * 100));
  document.getElementById('bar-your').style.width = yourPct + '%';
  document.getElementById('bar-your-amt').textContent = '$' + cd.avg_monthly_cost + '/mo';
  const firstBarLabel = document.querySelector('.calc-bar-label');
  if (firstBarLabel) firstBarLabel.textContent = `${countyName} avg $${cd.avg_monthly_cost}`;

  // Context message
  const ctxEl = document.getElementById('calc-context');
  if (cd.dc_count === 0) {
    ctxEl.textContent = `${countyName} has no data centers, and your bill reflects a near-baseline rate. Be aware — adjacent counties with DCs may still influence grid costs.`;
  } else {
    const farmImpact = annual > 0 ? `That's $${annual} per year — enough to buy ${Math.round(annual/15)} bushels of seed corn.` : '';
    ctxEl.textContent = `${countyName} has ${cd.dc_count} data center(s). Residents pay ~$${monthlyOvercharge} more per month than counties with no DCs. ${farmImpact}`;
  }

  playCaChingSound();
  result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Allow "Enter" key in calculator inputs
['calc-county','calc-kwh','calc-bill'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') runCalculator(); });
});

/* ── Analytics Chart ──────────────────────────────────────────── */
let chartInstance = null;

function renderChart() {
  const sortBy = document.getElementById('chart-sort').value;
  const filter = document.getElementById('chart-filter').value;

  let data = [...COUNTY_DATA];
  if      (filter === 'with')    data = data.filter(c => c.dc_count > 0);
  else if (filter === 'without') data = data.filter(c => c.dc_count === 0);

  if      (sortBy === 'cost') data.sort((a,b) => b.avg_monthly_cost - a.avg_monthly_cost);
  else if (sortBy === 'dc')   data.sort((a,b) => b.dc_count - a.dc_count);
  else                         data.sort((a,b) => a.county.localeCompare(b.county));

  const labels = data.map(c => c.county);
  const costs  = data.map(c => c.avg_monthly_cost);
  const colors = data.map(c =>
    c.dc_count >= 5 ? 'rgba(193,18,31,.8)' :
    c.dc_count > 0  ? 'rgba(224,123,57,.8)' :
                      'rgba(82,183,136,.8)'
  );

  const ctx = document.getElementById('costChart').getContext('2d');
  if (chartInstance) chartInstance.destroy();
  chartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Avg Monthly Cost ($)',
        data: costs,
        backgroundColor: colors,
        borderRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: ctx => ctx[0].label + ' County',
            afterLabel: ctx => {
              const c = data[ctx.dataIndex];
              return `Data Centers: ${c.dc_count}\nVs. no-DC avg: ${c.avg_monthly_cost > AVG_WITHOUT ? '+' : ''}$${c.avg_monthly_cost - AVG_WITHOUT}/mo`;
            }
          }
        }
      },
      scales: {
        x: { ticks: { maxRotation: 55, font: { size: 9 } } },
        y: {
          beginAtZero: false,
          min: 90,
          ticks: { callback: v => '$' + v },
          grid: { color: 'rgba(0,0,0,.05)' }
        }
      }
    }
  });
}

/* ── Petition ─────────────────────────────────────────────────── */
let sigCount = 1243;

document.getElementById('petition-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true; btn.textContent = 'Submitting…';

  const body = {
    name:   document.getElementById('p-name').value.trim(),
    email:  document.getElementById('p-email').value.trim(),
    county: document.getElementById('p-county').value,
  };

  try {
    const res  = await fetch('/api/petition', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await res.json();
    const msg  = document.getElementById('petition-msg');
    msg.classList.remove('hidden','error','success');
    if (data.ok) {
      msg.classList.add('success');
      msg.textContent = '🎉 ' + data.message;
      sigCount++;
      document.getElementById('sig-count').textContent = sigCount.toLocaleString();
      const prog = document.getElementById('prog-bar');
      if (prog) prog.style.width = Math.min(100, Math.round(sigCount / 2000 * 100)) + '%';
      e.target.reset();
      playCaChingSound();
    } else {
      msg.classList.add('error');
      msg.textContent = '❌ ' + (data.error || 'Something went wrong.');
    }
  } catch {
    const msg = document.getElementById('petition-msg');
    msg.classList.remove('hidden'); msg.classList.add('error');
    msg.textContent = '❌ Network error. Please try again.';
  } finally {
    btn.disabled = false; btn.textContent = '✅ Add My Name';
  }
});

/* ── Action helpers ───────────────────────────────────────────── */
function copyEmailTemplate() {
  const tpl = `Subject: Support Energy Cost Accountability for SC Residents\n\nDear Representative,\n\nAs a South Carolina resident, I am writing to urge you to support legislation requiring large-scale data centers to be transparent about their electricity consumption and its impact on residential utility rates.\n\nData centers in our area pay significantly lower rates while residents pay up to $${AVG_WITH - AVG_WITHOUT}/month more on average. This disparity is unjust and demands urgent reform.\n\nPlease support fair rate structures and transparent reporting for all large-scale electricity consumers.\n\nSincerely,\n[Your Name], [Your County] County, SC`;
  navigator.clipboard.writeText(tpl).then(() => {
    const toast = document.getElementById('email-copied');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 2800);
  });
}

function shareTwitter() {
  const text = encodeURIComponent(`SC data centers raise electricity bills by $${AVG_WITH - AVG_WITHOUT}/month for farmers and families. See which counties are hit hardest. #RootWatch #SouthCarolina`);
  window.open('https://twitter.com/intent/tweet?text=' + text, '_blank');
}
function shareFacebook() {
  window.open('https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(window.location.href), '_blank');
}

/* ── Chatbot ──────────────────────────────────────────────────── */
const chatMessages = document.getElementById('chat-messages');

function appendMsg(text, role) {
  const div = document.createElement('div');
  div.className = 'chat-msg ' + role;
  div.innerHTML = `<div class="msg-bubble">${text}</div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

async function sendMessage(text) {
  if (!text.trim()) return;
  appendMsg(text, 'user');
  const suggs = chatMessages.querySelector('.chat-suggestions');
  if (suggs) suggs.remove();
  const typing = appendMsg('Thinking…', 'bot typing');
  try {
    const res  = await fetch('/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ message: text }) });
    const data = await res.json();
    typing.remove();
    appendMsg(data.reply, 'bot');
  } catch {
    typing.remove();
    appendMsg('Sorry, something went wrong. Please try again.', 'bot');
  }
}

document.getElementById('chat-form').addEventListener('submit', e => {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  input.value = '';
  if (text) sendMessage(text);
});

function sendSuggestion(btn) { sendMessage(btn.textContent); }

/* ── Navbar shrink on scroll ──────────────────────────────────── */
window.addEventListener('scroll', () => {
  document.getElementById('navbar').style.boxShadow =
    window.scrollY > 10 ? '0 3px 20px rgba(0,0,0,.35)' : '0 2px 12px rgba(0,0,0,.3)';
}, { passive: true });