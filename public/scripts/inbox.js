// Notifications (bell) and messages (envelope) buttons with their dialogs. Served by
// routes/users/notifications.py and routes/users/messages.py. The buttons go into an
// empty [data-inbox] element: sidebar.js adds one with data-inbox="sidebar" at the top of
// the sidebar, where they look like the other sidebar links. They appear once the user is
// signed in. Live updates arrive through realtime.js (notificationsChanged, messagesChanged).
(() => {
  const mount = document.querySelector("[data-inbox]");
  if (!mount) return;
  const inSidebar = mount.dataset.inbox === "sidebar";

  const ICONS = {
    bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
    mail: "M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm-1 1l9 7 9-7",
    close: "M6 6l12 12M18 6L6 18",
    back: "M15 18l-6-6 6-6",
    trash: "M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3",
    check: "M5 12l5 5L20 7",
    compose: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  };
  const state = {
    started: false,
    starting: null,
    notifications: [],
    notificationsUnread: 0,
    messages: [],
    messagesUnread: 0,
    box: "inbox",
    recipients: null,
  };

  function icon(name) {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name]}" /></svg>`;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // User-written text must not go through the page translator.
  function userText(tag, className, text) {
    const node = element(tag, className, text);
    node.setAttribute("translate", "no");
    return node;
  }

  function iconButton(name, label, className = "inbox-icon-button") {
    const button = element("button", className);
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.innerHTML = icon(name);
    return button;
  }

  function headerButton(kind, iconName, label) {
    const button = iconButton(iconName, label, inSidebar ? "sidebar-button" : "inbox-button");
    if (inSidebar) button.append(element("span", "sidebar-button-label", label));
    button.dataset.inboxOpen = kind;
    const badge = element("span", "inbox-badge");
    badge.hidden = true;
    badge.setAttribute("aria-hidden", "true");
    button.append(badge);
    return button;
  }

  const notificationsButton = headerButton("notifications", "bell", "Notifications");
  const messagesButton = headerButton("messages", "mail", "Messages");
  if (!inSidebar) mount.classList.add("inbox-buttons");
  mount.hidden = true;
  mount.append(notificationsButton, messagesButton);

  // --- dialogs ---------------------------------------------------------------

  function buildDialog(id, title) {
    const dialog = element("dialog", "inbox-dialog");
    dialog.id = id;
    dialog.setAttribute("aria-labelledby", `${id}-title`);
    const header = element("div", "inbox-dialog-header");
    const heading = element("h2", "", title);
    heading.id = `${id}-title`;
    const tools = element("div", "inbox-dialog-tools");
    const close = iconButton("close", "Close");
    close.addEventListener("click", () => dialog.close());
    header.append(heading, tools);
    tools.append(close);
    const status = element("p", "inbox-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    const body = element("div", "inbox-dialog-body");
    dialog.append(header, status, body);
    // Clicking the backdrop (the dialog element itself) closes it.
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    document.body.append(dialog);
    return { dialog, tools, close, status, body };
  }

  const notificationsView = buildDialog("inbox-notifications", "Notifications");
  const markAllButton = element("button", "inbox-text-button", "Mark all as read");
  markAllButton.type = "button";
  notificationsView.tools.prepend(markAllButton);

  const messagesView = buildDialog("inbox-messages", "Messages");
  const composeButton = iconButton("compose", "New message");
  messagesView.tools.prepend(composeButton);

  function setStatus(view, message = "") {
    view.status.textContent = message ? window.i18n.t(message) : "";
  }

  // --- formatting --------------------------------------------------------------

  function locale() {
    return { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR" }[window.i18n?.language] || "en-GB";
  }

  function relativeTime(value) {
    const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
    const units = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
    const format = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" });
    for (const [unit, size] of units) {
      if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
    }
    return window.i18n.t("Just now");
  }

  function timeElement(value) {
    const node = element("time", "inbox-time", relativeTime(value));
    node.dateTime = value;
    node.title = new Date(value).toLocaleString(locale(), { dateStyle: "medium", timeStyle: "short" });
    node.setAttribute("translate", "no");
    return node;
  }

  function setBadge(button, count) {
    const badge = button.querySelector(".inbox-badge");
    const previous = Number(badge.dataset.count || 0);
    badge.dataset.count = String(count);
    badge.hidden = count === 0;
    badge.textContent = count > 99 ? "99+" : String(count);
    const label = button === notificationsButton ? "Notifications" : "Messages";
    const text = count ? window.i18n.t(`${label} ({count} unread)`, { count }) : window.i18n.t(label);
    button.setAttribute("aria-label", text);
    button.title = text;
    if (count > previous) {
      badge.classList.remove("is-new");
      // Restart the pulse animation for each new arrival.
      void badge.offsetWidth;
      badge.classList.add("is-new");
    }
  }

  // --- requests ----------------------------------------------------------------

  async function api(path, options = {}) {
    const init = { ...options, headers: { Accept: "application/json", ...(options.headers || {}) } };
    if (options.json !== undefined) {
      init.body = JSON.stringify(options.json);
      init.headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, init);
    if (response.status === 401) {
      stop();
      throw new Error("Your session has ended. Sign in again.");
    }
    if (!response.ok) {
      let detail = "Something went wrong. Try again.";
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
        else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg.replace(/^Value error, /, "");
      } catch {
        // Keep the generic message.
      }
      throw new Error(detail);
    }
    return response.status === 204 ? null : response.json();
  }

  // --- notifications -------------------------------------------------------------

  async function loadNotifications() {
    const data = await api("/notifications?limit=50");
    state.notifications = data.items;
    state.notificationsUnread = data.unread;
    setBadge(notificationsButton, data.unread);
    if (notificationsView.dialog.open) renderNotifications();
  }

  function renderNotifications() {
    const { body } = notificationsView;
    markAllButton.disabled = state.notificationsUnread === 0;
    if (!state.notifications.length) {
      body.replaceChildren(element("p", "inbox-empty", "You're all caught up."));
      return;
    }
    const list = element("ul", "inbox-list");
    for (const notification of state.notifications) {
      const item = element("li", `inbox-item${notification.read ? "" : " is-unread"}`);
      item.dataset.kind = notification.kind;
      const open = element("button", "inbox-item-main");
      open.type = "button";
      const title = element("strong", "inbox-item-title", notification.title);
      open.append(title);
      if (notification.body) open.append(userText("span", "inbox-item-preview", notification.body));
      open.append(timeElement(notification.created_at));
      open.addEventListener("click", () => openNotification(notification));
      const remove = iconButton("trash", "Delete notification");
      remove.addEventListener("click", () => deleteNotification(notification));
      item.append(open, remove);
      list.append(item);
    }
    body.replaceChildren(list);
  }

  async function openNotification(notification) {
    try {
      if (!notification.read) await api(`/notifications/${notification.id}/read`, { method: "POST" });
    } catch (error) {
      setStatus(notificationsView, error.message);
      return;
    }
    if (!notification.link) {
      await loadNotifications().catch(() => {});
      return;
    }
    const target = new URL(notification.link, window.location.origin);
    const inbox = target.searchParams.get("inbox");
    if (inbox && target.pathname === window.location.pathname) {
      notificationsView.dialog.close();
      open(inbox);
    } else if (target.pathname === window.location.pathname && target.hash) {
      notificationsView.dialog.close();
      window.location.hash = target.hash;
      document.dispatchEvent(new CustomEvent("inbox:navigate", { detail: { hash: target.hash } }));
    } else {
      window.location.assign(target.pathname + target.search + target.hash);
    }
    loadNotifications().catch(() => {});
  }

  async function deleteNotification(notification) {
    try {
      await api(`/notifications/${notification.id}`, { method: "DELETE" });
      await loadNotifications();
    } catch (error) {
      setStatus(notificationsView, error.message);
    }
  }

  markAllButton.addEventListener("click", async () => {
    try {
      await api("/notifications/read-all", { method: "POST" });
      await loadNotifications();
    } catch (error) {
      setStatus(notificationsView, error.message);
    }
  });

  // --- messages ------------------------------------------------------------------

  async function loadMessages() {
    const data = await api(`/messages?box=${state.box}`);
    state.messages = data.items;
    state.messagesUnread = data.unread;
    setBadge(messagesButton, data.unread);
  }

  async function refreshMessageCount() {
    const data = await api("/messages?box=inbox&limit=1");
    state.messagesUnread = data.unread;
    setBadge(messagesButton, data.unread);
  }

  function tabs() {
    const bar = element("div", "inbox-tabs");
    bar.setAttribute("role", "tablist");
    for (const [box, label] of [["inbox", "Inbox"], ["sent", "Sent"]]) {
      const tab = element("button", "inbox-tab", label);
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(state.box === box));
      if (box === "inbox" && state.messagesUnread) {
        tab.append(" ", element("span", "inbox-count", String(state.messagesUnread)));
      }
      tab.addEventListener("click", () => showMessageList(box));
      bar.append(tab);
    }
    return bar;
  }

  function renderMessageList() {
    const { body } = messagesView;
    if (!state.messages.length) {
      const empty = element("p", "inbox-empty", state.box === "inbox" ? "No messages yet." : "You haven't sent any messages.");
      body.replaceChildren(tabs(), empty);
      return;
    }
    const list = element("ul", "inbox-list");
    for (const message of state.messages) {
      const unread = message.incoming && !message.read;
      const item = element("li", `inbox-item${unread ? " is-unread" : ""}`);
      const open = element("button", "inbox-item-main");
      open.type = "button";
      const who = element("span", "inbox-item-who");
      who.append(
        element("span", "", message.incoming ? "From" : "To"), " ",
        userText("span", "", message.incoming ? message.sender : message.recipient),
      );
      open.append(who, userText("strong", "inbox-item-title", message.subject));
      open.append(userText("span", "inbox-item-preview", message.body));
      open.append(timeElement(message.created_at));
      open.addEventListener("click", () => showMessage(message));
      item.append(open);
      list.append(item);
    }
    body.replaceChildren(tabs(), list);
  }

  async function showMessageList(box = state.box) {
    state.box = box;
    setStatus(messagesView);
    try {
      await loadMessages();
      renderMessageList();
    } catch (error) {
      setStatus(messagesView, error.message);
    }
  }

  function backButton() {
    const button = element("button", "inbox-text-button inbox-back");
    button.type = "button";
    button.innerHTML = icon("back");
    button.append(element("span", "", "Back to messages"));
    button.addEventListener("click", () => showMessageList());
    return button;
  }

  async function showMessage(message) {
    setStatus(messagesView);
    const article = element("article", "inbox-message");
    const heading = userText("h3", "", message.subject);
    const meta = element("p", "inbox-message-meta");
    meta.append(
      element("span", "", message.incoming ? "From" : "To"), " ",
      userText("strong", "", message.incoming ? message.sender : message.recipient), " · ",
      timeElement(message.created_at),
    );
    const text = userText("div", "inbox-message-body", message.body);
    const actions = element("div", "inbox-actions");
    if (message.incoming) {
      const reply = element("button", "inbox-primary", "Reply");
      reply.type = "button";
      reply.addEventListener("click", () => showCompose({
        recipient: message.sender,
        subject: /^re:/i.test(message.subject) ? message.subject : `Re: ${message.subject}`,
        replyTo: message.id,
      }));
      actions.append(reply);
    }
    const remove = element("button", "inbox-secondary", "Delete");
    remove.type = "button";
    remove.addEventListener("click", async () => {
      try {
        await api(`/messages/${message.id}`, { method: "DELETE" });
        await showMessageList();
      } catch (error) {
        setStatus(messagesView, error.message);
      }
    });
    actions.append(remove);
    article.append(heading, meta, text, actions);
    messagesView.body.replaceChildren(backButton(), article);

    if (message.incoming && !message.read) {
      try {
        const result = await api(`/messages/${message.id}/read`, { method: "POST" });
        message.read = true;
        state.messagesUnread = result.unread;
        setBadge(messagesButton, result.unread);
      } catch (error) {
        setStatus(messagesView, error.message);
      }
    }
  }

  async function loadRecipients() {
    if (!state.recipients) state.recipients = await api("/messages/recipients");
    return state.recipients;
  }

  function field(label, control) {
    const wrapper = element("label", "inbox-field");
    wrapper.append(element("span", "", label), control);
    return wrapper;
  }

  async function showCompose({ recipient = "", subject = "", replyTo = null } = {}) {
    setStatus(messagesView);
    const form = element("form", "inbox-compose");
    const to = element("input");
    to.name = "recipient";
    to.required = true;
    to.maxLength = 64;
    to.autocomplete = "off";
    to.value = recipient;
    to.setAttribute("list", "inbox-recipients");
    to.setAttribute("translate", "no");
    const options = element("datalist");
    options.id = "inbox-recipients";
    const subjectInput = element("input");
    subjectInput.name = "subject";
    subjectInput.required = true;
    subjectInput.maxLength = 120;
    subjectInput.value = subject;
    subjectInput.setAttribute("translate", "no");
    const text = element("textarea");
    text.name = "body";
    text.required = true;
    text.maxLength = 4000;
    text.rows = 7;
    text.setAttribute("translate", "no");
    const actions = element("div", "inbox-actions");
    const send = element("button", "inbox-primary", "Send message");
    send.type = "submit";
    const cancel = element("button", "inbox-secondary", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => showMessageList());
    actions.append(send, cancel);
    form.append(field("To", to), options, field("Subject", subjectInput), field("Message", text), actions);
    messagesView.body.replaceChildren(backButton(), form);
    (recipient ? text : to).focus();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      send.disabled = true;
      setStatus(messagesView, "Sending...");
      try {
        await api("/messages", {
          method: "POST",
          json: { recipient: to.value.trim(), subject: subjectInput.value, body: text.value, reply_to: replyTo },
        });
        setStatus(messagesView, "Message sent.");
        await showMessageList("sent");
        setStatus(messagesView, "Message sent.");
      } catch (error) {
        setStatus(messagesView, error.message);
        send.disabled = false;
      }
    });

    try {
      for (const account of await loadRecipients()) {
        const option = element("option");
        option.value = account.username;
        if (account.display_name) option.label = account.display_name;
        options.append(option);
      }
    } catch (error) {
      setStatus(messagesView, error.message);
    }
  }

  composeButton.addEventListener("click", () => showCompose());

  // --- opening, starting and stopping ---------------------------------------------

  async function open(kind) {
    if (!state.started) return;
    if (kind === "messages") {
      if (notificationsView.dialog.open) notificationsView.dialog.close();
      if (!messagesView.dialog.open) messagesView.dialog.showModal();
      await showMessageList("inbox");
    } else {
      if (messagesView.dialog.open) messagesView.dialog.close();
      setStatus(notificationsView);
      if (!notificationsView.dialog.open) notificationsView.dialog.showModal();
      renderNotifications();
      await loadNotifications().catch((error) => setStatus(notificationsView, error.message));
    }
  }

  notificationsButton.addEventListener("click", () => open("notifications"));
  messagesButton.addEventListener("click", () => open("messages"));

  function onNotificationsChanged(change) {
    if (!state.started) return;
    if (typeof change?.unread === "number") setBadge(notificationsButton, change.unread);
    if (notificationsView.dialog.open || change?.notification) loadNotifications().catch(() => {});
  }

  function onMessagesChanged(change) {
    if (!state.started) return;
    if (typeof change?.unread === "number") {
      state.messagesUnread = change.unread;
      setBadge(messagesButton, change.unread);
    }
    // Only refresh the list view; never replace a message being read or written.
    if (messagesView.dialog.open && messagesView.body.querySelector(".inbox-list, .inbox-empty")) {
      showMessageList();
    }
  }

  function refresh() {
    if (!state.started) return;
    loadNotifications().catch(() => {});
    refreshMessageCount().catch(() => {});
  }

  window.realtime?.on("notificationsChanged", onNotificationsChanged);
  window.realtime?.on("messagesChanged", onMessagesChanged);
  window.realtime?.onReconnected(refresh);
  // Pages without live updates still catch up when the tab comes back into view.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });
  document.addEventListener("languagechange", () => {
    if (!state.started) return;
    setBadge(notificationsButton, Number(notificationsButton.querySelector(".inbox-badge").dataset.count || 0));
    setBadge(messagesButton, state.messagesUnread);
    if (notificationsView.dialog.open) renderNotifications();
    if (messagesView.dialog.open && messagesView.body.querySelector(".inbox-list, .inbox-empty")) renderMessageList();
  });

  // Links such as /profile?inbox=messages (used in emails and notifications) open a dialog.
  function openFromAddress() {
    const url = new URL(window.location.href);
    const kind = url.searchParams.get("inbox");
    if (kind !== "messages" && kind !== "notifications") return;
    url.searchParams.delete("inbox");
    window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
    open(kind);
  }

  async function start() {
    if (state.started) {
      refresh();
      return;
    }
    state.starting ??= (async () => {
      try {
        await loadNotifications();
        await refreshMessageCount();
      } catch {
        return;
      } finally {
        state.starting = null;
      }
      state.started = true;
      mount.hidden = false;
      window.realtime?.start();
      openFromAddress();
    })();
    await state.starting;
  }

  function stop() {
    state.started = false;
    state.recipients = null;
    mount.hidden = true;
    notificationsView.dialog.close();
    messagesView.dialog.close();
    setBadge(notificationsButton, 0);
    setBadge(messagesButton, 0);
  }

  window.inbox = { start, stop, open };
  start();
})();
