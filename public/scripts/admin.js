const loginView = document.getElementById("login-view");
const dashboardView = document.getElementById("dashboard-view");
const loginForm = document.getElementById("login-form");
const loginStatus = document.getElementById("login-status");
const dashboardStatus = document.getElementById("dashboard-status");
const logoutButton = document.getElementById("logout-button");
const accountName = document.getElementById("account-name");
const refreshButton = document.getElementById("refresh-button");
const settingsForm = document.getElementById("settings-form");
const recordsStatus = document.getElementById("records-status");
const gameRecordSelect = document.getElementById("game-record-select");
const gameRecordForm = document.getElementById("game-record-form");
const achievementGameSelect = document.getElementById("achievement-game-select");
const achievementRecordSelect = document.getElementById("achievement-record-select");
const achievementRecordForm = document.getElementById("achievement-record-form");
const toastRegion = document.getElementById("toast-region");
const svgNamespace = "http://www.w3.org/2000/svg";
const settingsStorageKey = "lcpgamecol-admin-settings";
let dashboardRefreshTimer = null;
let toastTimer = null;
let gameRecords = [];
let achievementRecords = [];
const richTextEditors = new Map();
// Forms with unsaved changes; background refreshes leave their records alone.
const dirtyRecordForms = new Set();
let liveRefreshTimer = null;

function initRichTextEditors() {
  for (const textarea of document.querySelectorAll("textarea[data-rich-text]")) {
    const container = document.createElement("div");
    container.setAttribute("translate", "no");
    textarea.after(container);
    const editor = new Quill(container, {
      theme: "snow",
      modules: {
        toolbar: [
          [{ header: [3, 4, false] }],
          ["bold", "italic", "underline"],
          [{ list: "ordered" }, { list: "bullet" }],
          ["link", "clean"],
        ],
      },
    });
    editor.root.setAttribute("aria-labelledby", textarea.getAttribute("aria-labelledby"));
    editor.on("text-change", (_delta, _oldDelta, source) => {
      textarea.value = editor.getText().trim() ? editor.root.innerHTML : "";
      if (source === "user") dirtyRecordForms.add(textarea.form);
    });
    richTextEditors.set(textarea.name, editor);
  }
}

function setRichTextValue(editor, value) {
  if (/<[a-z][\s\S]*>/i.test(value)) {
    editor.clipboard.dangerouslyPasteHTML(value, "silent");
  } else {
    editor.setText(value, "silent");
  }
}

function showLogin(message = "") {
  dashboardView.hidden = true;
  loginView.hidden = false;
  loginStatus.textContent = message;
  accountName.textContent = "";
  logoutButton.hidden = true;
  window.adminSidebar?.setAvailable(false);
  window.realtime?.stop();
}

function showDashboard(username, role) {
  loginView.hidden = true;
  dashboardView.hidden = false;
  accountName.textContent = username;
  logoutButton.hidden = false;
  window.adminSidebar?.setAvailable(true, role);
  window.realtime?.start();
}

function showToast(message) {
  toastRegion.textContent = message;
  toastRegion.classList.add("is-visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    toastRegion.classList.remove("is-visible");
  }, 3600);
}

async function loadDashboard() {
  dashboardStatus.textContent = "Updating collection data...";
  window.setStatusLoading(dashboardStatus, true);
  refreshButton.disabled = true;
  try {
    const response = await fetch("/admin/dashboard");
    if (response.status === 401) {
      showLogin("Your session expired. Please sign in again.");
      return;
    }
    if (response.status === 403) {
      showLogin("This account does not have administrator access.");
      return;
    }
    if (!response.ok) throw new Error("Dashboard data could not be loaded.");
    renderDashboard(await response.json());
    loadDevelopmentSettings();
    if (dirtyRecordForms.size === 0) await loadRecordGames(gameRecordSelect.value || undefined);
    dashboardStatus.textContent = "";
    const locale = { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR", it: "it-IT", es: "es-ES", ja: "ja-JP" }[window.i18n.language];
    document.getElementById("updated-label").textContent = window.i18n.t("UPDATED {time}", {
      time: new Date().toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" }),
    });
  } catch (error) {
    dashboardStatus.textContent = error.message;
  } finally {
    window.setStatusLoading(dashboardStatus, false);
    refreshButton.disabled = false;
  }
}

async function readApiResponse(response) {
  if (response.ok) return response.status === 204 ? null : response.json();
  let message = "The request could not be completed.";
  try {
    const body = await response.json();
    message = body.detail || message;
  } catch {
    // Keep the fallback message when the server returns no JSON body.
  }
  throw new Error(message);
}

function setFormField(form, name, value) {
  const field = form.elements.namedItem(name);
  if (field.type === "checkbox") {
    field.checked = Boolean(value);
  } else if (name === "screenshots" && Array.isArray(value)) {
    field.value = value.join("\n");
  } else {
    field.value = value ?? "";
  }
  if (richTextEditors.has(name)) setRichTextValue(richTextEditors.get(name), field.value);
}

function setRecordFormMode(form, editButtonId, deleteButtonId, hasRecord, editing, editLabel) {
  dirtyRecordForms.delete(form);
  for (const field of form.querySelectorAll(".record-fields input, .record-fields textarea, .record-fields select")) {
    field.disabled = hasRecord && !editing;
    richTextEditors.get(field.name)?.enable(!field.disabled);
  }
  form.querySelector('[type="submit"]').hidden = hasRecord && !editing;

  const editButton = document.getElementById(editButtonId);
  editButton.hidden = !hasRecord;
  editButton.textContent = editing ? "Cancel edit" : editLabel;
  editButton.dataset.editing = String(editing);
  document.getElementById(deleteButtonId).hidden = !hasRecord;
}

function clearGameForm() {
  gameRecordForm.reset();
  for (const name of richTextEditors.keys()) setFormField(gameRecordForm, name, "");
  setFormField(gameRecordForm, "release_year", new Date().getFullYear());
  setFormField(gameRecordForm, "platforms", "PC");
  setFormField(gameRecordForm, "gamemodes", "all");
  setFormField(gameRecordForm, "editions", "Standard");
  document.getElementById("game-form-title").textContent = "Create game";
  setRecordFormMode(gameRecordForm, "edit-game-button", "delete-game-button", false, true, "Edit game");
}

function selectGameRecord(gameId) {
  const game = gameRecords.find((record) => String(record.id) === String(gameId));
  if (!game) {
    clearGameForm();
    return;
  }
  for (const [name, value] of Object.entries(game)) {
    if (name !== "id") setFormField(gameRecordForm, name, value);
  }
  document.getElementById("game-form-title").textContent = window.i18n.t("Edit game #{id}", { id: game.id });
  setRecordFormMode(gameRecordForm, "edit-game-button", "delete-game-button", true, false, "Edit game");
}

function renderGameSelectors(preferredGameId) {
  gameRecordSelect.replaceChildren();
  achievementGameSelect.replaceChildren();
  for (const game of gameRecords) {
    const option = document.createElement("option");
    option.value = game.id;
    option.textContent = `${game.title} (#${game.id})`;
    gameRecordSelect.append(option);

    const achievementOption = option.cloneNode(true);
    achievementGameSelect.append(achievementOption);
  }

  if (gameRecords.length) {
    const selectedId = gameRecords.some((game) => String(game.id) === String(preferredGameId))
      ? String(preferredGameId)
      : String(gameRecords[0].id);
    gameRecordSelect.value = selectedId;
    achievementGameSelect.value = selectedId;
    selectGameRecord(selectedId);
  } else {
    clearGameForm();
  }
  achievementGameSelect.disabled = gameRecords.length === 0;
  document.getElementById("delete-game-button").disabled = gameRecords.length === 0;
}

function clearAchievementForm() {
  achievementRecordForm.reset();
  setFormField(achievementRecordForm, "status", "Locked");
  setFormField(achievementRecordForm, "achievement_type", "Bronze");
  document.getElementById("achievement-form-title").textContent = "Create achievement";
  setRecordFormMode(
    achievementRecordForm,
    "edit-achievement-button",
    "delete-achievement-button",
    false,
    true,
    "Edit achievement",
  );
}

function selectAchievementRecord(achievementId) {
  const achievement = achievementRecords.find(
    (record) => String(record.achievement_id) === String(achievementId),
  );
  if (!achievement) {
    clearAchievementForm();
    return;
  }
  for (const [name, value] of Object.entries(achievement)) {
    if (name !== "achievement_id" && name !== "game_id") setFormField(achievementRecordForm, name, value);
  }
  document.getElementById("achievement-form-title").textContent = window.i18n.t(
    "Edit achievement #{id}",
    { id: achievement.achievement_id },
  );
  setRecordFormMode(
    achievementRecordForm,
    "edit-achievement-button",
    "delete-achievement-button",
    true,
    false,
    "Edit achievement",
  );
}

async function loadAchievements(gameId, preferredAchievementId) {
  achievementRecordSelect.replaceChildren();
  achievementRecords = [];
  if (!gameId) {
    clearAchievementForm();
    return;
  }
  const response = await fetch(`/games/${gameId}/achievements?skip=0&limit=100`);
  achievementRecords = await readApiResponse(response);
  for (const achievement of achievementRecords) {
    const option = document.createElement("option");
    option.value = achievement.achievement_id;
    option.textContent = `${achievement.title} (#${achievement.achievement_id})`;
    achievementRecordSelect.append(option);
  }
  if (achievementRecords.length) {
    const selectedId = achievementRecords.some(
      (record) => String(record.achievement_id) === String(preferredAchievementId),
    ) ? String(preferredAchievementId) : String(achievementRecords[0].achievement_id);
    achievementRecordSelect.value = selectedId;
    selectAchievementRecord(selectedId);
  } else {
    clearAchievementForm();
  }
}

async function loadRecordGames(preferredGameId) {
  recordsStatus.textContent = "Loading records...";
  window.setStatusLoading(recordsStatus, true);
  try {
    const response = await fetch("/games?skip=0&limit=100");
    gameRecords = await readApiResponse(response);
    renderGameSelectors(preferredGameId);
    await loadAchievements(achievementGameSelect.value);
    recordsStatus.textContent = gameRecords.length ? "" : "No games yet. Create the first game to add achievements.";
  } catch (error) {
    recordsStatus.textContent = error.message;
    throw error;
  } finally {
    window.setStatusLoading(recordsStatus, false);
  }
}

function gameFormPayload() {
  const values = new FormData(gameRecordForm);
  return {
    title: values.get("title").trim(),
    genre: values.get("genre").trim(),
    release_year: Number(values.get("release_year")),
    release_date: values.get("release_date") || null,
    description: values.get("description") || "",
    cover_image_url: values.get("cover_image_url") || "",
    image_url: values.get("image_url") || "",
    screenshot_url: values.get("screenshot_url") || "",
    developer_name: values.get("developer_name") || "",
    publisher_name: values.get("publisher_name") || "",
    website_url: values.get("website_url") || "",
    trailer_url: values.get("trailer_url") || "",
    screenshots: values.get("screenshots").split(/\r?\n/).map((url) => url.trim()).filter(Boolean),
    platforms: values.get("platforms") || "PC",
    gamemodes: values.get("gamemodes") || "all",
    editions: values.get("editions") || "Standard",
    user_rating: Number(values.get("user_rating") || 0),
    critic_rating: Number(values.get("critic_rating") || 0),
    wishlisted: values.get("wishlisted") === "on",
    hoursplayed: Number(values.get("hoursplayed") || 0),
    esrb: values.get("esrb") || null,
    minimum_system_requirements: values.get("minimum_system_requirements").trim() || null,
    recommended_system_requirements: values.get("recommended_system_requirements").trim() || null,
  };
}

function achievementFormPayload() {
  const values = new FormData(achievementRecordForm);
  return {
    title: values.get("title").trim(),
    description: values.get("description") || null,
    image_url: values.get("image_url") || null,
    points: values.get("points") === "" ? null : Number(values.get("points")),
    unlocked: values.get("unlocked") === "on",
    date_unlocked: values.get("date_unlocked") || null,
    status: values.get("status"),
    achievement_type: values.get("achievement_type"),
  };
}

function setRecordTab(tabName, persist = true) {
  const gamesActive = tabName === "games";
  document.getElementById("games-tab").classList.toggle("active", gamesActive);
  document.getElementById("games-tab").setAttribute("aria-selected", String(gamesActive));
  document.getElementById("achievements-tab").classList.toggle("active", !gamesActive);
  document.getElementById("achievements-tab").setAttribute("aria-selected", String(!gamesActive));
  document.getElementById("games-records").hidden = !gamesActive;
  document.getElementById("achievements-records").hidden = gamesActive;
  if (persist) {
    saveDashboardSettings({ ...getDashboardSettings(), recordsTab: gamesActive ? "games" : "achievements" });
  }
}

document.getElementById("toggle-records-button").addEventListener("click", (event) => {
  const button = event.currentTarget;
  const content = document.getElementById("records-content");
  const tabs = document.querySelector(".record-tabs");
  const expanded = button.getAttribute("aria-expanded") === "true";
  content.hidden = expanded;
  tabs.hidden = expanded;
  button.setAttribute("aria-expanded", String(!expanded));
  button.textContent = expanded ? "Show records" : "Hide records";
  saveDashboardSettings({ ...getDashboardSettings(), recordsExpanded: !expanded });
});

gameRecordSelect.addEventListener("change", () => selectGameRecord(gameRecordSelect.value));
document.getElementById("edit-game-button").addEventListener("click", () => {
  const button = document.getElementById("edit-game-button");
  if (button.dataset.editing === "true") {
    selectGameRecord(gameRecordSelect.value);
  } else {
    setRecordFormMode(gameRecordForm, "edit-game-button", "delete-game-button", true, true, "Edit game");
  }
});
document.getElementById("new-game-button").addEventListener("click", () => {
  gameRecordSelect.value = "";
  clearGameForm();
  gameRecordForm.elements.namedItem("title").focus();
});
gameRecordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const gameId = gameRecordSelect.value;
  const editing = Boolean(gameId);
  recordsStatus.textContent = editing ? "Saving game changes..." : "Creating game...";
  try {
    const response = await fetch(editing ? `/games/${gameId}` : "/games", {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gameFormPayload()),
    });
    const saved = await readApiResponse(response);
    showToast(editing ? "Game updated." : "Game created.");
    await loadDashboard();
    await loadRecordGames(saved.id);
    recordsStatus.textContent = "Game saved.";
  } catch (error) {
    recordsStatus.textContent = error.message;
  }
});
document.getElementById("delete-game-button").addEventListener("click", async () => {
  const gameId = gameRecordSelect.value;
  const game = gameRecords.find((record) => String(record.id) === gameId);
  if (!game || !window.confirm(window.i18n.t("Delete {title} and its achievements?", { title: game.title }))) return;
  recordsStatus.textContent = "Deleting game...";
  try {
    await readApiResponse(await fetch(`/games/${gameId}`, { method: "DELETE" }));
    showToast("Game deleted.");
    await loadRecordGames();
    await loadDashboard();
    recordsStatus.textContent = "Game deleted.";
  } catch (error) {
    recordsStatus.textContent = error.message;
  }
});

achievementGameSelect.addEventListener("change", async () => {
  recordsStatus.textContent = "Loading achievements...";
  window.setStatusLoading(recordsStatus, true);
  try {
    await loadAchievements(achievementGameSelect.value);
    recordsStatus.textContent = "";
  } catch (error) {
    recordsStatus.textContent = error.message;
  } finally {
    window.setStatusLoading(recordsStatus, false);
  }
});
achievementRecordSelect.addEventListener("change", () => selectAchievementRecord(achievementRecordSelect.value));
document.getElementById("edit-achievement-button").addEventListener("click", () => {
  const button = document.getElementById("edit-achievement-button");
  if (button.dataset.editing === "true") {
    selectAchievementRecord(achievementRecordSelect.value);
  } else {
    setRecordFormMode(
      achievementRecordForm,
      "edit-achievement-button",
      "delete-achievement-button",
      true,
      true,
      "Edit achievement",
    );
  }
});
document.getElementById("new-achievement-button").addEventListener("click", () => {
  achievementRecordSelect.value = "";
  clearAchievementForm();
  achievementRecordForm.elements.namedItem("title").focus();
});
achievementRecordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const gameId = achievementGameSelect.value;
  if (!gameId) {
    recordsStatus.textContent = "Create a game before adding achievements.";
    return;
  }
  const achievementId = achievementRecordSelect.value;
  const editing = Boolean(achievementId);
  recordsStatus.textContent = editing ? "Saving achievement changes..." : "Creating achievement...";
  try {
    const path = `/games/${gameId}/achievements${editing ? `/${achievementId}` : ""}`;
    const response = await fetch(path, {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(achievementFormPayload()),
    });
    const saved = await readApiResponse(response);
    showToast(editing ? "Achievement updated." : "Achievement created.");
    await loadDashboard();
    achievementGameSelect.value = gameId;
    await loadAchievements(gameId, saved.achievement_id);
    recordsStatus.textContent = "Achievement saved.";
  } catch (error) {
    recordsStatus.textContent = error.message;
  }
});
document.getElementById("delete-achievement-button").addEventListener("click", async () => {
  const gameId = achievementGameSelect.value;
  const achievementId = achievementRecordSelect.value;
  const achievement = achievementRecords.find((record) => String(record.achievement_id) === achievementId);
  if (!achievement || !window.confirm(window.i18n.t("Delete achievement {title}?", { title: achievement.title }))) return;
  recordsStatus.textContent = "Deleting achievement...";
  try {
    await readApiResponse(await fetch(`/games/${gameId}/achievements/${achievementId}`, { method: "DELETE" }));
    showToast("Achievement deleted.");
    await loadAchievements(gameId);
    await loadDashboard();
    recordsStatus.textContent = "Achievement deleted.";
  } catch (error) {
    recordsStatus.textContent = error.message;
  }
});
for (const form of [gameRecordForm, achievementRecordForm]) {
  form.addEventListener("input", () => dirtyRecordForms.add(form));
}

// The library's Edit button links to /admin?edit-game=<id>; open that game ready to edit.
let requestedGameId = new URLSearchParams(window.location.search).get("edit-game");
function openRequestedGame() {
  // Wait until an administrator is signed in and the records have loaded.
  if (!requestedGameId || dashboardView.hidden) return;
  const gameId = requestedGameId;
  requestedGameId = null;
  const url = new URL(window.location.href);
  url.searchParams.delete("edit-game");
  window.history.replaceState(null, "", url);
  if (!gameRecords.some((game) => String(game.id) === gameId)) {
    showToast("That game is no longer in the library.");
    return;
  }
  const recordsToggle = document.getElementById("toggle-records-button");
  if (recordsToggle.getAttribute("aria-expanded") !== "true") recordsToggle.click();
  setRecordTab("games", false);
  gameRecordSelect.value = gameId;
  selectGameRecord(gameId);
  setRecordFormMode(gameRecordForm, "edit-game-button", "delete-game-button", true, true, "Edit game");
  document.getElementById("records-panel").scrollIntoView({ block: "start" });
  gameRecordForm.elements.namedItem("title").focus({ preventScroll: true });
}

// Another admin (or the library page) changed the collection: refresh the numbers.
function scheduleLiveRefresh() {
  clearTimeout(liveRefreshTimer);
  liveRefreshTimer = setTimeout(async () => {
    const hadUnsavedChanges = dirtyRecordForms.size > 0;
    await loadDashboard();
    if (hadUnsavedChanges) showToast("The library changed in another session. Your unsaved edits were kept.");
  }, 500);
}
window.realtime?.on("gameChanged", scheduleLiveRefresh);
window.realtime?.on("achievementChanged", scheduleLiveRefresh);
window.realtime?.onReconnected(scheduleLiveRefresh);

document.getElementById("games-tab").addEventListener("click", () => setRecordTab("games"));
document.getElementById("achievements-tab").addEventListener("click", () => setRecordTab("achievements"));

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(svgNamespace, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

function renderReleaseChart(items) {
  const chart = document.getElementById("release-chart");
  const empty = document.getElementById("release-empty");
  chart.replaceChildren();
  empty.hidden = items.length > 0;
  chart.hidden = items.length === 0;
  if (!items.length) return;

  const width = 720;
  const height = 220;
  const left = 35;
  const right = 12;
  const top = 18;
  const bottom = 34;
  const chartHeight = height - top - bottom;
  const maximum = Math.max(...items.map((item) => item.count), 1);
  const stepX = items.length === 1 ? 0 : (width - left - right) / (items.length - 1);
  const points = items.map((item, index) => ({
    x: items.length === 1 ? width / 2 : left + index * stepX,
    y: top + chartHeight - (item.count / maximum) * chartHeight,
    ...item,
  }));

  for (let index = 0; index < 4; index += 1) {
    const y = top + (chartHeight / 3) * index;
    chart.append(svgElement("line", { x1: left, y1: y, x2: width - right, y2: y, class: "chart-gridline" }));
  }

  if (points.length > 1) {
    const area = `${points[0].x},${height - bottom} ${points.map((point) => `${point.x},${point.y}`).join(" ")} ${points.at(-1).x},${height - bottom}`;
    chart.append(svgElement("polygon", { points: area, class: "chart-area" }));
    chart.append(svgElement("polyline", { points: points.map((point) => `${point.x},${point.y}`).join(" "), class: "chart-line" }));
  }

  for (const point of points) {
    const dot = svgElement("circle", { cx: point.x, cy: point.y, r: 4, class: "chart-point" });
    const title = svgElement("title");
    title.textContent = `${point.label}: ${point.count} game${point.count === 1 ? "" : "s"}`;
    dot.append(title);
    chart.append(dot);
    const label = svgElement("text", { x: point.x, y: height - 8, class: "chart-year", "text-anchor": "middle" });
    label.textContent = point.label;
    chart.append(label);
  }
}

function renderBars(targetId, items) {
  const target = document.getElementById(targetId);
  target.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "No data to chart yet.";
    target.append(empty);
    return;
  }

  const maximum = Math.max(...items.map((item) => item.count), 1);
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "bar-row";
    const label = document.createElement("span");
    label.className = "bar-label";
    label.textContent = item.label;
    const track = document.createElement("span");
    track.className = "bar-track";
    const fill = document.createElement("span");
    fill.className = "bar-fill";
    fill.style.width = `${Math.max(4, (item.count / maximum) * 100)}%`;
    track.append(fill);
    const count = document.createElement("strong");
    count.textContent = item.count;
    row.append(label, track, count);
    target.append(row);
  }
}

function renderRecentGames(items) {
  const target = document.getElementById("recent-games");
  const empty = document.getElementById("recent-empty");
  target.replaceChildren();
  empty.hidden = items.length > 0;
  for (const game of items) {
    const row = document.createElement("tr");
    const title = document.createElement("td");
    title.className = "recent-title";
    title.textContent = game.title;
    const year = document.createElement("td");
    year.textContent = game.release_year || "Not set";
    const record = document.createElement("td");
    const link = document.createElement("a");
    link.href = "/library";
    link.textContent = `#${game.id}`;
    link.setAttribute("aria-label", `View game ${game.title} in the game shelf`);
    record.append(link);
    row.append(title, year, record);
    target.append(row);
  }
}

function getDashboardSettings() {
  const defaults = {
    showRecentGames: true,
    showReleaseChart: true,
    compactView: false,
    autoRefreshSeconds: 0,
    recordsExpanded: true,
    recordsTab: "games",
  };

  try {
    const stored = JSON.parse(localStorage.getItem(settingsStorageKey) || "null");
    return {
      ...defaults,
      ...(stored || {}),
      recordsTab: stored?.recordsTab === "achievements" ? "achievements" : "games",
    };
  } catch {
    return defaults;
  }
}

function saveDashboardSettings(settings) {
  try {
    localStorage.setItem(settingsStorageKey, JSON.stringify(settings));
  } catch {
    // Ignore storage failures gracefully.
  }
}

function applyDashboardSettings() {
  const settings = getDashboardSettings();
  const recentSection = document.querySelector(".recent-section");
  const releasePanel = document.querySelector(".release-panel");
  const recordsContent = document.getElementById("records-content");
  const recordsToggle = document.getElementById("toggle-records-button");
  const recordTabs = document.querySelector(".record-tabs");
  const compactViewEnabled = document.body.classList.contains("compact-dashboard");

  if (recentSection) recentSection.hidden = !settings.showRecentGames;
  if (releasePanel) releasePanel.hidden = !settings.showReleaseChart;
  setRecordTab(settings.recordsTab, false);
  if (recordsContent && recordsToggle) {
    recordsContent.hidden = !settings.recordsExpanded;
    recordTabs.hidden = !settings.recordsExpanded;
    recordsToggle.setAttribute("aria-expanded", String(settings.recordsExpanded));
    recordsToggle.textContent = settings.recordsExpanded ? "Hide records" : "Show records";
  }

  if (settings.compactView) {
    document.body.classList.add("compact-dashboard");
  } else {
    document.body.classList.remove("compact-dashboard");
  }

  if (settingsForm) {
    settingsForm.querySelector('[name="showRecentGames"]').checked = settings.showRecentGames;
    settingsForm.querySelector('[name="showReleaseChart"]').checked = settings.showReleaseChart;
    settingsForm.querySelector('[name="compactView"]').checked = settings.compactView;
    settingsForm.querySelector('[name="autoRefreshSeconds"]').value = String(settings.autoRefreshSeconds);
  }

  if (compactViewEnabled !== settings.compactView) {
    document.body.classList.toggle("compact-dashboard", settings.compactView);
  }

  if (dashboardRefreshTimer) {
    clearInterval(dashboardRefreshTimer);
    dashboardRefreshTimer = null;
  }

  if (Number(settings.autoRefreshSeconds) > 0) {
    dashboardRefreshTimer = window.setInterval(() => {
      loadDashboard();
    }, Number(settings.autoRefreshSeconds) * 1000);
  }
}

function renderDashboard(data) {
  const overview = data.overview;
  document.getElementById("metric-games").textContent = overview.games;
  document.getElementById("metric-hours").textContent = overview.hours_played.toLocaleString();
  document.getElementById("metric-rating").textContent = overview.average_user_rating.toFixed(1);
  document.getElementById("critic-rating").textContent = window.i18n.t("Critic average {rating} / 100", {
    rating: overview.average_critic_rating.toFixed(1),
  });
  document.getElementById("metric-wishlist").textContent = overview.wishlist;
  document.getElementById("achievement-count").textContent = window.i18n.t("{count} TOTAL", {
    count: overview.achievements,
  });
  document.getElementById("completion-value").textContent = `${overview.achievement_completion}%`;
  document.getElementById("completion-ring").style.setProperty("--completion", `${overview.achievement_completion}%`);
  document.getElementById("completion-ring").setAttribute(
    "aria-label",
    window.i18n.t("{percent}% of achievements unlocked", { percent: overview.achievement_completion }),
  );
  document.getElementById("unlocked-count").textContent = overview.unlocked_achievements;
  document.getElementById("locked-count").textContent = overview.achievements - overview.unlocked_achievements;
  document.getElementById("footer-summary").textContent = window.i18n.t(
    "{games} TITLES / {achievements} ACHIEVEMENTS",
    { games: overview.games, achievements: overview.achievements },
  );
  renderReleaseChart(data.release_years);
  renderBars("achievement-type-chart", data.achievement_types);
  renderBars("genre-chart", data.genres);
  renderBars("platform-chart", data.platforms);
  renderRecentGames(data.recent_games);
}

async function fetchProfile() {
  const response = await fetch("/users");
  return response.ok ? response.json() : null;
}

const developmentPanel = document.getElementById("development-panel");
const skipTwoFactorInput = document.getElementById("setting-skip-two-factor");
const developmentStatus = document.getElementById("development-status");

function renderDevelopmentSettings(state) {
  developmentPanel.dataset.active = String(state.active);
  document.getElementById("development-mode-badge").textContent = state.dev_mode ? "DEVELOPMENT" : "PRODUCTION";
  skipTwoFactorInput.checked = state.enabled;
  // Leave a saved "on" switchable to off, even when the server is no longer in development mode.
  skipTwoFactorInput.disabled = !state.dev_mode && !state.enabled;
  if (state.active) {
    developmentStatus.textContent = "Two-step sign-in is skipped for every account. Turn this off when you are done.";
  } else if (state.enabled) {
    developmentStatus.textContent = "Saved as on, but ignored: this server is not in development mode.";
  } else {
    developmentStatus.textContent = "";
  }
}

async function loadDevelopmentSettings() {
  try {
    renderDevelopmentSettings(await readApiResponse(await fetch("/admin/development/two-factor")));
  } catch (error) {
    developmentStatus.textContent = error.message;
  }
}

skipTwoFactorInput.addEventListener("change", async () => {
  const enabled = skipTwoFactorInput.checked;
  skipTwoFactorInput.disabled = true;
  try {
    const state = await readApiResponse(await fetch("/admin/development/two-factor", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }));
    renderDevelopmentSettings(state);
    showToast(enabled ? "Two-step sign-in is now skipped." : "Two-step sign-in is required again.");
  } catch (error) {
    skipTwoFactorInput.checked = !enabled;
    skipTwoFactorInput.disabled = false;
    developmentStatus.textContent = error.message;
  }
});

if (settingsForm) {
  settingsForm.addEventListener("change", () => {
    const formData = new FormData(settingsForm);
    const settings = {
      ...getDashboardSettings(),
      showRecentGames: formData.get("showRecentGames") === "on",
      showReleaseChart: formData.get("showReleaseChart") === "on",
      compactView: formData.get("compactView") === "on",
      autoRefreshSeconds: Number(formData.get("autoRefreshSeconds") || 0),
    };
    saveDashboardSettings(settings);
    applyDashboardSettings();
  });
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = loginForm.querySelector("[type=submit]");
  submitButton.disabled = true;
  loginStatus.textContent = "Signing in...";
  window.setStatusLoading(loginStatus, true);
  try {
    const response = await fetch("/auth/token", {
      method: "POST",
      body: new URLSearchParams(new FormData(loginForm)),
    });
    if (!response.ok) {
      if (response.status === 429) {
        const body = await response.json();
        window.startLoginLockout(
          loginStatus,
          submitButton,
          Number(response.headers.get("Retry-After")) || 60,
          body.detail || "Login is temporarily locked.",
        );
      } else {
        loginStatus.textContent = "Incorrect username or password.";
      }
      return;
    }
    const result = await response.json();
    if (result.two_factor_required) {
      loginStatus.textContent = "Waiting for your sign-in code...";
      if (!(await window.twoFactorLogin.complete(result))) {
        loginStatus.textContent = "Sign-in cancelled.";
        return;
      }
    }
    const profile = await fetchProfile();
    if (!profile) {
      loginStatus.textContent = "Your profile could not be loaded.";
      return;
    }
    showDashboard(profile.username, profile.role);
    applyDashboardSettings();
    await loadDashboard();
    openRequestedGame();
  } catch {
    loginStatus.textContent = "The server could not be reached.";
  } finally {
    window.setStatusLoading(loginStatus, false);
    if (!window.isLoginLocked(submitButton)) submitButton.disabled = false;
  }
});

refreshButton.addEventListener("click", loadDashboard);
logoutButton.addEventListener("click", async () => {
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    showLogin("You have been signed out.");
  }
});

window.initRegistration({
  loginForm,
  registerForm: document.getElementById("register-form"),
  switchButton: document.getElementById("auth-switch"),
  onRegistered: (username) => {
    loginForm.elements.namedItem("username").value = username;
    loginStatus.textContent = window.i18n.t(
      "Account {username} created. It can browse the library; an administrator must grant dashboard access.",
      { username },
    );
  },
});
initRichTextEditors();
applyDashboardSettings();

fetchProfile()
  .then((profile) => {
    if (!profile) {
      showLogin();
      return;
    }
    showDashboard(profile.username, profile.role);
    applyDashboardSettings();
    return loadDashboard().then(openRequestedGame);
  })
  .catch(() => showLogin("The server could not be reached."));