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

const fallbackMonths = [
  {
    id: "demo-month",
    label: "Demo Month",
    subtitle: "Demo data. Sync Google Calendar to replace this with local review rows.",
    targetText: "Targets: 60 PO/week, 10h drift/week, 10h physical/week, 1h spiritual/week",
    sourceText: "Current data source: frontend demo fallback",
    totals: { productiveOutput: 178, hard: 154, soft: 48, spiritual: 5, physical: 31, drift: 42, sleep: 221, unscored: 243 },
    score: {
      raw: 78,
      band: "C",
      components: [
        { label: "PO", value: 44, max: 60, colorKey: "productiveOutput" },
        { label: "Drift", value: 15, max: 20, colorKey: "drift" },
        { label: "Physical", value: 14, max: 15, colorKey: "physical" },
        { label: "Spiritual", value: 5, max: 5, colorKey: "spiritual" }
      ]
    },
    review: {
      win: "Demo month shows the review layout with enough spread across categories.",
      leak: "Productive Output is the weakest lever in this demo month.",
      sleepDisplay: "7h 22m",
      sleepDetail: "Month-level average, 5 AM accounting-day based"
    },
    detail: {
      weeks: [
        { label: "Week 1", score: 72, hard: 34, soft: 10, spiritual: 1, physical: 7, drift: 12, sleep: 51, unscored: 53 },
        { label: "Week 2", score: 80, hard: 42, soft: 12, spiritual: 1.5, physical: 8, drift: 8, sleep: 52, unscored: 44 },
        { label: "Week 3", score: 76, hard: 37, soft: 11, spiritual: 1, physical: 7, drift: 11, sleep: 50, unscored: 51 },
        { label: "Week 4", score: 82, hard: 41, soft: 15, spiritual: 1.5, physical: 9, drift: 9, sleep: 53, unscored: 39 }
      ],
      trends: [
        { label: "PO vs target", value: 73, text: "Below target", colorKey: "productiveOutput" },
        { label: "Drift control", value: 75, text: "Controlled", colorKey: "drift" },
        { label: "Physical consistency", value: 93, text: "Strong", colorKey: "physical" },
        { label: "Spiritual consistency", value: 100, text: "Complete", colorKey: "spiritual" }
      ],
      notes: [
        { label: "Best week", text: "Week 4 had the strongest combined output and physical consistency." },
        { label: "Weakest recurring pattern", text: "Productive Output stayed below the weekly target." },
        { label: "Next target", text: "Raise hard-work hours while keeping drift near the current line." }
      ],
      dataNotes: [
        { label: "Grouping", text: "Monthly reviews roll up 5 AM accounting days." },
        { label: "Confidence", text: "This is demo data only." },
        { label: "Importer", text: "Google Calendar sync replaces this fallback after setup." }
      ]
    }
  }
];

function fmt(value) {
  return Number(value).toFixed(value % 1 === 0 ? 0 : 1);
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function loadPeriods() {
  try {
    const periods = await getJson("/api/months");
    return periods.length ? periods : fallbackMonths.map(({ id, label }) => ({ id, label }));
  } catch {
    return fallbackMonths.map(({ id, label }) => ({ id, label }));
  }
}

async function loadMonth(id) {
  try {
    return await getJson(`/api/month?id=${encodeURIComponent(id)}`);
  } catch {
    return fallbackMonths.find((month) => month.id === id) || fallbackMonths[0];
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

function renderHeader(month) {
  document.getElementById("subtitle").textContent = month.subtitle;
  document.getElementById("targetText").textContent = month.targetText;
  document.getElementById("sourceText").textContent = month.sourceText;
}

function renderWeeks(weeks) {
  document.getElementById("weekBars").innerHTML = weeks.map((week) => {
    const total = mixOrder.reduce((sum, key) => sum + week[key], 0);
    const stack = mixOrder.map((key) => `
      <span title="${LABELS[key]}: ${fmt(week[key])}h" style="width:${(week[key] / total) * 100}%; background:${CATEGORY_COLORS[key]}"></span>
    `).join("");
    return `
      <div class="week-row">
        <span class="subtle">${week.label}</span>
        <div class="stack">${stack}</div>
        <strong>${week.score}</strong>
      </div>
    `;
  }).join("");
}

function renderTrends(trends) {
  document.getElementById("trendList").innerHTML = trends.map((trend) => `
    <div class="trend-card">
      <div class="trend-head">
        <span>${trend.label}</span>
        <strong>${trend.text}</strong>
      </div>
      <div class="track">
        <div class="fill" style="width:${trend.value}%; background:${CATEGORY_COLORS[trend.colorKey] || trend.color}"></div>
      </div>
    </div>
  `).join("");
}

function renderNotes(containerId, notes) {
  document.getElementById(containerId).innerHTML = notes.map((note) => `
    <p><strong>${note.label}:</strong> ${note.text}</p>
  `).join("");
}

async function renderMonth(id) {
  const month = await loadMonth(id);
  renderHeader(month);
  renderMetrics(month.totals);
  renderMix(month.totals);
  renderScore(month.score);
  renderReview(month.review);
  renderWeeks(month.detail.weeks);
  renderTrends(month.detail.trends);
  renderNotes("monthNotes", month.detail.notes);
  renderNotes("dataNotes", month.detail.dataNotes);
}

async function init() {
  const periods = await loadPeriods();
  const selectedId = periods[0]?.id || fallbackMonths[0].id;
  renderPeriodSelect(periods, selectedId);
  await renderMonth(selectedId);
  document.getElementById("periodSelect").addEventListener("change", (event) => {
    renderMonth(event.target.value);
  });
}

init();
