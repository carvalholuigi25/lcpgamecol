(() => {
  const settingsStorageKey = "games-library-settings";
  const legacySettingKeys = {
    language: "games-library-language",
    theme: "games-library-theme",
  };

  function readSettings() {
    try {
      const settings = JSON.parse(localStorage.getItem(settingsStorageKey) || "{}");
      return settings && typeof settings === "object" && !Array.isArray(settings) ? settings : {};
    } catch {
      return {};
    }
  }

  function writeSetting(name, value) {
    const settings = readSettings();
    settings[name] = value;
    try {
      localStorage.setItem(settingsStorageKey, JSON.stringify(settings));
    } catch {
      // The setting remains active for this page when storage is unavailable.
    }
  }

  function migrateLegacySettings() {
    try {
      const settings = readSettings();
      let changed = false;
      for (const [name, key] of Object.entries(legacySettingKeys)) {
        const legacyValue = localStorage.getItem(key);
        if (!Object.hasOwn(settings, name) && legacyValue !== null) {
          settings[name] = legacyValue;
          changed = true;
        }
      }

      if (changed) {
        localStorage.setItem(settingsStorageKey, JSON.stringify(settings));
      }
      for (const key of Object.values(legacySettingKeys)) {
        localStorage.removeItem(key);
      }
    } catch {
      // Keep legacy values available if storage cannot complete the migration.
    }
  }

  migrateLegacySettings();
  window.gamesLibrarySettings = {
    get: (name) => readSettings()[name],
    set: writeSetting,
  };

  // The dictionaries live in locales/<lang>.json, shared with the mobile app (mobile/).
  // scripts/minify_js.mjs inlines them into the bundle as window.__lcpLocales, so they are
  // available synchronously, before any page script asks for a translation.
  const translations = { ...(window.__lcpLocales || {}) };

  const languageNames = {
    en: "English",
    pt: "Português",
    de: "Deutsch",
    fr: "Français",
    it: "Italiano",
    es: "Español",
    ja: "日本語",
    hu: "Magyar",
  };
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  const generatedTextSources = new Map();
  let currentLanguage = "en";
  const languageSelector = document.getElementById("language-selector");
  const originalTitle = document.title;

  function matchTemplate(template, message) {
    const names = [];
    const pattern = template.split(/(\{\w+\})/g).map((part) => {
      const placeholder = part.match(/^\{(\w+)\}$/);
      if (placeholder) {
        names.push(placeholder[1]);
        return "(.+?)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("");
    if (!names.length) return null;
    const match = message.match(new RegExp(`^${pattern}$`));
    if (!match) return null;
    return Object.fromEntries(names.map((name, index) => [name, match[index + 1]]));
  }

  function translate(message, values = {}) {
    const localizedMessages = translations[currentLanguage] || {};
    let template = localizedMessages[message];
    let matchedValues = {};
    if (!template) {
      for (const [source, localized] of Object.entries(localizedMessages)) {
        const match = matchTemplate(source, message);
        if (match) {
          template = localized;
          matchedValues = match;
          break;
        }
      }
    }
    template ||= message;
    const translated = template.replace(
      /\{(\w+)\}/g,
      (_, name) => values[name] ?? matchedValues[name] ?? `{${name}}`,
    );
    if (currentLanguage !== "en" && Object.keys(values).length) {
      generatedTextSources.set(
        translated,
        message.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? `{${name}}`),
      );
    }
    return translated;
  }

  function findSourceText(message) {
    if (generatedTextSources.has(message)) return generatedTextSources.get(message);
    const localizedMessages = Object.entries(translations[currentLanguage] || {});
    const exactMatch = localizedMessages.find(([, localized]) => localized === message);
    if (exactMatch) return exactMatch[0];

    for (const [source, localized] of localizedMessages) {
      const match = matchTemplate(localized, message);
      if (match) return source.replace(/\{(\w+)\}/g, (_, name) => match[name]);
    }
    return message;
  }

  function translateTextNode(node) {
    if (node.parentElement?.closest('[translate="no"]')) return;
    if (!originalText.has(node)) originalText.set(node, findSourceText(node.nodeValue));
    const source = originalText.get(node);
    const match = source.match(/^(\s*)([\s\S]*?)(\s*)$/);
    const translated = translate(match[2]);
    const result = `${match[1]}${translated}${match[3]}`;
    if (node.nodeValue !== result) node.nodeValue = result;
  }

  function translateElement(element) {
    if (element.closest('[translate="no"]')) return;
    for (const attribute of ["placeholder", "aria-label", "title", "alt"]) {
      if (!element.hasAttribute(attribute)) continue;
      let originals = originalAttributes.get(element);
      if (!originals) {
        originals = new Map();
        originalAttributes.set(element, originals);
      }
      const current = element.getAttribute(attribute);
      // Scripts may change an attribute later (e.g. a toggle's label). Any value other than
      // the one we last applied is new source text, written in the current language.
      let state = originals.get(attribute);
      if (!state || current !== state.applied) {
        state = { source: findSourceText(current), applied: current };
        originals.set(attribute, state);
      }
      const translated = translate(state.source);
      state.applied = translated;
      if (current !== translated) element.setAttribute(attribute, translated);
    }
  }

  function translateDocument(root = document.body) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType === Node.ELEMENT_NODE) translateElement(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) translateTextNode(node);
    if (root.nodeType === Node.ELEMENT_NODE) {
      for (const element of root.querySelectorAll("*")) translateElement(element);
    }
  }

  function setLanguage(language) {
    currentLanguage = Object.hasOwn(languageNames, language) ? language : "en";
    document.documentElement.lang = currentLanguage;
    document.title = translate(originalTitle);
    if (languageSelector) languageSelector.value = currentLanguage;
    window.gamesLibrarySettings.set("language", currentLanguage);
    translateDocument();
    document.dispatchEvent(new CustomEvent("languagechange", { detail: { language: currentLanguage } }));
  }

  const savedLanguage = window.gamesLibrarySettings.get("language") || "en";
  setLanguage(savedLanguage);
  languageSelector?.addEventListener("change", () => setLanguage(languageSelector.value));

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "characterData") translateTextNode(mutation.target);
      for (const node of mutation.addedNodes) translateDocument(node);
      if (mutation.type === "attributes") translateElement(mutation.target);
    }
  });
  observer.observe(document.body, {
    attributes: true,
    attributeFilter: ["placeholder", "aria-label", "title", "alt"],
    characterData: true,
    childList: true,
    subtree: true,
  });

  window.i18n = {
    get language() {
      return currentLanguage;
    },
    languageNames,
    setLanguage,
    t: translate,
  };
})();
