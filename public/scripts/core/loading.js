const pageLoader = document.getElementById("page-loader");

function hidePageLoader() {
  pageLoader.hidden = true;
}

function showPageLoader() {
  pageLoader.hidden = false;
}

window.setStatusLoading = (element, loading) => {
  element.classList.toggle("is-loading", loading);
};

document.addEventListener("click", (event) => {
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  ) {
    return;
  }

  const target = event.target instanceof Element ? event.target : null;
  const link = target?.closest("a[href]");
  if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;

  const destination = new URL(link.href, window.location.href);
  if (!["http:", "https:"].includes(destination.protocol)) return;
  if (
    destination.origin === window.location.origin &&
    destination.pathname === window.location.pathname &&
    destination.search === window.location.search &&
    destination.hash
  ) {
    return;
  }

  showPageLoader();
});

window.addEventListener("load", hidePageLoader);
window.addEventListener("pageshow", hidePageLoader);
if (document.readyState === "complete") hidePageLoader();
