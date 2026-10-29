// The signed-in user's own profile page (/profile), served by routes/users/profile.py.
const accessView = document.getElementById("access-view");
const profileView = document.getElementById("profile-view");
const accountName = document.getElementById("account-name");
const logoutButton = document.getElementById("logout-button");
const pageView = document.getElementById("user-page-view");
const profileForm = document.getElementById("user-profile-form");
const profileStatus = document.getElementById("user-profile-status");
const pageStatus = document.getElementById("profile-status");
const editButton = document.getElementById("user-page-edit");
const toastRegion = document.getElementById("toast-region");
const DEFAULT_GAME_COVER = "/public/images/default-game-cover.svg";
const ICONS = {
  earlier: "M15 18l-6-6 6-6",
  later: "M9 6l6 6-6 6",
  remove: "M6 6l12 12M18 6L6 18",
  favorite: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z",
};
let profile = null;
let busy = false;
let toastTimer = null;

function showToast(message) {
  toastRegion.textContent = message;
  toastRegion.classList.add("is-visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastRegion.classList.remove("is-visible"), 3600);
}

function showAccess(message) {
  profileView.hidden = true;
  accessView.hidden = false;
  document.getElementById("access-message").textContent = message;
  accountName.textContent = "";
  logoutButton.hidden = true;
  window.adminSidebar?.setAvailable(false);
}

function showProfile(principal) {
  accessView.hidden = true;
  profileView.hidden = false;
  accountName.textContent = principal.username;
  logoutButton.hidden = false;
  window.adminSidebar?.setAvailable(true, principal.role);
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

function fillAvatar(element, user) {
  element.replaceChildren();
  element.textContent = displayName(user).charAt(0).toUpperCase();
  if (!user.avatar_url) return;
  const image = document.createElement("img");
  image.alt = "";
  image.addEventListener("load", () => element.replaceChildren(image));
  image.src = user.avatar_url;
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

function toolButton(icon, label, onClick, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.disabled = disabled;
  button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[icon]}" /></svg>`;
  button.addEventListener("click", onClick);
  return button;
}

function gameItem(game, rank, tools) {
  const item = document.createElement("li");
  item.className = "favorite-game";
  const title = document.createElement("strong");
  title.setAttribute("translate", "no");
  title.textContent = game.title;
  const meta = document.createElement("span");
  meta.className = "chart-note";
  meta.textContent = [game.release_year, game.genre].filter(Boolean).join(" / ");
  const toolbar = document.createElement("span");
  toolbar.className = "favorite-tools";
  toolbar.append(...tools);
  item.append(gameCover(game));
  if (rank) {
    const badge = document.createElement("span");
    badge.className = "favorite-rank";
    badge.textContent = String(rank).padStart(2, "0");
    item.append(badge);
  }
  item.append(title, meta, toolbar);
  return item;
}

function renderFavorites() {
  const favorites = profile.favorite_games;
  const last = favorites.length - 1;
  document.getElementById("user-page-favorites").replaceChildren(...favorites.map((game, index) => {
    const name = { title: game.title };
    return gameItem(game, index + 1, [
      toolButton("earlier", window.i18n.t("Move {title} earlier", name), () => moveFavorite(index, -1), index === 0),
      toolButton("later", window.i18n.t("Move {title} later", name), () => moveFavorite(index, 1), index === last),
      toolButton("remove", window.i18n.t("Remove {title} from favorites", name), () => saveFavorites(
        favorites.filter((favorite) => favorite.id !== game.id).map((favorite) => favorite.id),
        window.i18n.t("Removed from your favorites."),
      )),
    ]);
  }));
  document.getElementById("user-page-favorites-empty").hidden = favorites.length > 0;
  document.getElementById("user-page-favorites-note").textContent =
    window.i18n.t("{count} OF {max}", { count: favorites.length, max: profile.favorites_max });
}

function renderWishlist() {
  const favoriteIds = new Set(profile.favorite_games.map((game) => game.id));
  const full = profile.favorite_games.length >= profile.favorites_max;
  document.getElementById("profile-wishlist").replaceChildren(...profile.wishlist_games.map((game) => {
    const name = { title: game.title };
    const tools = [toolButton("remove", window.i18n.t("Remove {title} from your wishlist", name), () => removeFromWishlist(game))];
    if (!favoriteIds.has(game.id)) {
      tools.unshift(toolButton("favorite", window.i18n.t("Add {title} to favorites", name), () => addToFavorites(game), full));
    }
    return gameItem(game, null, tools);
  }));
  document.getElementById("profile-wishlist-empty").hidden = profile.wishlist_games.length > 0;
}

function renderProfile() {
  const cover = document.getElementById("user-page-cover");
  cover.hidden = true;
  cover.onload = () => { cover.hidden = false; };
  cover.onerror = () => { cover.hidden = true; };
  if (profile.cover_url) cover.src = profile.cover_url;
  else cover.removeAttribute("src");

  fillAvatar(document.getElementById("user-page-avatar"), profile);
  document.getElementById("user-page-name").textContent = displayName(profile);
  document.getElementById("user-page-username").textContent = profile.username;
  const role = document.getElementById("user-page-role");
  role.className = `role-badge role-${profile.role}`;
  role.textContent = roleLabel(profile.role);

  const bio = document.getElementById("user-page-bio");
  bio.textContent = profile.bio || "";
  bio.hidden = !profile.bio;
  document.getElementById("user-page-bio-empty").hidden = Boolean(profile.bio);
  document.getElementById("user-page-role-text").textContent = roleLabel(profile.role);
  document.getElementById("user-page-joined").textContent = formatDate(profile.created_at);
  document.getElementById("user-page-location").textContent = profile.location || "—";
  document.getElementById("user-page-favorite-count").textContent = profile.favorite_games.length;
  document.getElementById("user-page-wishlist-count").textContent = profile.wishlist_games.length;
  document.getElementById("user-page-hours").textContent = window.i18n.t("{hours} h", { hours: profile.hours_in_favorites });
  document.getElementById("user-page-updated").textContent = formatDate(profile.updated_at);
  renderFavorites();
  renderWishlist();
}

async function loadProfile() {
  const response = await fetch("/users/me/profile", { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response, "Your profile could not be loaded."));
  profile = await response.json();
  renderProfile();
}

// Runs one change at a time, then shows the profile the server sent back.
async function runChange(request, successMessage) {
  if (busy) return;
  busy = true;
  pageStatus.textContent = "";
  try {
    const response = await request();
    if (!response.ok) throw new Error(await readError(response, "Your lists could not be updated."));
    await loadProfile();
    if (successMessage) showToast(successMessage);
  } catch (error) {
    showToast(window.i18n.t(error.message));
  } finally {
    busy = false;
  }
}

function profileBody(overrides = {}) {
  const body = {};
  for (const field of ["display_name", "location", "bio", "avatar_url", "cover_url"]) body[field] = profile[field];
  return { ...body, ...overrides };
}

function putProfile(body) {
  return fetch("/users/me/profile", {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function saveFavorites(ids, message) {
  return runChange(() => putProfile(profileBody({ favorite_game_ids: ids })), message);
}

function moveFavorite(index, offset) {
  const ids = profile.favorite_games.map((game) => game.id);
  [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
  return saveFavorites(ids, null);
}

function addToFavorites(game) {
  return runChange(() => fetch(`/games/${game.id}/favorite`, { method: "PUT" }), window.i18n.t("Added to your favorites."));
}

function removeFromWishlist(game) {
  return runChange(() => fetch(`/games/${game.id}/wishlist`, { method: "DELETE" }), window.i18n.t("Removed from your wishlist."));
}

function setEditing(editing) {
  pageView.hidden = editing;
  profileForm.hidden = !editing;
  editButton.hidden = editing;
  profileStatus.textContent = "";
}

// Uploaded images make a handy source for avatars and covers; only administrators can list them.
async function loadUploadedImages() {
  try {
    const response = await fetch("/admin/uploads", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const images = (await response.json()).filter((upload) => upload.previewable);
    document.getElementById("uploaded-images").replaceChildren(...images.map((upload) => {
      const option = document.createElement("option");
      option.value = `/admin/uploads/${upload.id}?inline=true`;
      option.label = upload.original_name;
      return option;
    }));
  } catch {
    // Links can still be typed in by hand.
  }
}

editButton.addEventListener("click", () => {
  for (const field of ["display_name", "location", "email", "bio", "avatar_url", "cover_url"]) {
    profileForm.elements[field].value = profile[field] || "";
  }
  setEditing(true);
  profileForm.elements.display_name.focus();
  if (profile.role === "admin") loadUploadedImages();
});

document.getElementById("user-profile-cancel").addEventListener("click", () => {
  setEditing(false);
  editButton.focus();
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const saveButton = document.getElementById("user-profile-save");
  const values = new FormData(profileForm);
  saveButton.disabled = true;
  profileStatus.textContent = "Saving profile...";
  window.setStatusLoading?.(profileStatus, true);
  try {
    // Favorites are left out so they stay as they are.
    const response = await putProfile({
      display_name: values.get("display_name"),
      location: values.get("location"),
      bio: values.get("bio"),
      avatar_url: values.get("avatar_url"),
      cover_url: values.get("cover_url"),
      email: values.get("email"),
    });
    if (!response.ok) throw new Error(await readError(response, "The profile could not be saved."));
    profile = await response.json();
    renderProfile();
    setEditing(false);
    editButton.focus();
    showToast(window.i18n.t("Your profile was saved."));
    // A new email address can make email codes available in the Security section.
    document.dispatchEvent(new CustomEvent("profilesaved"));
  } catch (error) {
    profileStatus.textContent = window.i18n.t(error.message);
  } finally {
    window.setStatusLoading?.(profileStatus, false);
    saveButton.disabled = false;
  }
});

document.addEventListener("languagechange", () => {
  if (profile) renderProfile();
});

logoutButton.addEventListener("click", async () => {
  await window.realtime?.stop();
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/library");
  }
});

// Favorites and wishlist changes made in another tab arrive as listsChanged events.
function refreshLists() {
  if (busy) return;
  loadProfile().catch((error) => { pageStatus.textContent = error.message; });
}

async function initProfile() {
  try {
    const principalResponse = await fetch("/users");
    if (!principalResponse.ok) {
      showAccess("Sign in to see your profile.");
      return;
    }
    const principal = await principalResponse.json();
    await loadProfile();
    showProfile(principal);
    window.realtime?.on("listsChanged", refreshLists);
    window.realtime?.on("gameChanged", refreshLists);
    window.realtime?.onReconnected(refreshLists);
    window.realtime?.start();
  } catch (error) {
    showAccess(error.message === "Failed to fetch" ? "The server could not be reached." : error.message);
  }
}

initProfile();
