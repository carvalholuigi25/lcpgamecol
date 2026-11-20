// Requires shelf.js to be loaded first.
const releaseFilter = document.getElementById("release-filter");
const globalTitleSearchToggle = document.getElementById("search-all-titles");
const releaseControls = releaseFilter.querySelectorAll("[data-release-control]");
const yearInput = document.getElementById("release-year");
const monthInput = document.getElementById("release-month");
const dayInput = document.getElementById("release-day");
const limitInput = document.getElementById("release-limit");
const releaseDateLabel = document.getElementById("colgamereldate");
const pagePrefix = document.getElementById("page-prefix");
const pageSelector = document.getElementById("page-selector");
const pageTotal = document.getElementById("page-total");
const firstPageButton = document.getElementById("first-page");
const previousPageButton = document.getElementById("previous-page");
const nextPageButton = document.getElementById("next-page");
const lastPageButton = document.getElementById("last-page");
const DEFAULT_LIMIT = 12;
// The backend (and IGDB) return at most this many titles per global search.
const GLOBAL_SEARCH_LIMIT = 500;
// One-letter queries match most of IGDB, so wait for a second character.
const GLOBAL_SEARCH_MIN_LENGTH = 2;
const GLOBAL_SEARCH_DELAY_MS = 350;
const LOCAL_SEARCH_PLACEHOLDER = searchInput.getAttribute("placeholder");
const GLOBAL_SEARCH_PLACEHOLDER = "Search all game titles";
// A reload requested during a load would be dropped by the busy guard, so run it afterwards.
let reloadQueued = false;
function reloadFirstPage() {
  if (globalTitleSearchToggle.checked) return;
  if (paginationBusy) {
    reloadQueued = true;
    return;
  }
  showReleases(1);
}
const currentSort = initSortSelect(document.getElementById("release-sort"), "releaseSort", reloadFirstPage);
let releasePage = 1;
let totalReleasePages = 1;
let paginationBusy = false;
let globalSearchTimer = null;
let globalSearchRequest = 0;
// The query and NSFW setting of the last global search, to skip identical repeats.
let lastGlobalSearchKey = null;

function pad(num) {
  return String(num).padStart(2, "0");
}

function updatePaginationControls() {
  const onFirst = releasePage <= 1;
  const onLast = releasePage >= totalReleasePages;
  firstPageButton.disabled = paginationBusy || onFirst;
  previousPageButton.disabled = paginationBusy || onFirst;
  nextPageButton.disabled = paginationBusy || onLast;
  lastPageButton.disabled = paginationBusy || onLast;
  releaseFilter.querySelector('[type="submit"]').disabled = paginationBusy;
  pageSelector.disabled = paginationBusy || totalReleasePages <= 1;
  if (pageSelector.options.length !== totalReleasePages) {
    pageSelector.replaceChildren(
      ...Array.from({ length: totalReleasePages }, (_, index) => {
        const page = index + 1;
        return new Option(page, page);
      }),
    );
  }
  if (!paginationBusy) pageSelector.value = String(releasePage);
  pagePrefix.textContent = window.i18n.t("Page");
  pageTotal.textContent = window.i18n.t("of {total}", { total: totalReleasePages });
}

async function readReleaseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("json")) {
    throw new Error(
      `The releases API returned ${contentType || "an unknown content type"} instead of JSON. ` +
        "Open this page through the FastAPI server and check that /games/all-releases reaches the API.",
    );
  }

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || "The game collection could not be loaded.");
  }
  return result;
}

// Fills empty inputs with tomorrow's date and returns the validated filter.
function readReleaseFilter() {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (!yearInput.value) yearInput.value = tomorrow.getFullYear();
  if (!monthInput.value) monthInput.value = tomorrow.getMonth() + 1;
  if (!dayInput.value) dayInput.value = tomorrow.getDate();
  if (!limitInput.value) limitInput.value = DEFAULT_LIMIT;

  const year = Number(yearInput.value);
  const month = Number(monthInput.value);
  const day = Number(dayInput.value);
  const limit = Math.min(100, Math.max(1, Math.trunc(Number(limitInput.value)) || DEFAULT_LIMIT));
  limitInput.value = limit;

  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    throw new Error(`${year}-${pad(month)}-${pad(day)} is not a valid date.`);
  }
  return { year, month, day, limit };
}

async function loadGamesReleases(page = releasePage) {
  if (paginationBusy) return;
  const { year, month, day, limit } = readReleaseFilter();
  paginationBusy = true;
  updatePaginationControls();
  appStatus.textContent = "Loading your shelf...";
  window.setStatusLoading(appStatus, true);
  releaseDateLabel.textContent = window.i18n.t("Date for next games releases: {date}", {
    date: `${year}-${pad(month)}-${pad(day)}`,
  });

  try {
    const params = new URLSearchParams({
      limit,
      skip: (page - 1) * limit,
      year,
      month,
      day,
      hide_nsfw: hideNsfwInput.checked,
      ...currentSort(),
    });
    const response = await fetch(`/games/all-releases?${params}`);
    const result = await readReleaseResponse(response);
    // The global title search was switched on while this page loaded: its results win.
    if (globalTitleSearchToggle.checked) return;
    games = result.items;
    releasePage = page;
    totalReleasePages = Math.max(1, Math.ceil(result.total / limit));
    renderGames();
    await syncReleaseLinks();
    appStatus.textContent = "";
  } finally {
    if (!globalTitleSearchToggle.checked) window.setStatusLoading(appStatus, false);
    paginationBusy = false;
    updatePaginationControls();
    if (reloadQueued) {
      reloadQueued = false;
      reloadFirstPage();
    }
  }
}

function showReleases(page) {
  loadGamesReleases(page).catch((error) => {
    if (!globalTitleSearchToggle.checked) appStatus.textContent = error.message;
  });
}

function setGlobalSearchMode(enabled) {
  appPanel.dataset.globalSearch = String(enabled);
  releaseControls.forEach((control) => control.classList.toggle("hidden", enabled));
  searchInput.setAttribute("placeholder", enabled ? GLOBAL_SEARCH_PLACEHOLDER : LOCAL_SEARCH_PLACEHOLDER);
}

function normalizeGlobalQuery(query) {
  return query.trim().replace(/\s+/g, " ");
}

// Shows a hint instead of the "No games found" panel when no search has run yet.
function showGlobalSearchHint(message) {
  games = [];
  renderGames();
  gamesEmpty.hidden = true;
  appStatus.textContent = window.i18n.t(message);
  window.setStatusLoading(appStatus, false);
}

async function searchGlobalTitles(query, { force = false } = {}) {
  clearTimeout(globalSearchTimer);
  const title = normalizeGlobalQuery(query);
  const key = `${title.toLowerCase()}|${hideNsfwInput.checked}`;
  if (!force && key === lastGlobalSearchKey) return;
  lastGlobalSearchKey = key;
  const request = ++globalSearchRequest;

  if (!title) {
    showGlobalSearchHint("Type a game title to search all games.");
    return;
  }
  if (title.length < GLOBAL_SEARCH_MIN_LENGTH) {
    showGlobalSearchHint("Type at least 2 characters to search.");
    return;
  }

  const params = new URLSearchParams({
    query: title,
    limit: GLOBAL_SEARCH_LIMIT,
    hide_nsfw: hideNsfwInput.checked,
  });
  appStatus.textContent = window.i18n.t("Searching all game titles...");
  window.setStatusLoading(appStatus, true);
  try {
    const response = await fetch(`/games/external-search?${params}`);
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("json")) {
      throw new Error("The global game search returned an unexpected response.");
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The global game search failed.");
    if (request !== globalSearchRequest) return;
    games = result;
    renderGames();
    await syncReleaseLinks();
    if (request !== globalSearchRequest) return;
    appStatus.textContent =
      result.length >= GLOBAL_SEARCH_LIMIT
        ? window.i18n.t("Showing the first {count} matches. Refine your search to see more.", {
            count: GLOBAL_SEARCH_LIMIT,
          })
        : "";
  } catch (error) {
    if (request !== globalSearchRequest) return;
    // Let the same query be retried after a failure.
    lastGlobalSearchKey = null;
    games = [];
    renderGames();
    appStatus.textContent = error.message;
  } finally {
    if (request === globalSearchRequest) window.setStatusLoading(appStatus, false);
  }
}

function scheduleGlobalTitleSearch() {
  clearTimeout(globalSearchTimer);
  globalSearchTimer = setTimeout(() => searchGlobalTitles(searchInput.value), GLOBAL_SEARCH_DELAY_MS);
}

globalTitleSearchToggle.addEventListener("change", () => {
  clearTimeout(globalSearchTimer);
  globalSearchRequest += 1;
  lastGlobalSearchKey = null;
  const globalSearchActive = globalTitleSearchToggle.checked;
  setGlobalSearchMode(globalSearchActive);
  if (globalSearchActive) {
    releaseDateLabel.textContent = "";
    searchGlobalTitles(searchInput.value, { force: true });
  } else {
    appStatus.textContent = "";
    window.setStatusLoading(appStatus, false);
    reloadFirstPage();
  }
});

searchInput.addEventListener("input", () => {
  if (globalTitleSearchToggle.checked) scheduleGlobalTitleSearch();
});

// Enter searches right away instead of waiting for the debounce.
searchInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.isComposing || !globalTitleSearchToggle.checked) return;
  event.preventDefault();
  searchGlobalTitles(searchInput.value);
});

hideNsfwInput.addEventListener("change", () => {
  if (globalTitleSearchToggle.checked) {
    searchGlobalTitles(searchInput.value);
  } else {
    reloadFirstPage();
  }
});

function navigateToReleasePage(page) {
  if (page < 1 || page > totalReleasePages || page === releasePage) return;
  showReleases(page);
}

releaseFilter.addEventListener("submit", (event) => {
  event.preventDefault();
  if (globalTitleSearchToggle.checked) return;
  showReleases(1);
});

firstPageButton.addEventListener("click", () => navigateToReleasePage(1));
previousPageButton.addEventListener("click", () => navigateToReleasePage(releasePage - 1));
nextPageButton.addEventListener("click", () => navigateToReleasePage(releasePage + 1));
lastPageButton.addEventListener("click", () => navigateToReleasePage(totalReleasePages));
pageSelector.addEventListener("change", () => {
  navigateToReleasePage(Number(pageSelector.value));
});
document.addEventListener("languagechange", updatePaginationControls);

initShelf({
  gameActions: "releases",
  load: () => {
    // Browsers may restore the checkbox state on reload, so honour it on the first load too.
    if (!globalTitleSearchToggle.checked) return loadGamesReleases(1);
    setGlobalSearchMode(true);
    return searchGlobalTitles(searchInput.value, { force: true });
  },
  reset: () => {
    clearTimeout(globalSearchTimer);
    globalSearchRequest += 1;
    lastGlobalSearchKey = null;
    releasePage = 1;
    totalReleasePages = 1;
    releaseDateLabel.textContent = "";
    updatePaginationControls();
  },
});
