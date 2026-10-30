(() => {
  // ISO 3166-1 alpha-2 codes; names come from Intl.DisplayNames in the page language.
  const countryCodes = (
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ " +
    "CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR " +
    "GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP " +
    "KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT " +
    "MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW " +
    "SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG " +
    "UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW"
  ).split(" ");
  const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const reasonLabels = { geoblock: "Geoblock", vpn: "VPN or proxy", lockdown: "Lockdown" };
  const localeByLanguage = {
    en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR", it: "it-IT", es: "es-ES", ja: "ja-JP",
  };

  const panel = document.getElementById("access-panel");
  const statusLine = document.getElementById("access-status");
  const saveButton = document.getElementById("access-save");
  const geoblockMode = document.getElementById("geoblock-mode");
  const countryInput = document.getElementById("geoblock-country-input");
  const countryList = document.getElementById("geoblock-countries");
  const blockUnknown = document.getElementById("geoblock-block-unknown");
  const blockHosting = document.getElementById("vpn-block-hosting");
  const timezoneSelect = document.getElementById("lockdown-timezone");
  const lockdownMessage = document.getElementById("lockdown-message");
  const windowList = document.getElementById("lockdown-windows");
  const windowKind = document.getElementById("window-kind");
  const windowDays = document.getElementById("window-days");
  const ipCheckResult = document.getElementById("ip-check-result");
  const switches = [...panel.querySelectorAll(".access-switch")];
  let state = null;

  const t = (message, values) => window.i18n.t(message, values);
  const locale = () => localeByLanguage[window.i18n.language] || "en-GB";

  function countryName(code) {
    try {
      return new Intl.DisplayNames([locale()], { type: "region" }).of(code) || code;
    } catch {
      return code;
    }
  }

  function dayName(index) {
    // 2024-01-01 was a Monday.
    return new Date(Date.UTC(2024, 0, 1 + index)).toLocaleDateString(locale(), { weekday: "short", timeZone: "UTC" });
  }

  function formatDateTime(value, options = { dateStyle: "medium", timeStyle: "short" }) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(locale(), options);
  }

  async function readProblem(response, fallback) {
    try {
      const body = await response.json();
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg.replace(/^Value error, /, "");
    } catch {
      // Use the fallback below.
    }
    return fallback;
  }

  function renderSwitch(button, on) {
    button.setAttribute("aria-checked", String(on));
    button.querySelector(".access-switch-label").textContent = on ? "On" : "Off";
    button.closest(".access-card").classList.toggle("is-on", on);
  }

  function renderCountryOptions() {
    const options = document.getElementById("geoblock-country-options");
    options.replaceChildren(
      ...countryCodes.map((code) => {
        const option = document.createElement("option");
        option.value = `${countryName(code)} (${code})`;
        return option;
      }),
    );
  }

  function renderCountries() {
    const { countries } = state.settings.geoblock;
    countryList.replaceChildren(
      ...countries.map((code) => {
        const item = document.createElement("li");
        item.className = "access-chip";
        const name = document.createElement("span");
        name.setAttribute("translate", "no");
        name.textContent = `${countryName(code)} · ${code}`;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "access-chip-remove";
        remove.textContent = "×";
        remove.setAttribute("aria-label", t("Remove {name}", { name: countryName(code) }));
        remove.addEventListener("click", () => {
          state.settings.geoblock.countries = countries.filter((value) => value !== code);
          renderCountries();
        });
        item.append(name, remove);
        return item;
      }),
    );
    document.getElementById("geoblock-empty").hidden = countries.length > 0;
  }

  function describeWindow(entry) {
    if (entry.kind === "once") {
      return t("Once, from {start} until {end}", {
        start: formatDateTime(entry.starts_at),
        end: formatDateTime(entry.ends_at),
      });
    }
    const days = entry.days.length === 7 ? t("Every day") : entry.days.map(dayName).join(", ");
    if (entry.start === entry.end) return t("{days}, all day", { days });
    return t("{days}, from {start} until {end}", { days, start: entry.start, end: entry.end });
  }

  function renderWindows() {
    const { windows } = state.settings.lockdown;
    windowList.replaceChildren(
      ...windows.map((entry, index) => {
        const item = document.createElement("li");
        const text = document.createElement("span");
        text.textContent = describeWindow(entry);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "danger-button upload-action";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
          windows.splice(index, 1);
          renderWindows();
        });
        item.append(text, remove);
        return item;
      }),
    );
    document.getElementById("lockdown-empty").hidden = windows.length > 0;
  }

  function renderLockdownState() {
    const element = document.getElementById("lockdown-state");
    const { status } = state;
    element.classList.toggle("is-active", status.lockdown_active);
    element.textContent = status.lockdown_active
      ? t("Locked now, until {date}.", { date: formatDateTime(status.lockdown_ends_at) })
      : state.settings.lockdown.enabled
        ? "Open now."
        : "";
  }

  // Built from the last saved settings, so unsaved edits in the cards do not show here.
  function renderRules() {
    const { geoblock, vpn, lockdown } = state.saved;
    const countries = geoblock.countries.map(countryName).join(", ");
    const rules = [
      {
        name: "Geoblock",
        on: geoblock.enabled,
        details: [
          countries
            ? t(geoblock.mode === "block" ? "Blocks {countries}" : "Allows only {countries}", { countries })
            : "No countries listed yet.",
          ...(geoblock.block_unknown ? ["Visitors whose country cannot be found are blocked too."] : []),
        ],
      },
      {
        name: "VPN checker",
        on: vpn.enabled,
        details: [vpn.block_hosting ? "VPNs, proxies, Tor, hosting providers and data centres" : "VPNs, proxies and Tor"],
      },
      {
        name: "Scheduled lockdown",
        on: lockdown.enabled,
        details: [
          ...(lockdown.windows.length ? lockdown.windows.map(describeWindow) : ["No lockdown times yet."]),
          t("Time zone: {zone}", { zone: lockdown.timezone }),
        ],
      },
    ];
    document.getElementById("access-rules").replaceChildren(
      ...rules.map((rule) => {
        const row = document.createElement("tr");
        const name = document.createElement("td");
        name.className = "recent-title";
        name.textContent = rule.name;
        const status = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `access-rule-status${rule.on ? " is-on" : ""}`;
        badge.textContent = rule.on ? "On" : "Off";
        status.append(badge);
        const details = document.createElement("td");
        details.append(
          ...rule.details.map((text) => {
            const line = document.createElement("span");
            line.className = "access-rule-detail";
            line.textContent = text;
            return line;
          }),
        );
        row.append(name, status, details);
        return row;
      }),
    );
  }

  function renderBlocks() {
    const rows = document.getElementById("access-blocks");
    rows.replaceChildren(
      ...state.recent_blocks.map((block) => {
        const row = document.createElement("tr");
        const cells = [
          formatDateTime(block.at, { timeStyle: "medium" }),
          reasonLabels[block.reason] || block.reason,
          block.ip,
          block.country ? `${countryName(block.country)} (${block.country})` : "—",
          block.path,
        ];
        for (const [index, value] of cells.entries()) {
          const cell = document.createElement("td");
          if (index >= 2) cell.setAttribute("translate", "no");
          cell.textContent = value;
          row.append(cell);
        }
        return row;
      }),
    );
    document.getElementById("access-blocks-empty").hidden = state.recent_blocks.length > 0;
  }

  function render() {
    const { geoblock, vpn, lockdown } = state.settings;
    renderSwitch(document.getElementById("geoblock-toggle"), geoblock.enabled);
    renderSwitch(document.getElementById("vpn-toggle"), vpn.enabled);
    renderSwitch(document.getElementById("lockdown-toggle"), lockdown.enabled);
    geoblockMode.value = geoblock.mode;
    blockUnknown.checked = geoblock.block_unknown;
    blockHosting.checked = vpn.block_hosting;
    if (![...timezoneSelect.options].some((option) => option.value === lockdown.timezone)) {
      timezoneSelect.append(new Option(lockdown.timezone, lockdown.timezone));
    }
    timezoneSelect.value = lockdown.timezone;
    lockdownMessage.value = lockdown.message;
    document.getElementById("access-server-note").hidden = !state.status.disabled_by_server;
    document.getElementById("access-updated").textContent = state.updated
      ? t("SAVED {date} BY {user}", { date: formatDateTime(state.updated.updated_at), user: state.updated.updated_by })
      : "";
    renderCountries();
    renderWindows();
    renderLockdownState();
    renderRules();
    renderBlocks();
  }

  function receive(body) {
    state = { ...body, saved: structuredClone(body.settings) };
    render();
  }

  // Unsaved edits live in state.settings; read the plain inputs back before saving.
  function collectSettings() {
    const { settings } = state;
    settings.geoblock.mode = geoblockMode.value;
    settings.geoblock.block_unknown = blockUnknown.checked;
    settings.vpn.block_hosting = blockHosting.checked;
    settings.lockdown.timezone = timezoneSelect.value;
    settings.lockdown.message = lockdownMessage.value.trim();
    return settings;
  }

  async function save(successMessage = "Access rules saved.") {
    saveButton.disabled = true;
    switches.forEach((button) => (button.disabled = true));
    statusLine.textContent = "Saving...";
    try {
      const response = await fetch("/admin/access-control", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(collectSettings()),
      });
      if (!response.ok) throw new Error(await readProblem(response, "The access rules could not be saved."));
      receive(await response.json());
      statusLine.textContent = "";
      showToast(successMessage);
      return true;
    } catch (error) {
      statusLine.textContent = error.message;
      return false;
    } finally {
      saveButton.disabled = false;
      switches.forEach((button) => (button.disabled = false));
    }
  }

  async function load() {
    try {
      const response = await fetch("/admin/access-control", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(await readProblem(response, "The access rules could not be loaded."));
      receive(await response.json());
    } catch (error) {
      statusLine.textContent = error.message;
    }
  }

  function addCountry() {
    const value = countryInput.value.trim();
    if (!value) return;
    const lower = value.toLowerCase();
    const code =
      value.match(/\(([A-Za-z]{2})\)$/)?.[1].toUpperCase() ||
      countryCodes.find((candidate) => candidate.toLowerCase() === lower || countryName(candidate).toLowerCase() === lower);
    if (!code || !countryCodes.includes(code)) {
      statusLine.textContent = t("{name} is not a known country.", { name: value });
      return;
    }
    statusLine.textContent = "";
    const { geoblock } = state.settings;
    if (!geoblock.countries.includes(code)) geoblock.countries = [...geoblock.countries, code].sort();
    countryInput.value = "";
    renderCountries();
  }

  function addWindow() {
    const kind = windowKind.value;
    let entry;
    if (kind === "weekly") {
      const days = [...windowDays.querySelectorAll("input:checked")].map((input) => Number(input.value));
      entry = {
        kind,
        days,
        start: document.getElementById("window-start").value,
        end: document.getElementById("window-end").value,
      };
      if (!days.length || !entry.start || !entry.end) {
        statusLine.textContent = "Choose the days and the times.";
        return;
      }
    } else {
      entry = {
        kind,
        starts_at: document.getElementById("window-starts-at").value,
        ends_at: document.getElementById("window-ends-at").value,
      };
      if (!entry.starts_at || !entry.ends_at || entry.ends_at <= entry.starts_at) {
        statusLine.textContent = "Choose a start and an end after it.";
        return;
      }
    }
    statusLine.textContent = "";
    state.settings.lockdown.windows.push(entry);
    renderWindows();
  }

  function showIpResult(result) {
    const rows = [
      ["Address", result.ip, true],
      ["Country", result.country ? `${countryName(result.country)} (${result.country})` : "Unknown", Boolean(result.country)],
      ["VPN, proxy or Tor", result.vpn ? "Yes" : "No"],
      ["Hosting or data centre", result.hosting ? "Yes" : "No"],
      ["Current rules", result.blocked ? t("Blocked ({rule})", { rule: t(reasonLabels[result.reason]) }) : "Allowed"],
    ];
    if (result.source === "private") rows.push(["Note", "Private or local address, never blocked."]);
    if (result.source === "error") rows.push(["Note", "The lookup service could not be reached."]);
    ipCheckResult.replaceChildren(
      ...rows.flatMap(([label, value, raw]) => {
        const term = document.createElement("dt");
        term.textContent = label;
        const detail = document.createElement("dd");
        if (raw) detail.setAttribute("translate", "no");
        detail.textContent = value;
        return [term, detail];
      }),
    );
    ipCheckResult.classList.toggle("is-blocked", result.blocked);
    ipCheckResult.hidden = false;
  }

  for (const button of switches) {
    button.addEventListener("click", async () => {
      const section = state.settings[button.dataset.section];
      section.enabled = !section.enabled;
      const label = button.closest(".access-card").querySelector("h3").textContent;
      const saved = await save(t(section.enabled ? "{name} is on." : "{name} is off.", { name: label }));
      if (!saved) {
        section.enabled = !section.enabled;
        renderSwitch(button, section.enabled);
      }
    });
  }

  document.getElementById("geoblock-country-add").addEventListener("click", addCountry);
  countryInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addCountry();
  });
  document.getElementById("window-add").addEventListener("click", addWindow);
  windowKind.addEventListener("change", () => {
    for (const field of panel.querySelectorAll("[data-window-kind]")) field.hidden = field.dataset.windowKind !== windowKind.value;
    windowDays.hidden = windowKind.value !== "weekly";
  });
  saveButton.addEventListener("click", () => save());

  document.getElementById("ip-check-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.getElementById("ip-check-submit");
    const ip = document.getElementById("ip-check-input").value.trim();
    submit.disabled = true;
    try {
      const query = ip ? `?ip=${encodeURIComponent(ip)}` : "";
      const response = await fetch(`/admin/access-control/check-ip${query}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(await readProblem(response, "The address could not be checked."));
      showIpResult(await response.json());
      statusLine.textContent = "";
    } catch (error) {
      ipCheckResult.hidden = true;
      statusLine.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });

  function renderDayPicker() {
    const checked = new Set([...windowDays.querySelectorAll("input:checked")].map((input) => input.value));
    windowDays.replaceChildren(
      ...dayNames.map((name, index) => {
        const label = document.createElement("label");
        label.className = "setting-option";
        label.title = name;
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = String(index);
        input.checked = checked.size ? checked.has(input.value) : index < 5;
        const text = document.createElement("span");
        text.setAttribute("translate", "no");
        text.textContent = dayName(index);
        label.append(input, text);
        return label;
      }),
    );
  }

  const timezones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  timezoneSelect.replaceChildren(...["UTC", ...timezones.filter((zone) => zone !== "UTC")].map((zone) => new Option(zone, zone)));
  timezoneSelect.setAttribute("translate", "no");
  renderDayPicker();
  renderCountryOptions();

  document.addEventListener("languagechange", () => {
    renderDayPicker();
    renderCountryOptions();
    if (state) render();
  });

  window.accessControl = { load };
})();
