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

const CATEGORY_SHADES = {
  productiveOutput: "#5b1673",
  hard: "#065f35",
  soft: "#16875b",
  spiritual: "#263b96",
  physical: "#a93212",
  drift: "#d19407",
  sleep: "#4f5f9f",
  unscored: "#3f444d"
};

const LABELS = {
  productiveOutput: "Productive Output",
  hard: "Hard Work",
  soft: "Soft Work",
  spiritual: "Meditate",
  physical: "Gym",
  drift: "Entertainment",
  sleep: "Sleep",
  unscored: "Unscored"
};

const metricOrder = ["productiveOutput", "hard", "soft", "spiritual", "physical", "drift", "sleep", "unscored"];
const mixOrder = ["hard", "soft", "spiritual", "physical", "drift", "sleep", "unscored"];

const fallbackWeeks = [
  {
    id: "demo-week",
    label: "Demo Week",
    subtitle: "Demo data. Sync Google Calendar to replace this with local review rows.",
    targetText: "Targets: 60 PO, 10h drift, 10h physical, 1h spiritual",
    sourceText: "Current data source: frontend demo fallback",
    totals: { productiveOutput: 42, hard: 36, soft: 12, spiritual: 1, physical: 7, drift: 8, sleep: 52, unscored: 58 },
    score: {
      raw: 76,
      band: "C",
      components: [
        { label: "PO", value: 42, max: 60, colorKey: "productiveOutput" },
        { label: "Drift", value: 21, max: 20, colorKey: "drift" },
        { label: "Physical", value: 10.5, max: 15, colorKey: "physical" },
        { label: "Spiritual", value: 5, max: 5, colorKey: "spiritual" }
      ]
    },
    review: {
      win: "Demo output is active enough to show the weekly review layout.",
      leak: "Productive Output is the limiting factor in this demo week.",
      sleepDisplay: "7h 26m",
      sleepDetail: "52h total sleep / 7 accounting days"
    },
    detail: { days: [] }
  }
];

function fmt(value) {
  return Number(value).toFixed(value % 1 === 0 ? 0 : 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function loadPeriods() {
  try {
    const periods = await getJson("/api/weeks");
    return periods.length ? periods : fallbackWeeks.map(({ id, label }) => ({ id, label }));
  } catch {
    return fallbackWeeks.map(({ id, label }) => ({ id, label }));
  }
}

async function loadWeek(id) {
  try {
    return await getJson(`/api/week?id=${encodeURIComponent(id)}`);
  } catch {
    return fallbackWeeks.find((week) => week.id === id) || fallbackWeeks[0];
  }
}

function renderPeriodSelect(periods, selectedId) {
  const select = document.getElementById("periodSelect");
  select.innerHTML = periods.map((period) => `
    <option value="${period.id}" ${period.id === selectedId ? "selected" : ""}>${period.label}</option>
  `).join("");
}

function renderMetrics(totals) {
  document.getElementById("metricRow").innerHTML = metricOrder.map((key) => `
    <article class="metric" style="--metric-color:${CATEGORY_COLORS[key]}; --metric-glow:${CATEGORY_SHADES[key]}">
      <span>${LABELS[key]}</span>
      <strong>${fmt(totals[key])}h</strong>
    </article>
  `).join("");
}

function renderMix(totals) {
  const total = mixOrder.reduce((sum, key) => sum + totals[key], 0);
  document.getElementById("mixTrack").innerHTML = mixOrder.map((key) => `
    <div
      class="mix-segment"
      title="${LABELS[key]}: ${fmt(totals[key])}h"
      style="width:${(totals[key] / total) * 100}%; background:${CATEGORY_COLORS[key]}"
    ></div>
  `).join("");
}

function renderScore(score) {
  document.getElementById("grade").textContent = score.band;
  document.getElementById("scoreText").textContent = `${fmt(score.raw)} points`;
  document.getElementById("scoreBars").innerHTML = score.components.map((item) => `
    <div class="score-item">
      <div class="score-head">
        <span>${item.label}</span>
        <strong>${fmt(item.value)} / ${fmt(item.max)}</strong>
      </div>
      <div class="track">
        <div class="fill" style="width:${Math.min(100, (item.value / item.max) * 100)}%; background:${CATEGORY_COLORS[item.colorKey] || item.color}"></div>
      </div>
    </div>
  `).join("");
}

function renderReview(review) {
  document.getElementById("winText").textContent = review.win;
  document.getElementById("leakText").textContent = review.leak;
  document.getElementById("sleepDisplay").textContent = review.sleepDisplay;
  document.getElementById("sleepDetail").textContent = review.sleepDetail;
}

function renderDays(days = []) {
  const container = document.getElementById("dayBars");
  if (!container) return;
  if (!days.length) {
    container.innerHTML = `<p class="subtle">No day breakdown available for this week.</p>`;
    return;
  }
  container.innerHTML = days.map((day) => {
    const total = mixOrder.reduce((sum, key) => sum + Number(day[key] || 0), 0) || 1;
    const annotations = (day.annotations || []).map(escapeHtml).join(", ");
    const stack = mixOrder.map((key) => `
      <span title="${LABELS[key]}: ${fmt(day[key] || 0)}h" style="width:${((day[key] || 0) / total) * 100}%; background:${CATEGORY_COLORS[key]}"></span>
    `).join("");
    return `
      <div class="week-row">
        <span class="week-day-label">
          <strong>${escapeHtml(day.label)}</strong>
          ${annotations ? `<em>${annotations}</em>` : ""}
        </span>
        <div class="stack">${stack}</div>
        <strong>${day.score}</strong>
      </div>
    `;
  }).join("");
}

function renderHeader(week) {
  document.getElementById("subtitle").textContent = week.subtitle;
  document.getElementById("targetText").textContent = week.targetText;
  document.getElementById("sourceText").textContent = week.sourceText;
}

async function renderWeek(id) {
  const week = await loadWeek(id);
  renderHeader(week);
  renderMetrics(week.totals);
  renderMix(week.totals);
  renderScore(week.score);
  renderReview(week.review);
  renderDays(week.detail?.days);
}

async function init() {
  const periods = await loadPeriods();
  const selectedId = periods[0]?.id || fallbackWeeks[0].id;
  renderPeriodSelect(periods, selectedId);
  await renderWeek(selectedId);
  document.getElementById("periodSelect").addEventListener("change", (event) => {
    renderWeek(event.target.value);
  });
}

init();
