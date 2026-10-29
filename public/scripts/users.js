const accessView = document.getElementById("access-view");
const usersView = document.getElementById("users-view");
const accountName = document.getElementById("account-name");
const logoutButton = document.getElementById("logout-button");
const userGrid = document.getElementById("user-grid");
const userSearch = document.getElementById("user-search");
const roleFilter = document.getElementById("user-role-filter");
const usersStatus = document.getElementById("users-status");
const userDialog = document.getElementById("user-dialog");
const pageView = document.getElementById("user-page-view");
const profileForm = document.getElementById("user-profile-form");
const profileStatus = document.getElementById("user-profile-status");
const editButton = document.getElementById("user-page-edit");
const pickerList = document.getElementById("favorite-picker-list");
const pickerSearch = document.getElementById("favorite-picker-search");
const toastRegion = document.getElementById("toast-region");
const DEFAULT_GAME_COVER = "/public/images/default-game-cover.svg";
const FAVORITE_GAMES_MAX = 12;
let users = [];
let gameOptions = null;
let activeUser = null;
let toastTimer = null;

function showToast(message) {
  toastRegion.textContent = message;
  toastRegion.classList.add("is-visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastRegion.classList.remove("is-visible"), 3600);
}

function showAccess(message) {
  usersView.hidden = true;
  accessView.hidden = false;
  document.getElementById("access-message").textContent = message;
  accountName.textContent = "";
  logoutButton.hidden = true;
  window.adminSidebar?.setAvailable(false);
}

function showUsers(username, role) {
  accessView.hidden = true;
  usersView.hidden = false;
  accountName.textContent = username;
  logoutButton.hidden = false;
  window.adminSidebar?.setAvailable(true, role);
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

function locale() {
  return { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR", it: "it-IT", es: "es-ES", ja: "ja-JP" }[window.i18n.language];
}

function formatDate(value) {
  return value ? new Date(value).toLocaleDateString(locale(), { dateStyle: "medium" }) : "—";
}

function displayName(user) {
  return user.display_name || user.username;
}

function roleLabel(role) {
  return role === "admin" ? "Administrator" : "Viewer";
}

function hasProfile(user) {
  return Boolean(user.avatar_url || user.cover_url || user.bio);
}

// Shows the image when it loads and falls back to the initial or plain cover when it does not.
function fillAvatar(element, user) {
  element.replaceChildren();
  element.textContent = displayName(user).charAt(0).toUpperCase();
  if (!user.avatar_url) return;
  const image = document.createElement("img");
  image.alt = "";
  image.addEventListener("load", () => element.replaceChildren(image));
  image.src = user.avatar_url;
}

function fillCover(element, url) {
  element.replaceChildren();
  if (!url) return;
  const image = document.createElement("img");
  image.alt = "";
  image.hidden = true;
  image.addEventListener("load", () => { image.hidden = false; });
  image.src = url;
  element.append(image);
}

function gameCover(game) {
  const image = document.createElement("img");
  image.alt = "";
  image.loading = "lazy";
  image.src = game.cover_image_url || DEFAULT_GAME_COVER;
  image.addEventListener("error", () => {
    if (!image.src.endsWith(DEFAULT_GAME_COVER)) image.src = DEFAULT_GAME_COVER;
  }, { once: true });
  return image;
}

function renderCard(user) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "user-card";
  card.setAttribute("aria-label", window.i18n.t("Open the profile of {name}", { name: displayName(user) }));

  const cover = document.createElement("span");
  cover.className = "user-card-cover";
  fillCover(cover, user.cover_url);

  const avatar = document.createElement("span");
  avatar.className = "user-avatar";
  avatar.setAttribute("aria-hidden", "true");
  fillAvatar(avatar, user);

  const identity = document.createElement("span");
  identity.className = "user-card-identity";
  const name = document.createElement("strong");
  name.setAttribute("translate", "no");
  name.textContent = displayName(user);
  const handle = document.createElement("span");
  handle.className = "user-handle";
  handle.setAttribute("translate", "no");
  handle.textContent = `@${user.username}`;
  identity.append(name, handle);

  const role = document.createElement("span");
  role.className = `role-badge role-${user.role}`;
  role.textContent = roleLabel(user.role);

  const bio = document.createElement("span");
  bio.className = "user-card-bio";
  if (user.bio) {
    bio.setAttribute("translate", "no");
    bio.textContent = user.bio;
  } else {
    bio.textContent = "No bio yet.";
  }

  const facts = document.createElement("span");
  facts.className = "user-card-facts";
  for (const [label, value] of [
    ["ACCOUNT", user.source === "configured" ? "Configured" : "Registered"],
    ["JOINED", formatDate(user.created_at)],
    ["FAVORITES", String(user.favorite_games.length)],
  ]) {
    const fact = document.createElement("span");
    const term = document.createElement("small");
    term.textContent = label;
    const detail = document.createElement("span");
    detail.textContent = value;
    fact.append(term, detail);
    facts.append(fact);
  }

  const favorites = document.createElement("span");
  favorites.className = "user-card-favorites";
  for (const game of user.favorite_games.slice(0, 5)) {
    const thumb = gameCover(game);
    thumb.title = game.title;
    favorites.append(thumb);
  }
  if (user.favorite_games.length > 5) {
    const more = document.createElement("span");
    more.className = "user-card-more";
    more.textContent = `+${user.favorite_games.length - 5}`;
    favorites.append(more);
  }

  card.append(cover, avatar, role, identity, bio, facts, favorites);
  card.addEventListener("click", () => openUserPage(user.username));
  return card;
}

function renderUsers() {
  const query = userSearch.value.trim().toLowerCase();
  const role = roleFilter.value;
  const visible = users.filter((user) => {
    if (role && user.role !== role) return false;
    if (!query) return true;
    return [user.username, user.display_name, user.location, ...user.favorite_games.map((game) => game.title)]
      .some((value) => value?.toLowerCase().includes(query));
  });
  userGrid.replaceChildren(...visible.map(renderCard));
  document.getElementById("users-empty").hidden = visible.length > 0;
}

function renderTotals() {
  document.getElementById("metric-users").textContent = users.length;
  document.getElementById("metric-admins").textContent = users.filter((user) => user.role === "admin").length;
  document.getElementById("metric-profiles").textContent = users.filter(hasProfile).length;
  document.getElementById("metric-favorites").textContent = users.reduce((sum, user) => sum + user.favorite_games.length, 0);
}

async function loadUsers() {
  const response = await fetch("/admin/users", { headers: { Accept: "application/json" } });
  if (response.status === 401) {
    showAccess("Sign in with an administrator account to see users.");
    return false;
  }
  if (response.status === 403) {
    showAccess("This account does not have administrator access.");
    return false;
  }
  if (!response.ok) throw new Error(await readError(response, "Users could not be loaded."));
  users = await response.json();
  renderTotals();
  renderUsers();
  return true;
}

function renderUserPage(user) {
  const cover = document.getElementById("user-page-cover");
  cover.hidden = true;
  cover.onload = () => { cover.hidden = false; };
  cover.onerror = () => { cover.hidden = true; };
  if (user.cover_url) cover.src = user.cover_url;
  else cover.removeAttribute("src");

  fillAvatar(document.getElementById("user-page-avatar"), user);
  document.getElementById("user-page-name").textContent = displayName(user);
  document.getElementById("user-page-username").textContent = user.username;
  const role = document.getElementById("user-page-role");
  role.className = `role-badge role-${user.role}`;
  role.textContent = roleLabel(user.role);

  const bio = document.getElementById("user-page-bio");
  bio.textContent = user.bio || "";
  bio.hidden = !user.bio;
  document.getElementById("user-page-role-text").textContent = roleLabel(user.role);
  document.getElementById("user-page-source").textContent =
    user.source === "configured" ? "Configured in the server settings" : "Registered on the site";
  document.getElementById("user-page-joined").textContent = formatDate(user.created_at);
  document.getElementById("user-page-location").textContent = user.location || "—";
  document.getElementById("user-page-favorite-count").textContent = user.favorite_games.length;
  document.getElementById("user-page-hours").textContent = window.i18n.t("{hours} h", { hours: user.hours_in_favorites });
  document.getElementById("user-page-updated").textContent = formatDate(user.updated_at);
  document.getElementById("user-page-two-factor").textContent = user.two_factor_enabled ? "On" : "Off";
  // Configured accounts keep the password from the server settings.
  const resetButton = document.getElementById("user-reset-link");
  resetButton.disabled = user.source === "configured";
  resetButton.title = user.source === "configured" ? "Change this password in the server settings." : "";
  document.getElementById("user-two-factor-off").hidden = !user.two_factor_enabled;
  document.getElementById("user-access-status").textContent = "";
  document.getElementById("user-reset-result").hidden = true;

  const favorites = document.getElementById("user-page-favorites");
  favorites.replaceChildren(...user.favorite_games.map((game, index) => {
    const item = document.createElement("li");
    item.className = "favorite-game";
    const rank = document.createElement("span");
    rank.className = "favorite-rank";
    rank.textContent = String(index + 1).padStart(2, "0");
    const title = document.createElement("strong");
    title.setAttribute("translate", "no");
    title.textContent = game.title;
    const meta = document.createElement("span");
    meta.className = "chart-note";
    meta.textContent = [game.release_year, game.genre].filter(Boolean).join(" / ");
    item.append(gameCover(game), rank, title, meta);
    return item;
  }));
  document.getElementById("user-page-favorites-empty").hidden = user.favorite_games.length > 0;
  document.getElementById("user-page-favorites-note").textContent =
    window.i18n.t("{count} OF {max}", { count: user.favorite_games.length, max: FAVORITE_GAMES_MAX });
}

function setEditing(editing) {
  pageView.hidden = editing;
  profileForm.hidden = !editing;
  editButton.hidden = editing;
  profileStatus.textContent = "";
}

function openUserPage(username) {
  activeUser = users.find((user) => user.username === username);
  if (!activeUser) return;
  renderUserPage(activeUser);
  setEditing(false);
  userDialog.showModal();
  document.getElementById("user-page-close").focus();
}

function updatePickerCount() {
  const checked = pickerList.querySelectorAll("input:checked").length;
  document.getElementById("favorite-picker-count").textContent =
    window.i18n.t("{count} OF {max}", { count: checked, max: FAVORITE_GAMES_MAX });
  for (const input of pickerList.querySelectorAll("input")) {
    input.disabled = !input.checked && checked >= FAVORITE_GAMES_MAX;
  }
}

function filterPicker() {
  const query = pickerSearch.value.trim().toLowerCase();
  for (const option of pickerList.children) {
    option.hidden = Boolean(query) && !option.dataset.title.includes(query);
  }
}

async function loadEditorOptions() {
  if (gameOptions === null) {
    const response = await fetch("/admin/users/game-options", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(await readError(response, "Games could not be loaded."));
    gameOptions = await response.json();
  }
  // Uploaded images make a handy source for avatars and covers; the list is optional.
  try {
    const response = await fetch("/admin/uploads", { headers: { Accept: "application/json" } });
    if (response.ok) {
      const images = (await response.json()).filter((upload) => upload.previewable);
      document.getElementById("uploaded-images").replaceChildren(...images.map((upload) => {
        const option = document.createElement("option");
        option.value = `/admin/uploads/${upload.id}?inline=true`;
        option.label = upload.original_name;
        return option;
      }));
    }
  } catch {
    // Links can still be typed in by hand.
  }
}

function fillEditor(user) {
  for (const field of ["display_name", "location", "bio", "avatar_url", "cover_url"]) {
    profileForm.elements[field].value = user[field] || "";
  }
  const favoriteIds = user.favorite_games.map((game) => game.id);
  const ordered = [
    ...favoriteIds.map((id) => gameOptions.find((game) => game.id === id)).filter(Boolean),
    ...gameOptions.filter((game) => !favoriteIds.includes(game.id)),
  ];
  pickerList.replaceChildren(...ordered.map((game) => {
    const label = document.createElement("label");
    label.className = "favorite-option";
    label.dataset.title = game.title.toLowerCase();
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = game.id;
    input.checked = favoriteIds.includes(game.id);
    input.addEventListener("change", updatePickerCount);
    const title = document.createElement("span");
    title.setAttribute("translate", "no");
    title.textContent = game.title;
    const year = document.createElement("small");
    year.textContent = game.release_year;
    label.append(input, title, year);
    return label;
  }));
  pickerSearch.value = "";
  updatePickerCount();
}

editButton.addEventListener("click", async () => {
  if (!activeUser) return;
  editButton.disabled = true;
  try {
    await loadEditorOptions();
    fillEditor(activeUser);
    setEditing(true);
    profileForm.elements.display_name.focus();
  } catch (error) {
    showToast(error.message);
  } finally {
    editButton.disabled = false;
  }
});

pickerSearch.addEventListener("input", filterPicker);
document.getElementById("user-profile-cancel").addEventListener("click", () => setEditing(false));
document.getElementById("user-page-close").addEventListener("click", () => userDialog.close());
userDialog.addEventListener("click", (event) => {
  if (event.target === userDialog) userDialog.close();
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const saveButton = document.getElementById("user-profile-save");
  const values = new FormData(profileForm);
  const body = {
    display_name: values.get("display_name"),
    location: values.get("location"),
    bio: values.get("bio"),
    avatar_url: values.get("avatar_url"),
    cover_url: values.get("cover_url"),
    // Checked favorites keep the order shown, which lists current favorites first.
    favorite_game_ids: [...pickerList.querySelectorAll("input:checked")].map((input) => Number(input.value)),
  };
  saveButton.disabled = true;
  profileStatus.textContent = "Saving profile...";
  window.setStatusLoading?.(profileStatus, true);
  try {
    const response = await fetch(`/admin/users/${encodeURIComponent(activeUser.username)}`, {
      method: "PUT",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(await readError(response, "The profile could not be saved."));
    const saved = await response.json();
    users = users.map((user) => (user.username === saved.username ? saved : user));
    activeUser = saved;
    renderTotals();
    renderUsers();
    renderUserPage(saved);
    setEditing(false);
    showToast(window.i18n.t("Profile of {name} saved.", { name: displayName(saved) }));
  } catch (error) {
    profileStatus.textContent = error.message;
  } finally {
    window.setStatusLoading?.(profileStatus, false);
    saveButton.disabled = false;
  }
});

userSearch.addEventListener("input", renderUsers);
roleFilter.addEventListener("change", renderUsers);
document.addEventListener("languagechange", () => {
  renderUsers();
  if (activeUser && userDialog.open) renderUserPage(activeUser);
});

logoutButton.addEventListener("click", async () => {
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/admin");
  }
});

document.getElementById("user-reset-link").addEventListener("click", async (event) => {
  const status = document.getElementById("user-access-status");
  const resetButton = event.currentTarget;
  resetButton.disabled = true;
  status.textContent = "";
  try {
    const response = await fetch(`/admin/users/${encodeURIComponent(activeUser.username)}/password-reset`, { method: "POST" });
    if (!response.ok) throw new Error(await readError(response, "The reset link could not be created."));
    const result = await response.json();
    document.getElementById("user-reset-url").value = result.link;
    document.getElementById("user-reset-result").hidden = false;
    status.textContent = window.i18n.t(result.emailed
      ? "Reset link created and emailed. It works once, for {minutes} minutes."
      : "Reset link created. Send it to the user yourself; it works once, for {minutes} minutes.",
    { minutes: Math.round(result.expires_in / 60) });
  } catch (error) {
    status.textContent = window.i18n.t(error.message);
  } finally {
    resetButton.disabled = false;
  }
});

document.getElementById("user-reset-copy").addEventListener("click", async () => {
  const field = document.getElementById("user-reset-url");
  try {
    await navigator.clipboard.writeText(field.value);
    showToast(window.i18n.t("Reset link copied."));
  } catch {
    field.select();
  }
});

document.getElementById("user-two-factor-off").addEventListener("click", async () => {
  const status = document.getElementById("user-access-status");
  const prompt = window.i18n.t("Turn off two-step sign-in for {name}? Only do this once you're sure it's really them.", { name: activeUser.username });
  if (!window.confirm(prompt)) return;
  try {
    const response = await fetch(`/admin/users/${encodeURIComponent(activeUser.username)}/two-factor`, { method: "DELETE" });
    if (!response.ok) throw new Error(await readError(response, "Two-step sign-in could not be turned off."));
    activeUser.two_factor_enabled = false;
    renderUserPage(activeUser);
    showToast(window.i18n.t("Two-step sign-in is off for {name}.", { name: activeUser.username }));
  } catch (error) {
    status.textContent = window.i18n.t(error.message);
  }
});

async function initUsers() {
  try {
    const profileResponse = await fetch("/users");
    if (!profileResponse.ok) {
      showAccess("Sign in with an administrator account to see users.");
      return;
    }
    const profile = await profileResponse.json();
    usersStatus.textContent = "Loading users...";
    if (await loadUsers()) showUsers(profile.username, profile.role);
    usersStatus.textContent = "";
  } catch (error) {
    if (usersView.hidden) showAccess("The server could not be reached.");
    else usersStatus.textContent = error.message;
  }
}

initUsers();
