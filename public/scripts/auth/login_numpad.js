for (const form of document.querySelectorAll('form#login-form')) {
  const password = form.querySelector('input[data-password-entry][name="password"][type="password"]');
  if (!password) continue;

  let passwordMaskCharacter = "*";
  let passwordMaskColor = window.getComputedStyle(password).color;
  const originalPasswordLengthConstraints = {
    minlength: password.getAttribute("minlength"),
    maxlength: password.getAttribute("maxlength"),
  };
  const passwordField = document.createElement("span");
  passwordField.className = "password-entry-field";
  password.before(passwordField);
  passwordField.append(password);

  const passwordMask = document.createElement("span");
  passwordMask.className = "password-entry-mask";
  passwordMask.setAttribute("aria-hidden", "true");
  passwordField.append(passwordMask);

  const controls = document.createElement("div");
  controls.className = "password-entry-controls";

  const modeLabel = document.createElement("label");
  modeLabel.className = "password-entry-mode";
  modeLabel.append("Password entry");

  const mode = document.createElement("select");
  mode.setAttribute("aria-label", "Password entry");
  mode.name = "password-entry-mode";
  mode.classList.add("password-entry-mode-select");

  for (const [value, label] of [["input", "Input only"], ["numpad", "Numpad"]]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    mode.append(option);
  }

  const keyboardOption = document.createElement("option");
  keyboardOption.value = "letters-symbols";
  keyboardOption.textContent = "Letters & symbols";
  mode.append(keyboardOption);
  modeLabel.append(mode);
  controls.append(modeLabel);

  const keypad = document.createElement("div");
  keypad.className = "password-entry-keypad";
  keypad.setAttribute("role", "group");
  keypad.setAttribute("aria-label", "Password keypad");
  keypad.hidden = true;

  for (const key of ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "delete", "clear"]) {
    const button = document.createElement("button");
    button.type = "button";
    if (key === "delete" || key === "clear") {
      button.dataset.passwordAction = key;
    } else {
      button.dataset.passwordKey = key;
    }
    button.textContent = key === "delete" ? "Delete" : key === "clear" ? "Clear" : key;
    if (key === "delete") button.setAttribute("aria-label", "Delete last digit");
    if (key === "clear") button.setAttribute("aria-label", "Clear password");
    keypad.append(button);
  }

  const maskToggle = document.createElement("button");
  maskToggle.type = "button";
  maskToggle.dataset.passwordAction = "toggle-mask";
  maskToggle.textContent = `Mask: ${passwordMaskCharacter}`;
  maskToggle.setAttribute("aria-label", `Toggle password mask character (currently ${passwordMaskCharacter})`);
  maskToggle.setAttribute("aria-pressed", String(passwordMaskCharacter === "-"));
  maskToggle.setAttribute("hidden", "true");
  keypad.append(maskToggle);
  controls.append(keypad);

  const keyboard = document.createElement("div");
  keyboard.className = "password-entry-keyboard";
  keyboard.setAttribute("role", "group");
  keyboard.setAttribute("aria-label", "Password letters and symbols");
  keyboard.hidden = true;
  controls.append(keyboard);

  const passwordLabel = password.closest("label");
  (passwordLabel || passwordField).after(controls);

  let shifted = false;
  let showingSymbols = false;

  function renderPasswordMask() {
    passwordMask.textContent = passwordMaskCharacter.repeat(password.value.length);
    const inputStyle = window.getComputedStyle(password);
    passwordMask.style.font = inputStyle.font;
    passwordMask.style.letterSpacing = inputStyle.letterSpacing;
    passwordMask.style.lineHeight = inputStyle.lineHeight;
    passwordMask.style.padding = inputStyle.padding;
    passwordMask.style.color = passwordMaskColor;
    maskToggle.textContent = `Mask: ${passwordMaskCharacter}`;
    maskToggle.setAttribute(
      "aria-label",
      `Toggle password mask character (currently ${passwordMaskCharacter})`,
    );
    maskToggle.setAttribute("aria-pressed", String(passwordMaskCharacter === "-"));
  }

  function togglePasswordMaskCharacter() {
    passwordMaskCharacter = passwordMaskCharacter === "*" ? "-" : "*";
    renderPasswordMask();
  }

  function makeKeyboardButton(label, key, action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "password-entry-key";
    button.textContent = label;
    if (action) {
      button.dataset.passwordAction = action;
    } else {
      button.dataset.passwordKey = key;
    }
    if (action === "space") button.setAttribute("aria-label", "Space");
    if (action === "delete") button.setAttribute("aria-label", "Delete last character");
    if (action === "clear") button.setAttribute("aria-label", "Clear password");
    if (action === "shift") button.setAttribute("aria-pressed", String(shifted));
    return button;
  }

  function appendKeyboardRow(keys, className = "") {
    const row = document.createElement("div");
    row.className = `password-entry-keyboard-row ${className}`.trim();
    for (const key of keys) {
      if (typeof key === "string") {
        const displayedKey = shifted && !showingSymbols ? key.toUpperCase() : key;
        row.append(makeKeyboardButton(displayedKey, displayedKey));
      } else {
        row.append(makeKeyboardButton(key.label, "", key.action));
      }
    }
    keyboard.append(row);
  }

  function renderKeyboard() {
    keyboard.replaceChildren();
    appendKeyboardRow(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]);

    if (showingSymbols) {
      appendKeyboardRow(["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"]);
      appendKeyboardRow(["-", "_", "=", "+", "[", "]", "{", "}", "\\", "|"]);
      appendKeyboardRow([";", ":", "'", "\"", ",", ".", "/", "?", "`", "~"]);
      appendKeyboardRow([
        { label: "ABC", action: "letters" },
        { label: "Space", action: "space" },
        { label: "Delete", action: "delete" },
        { label: "Clear", action: "clear" },
      ], "password-entry-keyboard-row--symbols-actions");
      return;
    }

    appendKeyboardRow(["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"]);
    appendKeyboardRow(["a", "s", "d", "f", "g", "h", "j", "k", "l"], "password-entry-keyboard-row--home");
    appendKeyboardRow([
      { label: "Shift", action: "shift" },
      ..."zxcvbnm",
      { label: "Delete", action: "delete" },
    ], "password-entry-keyboard-row--bottom");
    appendKeyboardRow([
      { label: "Symbols", action: "symbols" },
      { label: "Space", action: "space" },
      { label: "Clear", action: "clear" },
    ], "password-entry-keyboard-row--actions");
  }

  function updatePassword(value) {
    if (password.maxLength >= 0 && password.value.length + value.length > password.maxLength) return;
    password.value += value;
    password.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function handleKeyboardAction(action) {
    if (action === "clear") {
      password.value = "";
    } else if (action === "delete") {
      password.value = password.value.slice(0, -1);
    } else if (action === "toggle-mask") {
      togglePasswordMaskCharacter();
      return;
    } else if (action === "space") {
      updatePassword(" ");
      return;
    } else if (action === "shift") {
      shifted = !shifted;
      renderKeyboard();
      keyboard.querySelector('button[data-password-action="shift"]')?.focus();
      return;
    } else if (action === "symbols" || action === "letters") {
      showingSymbols = action === "symbols";
      shifted = false;
      renderKeyboard();
      keyboard.querySelector(
        `button[data-password-action="${showingSymbols ? "letters" : "symbols"}"]`,
      )?.focus();
      return;
    }
    password.dispatchEvent(new Event("input", { bubbles: true }));
  }

  mode.addEventListener("change", () => {
    const useKeypad = mode.value === "numpad";
    const useKeyboard = mode.value === "letters-symbols";
    keypad.hidden = !useKeypad;
    keyboard.hidden = !useKeyboard;
    controls.classList.toggle("is-keyboard", useKeyboard);
    passwordField.classList.remove("password-entry-field--custom-mask");
    if (useKeyboard) {
      shifted = false;
      showingSymbols = false;
      renderKeyboard();
    }
    if (useKeypad) {
      password.classList.add("password-numpad");
      password.setAttribute("minlength", "0");
      password.setAttribute("maxlength", "4");
    } else if (password.classList.contains("password-numpad")) {
      password.classList.remove("password-numpad");
      for (const [attribute, value] of Object.entries(originalPasswordLengthConstraints)) {
        if (value === null) password.removeAttribute(attribute);
        else password.setAttribute(attribute, value);
      }
    }
    passwordMaskColor = window.getComputedStyle(password).color;
    passwordField.classList.toggle("password-entry-field--custom-mask", useKeypad);
    renderPasswordMask();
    password.inputMode = useKeypad || useKeyboard ? "none" : "text";
  });

  password.addEventListener("keydown", (event) => {
    if (mode.value !== "input" && event.key !== "Tab") event.preventDefault();
  });
  password.addEventListener("input", renderPasswordMask);
  for (const eventName of ["paste", "drop"]) {
    password.addEventListener(eventName, (event) => {
      if (mode.value !== "input") event.preventDefault();
    });
  }

  function handleVirtualKey(event) {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("button[data-password-key], button[data-password-action]");
    if (!button) return;

    if (button.dataset.passwordAction) {
      handleKeyboardAction(button.dataset.passwordAction);
      return;
    }

    updatePassword(button.dataset.passwordKey);
  }

  keypad.addEventListener("click", handleVirtualKey);
  keyboard.addEventListener("click", handleVirtualKey);
}