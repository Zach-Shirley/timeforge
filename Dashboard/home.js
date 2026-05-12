const syncButton = document.getElementById("syncButton");
const syncStatus = document.getElementById("syncStatus");

function fmt(value) {
  return Number(value || 0).toFixed(Number(value || 0) % 1 === 0 ? 0 : 1);
}

function setSyncState(label, disabled = false) {
  syncButton.disabled = disabled;
  syncStatus.textContent = label;
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function getStaticData() {
  return getJson("/dashboard/data/app-data.json");
}

function periodSummary(period) {
  if (!period) return "<p>No generated row yet.</p>";
  return `
    <p><strong>${period.label}</strong></p>
    <p>Score ${fmt(period.score.raw)} ${period.score.band}</p>
    <p>PO ${fmt(period.totals.productiveOutput)}h, drift ${fmt(period.totals.drift)}h, sleep ${fmt(period.totals.sleep)}h.</p>
  `;
}

async function renderHomeStatus() {
  try {
    let status;
    try {
      status = await getJson("/api/home/status");
    } catch {
      status = (await getStaticData()).home;
    }
    document.getElementById("latestDay").innerHTML = periodSummary(status.latestDay);
    document.getElementById("latestWeek").innerHTML = periodSummary(status.latestWeek);
    document.getElementById("latestMonth").innerHTML = periodSummary(status.latestMonth);
    document.getElementById("systemStatus").innerHTML = `
      <p><strong>Raw events:</strong> ${status.db.calendarRaw.eventCount}</p>
      <p><strong>Raw through:</strong> ${status.db.calendarRaw.lastEnd || "not synced"}</p>
      <p><strong>Reviews:</strong> ${status.db.periodReviews.summaries.map((row) => `${row.completedRows} ${row.type}s`).join(", ")}</p>
    `;
  } catch (error) {
    document.getElementById("systemStatus").innerHTML = `<p>Could not load status: ${error.message}</p>`;
  }
}

syncButton.addEventListener("click", async () => {
  setSyncState("Syncing...", true);
  try {
    const response = await fetch("/api/sync/calendar", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    setSyncState(`Synced ${payload.pulledEvents} events; rebuilt ${payload.generatedDays ?? "?"} days, ${payload.generatedWeeks} weeks, and ${payload.generatedMonths} months.`, false);
    await renderHomeStatus();
  } catch (error) {
    setSyncState(`Sync failed: ${error.message}`, false);
  }
});

renderHomeStatus();
