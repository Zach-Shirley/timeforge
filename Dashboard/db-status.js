const fallbackStatus = {
  database: {
    path: "Data/time_tracking.sqlite",
    exists: false,
    sizeBytes: 0,
    tables: [],
    currentLocalDate: "",
    completedPeriodRule: "Week and month reviews are selectable only after the period is complete. Daily incomplete pulls can be shown by the daily page."
  },
  periodReviews: {
    summaries: [
      { type: "week", totalRows: 0, completedRows: 0, firstStart: null, lastEnd: null },
      { type: "month", totalRows: 0, completedRows: 0, firstStart: null, lastEnd: null }
    ],
    completedRows: []
  },
  calendarRaw: { eventCount: 0, firstStart: null, lastEnd: null },
  scoreProfiles: { count: 1 },
  syncRuns: [],
  connectorProbe: {
    value: "No local sync recorded yet.",
    updated_at: ""
  }
};

function fmtBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function safe(value, fallback = "not loaded") {
  return value || fallback;
}

async function getStatus() {
  try {
    const response = await fetch("/api/db/status");
    if (!response.ok) throw new Error(`Status ${response.status}`);
    return response.json();
  } catch {
    return fallbackStatus;
  }
}

function renderCards(status) {
  const cards = [
    { label: "DB Size", value: fmtBytes(status.database.sizeBytes), detail: "SQLite file" },
    { label: "Tables", value: status.database.tables.length, detail: "Current schema" },
    { label: "Review Rows", value: status.periodReviews.completedRows.length, detail: "Completed selectable rows" },
    { label: "Raw Events", value: status.calendarRaw.eventCount, detail: "Calendar events imported" }
  ];
  document.getElementById("statusCards").innerHTML = cards.map((card) => `
    <article class="panel status-card">
      <h3>${card.label}</h3>
      <strong>${card.value}</strong>
      <p class="subtle">${card.detail}</p>
    </article>
  `).join("");
}

function renderPeriods(status) {
  document.getElementById("periodSummaryRows").innerHTML = status.periodReviews.summaries.map((row) => `
    <tr>
      <td>${row.type}</td>
      <td>${row.totalRows}</td>
      <td>${row.completedRows}</td>
      <td>${safe(row.firstStart, "none")} -> ${safe(row.lastEnd, "none")}</td>
    </tr>
  `).join("");

  document.getElementById("periodRows").innerHTML = status.periodReviews.completedRows.map((row) => `
    <tr>
      <td>${row.period_type}</td>
      <td>${row.label}</td>
      <td>${row.period_start}</td>
      <td>${row.period_end}</td>
    </tr>
  `).join("");
}

function renderSource(status) {
  document.getElementById("dbBadge").textContent = status.database.exists ? "DB online" : "DB missing";
  document.getElementById("dbPath").innerHTML = `<span class="mono">${status.database.path}</span>`;
  document.getElementById("statusSubtitle").textContent = `Current local date: ${status.database.currentLocalDate}`;
  document.getElementById("rawCoverage").innerHTML = `<strong>Raw calendar:</strong> ${status.calendarRaw.eventCount} events, ${safe(status.calendarRaw.firstStart, "no start")} -> ${safe(status.calendarRaw.lastEnd, "no end")}.`;
  document.getElementById("selectorRule").innerHTML = `<strong>Selector rule:</strong> ${status.database.completedPeriodRule}`;
  document.getElementById("connectorProbe").innerHTML = `<strong>Calendar connector:</strong> ${safe(status.connectorProbe.value)}`;
}

function renderSyncRuns(status) {
  const container = document.getElementById("syncRuns");
  if (!status.syncRuns.length) {
    container.innerHTML = "<p>No local sync runs recorded yet.</p>";
    return;
  }
  container.innerHTML = status.syncRuns.map((run) => `
    <p><strong>${run.source} ${run.status}:</strong> ${run.pulled_events} events, ${safe(run.window_start, "no start")} -> ${safe(run.window_end, "no end")}.</p>
  `).join("");
}

async function init() {
  const status = await getStatus();
  renderCards(status);
  renderPeriods(status);
  renderSource(status);
  renderSyncRuns(status);
}

init();
