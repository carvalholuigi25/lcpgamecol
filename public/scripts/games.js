// Requires shelf.js to be loaded first.
const GAMES_LIMIT = 12;
const pagePrefix = document.getElementById("page-prefix");
const pageSelector = document.getElementById("page-selector");
const pageTotal = document.getElementById("page-total");
const firstPageButton = document.getElementById("first-page");
const previousPageButton = document.getElementById("previous-page");
const nextPageButton = document.getElementById("next-page");
const lastPageButton = document.getElementById("last-page");
let gamePage = 1;
let totalGamePages = 1;
let paginationBusy = false;

function updatePaginationControls() {
  const onFirst = gamePage <= 1;
  const onLast = gamePage >= totalGamePages;
  firstPageButton.disabled = paginationBusy || onFirst;
  previousPageButton.disabled = paginationBusy || onFirst;
  nextPageButton.disabled = paginationBusy || onLast;
  lastPageButton.disabled = paginationBusy || onLast;
  pageSelector.disabled = paginationBusy || totalGamePages <= 1;
  if (pageSelector.options.length !== totalGamePages) {
    pageSelector.replaceChildren(
      ...Array.from({ length: totalGamePages }, (_, index) => {
        const page = index + 1;
        return new Option(page, page);
      }),
    );
  }
  if (!paginationBusy) pageSelector.value = String(gamePage);
  pagePrefix.textContent = window.i18n.t("Page");
  pageTotal.textContent = window.i18n.t("of {total}", { total: totalGamePages });
}

async function readGamesResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("json")) {
    throw new Error(
      `The games API returned ${contentType || "an unknown content type"} from ${response.url} instead of JSON. ` +
        "Check that this request is reaching the FastAPI server.",
    );
  }

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || "The game collection could not be loaded.");
  }
  return result;
}

async function loadGames(page = gamePage) {
  if (paginationBusy) return;
  paginationBusy = true;
  updatePaginationControls();
  appStatus.textContent = "Loading your shelf...";
  window.setStatusLoading(appStatus, true);

  try {
    const params = new URLSearchParams({
      limit: GAMES_LIMIT,
      skip: (page - 1) * GAMES_LIMIT,
    });
    const response = await fetch(`/games/page?${params}`, { cache: "no-store" });
    const result = await readGamesResponse(response);
    games = result.items;
    gamePage = page;
    totalGamePages = Math.max(1, Math.ceil(result.total / GAMES_LIMIT));
    renderGames();
    appStatus.textContent = "";
  } finally {
    window.setStatusLoading(appStatus, false);
    paginationBusy = false;
    updatePaginationControls();
  }
}

function showGames(page) {
  loadGames(page).catch((error) => {
    appStatus.textContent = error.message;
  });
}

function navigateToGamePage(page) {
  if (page < 1 || page > totalGamePages || page === gamePage) return;
  showGames(page);
}

firstPageButton.addEventListener("click", () => navigateToGamePage(1));
previousPageButton.addEventListener("click", () => navigateToGamePage(gamePage - 1));
nextPageButton.addEventListener("click", () => navigateToGamePage(gamePage + 1));
lastPageButton.addEventListener("click", () => navigateToGamePage(totalGamePages));
pageSelector.addEventListener("change", () => {
  navigateToGamePage(Number(pageSelector.value));
});
document.addEventListener("languagechange", updatePaginationControls);

initShelf({
  load: () => loadGames(1),
  reset: () => {
    gamePage = 1;
    totalGamePages = 1;
    updatePaginationControls();
  },
});
