// Collapsible page-links sidebar shared by the admin pages.
(() => {
  const sidebar = document.getElementById("admin-sidebar");
  const toggleButton = document.getElementById("sidebar-toggle");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!sidebar || !toggleButton) return;

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
      if (open) links.find((link) => link.classList.contains("active"))?.focus() ?? links[0]?.focus();
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

  function setAvailable(available) {
    sidebar.hidden = !available;
    toggleButton.hidden = !available;
    document.body.classList.toggle("has-sidebar", available);
    if (!available) document.body.classList.remove("sidebar-open");
    syncToggle();
  }

  toggleButton.addEventListener("click", () => setOpen(!isOpen()));
  backdrop?.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && mobileQuery.matches && isOpen()) {
      setOpen(false);
      toggleButton.focus();
    }
  });
  sidebar.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || !event.target.closest("a[href]")) return;
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
