const availableThemes = ["auto", "dark", "white", "glassmorphism", "liquid-glass", "sunsetvibes", "cyber-retro", "rgb"];
const localeByLanguage = { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR", it: "it-IT", es: "es-ES", ja: "ja-JP" };
const themeSelector = document.getElementById("theme-selector");
const liveClock = document.getElementById("live-clock");
const lockoutTimers = new WeakMap();
let selectedTheme = "auto";
let autoThemeTimer = null;
// Only the Cyber Retro theme uses this font, so it is fetched when that theme is picked
// instead of render-blocking every page load.
const PIXEL_FONT_URL = "https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap";

function loadPixelFont() {
  if (document.getElementById("pixel-font")) return;
  const link = document.createElement("link");
  link.id = "pixel-font";
  link.rel = "stylesheet";
  link.href = PIXEL_FONT_URL;
  document.head.append(link);
}

function applyAutoTheme() {
  const now = new Date();
  const hour = now.getHours();
  document.body.dataset.theme = hour >= 18 || hour < 7 ? "dark" : "white";

  const nextHour = new Date(now);
  nextHour.setHours(hour + 1, 0, 0, 0);
  autoThemeTimer = window.setTimeout(
    applyAutoTheme,
    nextHour.getTime() - now.getTime(),
  );
}

function applyTheme(theme) {
  selectedTheme = availableThemes.includes(theme) ? theme : "auto";
  if (autoThemeTimer !== null) {
    window.clearTimeout(autoThemeTimer);
    autoThemeTimer = null;
  }

  if (selectedTheme === "auto") {
    applyAutoTheme();
  } else {
    document.body.dataset.theme = selectedTheme;
  }
  if (selectedTheme === "cyber-retro") loadPixelFont();
  if (themeSelector) themeSelector.value = selectedTheme;
  window.gamesLibrarySettings.set("theme", selectedTheme);
}

if (themeSelector) {
  const savedTheme = window.gamesLibrarySettings.get("theme") || "auto";
  applyTheme(savedTheme);
  themeSelector.addEventListener("change", () => applyTheme(themeSelector.value));
}

function updateClock() {
  if (!liveClock) return;
  const now = new Date();
  liveClock.dateTime = now.toISOString();
  liveClock.textContent = new Intl.DateTimeFormat(
    localeByLanguage[window.i18n?.language] || undefined,
    {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    },
  ).format(now);
}

updateClock();
window.setInterval(updateClock, 1000);
document.addEventListener("languagechange", updateClock);

window.isLoginLocked = (button) => Number(button.dataset.lockedUntil) > Date.now();
window.startLoginLockout = (status, button, duration, detail) => {
  const panel = status.parentElement.querySelector("[data-lockout]");
  if (!panel) return;

  const totalSeconds = Math.max(1, Math.ceil(duration));
  const progress = panel.querySelector("progress");
  const countdown = panel.querySelector("[data-lockout-countdown]");
  const message = panel.querySelector("[data-lockout-message]");
  const lockedUntil = Date.now() + totalSeconds * 1000;
  const existingTimer = lockoutTimers.get(button);
  if (existingTimer) window.clearInterval(existingTimer);

  panel.hidden = false;
  message.textContent = detail;
  progress.max = totalSeconds;
  button.dataset.lockedUntil = String(lockedUntil);
  button.disabled = true;

  const refresh = () => {
    const remaining = Math.max(0, Math.ceil((lockedUntil - Date.now()) / 1000));
    progress.value = remaining;
    const units = {
      en: remaining === 1 ? "second" : "seconds",
      pt: remaining === 1 ? "segundo" : "segundos",
      de: remaining === 1 ? "Sekunde" : "Sekunden",
      fr: remaining === 1 ? "seconde" : "secondes",
    };
    countdown.textContent = window.i18n.t("Try again in {seconds} {unit}.", {
      seconds: remaining,
      unit: units[window.i18n.language] || units.en,
    });
    if (remaining === 0) {
      window.clearInterval(lockoutTimers.get(button));
      lockoutTimers.delete(button);
      delete button.dataset.lockedUntil;
      button.disabled = false;
      panel.hidden = true;
      status.textContent = "Login unlocked. You can try again.";
    }
  };

  refresh();
  lockoutTimers.set(button, window.setInterval(refresh, 250));
};