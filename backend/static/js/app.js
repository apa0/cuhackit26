/* ── Tab navigation ──────────────────────────────────────── */
function switchTab(name) {
  document.querySelectorAll('.nav-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === name);
  });
  document.querySelectorAll('.tab-section').forEach(s => {
    s.classList.toggle('active', s.id === 'tab-' + name);
  });
  if (name === 'analytics') renderChart();
}

document.querySelectorAll('.nav-tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

/* ── County map detail panel ────────────────────────────── */
function showCountyDetail(name, dcs, cost, adjacent) {
  const panel = document.getElementById('county-detail');
  document.getElementById('detail-name').textContent = name + ' County';
  document.getElementById('detail-dcs').textContent  = dcs;
  document.getElementById('detail-cost').textContent = '$' + cost + '/mo';

  const adjContainer = document.getElementById('detail-adj');
  adjContainer.innerHTML = '';
  adjacent.forEach(adj => {
    const countyData = COUNTY_DATA.find(c => c.county === adj);
    const hasDC = countyData && countyData.dc_count > 0;
    const tag = document.createElement('span');
    tag.className = 'adj-tag' + (hasDC ? ' has-dc' : '');
    tag.textContent = adj + (hasDC ? ` (${countyData.dc_count} DC)` : '');
    adjContainer.appendChild(tag);
  });

  panel.classList.remove('hidden');
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeDetail() {
  document.getElementById('county-detail').classList.add('hidden');
}

/* ── Chart ───────────────────────────────────────────────── */
let chartInstance = null;

function renderChart() {
  const sortBy  = document.getElementById('chart-sort').value;
  const filter  = document.getElementById('chart-filter').value;

  let data = [...COUNTY_DATA];

  if      (filter === 'with')    data = data.filter(c => c.dc_count > 0);
  else if (filter === 'without') data = data.filter(c => c.dc_count === 0);

  if      (sortBy === 'cost') data.sort((a, b) => b.avg_monthly_cost - a.avg_monthly_cost);
  else if (sortBy === 'dc')   data.sort((a, b) => b.dc_count - a.dc_count);
  else                         data.sort((a, b) => a.county.localeCompare(b.county));

  const labels = data.map(c => c.county);
  const costs  = data.map(c => c.avg_monthly_cost);
  const colors = data.map(c => {
    if (c.dc_count >= 5) return 'rgba(193,18,31,.8)';
    if (c.dc_count > 0)  return 'rgba(224,123,57,.8)';
    return 'rgba(82,183,136,.8)';
  });

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
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              const c = data[ctx.dataIndex];
              return `Data Centers: ${c.dc_count}`;
            }
          }
        }
      },
      scales: {
        x: { ticks: { maxRotation: 60, font: { size: 10 } } },
        y: {
          beginAtZero: false,
          min: 90,
          ticks: { callback: v => '$' + v }
        }
      }
    }
  });
}

/* ── Petition form ───────────────────────────────────────── */
let sigCount = 1243;

document.getElementById('petition-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = 'Submitting…';

  const body = {
    name:   document.getElementById('p-name').value.trim(),
    email:  document.getElementById('p-email').value.trim(),
    county: document.getElementById('p-county').value,
  };

  try {
    const res  = await fetch('/api/petition', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json();
    const msg  = document.getElementById('petition-msg');
    msg.classList.remove('hidden', 'error', 'success');
    if (data.ok) {
      msg.classList.add('success');
      msg.textContent = '🎉 ' + data.message;
      sigCount++;
      document.getElementById('sig-count').textContent = sigCount.toLocaleString();
      e.target.reset();
    } else {
      msg.classList.add('error');
      msg.textContent = '❌ ' + (data.error || 'Something went wrong.');
    }
  } catch {
    const msg = document.getElementById('petition-msg');
    msg.classList.remove('hidden');
    msg.classList.add('error');
    msg.textContent = '❌ Network error. Please try again.';
  } finally {
    btn.disabled = false;
    btn.textContent = '✅ Sign the Petition';
  }
});

/* ── Action — email template ────────────────────────────── */
function copyEmailTemplate() {
  const template = `Subject: Support Energy Cost Accountability for SC Residents\n\nDear Representative,\n\nI am writing to urge you to support legislation requiring large-scale data centers to be transparent about their electricity consumption and its impact on residential utility rates.\n\nData centers in South Carolina counties pay significantly lower rates while residents in those counties pay up to $47/month more on average. This disparity is unjust and demands urgent reform.\n\nPlease support fair rate structures and transparent reporting for all large-scale electricity consumers.\n\nSincerely,\n[Your Name]\n[Your County], SC`;
  navigator.clipboard.writeText(template).then(() => {
    const toast = document.getElementById('email-copied');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 2500);
  });
}

function shareTwitter() {
  const text = encodeURIComponent('SC data centers are raising our electric bills by $47/month. See which counties are most affected and take action. #RootWatch #SouthCarolina');
  window.open('https://twitter.com/intent/tweet?text=' + text, '_blank');
}

function shareFacebook() {
  window.open('https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(window.location.href), '_blank');
}

/* ── Chatbot ─────────────────────────────────────────────── */
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

  // Remove suggestion buttons after first message
  const suggs = chatMessages.querySelector('.chat-suggestions');
  if (suggs) suggs.remove();

  const typing = appendMsg('…', 'bot typing');

  try {
    const res  = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }) });
    const data = await res.json();
    typing.remove();
    appendMsg(data.reply, 'bot');
  } catch {
    typing.remove();
    appendMsg('Sorry, something went wrong. Please try again.', 'bot');
  }
}

document.getElementById('chat-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  input.value = '';
  sendMessage(text);
});

function sendSuggestion(btn) {
  sendMessage(btn.textContent);
}
