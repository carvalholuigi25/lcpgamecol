const statusMessage = document.getElementById("workspace-status");
const accountName = document.getElementById("workspace-account");

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    let detail = "The request could not be completed.";
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      // Keep the HTTP failure explicit when the response is not JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function message(text) {
  statusMessage.textContent = text;
}

function setFormValue(form, name, value) {
  form.elements.namedItem(name).value = value ?? "";
}

function clearForm(form) {
  form.reset();
  const platforms = form.elements.namedItem("platforms");
  if (platforms) platforms.value = "PC";
}

async function loadGames() {
  const games = [];
  for (let skip = 0; ; skip += 100) {
    const page = await requestJson(`/games/page?skip=${skip}&limit=100`);
    games.push(...page.items);
    if (games.length >= page.total || page.items.length === 0) break;
  }
  for (const selector of document.querySelectorAll('select[name="game_id"]')) {
    selector.replaceChildren(...games.map((game) => {
      const option = document.createElement("option");
      option.value = game.id;
      option.textContent = game.title;
      return option;
    }));
  }
  return games;
}

function wireGameForms(games, permissions) {
  const createForm = document.getElementById("game-create-form");
  if (permissions.includes("games.create")) {
    document.getElementById("workspace-games-create").hidden = false;
    createForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = createForm.querySelector("button[type=submit]");
      button.disabled = true;
      try {
        const values = Object.fromEntries(new FormData(createForm));
        values.release_year = Number(values.release_year);
        await requestJson("/games", { method: "POST", body: JSON.stringify(values) });
        message("Game created.");
        clearForm(createForm);
      } catch (error) {
        message(error.message);
      } finally {
        button.disabled = false;
      }
    });
  }

  const editForm = document.getElementById("game-edit-form");
  if (permissions.includes("games.edit")) {
    document.getElementById("workspace-games-edit").hidden = false;
    const populate = async () => {
      const id = editForm.elements.namedItem("game_id").value;
      if (!id) return;
      const game = await requestJson(`/games/${id}`);
      for (const key of ["title", "genre", "release_year", "platforms"]) {
        const value = game[key];
        setFormValue(editForm, key, Array.isArray(value) ? value.join(", ") : value);
      }
    };
    editForm.elements.namedItem("game_id").addEventListener("change", () => {
      populate().catch((error) => message(error.message));
    });
    if (games.length) populate().catch((error) => message(error.message));
    editForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = editForm.querySelector("button[type=submit]");
      button.disabled = true;
      try {
        const id = editForm.elements.namedItem("game_id").value;
        const existing = await requestJson(`/games/${id}`);
        const values = Object.fromEntries(new FormData(editForm));
        values.release_year = Number(values.release_year);
        delete values.game_id;
        await requestJson(`/games/${id}`, {
          method: "PUT",
          body: JSON.stringify({ ...existing, ...values }),
        });
        message("Game updated.");
      } catch (error) {
        message(error.message);
      } finally {
        button.disabled = false;
      }
    });
  }

  const deleteForm = document.getElementById("game-delete-form");
  if (permissions.includes("games.delete")) {
    document.getElementById("workspace-games-delete").hidden = false;
    deleteForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = deleteForm.elements.namedItem("game_id").value;
      const title = games.find((game) => String(game.id) === id)?.title || "this game";
      if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return;
      const button = deleteForm.querySelector("button[type=submit]");
      button.disabled = true;
      try {
        await requestJson(`/games/${id}`, { method: "DELETE" });
        message("Game deleted.");
        games = await loadGames();
        if (games.length) await wireEditSelection(games, editForm);
      } catch (error) {
        message(error.message);
      } finally {
        button.disabled = false;
      }
    });
  }
}

async function wireEditSelection(games, editForm) {
  if (!editForm || !games.length) return;
  const selector = editForm.elements.namedItem("game_id");
  if (!selector.value) selector.value = String(games[0].id);
  const game = await requestJson(`/games/${selector.value}`);
  for (const key of ["title", "genre", "release_year", "platforms"]) {
    const value = game[key];
    setFormValue(editForm, key, Array.isArray(value) ? value.join(", ") : value);
  }
}

async function wireUserForm(games) {
  const form = document.getElementById("user-edit-form");
  const users = await requestJson("/users/manageable");
  const selector = form.elements.namedItem("username");
  const favorites = form.elements.namedItem("favorite_game_ids");
  favorites.replaceChildren(...games.map((game) => {
    const option = document.createElement("option");
    option.value = game.id;
    option.textContent = game.title;
    return option;
  }));
  selector.replaceChildren(...users.map((user) => {
    const option = document.createElement("option");
    option.value = user.username;
    option.textContent = user.display_name ? `${user.display_name} (${user.username})` : user.username;
    return option;
  }));
  const populate = async () => {
    const profile = await requestJson(`/users/manageable/${encodeURIComponent(selector.value)}`);
    for (const key of ["display_name", "bio", "location", "avatar_url", "cover_url"]) {
      setFormValue(form, key, profile[key]);
    }
    const favoriteIds = new Set(profile.favorite_game_ids.map(String));
    for (const option of favorites.options) {
      option.selected = favoriteIds.has(option.value);
    }
  };
  selector.addEventListener("change", () => populate().catch((error) => message(error.message)));
  if (users.length) await populate();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(form));
      delete payload.username;
      payload.favorite_game_ids = [...favorites.selectedOptions].map((option) => Number(option.value));
      await requestJson(`/users/manageable/${encodeURIComponent(selector.value)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      message(`Profile saved for ${selector.value}.`);
    } catch (error) {
      message(error.message);
    } finally {
      button.disabled = false;
    }
  });
}

async function initializeWorkspace() {
  message("Loading your granted actions…");
  try {
    const access = await requestJson("/users/me/permissions");
    accountName.textContent = access.username;
    window.adminSidebar?.setAvailable(true, access.role);
    const permissions = access.permissions;
    if (!permissions.length) {
      message("Your account has no granted management actions. Ask an administrator to enable them.");
      return;
    }
    let games = [];
    if (permissions.some((permission) => permission.startsWith("games.")) || permissions.includes("users.edit_profile")) {
      games = await loadGames();
    }
    wireGameForms(games, permissions);
    if (permissions.includes("users.edit_profile")) {
      document.getElementById("workspace-users-edit").hidden = false;
      await wireUserForm(games);
    }
    message("");
  } catch (error) {
    window.adminSidebar?.setAvailable(false);
    message(error.message);
  }
}

initializeWorkspace();
