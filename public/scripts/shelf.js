// Shared behaviour for the Game Shelf pages (login, rendering, details, logout).
// Page scripts call initShelf({ load, reset, refresh, gameActions }) after this file is loaded.

const mLoginPanel = document.getElementById("mlogin-panel");
const loginPanel = document.getElementById("login-panel");
const loginForm = document.getElementById("login-form");
const appPanel = document.getElementById("app-panel");
const loginStatus = document.getElementById("login-status");
const appStatus = document.getElementById("app-status");
const gamesContainer = document.getElementById("games");
const count = document.getElementById("count");
const searchInput = document.getElementById("search");
const detailsDialog = document.getElementById("game-details");
// Own modal dialog so the lightbox stacks above (and stays interactive over) the details dialog.
const lightboxDialog = document.getElementById("screenshot-lightbox");
const userMenu = document.getElementById("user-menu");
const userAvatar = document.getElementById("user-avatar");
const usernameDisplay = document.getElementById("username-display");
const logoutButton = document.getElementById("logout-button");
const platformSwitch = document.getElementById("platform-switch");
const platformMenu = platformSwitch?.querySelector(".platform-switch-menu");
const platformLabel = platformSwitch?.querySelector(".platform-switch-label");
const detailsActions = document.getElementById("details-actions");
const detailsActionsStatus = document.getElementById("details-actions-status");
const DEFAULT_GAME_COVER = "/public/images/default-game-cover.svg";
const LIST_ACTIONS = {
  wishlist: {
    path: "wishlist",
    list: "wishlist",
    stateKey: "wishlisted",
    add: "Add to wishlist",
    remove: "Remove from wishlist",
    icons: ["bi-bookmark-plus", "bi-bookmark-check-fill"],
    added: "Added to your wishlist.",
    removed: "Removed from your wishlist.",
  },
  favorite: {
    path: "favorite",
    list: "favorites",
    stateKey: "favorite",
    add: "Add to favorites",
    remove: "Remove from favorites",
    icons: ["bi-heart", "bi-heart-fill"],
    added: "Added to your favorites.",
    removed: "Removed from your favorites.",
  },
};
let games = [];
let currentProfile = null;
// "library": games are library rows. "releases": games are IGDB records, linked to a
// library copy (if any) through releaseLinks. null: no wishlist/favorite/edit/delete.
let gameActionsMode = null;
let myLists = { wishlist: new Set(), favorites: new Set() };
// IGDB id -> library game id, or null once we know the release is not in the library.
const releaseLinks = new Map();
let activeDetailsGameId = null;
let detailsTrailerPlayer = null;
let screenshotGallery = null;
let screenshotGalleryItems = [];
let screenshotGalleryOpen = false;
// An empty set means all platforms.
let selectedPlatforms = new Set();
let renderedPlatforms = null;

// Sort selects hold "field:order" values; the choice is remembered per browser.
function initSortSelect(select, settingName, onChange) {
  if (!select) return () => ({});
  const saved = window.gamesLibrarySettings.get(settingName);
  if ([...select.options].some((option) => option.value === saved)) select.value = saved;
  select.addEventListener("change", () => {
    window.gamesLibrarySettings.set(settingName, select.value);
    onChange();
  });
  return () => {
    const [sort, order] = select.value.split(":");
    return { sort, order };
  };
}

function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[character],
  );
}

function isEmpty(value) {
  return value === null || value === undefined || value === "";
}

function convToArtworkMed(cover) {
  return String(cover).replace("t_thumb", "t_screenshot_med_2x");
}

function convToCoverBig(cover) {
  return String(cover).replace("t_thumb", "t_cover_big");
}

function coverOf(game) {
  const cover = game.cover_image_url || game.image_url;
  return cover ? convToCoverBig(cover) : "";
}

function artworkOf(game) {
  const artwork = game.screenshot_url;
  return artwork ? convToArtworkMed(artwork) : "";
}

function formatDetail(value) {
  if (isEmpty(value) || (Array.isArray(value) && value.length === 0)) return window.i18n.t("Not set");
  if (typeof value === "boolean") return window.i18n.t(value ? "Yes" : "No");
  return escapeHtml(Array.isArray(value) ? value.join(", ") : value);
}

function safeWebUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

function setImage(image, fallback, source, altText) {
  image.alt = altText;
  image.hidden = false;
  fallback.hidden = true;
  image.dataset.fallbackApplied = String(!source);
  image.onerror = () => {
    if (image.dataset.fallbackApplied !== "true") {
      image.dataset.fallbackApplied = "true";
      image.src = DEFAULT_GAME_COVER;
    } else {
      image.hidden = true;
      fallback.hidden = false;
    }
  };
  image.src = source || DEFAULT_GAME_COVER;
}

function gameCard(game) {
  const cover = coverOf(game);
  const title = escapeHtml(game.title);

  const coverHtml = `<img class="game-cover game-cover-image" src="${escapeHtml(cover || DEFAULT_GAME_COVER)}" alt="${title} cover" loading="lazy" data-fallback-applied="${!cover}"><div class="game-cover game-cover-fallback" hidden>No cover image</div>`;
  const lists = listStateOf(game);
  const badges = [
    lists.favorite ? `<i class="bi bi-heart-fill" role="img" aria-label="In your favorites" title="In your favorites"></i>` : "",
    lists.wishlisted ? `<i class="bi bi-bookmark-check-fill" role="img" aria-label="On your wishlist" title="On your wishlist"></i>` : "",
  ].join("");
  
    return `
    <article class="game panel">
      ${badges ? `<span class="game-badges">${badges}</span>` : ""}
      ${coverHtml}
      <div><h2 class="longtitle">${title}</h2><p class="hidden">${escapeHtml(game.description || "No description yet.")}</p></div>
      <div><div class="meta hidden"><span>${escapeHtml(game.genre || "Uncategorized")}</span><span>${escapeHtml(game.release_year ?? "")}</span></div><button class="details-button" type="button" data-game-id="${escapeHtml(game.id)}">View details</button></div>
    </article>`;
}

// Platforms are stored as a comma-separated string, e.g. "PC, PlayStation 5".
function platformsOf(game) {
  const platforms = Array.isArray(game.platforms)
    ? game.platforms
    : String(game.platforms ?? "").split(",");
  return platforms.map((platform) => platform.trim()).filter(Boolean);
}

function platformOption(value, text, checked) {
  return `<label><input type="checkbox" value="${escapeHtml(value)}"${checked ? " checked" : ""}>${escapeHtml(text)}</label>`;
}

function updatePlatformLabel() {
  const selected = [...selectedPlatforms];
  platformLabel.textContent =
    selected.length === 0 ? window.i18n.t("All platforms")
    : selected.length === 1 ? selected[0]
    : window.i18n.t("{count} platforms", { count: selected.length });
}

// Rebuilds the platform checkboxes from the loaded games ("" is "All platforms").
function renderPlatformSwitch() {
  if (!platformSwitch) return;
  const platforms = [...new Set(games.flatMap(platformsOf))].sort();
  // Only rebuild when the list changes, so toggling a checkbox keeps its focus.
  if (platforms.join("|") === renderedPlatforms) return;
  renderedPlatforms = platforms.join("|");
  selectedPlatforms = new Set(platforms.filter((platform) => selectedPlatforms.has(platform)));
  platformMenu.innerHTML = [
    platformOption("", "All platforms", selectedPlatforms.size === 0),
    ...platforms.map((platform) => platformOption(platform, platform, selectedPlatforms.has(platform))),
  ].join("");
  updatePlatformLabel();
}

function resetPlatformSwitch() {
  selectedPlatforms = new Set();
  renderedPlatforms = null;
  if (!platformSwitch) return;
  platformSwitch.open = false;
  platformMenu.innerHTML = platformOption("", "All platforms", true);
  updatePlatformLabel();
}

function filterGames(items) {
  const query = searchInput.value.trim().toLowerCase();
  return items.filter(
    (game) =>
      (selectedPlatforms.size === 0 ||
        platformsOf(game).some((platform) => selectedPlatforms.has(platform))) &&
      `${game.title ?? ""} ${game.genre ?? ""}`.toLowerCase().includes(query),
  );
}

// Renders the loaded games, respecting the search box and selected platform.
function renderGames() {
  renderPlatformSwitch();
  const items = filterGames(games);
  count.textContent = window.i18n.t(items.length === 1 ? "{count} game" : "{count} games", {
    count: items.length,
  });
  gamesContainer.innerHTML = items.map(gameCard).join("");
}

function replaceSpaces(str) {
  return str.toLowerCase().replace(/\s+/g, '');
}

function getRatingStatus(rating) {
  if (!Number.isFinite(rating)) return "unknown";
  return rating >= 90 ? "excellent" :
    rating >= 80 ? "verygood" :
    rating >= 70 ? "good" :
    rating >= 50 ? "mediocre" :
    rating >= 40 ? "bad" :
    rating >= 30 ? "verybad" :
    "abysmal";
}

// Circular progress bar for 0-100 ratings; falls back to "Not set" text.
function ratingDetail(label, value) {
  const key = replaceSpaces(label);
  const rating = isEmpty(value) ? NaN : Math.min(100, Math.max(0, Math.round(Number(value))));
  if (!Number.isFinite(rating)) {
    return `<dd class="val${key} unknown">Not set</dd>`;
  }
  return `<dd class="val${key} ${getRatingStatus(rating)}" data-value="${rating}">
      <div class="progress-bar" role="progressbar" aria-label="${escapeHtml(label)}"
        aria-valuemin="0" aria-valuemax="100" aria-valuenow="${rating}" style="--rating: ${rating}">
        <span class="progress-label">${rating}%</span>
      </div>
    </dd>`;
}

const richTextTags = new Set(["P", "BR", "H3", "H4", "STRONG", "B", "EM", "I", "U", "S", "OL", "UL", "LI", "A"]);

// Rebuild admin-authored rich text keeping only the formatting the Quill editor produces.
function sanitizeRichText(html) {
  const source = new DOMParser().parseFromString(html, "text/html").body;
  const output = document.createElement("div");
  const copyChildren = (from, to) => {
    for (const node of from.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        to.append(node.textContent);
      } else if (node.nodeType === Node.ELEMENT_NODE && richTextTags.has(node.tagName)) {
        const element = document.createElement(node.tagName);
        const url = node.tagName === "A" && safeWebUrl(node.getAttribute("href"));
        if (url) {
          element.href = url.href;
          element.target = "_blank";
          element.rel = "noopener noreferrer";
        }
        if (node.tagName === "LI" && ["bullet", "ordered"].includes(node.dataset.list)) {
          element.dataset.list = node.dataset.list;
        }
        copyChildren(node, element);
        to.append(element);
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        copyChildren(node, to);
      }
    }
  };
  copyChildren(source, output);
  return output.innerHTML;
}

function richTextDetail(key, value) {
  if (isEmpty(value)) return `<dd class="val${key}">${formatDetail(value)}</dd>`;
  const html = /<[a-z][\s\S]*>/i.test(value) ? sanitizeRichText(value) : escapeHtml(value);
  return `<dd class="val${key} rich-text" translate="no">${html}</dd>`;
}

function getGamesDetailsRes(label, value) {
  const key = replaceSpaces(label);
  let detail;
  if (label.toLowerCase().includes("rating")) {
    detail = ratingDetail(label, value);
  } else if (label.toLowerCase().includes("system requirements")) {
    detail = richTextDetail(key, value);
  } else if (label === "Website" && safeWebUrl(value)) {
    const url = safeWebUrl(value);
    detail = `<dd class="val${key}"><a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url.hostname)}</a></dd>`;
  } else {
    detail = `<dd class="val${key}">${formatDetail(value)}</dd>`;
  }

  return `
  <div class="${key}">
    <dt class="lbl${key}">${label}</dt>
    ${detail}
  </div>`;
}

function renderTrailer(trailerUrl) {
  const section = document.getElementById("details-trailer-section");
  const container = document.getElementById("details-trailer");
  detailsTrailerPlayer?.dispose();
  detailsTrailerPlayer = null;
  container.replaceChildren();
  const url = safeWebUrl(trailerUrl);
  section.hidden = !url;
  if (!url) return;

  let videoSource = null;
  if (["youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com", "youtu.be"].includes(url.hostname)) {
    const videoId = url.hostname === "youtu.be"
      ? url.pathname.slice(1)
      : url.searchParams.get("v") || url.pathname.match(/^\/(?:embed|shorts)\/([^/]+)/)?.[1];
    if (videoId && /^[\w-]+$/.test(videoId)) {
      videoSource = {
        src: `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`,
        type: "video/youtube",
      };
    }
  } else if (/\.(mp4|webm|ogg)$/i.test(url.pathname)) {
    const extension = url.pathname.match(/\.(mp4|webm|ogg)$/i)[1].toLowerCase();
    videoSource = {
      src: url.href,
      type: { mp4: "video/mp4", webm: "video/webm", ogg: "video/ogg" }[extension],
    };
  }

  if (videoSource) {
    const video = document.createElement("video");
    video.className = "video-js vjs-big-play-centered details-trailer-video";
    video.controls = true;
    video.preload = "metadata";
    container.append(video);
    detailsTrailerPlayer = window.videojs(video, {
      aspectRatio: "16:9",
      controls: true,
      fluid: true,
      preload: "metadata",
      techOrder: ["youtube", "html5"],
      sources: [videoSource],
    });
    return;
  }

  let embedUrl = "";
  if (["vimeo.com", "www.vimeo.com", "player.vimeo.com"].includes(url.hostname)) {
    const videoId = url.pathname.match(/\/(?:video\/)?(\d+)/)?.[1];
    if (videoId) embedUrl = `https://player.vimeo.com/video/${videoId}`;
  }

  if (embedUrl) {
    const frame = document.createElement("iframe");
    frame.className = "details-trailer-frame";
    frame.title = "Game trailer";
    frame.src = embedUrl;
    frame.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    frame.allowFullscreen = true;
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation");
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    container.append(frame);
    return;
  }

  const link = document.createElement("a");
  link.href = url.href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Watch trailer";
  container.append(link);
}

function renderScreenshotGallery(game) {
  const section = document.getElementById("details-screenshots-section");
  const gallery = document.getElementById("details-screenshot-gallery");
  const screenshot = document.getElementById("details-screenshot");
  const fallback = document.getElementById("details-screenshot-fallback");
  const imageUrls = [...new Set([game.screenshot_url, ...(game.screenshots || [])]
    .filter((url) => typeof url === "string" && safeWebUrl(url)))];
  gallery.replaceChildren();
  section.hidden = imageUrls.length === 0;
  screenshotGalleryItems = imageUrls.map((imageUrl, index) => ({
    src: imageUrl,
    thumb: imageUrl,
    alt: `${game.title} screenshot ${index + 1}`,
    subHtml: `<h4>${escapeHtml(game.title)}</h4><p>Screenshot ${index + 1}</p>`,
  }));
  for (const [index, imageUrl] of imageUrls.entries()) {
    const button = document.createElement("button");
    button.className = "details-screenshot-thumb";
    button.type = "button";
    button.setAttribute("aria-label", `Show screenshot ${index + 1}`);
    button.setAttribute("aria-pressed", String(index === 0));
    const image = document.createElement("img");
    image.src = imageUrl;
    image.alt = `${game.title} screenshot ${index + 1}`;
    image.loading = "lazy";
    button.append(image);
    button.addEventListener("click", () => {
      setImage(screenshot, fallback, imageUrl, image.alt);
      for (const thumbnail of gallery.children) {
        thumbnail.setAttribute("aria-pressed", String(thumbnail === button));
      }
      if (!screenshotGallery) {
        screenshotGallery = window.lightGallery(gallery, {
          container: lightboxDialog,
          download: false,
          dynamic: true,
          dynamicEl: screenshotGalleryItems,
          plugins: [window.lgZoom],
        });
        gallery.addEventListener("lgAfterClose", () => {
          screenshotGalleryOpen = false;
          if (lightboxDialog.open) lightboxDialog.close();
        });
      } else {
        screenshotGallery.refresh(screenshotGalleryItems);
      }
      if (!lightboxDialog.open) lightboxDialog.showModal();
      screenshotGallery.openGallery(index, button);
      screenshotGalleryOpen = true;
    });
    gallery.append(button);
  }
  screenshotGallery?.refresh(screenshotGalleryItems);
}

function showGameDetails(game) {
  if (!game) return;
  // Keep the last action message while live updates re-render the same game.
  if (activeDetailsGameId !== game.id || !detailsDialog.open) {
    if (detailsActionsStatus) detailsActionsStatus.textContent = "";
  }
  activeDetailsGameId = game.id;
  const minimumRequirements = game.minimum_system_requirements?.trim()
    ? game.minimum_system_requirements
    : null;
  const recommendedRequirements = game.recommended_system_requirements?.trim()
    ? game.recommended_system_requirements
    : null;
  const requirementsWarning = document.getElementById("details-requirements-warning");
  requirementsWarning.hidden = Boolean(minimumRequirements || recommendedRequirements);
  requirementsWarning.textContent = requirementsWarning.hidden
    ? ""
    : window.i18n.t("No system requirements have been added for this game.");
  document.getElementById("details-title").textContent = game.title;
  const mainScreenshot = game.screenshot_url || game.screenshots?.[0] || "";
  setImage(
    document.getElementById("details-screenshot"),
    document.getElementById("details-screenshot-fallback"),
    mainScreenshot ? convToArtworkMed(mainScreenshot) : artworkOf(game),
    `${game.title} cover`,
  );
  setImage(
    document.getElementById("details-image"),
    document.getElementById("details-image-fallback"),
    coverOf(game),
    `${game.title} cover`,
  );
  document.getElementById("details-description").textContent =
    game.description || "No description yet.";
  document.getElementById("details-grid").innerHTML = [
    ["Genre", game.genre],
    ["Developer", game.developer_name],
    ["Publisher", game.publisher_name],
    ["Website", game.website_url],
    ["Release date", game.release_date || game.release_year],
    ["Platforms", game.platforms],
    ["Game modes", Array.isArray(game.gamemodes) ? game.gamemodes.map((mode) => mode.name).join(", ") : game.gamemodes],
    ["Edition", game.editions],
    ["ESRB", getGameESRBLabel(game.esrb)],
    ["User rating", game.user_rating],
    ["Critic rating", game.critic_rating],
    ["Hours played", game.hoursplayed],
  ].map(
      ([label, value]) => getGamesDetailsRes(label, value),
    ).join("");
  const actionsGrid = document.getElementById("details-grid-actions");
  if (actionsGrid) {
    actionsGrid.innerHTML = [
      ["Wishlisted", game.wishlisted],
    ].map(
        ([label, value]) => getGamesDetailsRes(label, value),
      ).join("");
  }
  renderDetailsActions(game);
  document.getElementById("details-grid-info").innerHTML = [
    ["Minimum system requirements", minimumRequirements],
    ["Recommended system requirements", recommendedRequirements]
  ].map(
      ([label, value]) => getGamesDetailsRes(label, value),
    ).join("");
  renderScreenshotGallery(game);
  const achievementList = document.getElementById("details-achievements-list");
  const achievementStatus = document.getElementById("details-achievements-status");
  achievementList.replaceChildren();
  achievementStatus.textContent = "Loading achievements...";
  window.setStatusLoading(achievementStatus, true);
  if (!detailsDialog.open) detailsDialog.showModal();
  renderTrailer(game.trailer_url);
  loadGameAchievements(game.id);
}

// gameId is the id of the game shown in the dialog. On the releases page that is an
// IGDB id, and the achievements belong to the release's library copy instead.
async function loadGameAchievements(gameId) {
  const achievementList = document.getElementById("details-achievements-list");
  const achievementStatus = document.getElementById("details-achievements-status");
  const game = games.find((item) => item.id === gameId);
  const libraryId = gameActionsMode === "releases" ? (game ? libraryIdOf(game) : null) : gameId;
  if (libraryId === null) {
    window.setStatusLoading(achievementStatus, false);
    achievementList.replaceChildren();
    achievementStatus.textContent = window.i18n.t("Add this release to the library to track its achievements.");
    return;
  }
  try {
    const response = await fetch(`/games/${encodeURIComponent(libraryId)}/achievements?limit=100`);
    if (!response.ok) throw new Error("Achievements could not be loaded.");
    const achievements = await response.json();
    if (String(activeDetailsGameId) !== String(gameId)) return;
    window.setStatusLoading(achievementStatus, false);
    achievementList.innerHTML = achievements.map((achievement) => {
      const unlocked = Boolean(achievement.unlocked);
      // One span per part so i18n.js can translate the type and points separately.
      const metadata = [
        achievement.achievement_type,
        achievement.points == null ? "" : `${achievement.points} points`,
        unlocked && achievement.date_unlocked ? achievement.date_unlocked : "",
      ].filter(Boolean).map((part) => `<span>${escapeHtml(part)}</span>`).join(" / ");
      return `<li class="achievement-item${unlocked ? " is-unlocked" : ""}">
        <span class="achievement-state" role="img" aria-label="${unlocked ? "Unlocked" : "Locked"}"></span>
        <div class="achievement-copy">
          <img src="${escapeHtml(achievement.image_url)}" alt="${escapeHtml(achievement.title)}" class="img-fluid img-achievement-icon" />
          <div class="achievement-copy-i md:ms-1">
            <strong>${escapeHtml(achievement.title)}</strong>
            <span>${escapeHtml(achievement.description || "No description.")}</span>
          </div>
        </div>
        <span class="achievement-meta">${metadata}</span>
      </li>`;
    }).join("");
    achievementStatus.textContent = achievements.length
      ? window.i18n.t("{count} of {total} unlocked", {
        count: achievements.filter((achievement) => achievement.unlocked).length,
        total: achievements.length,
      })
      : window.i18n.t("No achievements for this game yet.");
  } catch (error) {
    if (String(activeDetailsGameId) !== String(gameId)) return;
    window.setStatusLoading(achievementStatus, false);
    achievementStatus.textContent = error.message;
  }
}

function isAdmin() {
  return currentProfile?.role === "admin";
}

// The library game behind a card: itself on the library page, its imported copy on
// the releases page (null when the release is not in the library yet).
function libraryIdOf(game) {
  if (gameActionsMode === "releases") return releaseLinks.get(game.id) ?? null;
  return gameActionsMode ? game.id : null;
}

function listStateOf(game) {
  const libraryId = libraryIdOf(game);
  return {
    wishlisted: libraryId !== null && myLists.wishlist.has(libraryId),
    favorite: libraryId !== null && myLists.favorites.has(libraryId),
  };
}

function activeGame() {
  return games.find((item) => item.id === activeDetailsGameId);
}

function renderDetailsActions(game) {
  if (!detailsActions) return;
  detailsActions.hidden = !gameActionsMode || !currentProfile;
  if (detailsActions.hidden) return;
  const lists = listStateOf(game);
  for (const button of detailsActions.querySelectorAll("[data-list-action]")) {
    const action = LIST_ACTIONS[button.dataset.listAction];
    const active = lists[action.stateKey];
    button.setAttribute("aria-pressed", String(active));
    button.querySelector("i").className = `bi ${action.icons[Number(active)]}`;
    // Icon-only button: the label lives in aria-label (screen readers) and title (tooltip).
    const label = window.i18n.t(active ? action.remove : action.add);
    button.setAttribute("aria-label", label);
    button.title = label;
  }
  const libraryId = libraryIdOf(game);
  const editLink = document.getElementById("details-edit");
  editLink.hidden = !isAdmin();
  // On the releases page the game may still need importing; the click handler does that.
  editLink.href = libraryId === null ? "/admin" : `/admin?edit-game=${encodeURIComponent(libraryId)}#records-panel`;
  document.getElementById("details-delete").hidden = !isAdmin() || libraryId === null;
}

async function readActionError(response, fallback) {
  try {
    return (await response.json()).detail || fallback;
  } catch {
    return fallback;
  }
}

function renderActiveDetailsActions() {
  const game = activeGame();
  if (game && detailsDialog.open) renderDetailsActions(game);
}

async function loadMyLists() {
  if (!gameActionsMode) return;
  const response = await fetch("/users/me/game-lists", { cache: "no-store" });
  if (!response.ok) return;
  const lists = await response.json();
  myLists = { wishlist: new Set(lists.wishlist), favorites: new Set(lists.favorites) };
  renderGames();
  renderActiveDetailsActions();
}

// Releases page: find which of the shown IGDB games are already in the library.
async function syncReleaseLinks(ids = games.map((game) => game.id)) {
  if (gameActionsMode !== "releases" || !ids.length) return;
  const response = await fetch(`/games/igdb/links?ids=${ids.slice(0, 100).join(",")}`, { cache: "no-store" });
  if (!response.ok) return;
  const links = await response.json();
  const openGame = detailsDialog.open ? activeGame() : null;
  const openLinkBefore = openGame ? libraryIdOf(openGame) : null;
  for (const id of ids) releaseLinks.set(id, links[id] ?? null);
  renderGames();
  renderActiveDetailsActions();
  if (openGame && libraryIdOf(openGame) !== openLinkBefore) loadGameAchievements(openGame.id);
}

// Returns the library id for a game, importing an IGDB release first when needed.
async function ensureLibraryGame(game) {
  const libraryId = libraryIdOf(game);
  if (libraryId !== null) return libraryId;
  detailsActionsStatus.textContent = window.i18n.t("Adding {title} to the library...", { title: game.title });
  const response = await fetch(`/games/igdb/${encodeURIComponent(game.id)}/import`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await readActionError(response, "The game could not be added to the library."));
  }
  const status = await response.json();
  releaseLinks.set(game.id, status.game_id);
  if (activeDetailsGameId === game.id) loadGameAchievements(game.id);
  return status.game_id;
}

async function toggleGameList(button) {
  const action = LIST_ACTIONS[button.dataset.listAction];
  const game = activeGame();
  if (!game) return;
  const active = button.getAttribute("aria-pressed") === "true";
  button.disabled = true;
  try {
    const libraryId = await ensureLibraryGame(game);
    const response = await fetch(`/games/${encodeURIComponent(libraryId)}/${action.path}`, {
      method: active ? "DELETE" : "PUT",
    });
    if (!response.ok) {
      throw new Error(await readActionError(response, "Your lists could not be updated."));
    }
    const state = await response.json();
    myLists.wishlist[state.wishlisted ? "add" : "delete"](state.game_id);
    myLists.favorites[state.favorite ? "add" : "delete"](state.game_id);
    renderGames();
    if (activeDetailsGameId === game.id) renderDetailsActions(game);
    detailsActionsStatus.textContent = window.i18n.t(state[action.stateKey] ? action.added : action.removed);
  } catch (error) {
    detailsActionsStatus.textContent = window.i18n.t(error.message);
  } finally {
    button.disabled = false;
  }
}

async function editActiveGame(event) {
  if (gameActionsMode !== "releases") return;
  event.preventDefault();
  const game = activeGame();
  if (!game) return;
  try {
    const libraryId = await ensureLibraryGame(game);
    window.location.href = `/admin?edit-game=${encodeURIComponent(libraryId)}#records-panel`;
  } catch (error) {
    detailsActionsStatus.textContent = window.i18n.t(error.message);
  }
}

async function deleteActiveGame(refresh) {
  const game = activeGame();
  const libraryId = game ? libraryIdOf(game) : null;
  if (libraryId === null) return;
  const releases = gameActionsMode === "releases";
  const question = releases ? "Remove {title} from the library?" : "Delete {title} and its achievements?";
  if (!window.confirm(window.i18n.t(question, { title: game.title }))) return;
  const button = document.getElementById("details-delete");
  button.disabled = true;
  try {
    const response = await fetch(`/games/${encodeURIComponent(libraryId)}`, { method: "DELETE" });
    if (!response.ok && response.status !== 404) {
      throw new Error(await readActionError(response, "The game could not be deleted."));
    }
    if (releases) {
      // The release itself is still on IGDB, so keep its details open.
      releaseLinks.set(game.id, null);
      myLists.wishlist.delete(libraryId);
      myLists.favorites.delete(libraryId);
      renderGames();
      renderDetailsActions(game);
      loadGameAchievements(game.id);
      detailsActionsStatus.textContent = window.i18n.t("{title} was removed from the library.", { title: game.title });
      return;
    }
    detailsDialog.close();
    await refresh();
    appStatus.textContent = window.i18n.t("{title} was deleted.", { title: game.title });
  } catch (error) {
    detailsActionsStatus.textContent = window.i18n.t(error.message);
  } finally {
    button.disabled = false;
  }
}

function showApp(profile) {
  const { username } = profile;
  currentProfile = profile;
  mLoginPanel.classList.add("hidden");
  appPanel.style.display = "block";
  userAvatar.textContent = username.charAt(0).toUpperCase();
  usernameDisplay.textContent = username;
  userMenu.hidden = false;
  loginStatus.textContent = "";
}

function showLogin() {
  currentProfile = null;
  myLists = { wishlist: new Set(), favorites: new Set() };
  releaseLinks.clear();
  if (detailsDialog.open) detailsDialog.close();
  appPanel.style.display = "none";
  userMenu.hidden = true;
  usernameDisplay.textContent = "";
  userAvatar.textContent = "";
  mLoginPanel.classList.remove("hidden");
  loginPanel.style.display = "block";
  appStatus.textContent = "";
  searchInput.value = "";
  games = [];
  resetPlatformSwitch();
  gamesContainer.replaceChildren();
  count.textContent = "";
  if(!loginStatus.classList.contains("hidden")) {
    loginStatus.classList.add("hidden");
  }
}

async function fetchProfile() {
  const response = await fetch("/users");
  return response.ok ? response.json() : null;
}

function initShelf({ load, reset = () => {}, refresh = null, gameActions = null }) {
  gameActionsMode = gameActions;

  async function openShelf(profile) {
    showApp(profile);
    window.setStatusLoading(appStatus, true);
    try {
      await load();
      await loadMyLists();
      window.setStatusLoading(appStatus, false);
    } catch (error) {
      window.setStatusLoading(appStatus, false);
      appStatus.textContent = error.message;
    }
    if (gameActionsMode) window.realtime?.start();
  }

  // Collapse bursts of live events (e.g. an admin saving several records) into one reload.
  let liveRefreshTimer = null;
  let pendingChanges = [];
  function scheduleLiveRefresh(change) {
    if (change) pendingChanges.push(change);
    clearTimeout(liveRefreshTimer);
    liveRefreshTimer = setTimeout(async () => {
      const changes = pendingChanges;
      pendingChanges = [];
      try {
        await refresh();
      } catch (error) {
        appStatus.textContent = error.message;
        return;
      }
      if (!detailsDialog.open) return;
      const removed = changes.some(
        (item) => item.action === "cleared" || (item.action === "deleted" && item.game_id === activeDetailsGameId),
      );
      if (removed) {
        detailsDialog.close();
        appStatus.textContent = window.i18n.t("This game was removed from the library.");
      } else if (changes.some((item) => item.game_id === activeDetailsGameId)) {
        const game = games.find((item) => item.id === activeDetailsGameId);
        if (game) showGameDetails(game);
      }
    }, 300);
  }

  if (gameActionsMode === "releases" && window.realtime) {
    // Release data comes from IGDB; only which releases are in the library can change.
    window.realtime.on("gameChanged", () => syncReleaseLinks());
    window.realtime.on("achievementChanged", (change) => {
      const game = detailsDialog.open ? activeGame() : null;
      if (game && libraryIdOf(game) === change.game_id) loadGameAchievements(game.id);
    });
    window.realtime.on("listsChanged", () => loadMyLists());
    window.realtime.onReconnected(() => {
      syncReleaseLinks();
      loadMyLists();
    });
  }

  if (gameActionsMode === "library" && refresh && window.realtime) {
    window.realtime.on("gameChanged", scheduleLiveRefresh);
    window.realtime.on("achievementChanged", (change) => {
      if (detailsDialog.open && change.game_id === activeDetailsGameId) loadGameAchievements(change.game_id);
    });
    window.realtime.on("listsChanged", () => loadMyLists());
    window.realtime.onReconnected(() => {
      scheduleLiveRefresh();
      loadMyLists();
    });
  }

  detailsActions?.addEventListener("click", (event) => {
    const listButton = event.target.closest("[data-list-action]");
    if (listButton) toggleGameList(listButton);
    if (event.target.closest("#details-edit")) editActiveGame(event);
    if (event.target.closest("#details-delete")) deleteActiveGame(refresh);
  });

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = loginForm.querySelector('[type="submit"]');
    submitButton.disabled = true;

    if(loginStatus.classList.contains("hidden")) {
      loginStatus.classList.remove("hidden");
    }

    loginStatus.textContent = "Signing in...";
    window.setStatusLoading(loginStatus, true);

    try {
      const response = await fetch("/auth/token", {
        method: "POST",
        body: new URLSearchParams(new FormData(loginForm)),
      });
      if (!response.ok) {
        if (response.status === 429) {
          const body = await response.json();
          window.startLoginLockout(
            loginStatus,
            submitButton,
            Number(response.headers.get("Retry-After")) || 60,
            body.detail || "Login is temporarily locked.",
          );
        } else {
          loginStatus.textContent = "Incorrect username or password.";
        }
        return;
      }
      const profile = await fetchProfile();
      if (!profile) {
        loginStatus.textContent = "Signed in, but your profile could not be loaded.";
        return;
      }
      loginForm.reset();
      await openShelf(profile);
    } catch {
      loginStatus.textContent = "The server could not be reached.";
    } finally {
      window.setStatusLoading(loginStatus, false);
      if (!window.isLoginLocked(submitButton)) submitButton.disabled = false;
    }
  });

  window.initRegistration({
    loginForm,
    registerForm: document.getElementById("register-form"),
    switchButton: document.getElementById("auth-switch"),
    onRegistered: (username, password) => {
      // Sign the new account in straight away.
      loginForm.elements.namedItem("username").value = username;
      loginForm.elements.namedItem("password").value = password;
      loginForm.requestSubmit();
    },
  });

  searchInput.addEventListener("input", renderGames);

  platformMenu?.addEventListener("change", (event) => {
    const { value, checked } = event.target;
    if (value === "" || (!checked && selectedPlatforms.size === 1)) {
      selectedPlatforms.clear();
    } else if (checked) {
      selectedPlatforms.add(value);
    } else {
      selectedPlatforms.delete(value);
    }
    platformMenu.querySelectorAll("input").forEach((input) => {
      input.checked = input.value === "" ? selectedPlatforms.size === 0 : selectedPlatforms.has(input.value);
    });
    updatePlatformLabel();
    renderGames();
  });

  // Close the dropdown when clicking outside it or pressing Escape.
  document.addEventListener("click", (event) => {
    if (platformSwitch?.open && !platformSwitch.contains(event.target)) platformSwitch.open = false;
  });
  platformSwitch?.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && platformSwitch.open) {
      platformSwitch.open = false;
      platformSwitch.querySelector("summary").focus();
    }
  });

  gamesContainer.addEventListener("click", (event) => {
    const button = event.target.closest("[data-game-id]");
    if (button) {
      showGameDetails(games.find((game) => String(game.id) === button.dataset.gameId));
    }
  });

  // <img> error events don't bubble, so listen in the capture phase.
  gamesContainer.addEventListener(
    "error",
    (event) => {
      if (event.target.matches?.(".game-cover-image")) {
        if (event.target.dataset.fallbackApplied !== "true") {
          event.target.dataset.fallbackApplied = "true";
          event.target.src = DEFAULT_GAME_COVER;
        } else {
          event.target.hidden = true;
          event.target.nextElementSibling.hidden = false;
        }
      }
    },
    true,
  );

  document.getElementById("close-details").addEventListener("click", () => {
    detailsDialog.close();
  });
  detailsDialog.addEventListener("close", () => {
    if (screenshotGalleryOpen) screenshotGallery?.closeGallery();
    screenshotGalleryOpen = false;
    if (lightboxDialog.open) lightboxDialog.close();
    detailsTrailerPlayer?.dispose();
    detailsTrailerPlayer = null;
  });
  // Escape now targets the lightbox dialog: let lightGallery animate out, then close it.
  lightboxDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    screenshotGallery?.closeGallery();
  });

  logoutButton.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      const response = await fetch("/auth/logout", { method: "POST" });
      // 401 means the session had already expired, which is still a logout.
      if (!response.ok && response.status !== 401) {
        appStatus.textContent = "You could not be logged out.";
        return;
      }
      showLogin();
      window.realtime?.stop();
      reset();
    } catch {
      appStatus.textContent = "The server could not be reached.";
    } finally {
      logoutButton.disabled = false;
    }
  });

  document.getElementById("mgames").onmousemove = e => {
    for(const games of document.getElementsByClassName("game")) {
      const rect = games.getBoundingClientRect(),
            x = e.clientX - rect.left,
            y = e.clientY - rect.top;

      games.style.setProperty("--mouse-x", `${x}px`);
      games.style.setProperty("--mouse-y", `${y}px`);
    };
  }

  fetchProfile()
    .then((profile) => {
      if (profile) return openShelf(profile);
    })
    .catch(() => {
      if(loginStatus.classList.contains("hidden")) {
        loginStatus.classList.remove("hidden");
      }
      
      loginStatus.textContent = "The server could not be reached.";
    });
}
