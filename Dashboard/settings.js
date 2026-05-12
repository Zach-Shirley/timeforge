async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function getSettings() {
  try {
    return await getJson("/api/settings");
  } catch {
    return (await getJson("/dashboard/data/app-data.json")).settings;
  }
}

function labelize(key) {
  return key.replace(/([A-Z])/g, " $1").replace(/^./, (char) => char.toUpperCase());
}

async function init() {
  const settings = await getSettings();
  document.getElementById("profileName").textContent = settings.scoreProfile.name;
  document.getElementById("scoreSettings").innerHTML = Object.entries(settings.scoreProfile.config).map(([key, value]) => `
    <article class="field-card">
      <span>${labelize(key)}</span>
      <strong>${value}</strong>
    </article>
  `).join("");
  document.getElementById("suffixRules").innerHTML = Object.entries(settings.categoryRules.suffixes).map(([number, category]) => `
    <p><strong>${number}:</strong> ${category}</p>
  `).join("");
  document.getElementById("wakeRule").textContent = settings.categoryRules.dayAccounting || settings.categoryRules.wakeCycle || "";
}

init();
