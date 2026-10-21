// Requires shelf.js to be loaded first.
const releaseFilter = document.getElementById("release-filter");
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
let releasePage = 1;
let totalReleasePages = 1;
let paginationBusy = false;

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
    });
    const response = await fetch(`/games/all-releases?${params}`);
    const result = await readReleaseResponse(response);
    games = result.items;
    releasePage = page;
    totalReleasePages = Math.max(1, Math.ceil(result.total / limit));
    renderGames();
    appStatus.textContent = "";
  } finally {
    window.setStatusLoading(appStatus, false);
    paginationBusy = false;
    updatePaginationControls();
  }
}

function showReleases(page) {
  loadGamesReleases(page).catch((error) => {
    appStatus.textContent = error.message;
  });
}

function navigateToReleasePage(page) {
  if (page < 1 || page > totalReleasePages || page === releasePage) return;
  showReleases(page);
}

releaseFilter.addEventListener("submit", (event) => {
  event.preventDefault();
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
  load: () => loadGamesReleases(1),
  reset: () => {
    releasePage = 1;
    totalReleasePages = 1;
    releaseDateLabel.textContent = "";
    updatePaginationControls();
  },
});
