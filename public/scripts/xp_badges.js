// XP rank badges. The API sends each rank as { level, rank, rank_key } (backend/gamification/xp.py);
// this file turns it into a badge. Styles are in public/styles/scss/_xp_badges.scss.
(() => {
  const ICONS = {
    rookie: "bi-egg-fill",
    explorer: "bi-compass-fill",
    adventurer: "bi-map-fill",
    veteran: "bi-shield-fill",
    elite: "bi-gem",
    champion: "bi-trophy-fill",
    legend: "bi-stars",
  };

  const t = (message, values) => window.i18n?.t(message, values) ?? message;

  function iconFor(key) {
    return ICONS[key] || "bi-award-fill";
  }

  function keyOf(rank) {
    return String(rank.rank_key || rank.key || rank.rank || rank.name || "").toLowerCase();
  }

  // Small pill for next to a name: icon, rank name and level.
  function badge(rank, { showName = true } = {}) {
    const key = keyOf(rank);
    const name = t(rank.rank || rank.name || "");
    const element = document.createElement("span");
    element.className = "xp-badge";
    element.dataset.rank = key;
    const title = t("{rank} · Level {level}", { rank: name, level: rank.level });
    element.title = title;
    element.setAttribute("role", "img");
    element.setAttribute("aria-label", title);
    const icon = document.createElement("i");
    icon.className = `bi ${iconFor(key)}`;
    icon.setAttribute("aria-hidden", "true");
    element.append(icon);
    if (showName) {
      const label = document.createElement("span");
      label.className = "xp-badge-name";
      label.setAttribute("aria-hidden", "true");
      label.textContent = name;
      element.append(label);
    }
    const level = document.createElement("span");
    level.className = "xp-badge-level";
    level.setAttribute("aria-hidden", "true");
    level.textContent = rank.level;
    element.append(level);
    return element;
  }

  function badgeHtml(rank, options) {
    return rank ? badge(rank, options).outerHTML : "";
  }

  // Large badge for the rank collection: { name, level, key } from /users/me/xp "ranks".
  function medal(rank, { earned, current }) {
    const key = keyOf(rank);
    const item = document.createElement("li");
    item.className = "xp-medal";
    item.dataset.rank = key;
    if (!earned) item.dataset.locked = "";
    if (current) item.dataset.current = "";
    const shape = document.createElement("span");
    shape.className = "xp-medal-shape";
    shape.setAttribute("aria-hidden", "true");
    shape.innerHTML = `<i class="bi ${iconFor(key)}"></i>`;
    const name = document.createElement("strong");
    name.textContent = t(rank.name);
    const note = document.createElement("small");
    note.textContent = current ? t("Current rank")
      : earned ? t("Earned")
      : t("Level {level}", { level: rank.level });
    item.append(shape, name, note);
    return item;
  }

  window.xpBadges = { badge, badgeHtml, medal, iconFor };
})();
