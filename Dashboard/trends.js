const CATEGORY_COLORS = {
  productiveOutput: "var(--po)",
  hard: "var(--hard)",
  soft: "var(--soft)",
  spiritual: "var(--spiritual)",
  physical: "var(--physical)",
  drift: "var(--drift)",
  sleep: "var(--sleep)",
  unscored: "var(--unscored)"
};

const LABELS = {
  productiveOutput: "PO",
  hard: "Hard",
  soft: "Soft",
  spiritual: "Meditate",
  physical: "Gym",
  drift: "Entertainment",
  sleep: "Sleep",
  unscored: "Unscored"
};

const trendKeys = ["hard", "soft", "spiritual", "physical", "drift", "sleep", "unscored"];
const enabled = new Set(trendKeys);
let currentPayload;

function fmt(value) {
  return Number(value || 0).toFixed(Number(value || 0) % 1 === 0 ? 0 : 1);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function parseDateOnly(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  return new Date(year, month - 1, day);
}

function inclusiveDays(start, end) {
  if (!start || !end) return 1;
  const startDate = parseDateOnly(start);
  const endDate = parseDateOnly(end);
  const days = Math.round((endDate - startDate) / 86400000) + 1;
  return Number.isFinite(days) && days > 0 ? days : 1;
}

function periodCapacity(row, type) {
  if (type === "day") return 24;
  return inclusiveDays(row.start, row.end) * 24;
}

function visibleKeys() {
  return trendKeys.filter((key) => enabled.has(key));
}

function trendTotals(row, type) {
  const capacity = periodCapacity(row, type);
  const totals = { ...row.totals };
  const fixedHours = trendKeys
    .filter((key) => key !== "unscored")
    .reduce((sum, key) => sum + Number(totals[key] || 0), 0);
  const rawUnscored = Number(totals.unscored || 0);
  totals.unscored = Math.max(0, capacity - fixedHours);
  totals._rawUnscored = rawUnscored;
  totals._unscoredAdjustment = totals.unscored - rawUnscored;
  totals._overflow = Math.max(0, fixedHours - capacity);
  return totals;
}

function totalHours(row, keys, type) {
  const totals = trendTotals(row, type);
  const shown = keys.reduce((sum, key) => sum + Number(totals[key] || 0), 0);
  return Math.min(periodCapacity(row, type), shown);
}

function segmentTitle(key, hours, totals) {
  if (key !== "unscored" || Math.abs(Number(totals._unscoredAdjustment || 0)) < 0.01) {
    return `${LABELS[key]}: ${fmt(hours)}h`;
  }
  const raw = Number(totals._rawUnscored || 0);
  const direction = totals._unscoredAdjustment > 0 ? "+" : "";
  return `${LABELS[key]}: ${fmt(hours)}h (${direction}${fmt(totals._unscoredAdjustment)}h capacity balance from ${fmt(raw)}h raw)`;
}

function percentChange(current, previous) {
  if (previous <= 0.01 && current <= 0.01) return "0%";
  if (previous <= 0.01) return "+100%";
  const change = ((current - previous) / previous) * 100;
  const digits = Math.abs(change) >= 10 ? 0 : 1;
  return `${change > 0 ? "+" : ""}${change.toFixed(digits)}%`;
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

let staticDataCache;

async function getTrendData(type) {
  try {
    return await getJson(`/api/trends?type=${encodeURIComponent(type)}`);
  } catch {
    if (!staticDataCache) staticDataCache = await getJson("/dashboard/data/app-data.json");
    return staticDataCache.trends[type];
  }
}

function renderToggles() {
  document.getElementById("categoryToggles").innerHTML = trendKeys.map((key) => `
    <label class="toggle-pill">
      <input type="checkbox" value="${key}" ${enabled.has(key) ? "checked" : ""}>
      <span style="--pill-color:${CATEGORY_COLORS[key]}">${LABELS[key]}</span>
    </label>
  `).join("");
  document.querySelectorAll("#categoryToggles input").forEach((input) => {
    input.addEventListener("change", () => {
      input.checked ? enabled.add(input.value) : enabled.delete(input.value);
      loadAndRender();
    });
  });
}

function renderStack(row, type) {
  const keys = visibleKeys();
  const capacity = periodCapacity(row, type);
  const totals = trendTotals(row, type);
  let widthUsed = 0;
  const segments = keys.map((key) => {
    const hours = Number(totals[key] || 0);
    if (hours <= 0 || widthUsed >= 100) return "";
    const width = Math.max(0, Math.min((hours / capacity) * 100, 100 - widthUsed));
    widthUsed += width;
    if (width <= 0) return "";
    return `
      <span
        class="trend-segment"
        title="${escapeHtml(segmentTitle(key, hours, totals))}"
        style="width:${width}%; background:${CATEGORY_COLORS[key]}"
      >${hours >= 0.5 ? `<b>${fmt(hours)}</b>` : ""}</span>
    `;
  }).join("");
  const emptyWidth = Math.max(0, 100 - widthUsed);
  const empty = emptyWidth > 0
    ? `<span class="trend-empty" title="Hidden or open period capacity" style="width:${emptyWidth}%"></span>`
    : "";
  return `${segments}${empty}`;
}

function renderRows(payload) {
  currentPayload = payload;
  document.getElementById("subtitle").textContent = `${payload.type} view`;
  document.getElementById("rowCount").textContent = `${payload.rows.length} rows`;
  const keys = visibleKeys();
  document.getElementById("trendBoard").innerHTML = payload.rows.map((row) => {
    const shownHours = totalHours(row, keys, payload.type);
    return `
      <div class="trend-row">
        <span class="trend-label">${escapeHtml(row.label)}</span>
        <div class="stack trend-stack">${renderStack(row, payload.type)}</div>
        <div class="trend-meta">
          <span>score <strong>${fmt(row.score)}</strong></span>
          <span>shown <strong>${fmt(shownHours)}h</strong></span>
        </div>
      </div>
    `;
  }).join("");
  renderVerticalTrend(payload);
}

function renderVerticalTrend(payload) {
  const container = document.getElementById("verticalTrend");
  const count = document.getElementById("verticalCount");
  if (!container) return;

  const keys = visibleKeys();
  const rows = payload.rows;
  if (count) count.textContent = `${rows.length} rows, visible section hours`;
  if (!rows.length) {
    container.innerHTML = `<p class="subtle">No trend rows available.</p>`;
    return;
  }

  const width = Math.max(760, rows.length * 72);
  const height = 330;
  const top = 34;
  const base = 260;
  const left = 34;
  const right = 24;
  const plotWidth = width - left - right;
  const barWidth = Math.max(18, Math.min(34, (plotWidth / rows.length) * 0.5));
  const points = [];

  const bars = rows.map((row, index) => {
    const x = left + ((index + 0.5) * plotWidth / rows.length);
    const capacity = periodCapacity(row, payload.type);
    const totals = trendTotals(row, payload.type);
    const shownHours = totalHours(row, keys, payload.type);
    const shownRatio = Math.min(1, shownHours / capacity);
    points.push([x, base - (shownRatio * (base - top)), shownHours]);

    let cumulative = 0;
    const segments = keys.map((key) => {
      const hours = Number(totals[key] || 0);
      if (hours <= 0 || cumulative >= capacity) return "";
      const cappedHours = Math.min(hours, capacity - cumulative);
      const segmentHeight = (cappedHours / capacity) * (base - top);
      const y = base - ((cumulative + cappedHours) / capacity) * (base - top);
      cumulative += hours;
      const label = hours >= 0.5 && segmentHeight >= 14
        ? `<text x="${x - (barWidth / 2) + 3}" y="${y + Math.min(segmentHeight - 3, 13)}" class="vertical-segment-label">${fmt(hours)}</text>`
        : "";
      return `
        <rect x="${x - (barWidth / 2)}" y="${y}" width="${barWidth}" height="${Math.max(0, segmentHeight)}" fill="${CATEGORY_COLORS[key]}"></rect>
        ${label}
      `;
    }).join("");

    return `
      <g>
        <rect x="${x - (barWidth / 2)}" y="${top}" width="${barWidth}" height="${base - top}" class="vertical-empty"></rect>
        ${segments}
        <text x="${x}" y="${base + 22}" class="vertical-label">${escapeHtml(row.label)}</text>
        <text x="${x}" y="${base + 40}" class="vertical-total">${fmt(shownHours)}h</text>
      </g>
    `;
  }).join("");

  const linePoints = points.map(([x, y]) => `${x},${y}`).join(" ");
  const changeLabels = points.slice(1).map(([x, y, hours], index) => {
    const [previousX, previousY, previousHours] = points[index];
    const labelX = (previousX + x) / 2;
    const labelY = Math.min(previousY, y) - 9;
    return `<text x="${labelX}" y="${Math.max(14, labelY)}" class="vertical-change">${percentChange(hours, previousHours)}</text>`;
  }).join("");

  container.innerHTML = `
    <div class="vertical-trend-wrap">
      <svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="Visible hours vertical trend">
        <line x1="${left}" y1="${base}" x2="${width - right}" y2="${base}" class="vertical-axis"></line>
        ${bars}
        <polyline points="${linePoints}" class="vertical-line"></polyline>
        ${points.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="3.5" class="vertical-point"></circle>`).join("")}
        ${changeLabels}
      </svg>
    </div>
  `;
}

async function loadAndRender() {
  const type = document.getElementById("typeSelect").value;
  renderRows(await getTrendData(type));
}

async function init() {
  renderToggles();
  document.getElementById("typeSelect").addEventListener("change", loadAndRender);
  await loadAndRender();
}

init();
