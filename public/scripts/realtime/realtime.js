// Live library updates from the SignalR hub at /hubs/library (backend/realtime/hub.py).
// Needs @microsoft/signalr loaded first. Pages call window.realtime.start() after
// sign-in and stop() on sign-out; the auth cookie authenticates the connection.
(() => {
  const handlers = new Map();
  const reconnectedHandlers = new Set();
  const statusLabels = {
    connecting: "Connecting...",
    live: "Live",
    reconnecting: "Reconnecting...",
    offline: "Offline",
  };
  let connection = null;

  function setStatus(state) {
    for (const element of document.querySelectorAll("[data-realtime-status]")) {
      element.hidden = state === "stopped";
      element.dataset.state = state;
      element.textContent = window.i18n.t(statusLabels[state] || "");
      element.title = window.i18n.t("Live updates");
    }
  }

  function buildConnection() {
    const hub = new signalR.HubConnectionBuilder()
      .withUrl("/hubs/library", { transport: signalR.HttpTransportType.WebSockets })
      .withAutomaticReconnect([0, 2000, 5000, 10000, 30000])
      .configureLogging(signalR.LogLevel.Warning)
      .build();
    for (const [event, eventHandlers] of handlers) {
      for (const handler of eventHandlers) hub.on(event, handler);
    }
    hub.onreconnecting(() => setStatus("reconnecting"));
    // Events sent while disconnected are lost, so let pages reload what they show.
    hub.onreconnected(() => {
      setStatus("live");
      for (const handler of reconnectedHandlers) handler();
    });
    hub.onclose(() => {
      if (connection === hub) setStatus("offline");
    });
    return hub;
  }

  async function start() {
    if (!window.signalR) return;
    if (connection) return;
    connection = buildConnection();
    setStatus("connecting");
    try {
      await connection.start();
      setStatus("live");
    } catch {
      connection = null;
      setStatus("offline");
    }
  }

  async function stop() {
    const current = connection;
    connection = null;
    setStatus("stopped");
    await current?.stop();
  }

  function on(event, handler) {
    if (!handlers.has(event)) handlers.set(event, new Set());
    handlers.get(event).add(handler);
    connection?.on(event, handler);
  }

  function onReconnected(handler) {
    reconnectedHandlers.add(handler);
  }

  window.realtime = { start, stop, on, onReconnected };
})();
