// The feedback page (/feedback), served by routes/users/feedback.py. Everyone can send
// feedback and follow the replies; administrators also get the "All feedback" panel
// where they change its status and reply (replies are emailed when the user has an address).
const accessView = document.getElementById("access-view");
const feedbackView = document.getElementById("feedback-view");
const accountName = document.getElementById("account-name");
const logoutButton = document.getElementById("logout-button");
const feedbackForm = document.getElementById("feedback-form");
const formStatus = document.getElementById("feedback-form-status");
const myList = document.getElementById("my-feedback");
const myStatus = document.getElementById("my-feedback-status");
const managePanel = document.getElementById("manage");
const manageList = document.getElementById("manage-list");
const manageStatus = document.getElementById("manage-status");
const toastRegion = document.getElementById("toast-region");
const CATEGORY_LABELS = { bug: "Bug report", idea: "Idea", question: "Question", praise: "Praise", other: "Other" };
const STATUS_LABELS = { open: "Open", in_progress: "In progress", answered: "Answered", closed: "Closed" };
const EMAIL_STATUS_LABELS = {
  sent: "Reply emailed to the user.",
  saved: "Reply saved to the mail outbox folder.",
  no_address: "Not emailed: the user has no email address.",
  disabled: "Not emailed: email is not set up on the server.",
  failed: "The reply email could not be sent.",
};
let principal = null;
let myFeedback = [];
let allFeedback = { items: [], counts: {}, email_enabled: false };
let manageFilter = "";
let toastTimer = null;
let refreshTimer = null;

function showToast(message) {
  toastRegion.textContent = message;
  toastRegion.classList.add("is-visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastRegion.classList.remove("is-visible"), 3600);
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

function locale() {
  return { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR", it: "it-IT", es: "es-ES", ja: "ja-JP" }[window.i18n.language];
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString(locale(), { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function userText(tag, className, text) {
  const node = element(tag, className, text);
  node.setAttribute("translate", "no");
  return node;
}

function badge(text, className = "") {
  return element("span", `role-badge ${className}`.trim(), text);
}

function feedbackCard(item, { manage = false } = {}) {
  const card = element("li", "feedback-card");
  card.dataset.status = item.status;
  const head = element("div", "feedback-card-head");
  head.append(
    userText("strong", "feedback-subject", item.subject),
    badge(STATUS_LABELS[item.status] || item.status, `status-${item.status}`),
    badge(CATEGORY_LABELS[item.category] || item.category),
  );
  const meta = element("p", "feedback-meta");
  if (manage) meta.append(userText("strong", "", item.username), " · ");
  meta.append(userText("span", "", formatDate(item.created_at)));
  if (item.page_url) {
    const page = userText("a", "", item.page_url);
    page.href = item.page_url;
    meta.append(" · ", page);
  }
  card.append(head, meta, userText("p", "feedback-text", item.message));

  if (item.reply && !manage) {
    const reply = element("div", "feedback-reply");
    const heading = element("p", "kicker");
    heading.append(element("span", "", "Reply from"), " ", userText("span", "", item.replied_by), " · ",
      userText("span", "", formatDate(item.replied_at)));
    reply.append(heading, userText("p", "feedback-text", item.reply));
    card.append(reply);
  }
  if (manage) card.append(manageForm(item));
  return card;
}

function manageForm(item) {
  const form = element("form", "feedback-manage");
  const fields = element("div", "record-fields");
  const statusLabel = element("label", "", "Status");
  const status = element("select");
  status.name = "status";
  for (const [value, label] of Object.entries(STATUS_LABELS)) {
    const option = element("option", "", label);
    option.value = value;
    option.selected = value === item.status;
    status.append(option);
  }
  statusLabel.append(status);
  const replyLabel = element("label", "field-wide", "Reply");
  const reply = element("textarea");
  reply.name = "reply";
  reply.rows = 3;
  reply.maxLength = 4000;
  reply.value = item.reply || "";
  reply.setAttribute("translate", "no");
  reply.addEventListener("input", () => { form.dataset.dirty = "true"; });
  status.addEventListener("change", () => { form.dataset.dirty = "true"; });
  replyLabel.append(reply);
  fields.append(statusLabel, replyLabel);

  const note = element("p", "profile-form-hint");
  if (item.replied_at) {
    note.append(element("span", "", "Replied by"), " ", userText("span", "", item.replied_by), " · ",
      userText("span", "", formatDate(item.replied_at)));
    if (item.email_status) note.append(" · ", element("span", "", EMAIL_STATUS_LABELS[item.email_status] || item.email_status));
  }

  const actions = element("div", "upload-actions");
  const save = element("button", "primary-button", "Save");
  save.type = "submit";
  const remove = element("button", "danger-button", "Delete");
  remove.type = "button";
  actions.append(save, remove);
  form.append(fields, note, actions);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    save.disabled = true;
    manageStatus.textContent = "";
    try {
      await requestJson(`/admin/feedback/${item.id}`, {
        method: "PUT",
        // Leaving an unchanged status out lets a new reply mark the feedback as answered.
        body: JSON.stringify({ status: status.value === item.status ? null : status.value, reply: reply.value }),
      }, "The feedback could not be saved.");
      delete form.dataset.dirty;
      showToast(window.i18n.t(reply.value.trim() && reply.value.trim() !== (item.reply || "") ? "Reply sent." : "Feedback updated."));
      await loadAll();
    } catch (error) {
      manageStatus.textContent = window.i18n.t(error.message);
      save.disabled = false;
    }
  });
  remove.addEventListener("click", async () => {
    if (!window.confirm(window.i18n.t("Delete this feedback? This cannot be undone."))) return;
    try {
      await requestJson(`/admin/feedback/${item.id}`, { method: "DELETE" }, "The feedback could not be deleted.");
      showToast(window.i18n.t("Feedback deleted."));
      await loadAll();
    } catch (error) {
      manageStatus.textContent = window.i18n.t(error.message);
    }
  });
  return form;
}

function renderMine() {
  myList.replaceChildren(...myFeedback.map((item) => feedbackCard(item)));
  document.getElementById("my-feedback-empty").hidden = myFeedback.length > 0;
  document.getElementById("my-feedback-count").textContent = myFeedback.length
    ? window.i18n.t("{count} sent", { count: myFeedback.length })
    : "";
}

function renderManage() {
  const items = allFeedback.items.filter((item) => !manageFilter || item.status === manageFilter);
  manageList.replaceChildren(...items.map((item) => feedbackCard(item, { manage: true })));
  document.getElementById("manage-empty").hidden = items.length > 0;
  const total = Object.values(allFeedback.counts).reduce((sum, count) => sum + count, 0);
  for (const counter of document.querySelectorAll("#manage-tabs [data-count]")) {
    const key = counter.dataset.count;
    counter.textContent = `(${key ? allFeedback.counts[key] || 0 : total})`;
  }
  document.getElementById("manage-email-note").textContent = window.i18n.t(
    allFeedback.email_enabled ? "Replies are emailed to users with an address." : "Email is off: replies are only shown in the app.",
  );
}

async function loadMine() {
  myFeedback = await requestJson("/feedback/mine", {}, "Your feedback could not be loaded.");
  renderMine();
}

async function loadManage() {
  allFeedback = await requestJson("/admin/feedback", {}, "The feedback could not be loaded.");
  renderManage();
}

async function loadAll() {
  const tasks = [loadMine().catch((error) => { myStatus.textContent = window.i18n.t(error.message); })];
  if (principal?.role === "admin") {
    tasks.push(loadManage().catch((error) => { manageStatus.textContent = window.i18n.t(error.message); }));
  }
  await Promise.all(tasks);
}

// Several changes can arrive at once (a reply, then its email status), so batch them,
// and never re-render the admin list while a reply is being written.
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    loadMine().catch(() => {});
    if (principal?.role === "admin" && !manageList.querySelector("form[data-dirty]")) loadManage().catch(() => {});
  }, 300);
}

async function loadEmailHint() {
  const hint = document.getElementById("feedback-email-hint");
  try {
    const profile = await requestJson("/users/me/profile");
    if (!profile.email) return;
    hint.replaceChildren(element("span", "", "Replies are also emailed to"), " ", userText("strong", "", profile.email), ".");
  } catch {
    // Keep the default hint.
  }
}

function prefillPage() {
  const input = feedbackForm.elements.page_url;
  const from = new URLSearchParams(window.location.search).get("from");
  let path = from && from.startsWith("/") && !from.startsWith("//") ? from : "";
  if (!path && document.referrer) {
    try {
      const referrer = new URL(document.referrer);
      if (referrer.origin === window.location.origin && referrer.pathname !== "/feedback") path = referrer.pathname;
    } catch {
      // Ignore malformed referrers.
    }
  }
  input.value = path;
}

feedbackForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = document.getElementById("feedback-submit");
  const values = new FormData(feedbackForm);
  submit.disabled = true;
  formStatus.textContent = window.i18n.t("Sending...");
  window.setStatusLoading?.(formStatus, true);
  try {
    await requestJson("/feedback", {
      method: "POST",
      body: JSON.stringify({
        category: values.get("category"),
        subject: values.get("subject"),
        message: values.get("message"),
        page_url: values.get("page_url") || null,
      }),
    }, "Your feedback could not be sent.");
    feedbackForm.reset();
    formStatus.textContent = "";
    showToast(window.i18n.t("Thanks! Your feedback was sent."));
    await loadAll();
  } catch (error) {
    formStatus.textContent = window.i18n.t(error.message);
  } finally {
    window.setStatusLoading?.(formStatus, false);
    submit.disabled = false;
  }
});

document.getElementById("manage-tabs").addEventListener("click", (event) => {
  const tab = event.target.closest("[data-status]");
  if (!tab) return;
  manageFilter = tab.dataset.status;
  for (const other of document.querySelectorAll("#manage-tabs [data-status]")) {
    const active = other === tab;
    other.classList.toggle("active", active);
    other.setAttribute("aria-selected", String(active));
  }
  renderManage();
});

document.addEventListener("languagechange", () => {
  if (!principal) return;
  renderMine();
  if (principal.role === "admin") renderManage();
});

// A notification link to /feedback#manage while already here only changes the hash.
function revealFromHash() {
  if (window.location.hash === "#manage" && !managePanel.hidden) managePanel.scrollIntoView({ behavior: "smooth" });
}
window.addEventListener("hashchange", revealFromHash);

logoutButton.addEventListener("click", async () => {
  await window.realtime?.stop();
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/library");
  }
});

function showAccess(message) {
  feedbackView.hidden = true;
  accessView.hidden = false;
  document.getElementById("access-message").textContent = message;
  accountName.textContent = "";
  logoutButton.hidden = true;
  window.adminSidebar?.setAvailable(false);
}

async function initFeedback() {
  try {
    const response = await fetch("/users");
    if (!response.ok) {
      showAccess("Sign in to send feedback.");
      return;
    }
    principal = await response.json();
    accessView.hidden = true;
    feedbackView.hidden = false;
    accountName.textContent = principal.username;
    logoutButton.hidden = false;
    managePanel.hidden = principal.role !== "admin";
    window.adminSidebar?.setAvailable(true, principal.role);
    prefillPage();
    await Promise.all([loadAll(), loadEmailHint()]);
    revealFromHash();
    window.realtime?.on("feedbackChanged", scheduleRefresh);
    window.realtime?.onReconnected(scheduleRefresh);
    window.realtime?.start();
  } catch (error) {
    showAccess(error.message === "Failed to fetch" ? "The server could not be reached." : error.message);
  }
}

initFeedback();
