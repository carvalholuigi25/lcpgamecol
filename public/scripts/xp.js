// XP, level and rank card on the profile page (/profile), served by routes/users/xp.py.
// Requires profile.js (locale, formatDate, showToast) to be loaded first.
(() => {
  const status = document.getElementById("xp-status");
  let lastState = null;
  let leaderboard = [];

  function listItem(label, value, className = "") {
    const item = document.createElement("li");
    if (className) item.className = className;
    const name = document.createElement("span");
    name.textContent = label;
    const amount = document.createElement("strong");
    amount.textContent = value;
    item.append(name, amount);
    return item;
  }

  function render() {
    if (!lastState) return;
    const state = lastState;
    const t = window.i18n.t;
    document.getElementById("xp-level").textContent = state.level;
    document.getElementById("xp-total").textContent = state.xp.toLocaleString(locale());
    document.getElementById("xp-rank-badge").textContent = t(state.rank);
    document.getElementById("xp-bar-fill").style.width = `${state.progress}%`;
    document.getElementById("xp-bar").setAttribute("aria-valuenow", String(state.progress));
    const toNext = state.next_level_xp - state.xp;
    let next = t("{xp} XP to level {level}.", { xp: toNext, level: state.level + 1 });
    if (state.next_rank) {
      next += ` ${t("Rank {rank} at level {level}.", { rank: t(state.next_rank.name), level: state.next_rank.level })}`;
    }
    document.getElementById("xp-next").textContent = next;

    document.getElementById("xp-actions").replaceChildren(
      ...state.actions.map((action) => listItem(
        action.daily_limit ? `${t(action.label)} · ${t("up to {count} a day", { count: action.daily_limit })}` : t(action.label),
        `+${action.xp}`,
      )),
    );
    document.getElementById("xp-recent").replaceChildren(
      ...state.recent.map((event) => listItem(`${t(event.label)} · ${formatDate(event.created_at)}`, `+${event.xp}`)),
    );
    document.getElementById("xp-recent-empty").hidden = state.recent.length > 0;
    document.getElementById("xp-leaderboard").replaceChildren(
      ...leaderboard.map((row) => {
        const item = listItem(
          `${row.position}. ${row.display_name || row.username} · ${t("Level {level}", { level: row.level })} ${t(row.rank)}`,
          `${row.xp.toLocaleString(locale())} XP`,
          row.username.toLowerCase() === accountName.textContent.toLowerCase() ? "is-me" : "",
        );
        item.firstChild.setAttribute("translate", "no");
        return item;
      }),
    );
  }

  async function load() {
    try {
      const [mine, board] = await Promise.all([
        fetch("/users/me/xp", { cache: "no-store" }),
        fetch("/users/xp/leaderboard?limit=10", { cache: "no-store" }),
      ]);
      if (!mine.ok || !board.ok) throw new Error("Your XP could not be loaded.");
      lastState = await mine.json();
      leaderboard = await board.json();
      status.textContent = "";
      render();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  window.realtime?.on("xpChanged", (change) => {
    if (lastState && change.level > lastState.level) {
      showToast(window.i18n.t("Level up! You are now level {level}.", { level: change.level }));
    }
    load();
  });
  window.realtime?.onReconnected(load);
  document.addEventListener("languagechange", render);
  load();
})();
