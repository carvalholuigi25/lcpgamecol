// The moderation queue and rules (/admin/moderation), served by routes/games/moderation.py.
const accessView = document.getElementById("access-view");
const moderationView = document.getElementById("moderation-view");
const accountName = document.getElementById("account-name");
const logoutButton = document.getElementById("logout-button");
const queueList = document.getElementById("queue-list");
const queueStatus = document.getElementById("queue-status");
const rulesForm = document.getElementById("rules-form");
const rulesStatus = document.getElementById("rules-status");
const toastRegion = document.getElementById("toast-region");
const STATUS_LABELS = { pending: "Waiting for review", hidden: "Hidden", visible: "Visible" };
const REASON_LABELS = { spam: "Spam", offensive: "Offensive", spoilers: "Spoilers", off_topic: "Off topic", other: "Other" };
let refreshTimer = null;
let toastTimer = null;

function showToast(message) {
  toastRegion.textContent = window.i18n.t(message);
  toastRegion.classList.add("is-visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastRegion.classList.remove("is-visible"), 3600);
}

function showAccess(message) {
  moderationView.hidden = true;
  accessView.hidden = false;
  document.getElementById("access-message").textContent = message;
  accountName.textContent = "";
  logoutButton.hidden = true;
  window.adminSidebar?.setAvailable(false);
}

async function readError(response, fallback) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg.replace(/^Value error, /, "");
    return fallback;
  } catch {
    return fallback;
  }
}

async function requestJson(path, options = {}, fallback = "The request failed.") {
  const response = await fetch(path, {
    ...options,
    headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!response.ok) throw new Error(await readError(response, fallback));
  return response.status === 204 ? null : response.json();
}

function formatDate(value) {
  const locale = { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR", it: "it-IT", es: "es-ES", ja: "ja-JP" }[window.i18n.language];
  return value ? new Date(value).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// User-written text, left alone by i18n.js.
function userText(tag, className, text) {
  const node = element(tag, className, text);
  node.setAttribute("translate", "no");
  return node;
}

// Rich text is shown as plain text here: enough to judge it, and nothing in it can run.
function postText(body) {
  if (!body) return "";
  if (!/<[a-z][\s\S]*>/i.test(body)) return body;
  const source = new DOMParser().parseFromString(body.replace(/<\/(p|li|blockquote)>/gi, "\n$&"), "text/html");
  return source.body.textContent.trim();
}

function queueCard(item) {
  const card = element("li", "feedback-card moderation-card");
  card.dataset.status = item.status;
  const head = element("div", "feedback-card-head");
  head.append(
    userText("strong", "feedback-subject", item.game_title),
    element("span", `role-badge moderation-status-${item.status}`, window.i18n.t(STATUS_LABELS[item.status] || item.status)),
    element("span", "role-badge", window.i18n.t(item.kind === "review" ? "Review" : "Comment")),
  );
  if (item.open_reports) {
    head.append(element("span", "role-badge moderation-reports",
      window.i18n.t(item.open_reports === 1 ? "{count} report" : "{count} reports", { count: item.open_reports })));
  }
  const meta = element("p", "feedback-meta");
  meta.append(userText("strong", "", item.display_name || item.username), " · ", userText("span", "", formatDate(item.created_at)));
  if (item.rating) meta.append(" · ", userText("span", "", "★".repeat(item.rating)));
  card.append(head, meta, userText("p", "feedback-text", postText(item.body) || "—"));

  if (item.reports.length) {
    const reports = element("ul", "moderation-report-list");
    for (const report of item.reports) {
      const line = element("li");
      line.append(
        userText("strong", "", report.reporter), " · ",
        element("span", "", window.i18n.t(REASON_LABELS[report.reason] || report.reason)),
      );
      if (report.details) line.append(" — ", userText("span", "", report.details));
      reports.append(line);
    }
    card.append(reports);
  }

  const tools = element("div", "feedback-manage moderation-tools");
  const note = element("input", "moderation-note");
  note.maxLength = 300;
  note.placeholder = "Note to the author (optional)";
  note.setAttribute("aria-label", "Note to the author (optional)");
  const actions = element("div", "upload-actions");
  const buttons = [
    ["approve", "primary-button", "Approve", "Approved. Everyone can see it again."],
    ["hide", "secondary-button", "Hide", "Hidden from everyone but the author."],
    ["remove", "danger-button", "Delete", "Deleted. The author was told."],
  ];
  for (const [action, className, label, done] of buttons) {
    if (action === "hide" && item.status === "hidden") continue;
    const button = element("button", className, label);
    button.type = "button";
    button.addEventListener("click", async () => {
      if (action === "remove" && !window.confirm(window.i18n.t("Delete this post for good?"))) return;
      for (const other of actions.querySelectorAll("button")) other.disabled = true;
      try {
        await requestJson(`/admin/moderation/${item.kind}/${item.id}/${action}`, {
          method: "POST",
          body: JSON.stringify({ note: note.value.trim() || null }),
        }, "The post could not be updated.");
        showToast(done);
        await loadQueue();
      } catch (error) {
        queueStatus.textContent = window.i18n.t(error.message);
        for (const other of actions.querySelectorAll("button")) other.disabled = false;
      }
    });
    actions.append(button);
  }
  tools.append(note, actions);
  card.append(tools);
  return card;
}

async function loadQueue() {
  try {
    const result = await requestJson("/admin/moderation/queue", {}, "The moderation queue could not be loaded.");
    queueList.replaceChildren(...result.items.map(queueCard));
    document.getElementById("queue-empty").hidden = result.items.length > 0;
    document.getElementById("queue-count").textContent = window.i18n.t("{count} IN THE QUEUE", { count: result.items.length });
    document.getElementById("metric-pending").textContent = result.counts.pending;
    document.getElementById("metric-reported").textContent = result.counts.reported;
    document.getElementById("metric-hidden").textContent = result.counts.hidden;
    queueStatus.textContent = "";
  } catch (error) {
    queueStatus.textContent = window.i18n.t(error.message);
  }
}

function fillRules(rules) {
  rulesForm.elements.namedItem("blocked_words").value = rules.blocked_words.join("\n");
  rulesForm.elements.namedItem("blocked_words_action").value = rules.blocked_words_action;
  rulesForm.elements.namedItem("report_threshold").value = rules.report_threshold;
  document.getElementById("metric-words").textContent = rules.blocked_words.length;
}

async function loadRules() {
  fillRules(await requestJson("/admin/moderation/settings", {}, "The moderation rules could not be loaded."));
}

rulesForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(rulesForm);
  const button = rulesForm.querySelector('[type="submit"]');
  button.disabled = true;
  rulesStatus.textContent = "";
  try {
    fillRules(await requestJson("/admin/moderation/settings", {
      method: "PUT",
      body: JSON.stringify({
        blocked_words: String(data.get("blocked_words")).split("\n"),
        blocked_words_action: data.get("blocked_words_action"),
        report_threshold: Number(data.get("report_threshold")),
      }),
    }, "The moderation rules could not be saved."));
    showToast("Moderation rules saved.");
  } catch (error) {
    rulesStatus.textContent = window.i18n.t(error.message);
  } finally {
    button.disabled = false;
  }
});

function scheduleRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer);
  // Don't throw away a note an administrator is typing; try again a little later.
  const typing = document.activeElement?.classList.contains("moderation-note") && document.activeElement.value;
  refreshTimer = window.setTimeout(typing ? scheduleRefresh : loadQueue, typing ? 5000 : 300);
}

logoutButton.addEventListener("click", async () => {
  await window.realtime?.stop();
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/admin");
  }
});

document.addEventListener("languagechange", loadQueue);

async function initModeration() {
  try {
    const response = await fetch("/users");
    if (!response.ok) {
      showAccess("Sign in with an administrator account to moderate reviews and comments.");
      return;
    }
    const principal = await response.json();
    if (principal.role !== "admin") {
      showAccess("This account does not have administrator access.");
      return;
    }
    accessView.hidden = true;
    moderationView.hidden = false;
    accountName.textContent = principal.username;
    logoutButton.hidden = false;
    window.adminSidebar?.setAvailable(true, principal.role);
    await Promise.all([loadQueue(), loadRules()]);
    window.realtime?.on("moderationChanged", scheduleRefresh);
    window.realtime?.onReconnected(loadQueue);
    window.realtime?.start();
  } catch (error) {
    showAccess(error.message === "Failed to fetch" ? "The server could not be reached." : error.message);
  }
}

initModeration();
