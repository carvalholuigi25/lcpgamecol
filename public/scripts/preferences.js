// Palettes live in public/styles/scss/_seasonal_themes.scss. "seasonal" picks one by date.
const seasonalThemes = {
  spring: "Spring",
  summer: "Summer",
  fall: "Fall",
  winter: "Winter",
  halloween: "Halloween",
  easter: "Easter",
  christmas: "Christmas",
  "new-years-eve": "New Year's Eve",
};
const availableThemes = [
  "auto", "dark", "white", "glassmorphism", "liquid-glass", "sunsetvibes", "cyber-retro", "rgb",
  "seasonal", ...Object.keys(seasonalThemes),
];
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

// Easter Sunday in the Gregorian calendar (the anonymous Gregorian algorithm).
function easterSunday(year) {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(year, month - 1, day);
}

// Holidays first (the fortnight before Halloween, Holy Week to Easter Monday,
// 1 to 26 December, 27 December to 1 January), otherwise the northern meteorological season.
function seasonalThemeFor(date) {
  const today = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const month = today.getMonth() + 1;
  const day = today.getDate();
  const daysFromEaster = Math.round((today - easterSunday(today.getFullYear())) / 86400000);
  if ((month === 10 && day >= 17) || (month === 11 && day === 1)) return "halloween";
  if (month === 12 && day <= 26) return "christmas";
  if ((month === 12 && day >= 27) || (month === 1 && day === 1)) return "new-years-eve";
  if (daysFromEaster >= -7 && daysFromEaster <= 1) return "easter";
  if (month >= 3 && month <= 5) return "spring";
  if (month >= 6 && month <= 8) return "summer";
  if (month >= 9 && month <= 11) return "fall";
  return "winter";
}

function applySeasonalTheme() {
  const now = new Date();
  document.body.dataset.theme = seasonalThemeFor(now);
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  autoThemeTimer = window.setTimeout(applySeasonalTheme, tomorrow.getTime() - now.getTime());
}

function addSeasonalOptions(select) {
  if (select.querySelector('option[value="seasonal"]')) return;
  const group = document.createElement("optgroup");
  group.label = window.i18n?.t("Seasonal") ?? "Seasonal";
  group.append(
    new Option("Seasonal (auto)", "seasonal"),
    ...Object.entries(seasonalThemes).map(([value, label]) => new Option(label, value)),
  );
  select.append(group);
  // Only text nodes are translated automatically, not the group label.
  document.addEventListener("languagechange", () => {
    group.label = window.i18n.t("Seasonal");
  });
}

function applyTheme(theme) {
  selectedTheme = availableThemes.includes(theme) ? theme : "auto";
  if (autoThemeTimer !== null) {
    window.clearTimeout(autoThemeTimer);
    autoThemeTimer = null;
  }

  if (selectedTheme === "auto") {
    applyAutoTheme();
  } else if (selectedTheme === "seasonal") {
    applySeasonalTheme();
  } else {
    document.body.dataset.theme = selectedTheme;
  }
  if (selectedTheme === "cyber-retro") loadPixelFont();
  if (themeSelector) themeSelector.value = selectedTheme;
  window.gamesLibrarySettings.set("theme", selectedTheme);
}

if (themeSelector) {
  addSeasonalOptions(themeSelector);
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