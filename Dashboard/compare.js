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
  productiveOutput: "PO",
  hard: "Hard",
  soft: "Soft",
  spiritual: "Meditate",
  physical: "Gym",
  drift: "Entertainment",
  sleep: "Sleep",
  unscored: "Unscored"
};

const metricOrder = ["productiveOutput", "hard", "soft", "spiritual", "physical", "drift", "sleep", "unscored"];

function fmt(value) {
  return Number(value || 0).toFixed(Number(value || 0) % 1 === 0 ? 0 : 1);
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

function periodSet(data, type) {
  if (type === "day") return data.days;
  if (type === "month") return data.months;
  return data.weeks;
}

function staticComparison(data, type, a, b) {
  const set = periodSet(data, type);
  const first = set.byId[a];
  const second = set.byId[b];
  const keys = ["productiveOutput", "hard", "soft", "spiritual", "physical", "drift", "sleep", "unscored"];
  return {
    type,
    a: first,
    b: second,
    scoreDelta: Number((first.score.raw - second.score.raw).toFixed(1)),
    deltas: Object.fromEntries(keys.map((key) => [key, Number(((first.totals[key] || 0) - (second.totals[key] || 0)).toFixed(2))]))
  };
}

function options(periods, selected) {
  return periods.map((period) => `<option value="${period.id}" ${period.id === selected ? "selected" : ""}>${period.label}</option>`).join("");
}

function renderMetricSet(containerId, totals) {
  document.getElementById(containerId).innerHTML = metricOrder.map((key) => `
    <article class="metric" style="--metric-color:${CATEGORY_COLORS[key]}; --metric-glow:${CATEGORY_SHADES[key]}">
      <span>${LABELS[key]}</span>
      <strong>${fmt(totals[key])}h</strong>
    </article>
  `).join("");
}

function renderComparison(payload) {
  document.getElementById("scoreDelta").textContent = `${payload.scoreDelta > 0 ? "+" : ""}${fmt(payload.scoreDelta)}`;
  document.getElementById("scoreContext").textContent = `${payload.a.label} vs ${payload.b.label}`;
  document.getElementById("labelA").textContent = `${payload.a.score.raw} ${payload.a.score.band}`;
  document.getElementById("labelB").textContent = `${payload.b.score.raw} ${payload.b.score.band}`;
  renderMetricSet("metricsA", payload.a.totals);
  renderMetricSet("metricsB", payload.b.totals);
  document.getElementById("deltaBars").innerHTML = metricOrder.slice(0, 6).map((key) => {
    const delta = payload.deltas[key];
    return `
      <div class="score-item">
        <div class="score-head">
          <span>${LABELS[key]}</span>
          <strong>${delta > 0 ? "+" : ""}${fmt(delta)}h</strong>
        </div>
        <div class="track">
          <div class="fill" style="width:${Math.min(100, Math.abs(delta) * 6)}%; background:${CATEGORY_COLORS[key]}"></div>
        </div>
      </div>
    `;
  }).join("");
}

async function loadOptions() {
  const type = document.getElementById("typeSelect").value;
  let periods;
  try {
    periods = await getJson(`/api/compare/options?type=${encodeURIComponent(type)}`);
  } catch {
    periods = periodSet(await getStaticData(), type).options;
  }
  const first = periods[0]?.id || "";
  const second = periods[1]?.id || first;
  document.getElementById("periodA").innerHTML = options(periods, first);
  document.getElementById("periodB").innerHTML = options(periods, second);
  await loadComparison();
}

async function loadComparison() {
  const type = document.getElementById("typeSelect").value;
  const a = document.getElementById("periodA").value;
  const b = document.getElementById("periodB").value;
  if (!a || !b) return;
  try {
    renderComparison(await getJson(`/api/compare?type=${encodeURIComponent(type)}&a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`));
  } catch {
    renderComparison(staticComparison(await getStaticData(), type, a, b));
  }
}

async function init() {
  document.getElementById("typeSelect").addEventListener("change", loadOptions);
  document.getElementById("periodA").addEventListener("change", loadComparison);
  document.getElementById("periodB").addEventListener("change", loadComparison);
  await loadOptions();
}

init();
