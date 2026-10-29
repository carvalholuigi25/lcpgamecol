// Collapsible page-links sidebar shared by every page. Pages include an empty
// <aside id="admin-sidebar"> and a #sidebar-toggle button; the links are built here
// so they stay the same everywhere. The Activity group on top holds the notifications
// and messages buttons (inbox.js fills [data-inbox="sidebar"]) and the feedback link.
// Pages call setAvailable(true, role) once signed in; admin-only groups need role "admin".
(() => {
  const sidebar = document.getElementById("admin-sidebar");
  const toggleButton = document.getElementById("sidebar-toggle");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!sidebar || !toggleButton) return;

  const ICONS = {
    overview: "M4 13h6V4H4zm10 7h6v-9h-6zM4 20h6v-4H4zm10-11h6V4h-6z",
    records: "M5 4h14v16H5zM9 8h6m-6 4h6m-6 4h4",
    settings: "M4 7h10m4 0h2M4 17h4m4 0h8M14 4v6m-6 4v6",
    charts: "M4 20V10m6 10V4m6 16v-7m4 7H3",
    recent: "M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
    star: "M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7z",
    users: "M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1m6.5-9a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21 19v-1a4 4 0 0 0-3-3.9M16 3.1a3.5 3.5 0 0 1 0 6.8",
    feedback: "M4 5h16v11H9l-5 4zM8 9h8m-8 3h5",
    games: "M6 9h4m-2-2v4m7-1h.01M18 8h.01M7 5h10a4 4 0 0 1 4 4v4a3 3 0 0 1-5.4 1.8L14 13h-4l-1.6 1.8A3 3 0 0 1 3 13V9a4 4 0 0 1 4-4z",
    releases: "M5 5h14v15H5zM5 9h14M9 3v4m6-4v4",
    profile: "M19 20v-1a5 5 0 0 0-5-5h-4a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    docs: "M9 8l-4 4 4 4m6-8l4 4-4 4",
  };
  const GROUPS = [
    { label: "ACTIVITY", inbox: true, links: [["/feedback", "feedback", "Feedback"]] },
    {
      label: "DASHBOARD",
      admin: true,
      links: [
        ["/admin", "overview", "Overview"],
        ["/admin#records-panel", "records", "Records"],
        ["/admin#settings-panel", "settings", "Settings"],
        ["/admin#charts-section", "charts", "Charts"],
        ["/admin#recent-section", "recent", "Recent games"],
      ],
    },
    {
      label: "TOOLS",
      admin: true,
      links: [
        ["/admin/special-features", "star", "Special features"],
        ["/admin/user-directory", "users", "Users"],
        ["/feedback#manage", "feedback", "Manage feedback"],
      ],
    },
    {
      label: "LIBRARY",
      links: [
        ["/library", "games", "Games"],
        ["/library/releases", "releases", "Releases"],
        ["/profile", "profile", "My profile"],
        ["/docs", "docs", "API docs"],
      ],
    },
  ];

  function svg(path) {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}" /></svg>`;
  }

  function buildNav() {
    const nav = document.createElement("nav");
    nav.className = "sidebar-nav";
    nav.setAttribute("aria-label", "Page links");
    for (const group of GROUPS) {
      const section = document.createElement("div");
      section.className = "sidebar-section";
      if (group.admin) section.dataset.adminOnly = "";
      const label = document.createElement("p");
      label.className = "sidebar-group";
      label.textContent = group.label;
      section.append(label);
      if (group.inbox) {
        const inbox = document.createElement("div");
        inbox.className = "sidebar-inbox";
        inbox.dataset.inbox = "sidebar";
        section.append(inbox);
      }
      for (const [href, icon, text] of group.links) {
        const link = document.createElement("a");
        link.href = href;
        link.title = text;
        link.innerHTML = svg(ICONS[icon]);
        const span = document.createElement("span");
        span.textContent = text;
        link.append(span);
        section.append(link);
      }
      nav.append(section);
    }
    sidebar.replaceChildren(nav);
  }

  buildNav();
  const storageKey = "lcpgamecol-admin-sidebar";
  const mobileQuery = window.matchMedia("(max-width: 860px)");
  const links = [...sidebar.querySelectorAll("a[href]")];

  function readCollapsed() {
    try {
      return localStorage.getItem(storageKey) === "collapsed";
    } catch {
      return false;
    }
  }

  function saveCollapsed(collapsed) {
    try {
      localStorage.setItem(storageKey, collapsed ? "collapsed" : "expanded");
    } catch {
      // The sidebar still toggles for this page when storage is unavailable.
    }
  }

  function isOpen() {
    return mobileQuery.matches
      ? document.body.classList.contains("sidebar-open")
      : !document.body.classList.contains("sidebar-collapsed");
  }

  function focusableItems() {
    return [...sidebar.querySelectorAll("a[href], button")].filter((item) => item.offsetParent !== null);
  }

  function syncToggle() {
    const open = isOpen();
    toggleButton.setAttribute("aria-expanded", String(open));
    const label = open ? "Hide page links" : "Show page links";
    toggleButton.setAttribute("aria-label", label);
    toggleButton.title = label;
    if (backdrop) backdrop.hidden = !(mobileQuery.matches && open);
  }

  function setOpen(open) {
    if (mobileQuery.matches) {
      document.body.classList.toggle("sidebar-open", open);
      if (open) (links.find((link) => link.classList.contains("active")) ?? focusableItems()[0])?.focus();
    } else {
      document.body.classList.toggle("sidebar-collapsed", !open);
      saveCollapsed(!open);
    }
    syncToggle();
  }

  function markActiveLink() {
    const { pathname, hash } = window.location;
    let active = links.find((link) => {
      const url = new URL(link.href, window.location.href);
      return url.pathname === pathname && url.hash && url.hash === hash;
    });
    active ??= links.find((link) => {
      const url = new URL(link.href, window.location.href);
      return url.pathname === pathname && (!url.hash || url.hash === "#top");
    });
    for (const link of links) {
      link.classList.toggle("active", link === active);
      if (link === active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  }

  function setAvailable(available, role = null) {
    sidebar.hidden = !available;
    toggleButton.hidden = !available;
    for (const section of sidebar.querySelectorAll("[data-admin-only]")) section.hidden = role !== "admin";
    document.body.classList.toggle("has-sidebar", available);
    if (!available) document.body.classList.remove("sidebar-open");
    syncToggle();
  }

  toggleButton.addEventListener("click", () => setOpen(!isOpen()));
  backdrop?.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && mobileQuery.matches && isOpen() && !document.querySelector("dialog[open]")) {
      setOpen(false);
      toggleButton.focus();
    }
  });
  sidebar.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || !event.target.closest("a[href], button")) return;
    if (mobileQuery.matches) setOpen(false);
  });
  mobileQuery.addEventListener("change", () => {
    document.body.classList.remove("sidebar-open");
    syncToggle();
  });
  window.addEventListener("hashchange", markActiveLink);

  document.body.classList.toggle("sidebar-collapsed", readCollapsed());
  markActiveLink();
  syncToggle();
  window.adminSidebar = { setAvailable, setOpen };
})();
