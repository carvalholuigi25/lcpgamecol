(() => {
  const selector = document.getElementById("language-selector");
  if (!selector || selector.dataset.flagPickerEnhanced) return;
  selector.dataset.flagPickerEnhanced = "true";
  selector.hidden = true;

  const flagFiles = { en: "us", pt: "pt", de: "de", fr: "fr", it: "it", es: "es", ja: "jp", hu: "hu" };

  const picker = document.createElement("div");
  picker.className = "language-picker";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "language-picker-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");

  const menu = document.createElement("div");
  menu.className = "language-picker-menu";
  menu.setAttribute("role", "listbox");
  menu.hidden = true;
  menu.removeAttribute("style");

  function makeFlag(language) {
    const flag = document.createElement("img");
    flag.className = "language-picker-flag";
    flag.src = `/public/images/flags/${flagFiles[language] || language}.svg`;
    flag.alt = "";
    flag.width = 22;
    flag.height = 15;
    return flag;
  }

  function updateTrigger() {
    const option = selector.options[selector.selectedIndex];
    if (!option) return;
    trigger.replaceChildren(makeFlag(option.value), document.createTextNode(option.textContent));
  }

  for (const option of selector.options) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "language-picker-option";
    item.setAttribute("role", "option");
    Object.assign(item.style, {
      display: "flex",
      width: "100%",
      alignItems: "center",
      textAlign: "left",
    });
    item.append(makeFlag(option.value), document.createTextNode(option.textContent));
    item.addEventListener("click", () => {
      selector.value = option.value;
      selector.dispatchEvent(new Event("change", { bubbles: true }));
      updateTrigger();
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    });
    menu.append(item);
  }

  trigger.addEventListener("click", () => {
    menu.hidden = !menu.hidden;
    trigger.setAttribute("aria-expanded", String(!menu.hidden));
  });

  document.addEventListener("click", (event) => {
    if (!picker.contains(event.target)) {
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    }
  });

  picker.append(trigger, menu);
  selector.after(picker);
  updateTrigger();
})();
