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
let currentDay;
let hideUnscored = false;
let estimateEnabled = false;

function fmt(value) {
  return Number(value || 0).toFixed(Number(value || 0) % 1 === 0 ? 0 : 2);
}

function timeLabel(value) {
  return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function timelineTimeCell(event) {
  const visibleRange = `${timeLabel(event.start)}-${timeLabel(event.end)}`;
  if (!event.clippedByAccountingDay || !event.sourceStart || !event.sourceEnd) {
    return `<span>${visibleRange}</span>`;
  }
  return `
    <span class="time-cell">
      ${visibleRange}
      <small>full ${timeLabel(event.sourceStart)}-${timeLabel(event.sourceEnd)}</small>
    </span>
  `;
}

function allocationLabel(event) {
  const entries = Object.entries(event.allocations || {});
  if (entries.length <= 1) return `${fmt(event.hours)}h`;
  return `${fmt(event.hours)}h - ${entries.map(([key, value]) => `${Math.round(value * 100)}% ${LABELS[key] || key}`).join(" / ")}`;
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

let staticDataCache;

async function getStaticData() {
  if (!staticDataCache) staticDataCache = await getJson("/dashboard/data/app-data.json");
  return staticDataCache;
}

async function loadPeriods() {
  try {
    return await getJson("/api/days");
  } catch {
    return (await getStaticData()).days.options;
  }
}

async function loadDay(id) {
  try {
    return await getJson(`/api/day?id=${encodeURIComponent(id)}`);
  } catch {
    return (await getStaticData()).days.byId[id];
  }
}

function renderPeriodSelect(periods, selectedId) {
  document.getElementById("periodSelect").innerHTML = periods.map((period) => `
    <option value="${period.id}" ${period.id === selectedId ? "selected" : ""}>${period.label}${period.completed ? "" : " (live)"}</option>
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

function renderScore(score, label = "points") {
  document.getElementById("grade").textContent = score.band;
  document.getElementById("scoreText").textContent = `${fmt(score.raw)} ${label}`;
  document.getElementById("scoreBars").innerHTML = score.components.map((item) => `
    <div class="score-item">
      <div class="score-head">
        <span>${item.label}</span>
        <strong>${fmt(item.value)} / ${fmt(item.max)}</strong>
      </div>
      <div class="track">
        <div class="fill" style="width:${Math.min(100, (item.value / item.max) * 100)}%; background:${CATEGORY_COLORS[item.colorKey]}"></div>
      </div>
    </div>
  `).join("");
}

function renderTimeline(events = [], annotations = []) {
  const container = document.getElementById("timeline");
  const visibleEvents = hideUnscored
    ? events.filter((event) => event.category !== "unscored")
    : events;

  if (!visibleEvents.length && !annotations.length) {
    container.innerHTML = `<p class="subtle">No raw event blocks found for this accounting day.</p>`;
    return;
  }

  const annotationRows = annotations.map((annotation) => `
    <div class="timeline-row annotation-row">
      <span>All day</span>
      <strong>${escapeHtml(annotation.title)}</strong>
      <em>note</em>
    </div>
  `).join("");

  const eventRows = visibleEvents.map((event) => `
    <div class="timeline-row" style="--event-color:${CATEGORY_COLORS[event.category] || "var(--unscored)"}">
      ${timelineTimeCell(event)}
      <strong>${escapeHtml(event.title)}</strong>
      <em>${allocationLabel(event)}</em>
    </div>
  `).join("");

  container.innerHTML = `${annotationRows}${eventRows}`;
}

function renderReview(day) {
  document.getElementById("subtitle").textContent = `${day.subtitle}${day.completed ? "" : " Incomplete/live."}`;
  document.getElementById("sourceText").textContent = day.sourceText;
  document.getElementById("winText").textContent = day.review.win;
  document.getElementById("leakText").textContent = day.review.leak;
  document.getElementById("sleepDisplay").textContent = day.review.sleepDisplay;
  document.getElementById("sleepDetail").textContent = day.review.sleepDetail;
}

function poScore(po) {
  if (po <= 60) return po;
  if (po <= 80) return 60 + ((po - 60) * 0.6);
  if (po <= 100) return 72 + ((po - 80) * 0.4);
  return 80 + ((po - 100) * 0.2);
}

function driftScore(drift) {
  if (drift <= 10) return 20 + Math.min(5, (10 - drift) * 0.5);
  if (drift >= 20) return 0;
  return 20 * ((20 - drift) / 10);
}

function bandForScore(raw) {
  if (raw >= 90) return "A";
  if (raw >= 80) return "B";
  if (raw >= 70) return "C";
  if (raw >= 60) return "D";
  return "F";
}

function scoreFromTotals(totals, days = 1) {
  const scale = days ? 7 / days : 1;
  const weeklyPo = Number(totals.productiveOutput || 0) * scale;
  const weeklyDrift = Number(totals.drift || 0) * scale;
  const weeklyPhysical = Number(totals.physical || 0) * scale;
  const weeklySpiritual = Number(totals.spiritual || 0) * scale;
  const components = [
    { label: "PO", value: Number(poScore(weeklyPo).toFixed(1)), max: 60, colorKey: "productiveOutput" },
    { label: "Drift", value: Number(driftScore(weeklyDrift).toFixed(1)), max: 20, colorKey: "drift" },
    { label: "Physical", value: Number(Math.min(15, 15 * (weeklyPhysical / 10)).toFixed(1)), max: 15, colorKey: "physical" },
    { label: "Spiritual", value: Number(Math.min(5, 5 * weeklySpiritual).toFixed(1)), max: 5, colorKey: "spiritual" }
  ];
  const raw = Number(components.reduce((sum, component) => sum + component.value, 0).toFixed(1));
  return { raw, band: bandForScore(raw), components };
}

function estimateDay(day) {
  const events = day.detail?.timeline || [];
  if (!events.length) return null;

  const firstNonSleep = events.find((event) => event.category !== "sleep");
  const sleepBlock = events.find((event) => event.category === "sleep");
  const wakeTime = Date.parse(sleepBlock?.end || firstNonSleep?.start || events[0].start);
  const latestEnd = events.reduce((latest, event) => Math.max(latest, Date.parse(event.end)), wakeTime);
  const elapsedAwake = Math.max(0.25, (latestEnd - wakeTime) / 3600000);
  const targetAwake = 16;
  const factor = Math.max(1, Math.min(3, targetAwake / elapsedAwake));
  const projectedTotals = { ...day.totals };

  ["productiveOutput", "hard", "soft", "spiritual", "physical", "drift", "unscored"].forEach((key) => {
    projectedTotals[key] = Number((Number(day.totals[key] || 0) * factor).toFixed(2));
  });
  projectedTotals.sleep = Number(day.totals.sleep || 0);

  return {
    elapsedAwake,
    targetAwake,
    factor,
    projectedTotals,
    score: scoreFromTotals(projectedTotals, 1)
  };
}

function renderEstimateControls(day) {
  const control = document.getElementById("estimateControl");
  const toggle = document.getElementById("estimateToggle");
  if (!control || !toggle) return;
  control.hidden = Boolean(day.completed);
  if (day.completed) {
    estimateEnabled = false;
    toggle.checked = false;
  }
}

function renderEstimatePanel(day, estimate) {
  const panel = document.getElementById("estimatePanel");
  if (!panel) return;
  if (!estimateEnabled || day.completed || !estimate) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  panel.hidden = false;
  panel.innerHTML = `
    <div class="estimate-card">
      <span>Projected score</span>
      <strong>${fmt(estimate.score.raw)} ${estimate.score.band}</strong>
    </div>
    <div class="estimate-card">
      <span>Awake pace</span>
      <strong>${fmt(estimate.elapsedAwake)}h / ${fmt(estimate.targetAwake)}h</strong>
    </div>
    <div class="estimate-card">
      <span>Projected PO</span>
      <strong>${fmt(estimate.projectedTotals.productiveOutput)}h</strong>
    </div>
    <div class="estimate-card">
      <span>Projected drift</span>
      <strong>${fmt(estimate.projectedTotals.drift)}h</strong>
    </div>
  `;
}

function renderDayState(day) {
  const estimate = estimateDay(day);
  renderReview(day);
  renderMetrics(day.totals);
  renderScore(
    estimateEnabled && !day.completed && estimate ? estimate.score : day.score,
    estimateEnabled && !day.completed ? "estimated points" : "points"
  );
  renderTimeline(day.detail.timeline, day.detail.annotations || []);
  renderEstimateControls(day);
  renderEstimatePanel(day, estimate);
}

async function renderDay(id) {
  const day = await loadDay(id);
  currentDay = day;
  renderDayState(day);
}

async function init() {
  const periods = await loadPeriods();
  const selectedId = periods[0]?.id;
  renderPeriodSelect(periods, selectedId);
  if (selectedId) await renderDay(selectedId);
  document.getElementById("periodSelect").addEventListener("change", (event) => renderDay(event.target.value));
  document.getElementById("hideUnscoredToggle")?.addEventListener("change", (event) => {
    hideUnscored = event.target.checked;
    if (currentDay) renderTimeline(currentDay.detail.timeline, currentDay.detail.annotations || []);
  });
  document.getElementById("estimateToggle")?.addEventListener("change", (event) => {
    estimateEnabled = event.target.checked;
    if (currentDay) renderDayState(currentDay);
  });
}

init();
