// The Security section of the profile page: two-step sign-in settings, served by
// routes/users/two_factor.py. Shows the current state, walks through setting up an
// authenticator app or email codes, shows recovery codes once, and asks for the
// password before turning it off or making new recovery codes.
(() => {
  const view = document.getElementById("two-factor-view");
  if (!view) return;
  const statusLine = document.getElementById("two-factor-status");
  const badge = document.getElementById("two-factor-badge");
  const METHOD_LABELS = { totp: "Authenticator app", email: "Email code" };
  let state = null;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function button(text, className, onClick, type = "button") {
    const node = element("button", className, text);
    node.type = type;
    if (onClick) node.addEventListener("click", onClick);
    return node;
  }

  function setStatus(message = "") {
    statusLine.textContent = message ? window.i18n.t(message) : "";
  }

  async function request(path, body) {
    const response = await fetch(path, body === undefined
      ? { headers: { Accept: "application/json" } }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) {
      let detail = "Something went wrong. Try again.";
      try {
        const data = await response.json();
        if (typeof data.detail === "string") detail = data.detail;
        else if (Array.isArray(data.detail) && data.detail[0]?.msg) detail = data.detail[0].msg;
      } catch {
        // Keep the generic message.
      }
      throw new Error(detail);
    }
    return response.json();
  }

  function formatDate(value) {
    const locale = { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR" }[window.i18n.language];
    return new Date(value).toLocaleDateString(locale, { dateStyle: "medium" });
  }

  function codeField(label = "Code", recovery = false) {
    const wrapper = element("label", "two-factor-field");
    wrapper.append(element("span", "", label));
    const input = element("input");
    input.name = "code";
    input.required = true;
    input.autocomplete = recovery ? "off" : "one-time-code";
    input.inputMode = recovery ? "text" : "numeric";
    input.maxLength = recovery ? 12 : 6;
    input.placeholder = recovery ? "xxxx-xxxx" : "123456";
    wrapper.append(input);
    return wrapper;
  }

  // --- states -------------------------------------------------------------------

  function renderBadge() {
    badge.textContent = window.i18n.t(state.enabled ? "On" : "Off");
    badge.classList.toggle("role-admin", state.enabled);
  }

  function renderMethodChoice(switching = false) {
    const choices = element("div", "two-factor-options");
    for (const method of ["totp", "email"]) {
      const option = element("button", "two-factor-option");
      option.type = "button";
      option.append(element("strong", "", METHOD_LABELS[method]));
      const description = method === "totp"
        ? "Codes from Google Authenticator, Microsoft Authenticator, 1Password, Authy and similar apps. Works offline."
        : state.email_available
          ? "A code is emailed to you each time you sign in."
          : "Add an email address to your profile first (and email must be set up on the server).";
      option.append(element("span", "", description));
      option.disabled = (method === "email" && !state.email_available) || (switching && state.method === method);
      option.addEventListener("click", () => startSetup(method));
      choices.append(option);
    }
    const nodes = [choices];
    if (switching) nodes.push(button("Cancel", "secondary-button", renderState));
    view.replaceChildren(...nodes);
  }

  function renderEnabled() {
    const summary = element("p", "two-factor-summary");
    summary.append(
      element("span", "", window.i18n.t("Using {method} since {date}.", {
        method: window.i18n.t(METHOD_LABELS[state.method]).toLowerCase(),
        date: formatDate(state.enabled_at),
      })),
      " ",
      element("span", state.recovery_codes_left <= 2 ? "two-factor-warning" : "",
        window.i18n.t("{count} recovery codes left.", { count: state.recovery_codes_left })),
    );
    const actions = element("div", "upload-actions");
    actions.append(
      button("Switch method", "secondary-button", () => renderMethodChoice(true)),
      button("New recovery codes", "secondary-button", () => renderPasswordPrompt("codes")),
      button("Turn off", "danger-button", () => renderPasswordPrompt("disable")),
    );
    view.replaceChildren(summary, actions);
  }

  function renderState() {
    setStatus();
    renderBadge();
    if (state.enabled) renderEnabled();
    else renderMethodChoice();
  }

  function renderPasswordPrompt(action) {
    const form = element("form", "two-factor-form");
    const intro = element("p", "profile-form-hint", action === "disable"
      ? "Enter your password to turn off two-step sign-in."
      : "Enter your password to make new recovery codes. The old ones stop working.");
    const label = element("label", "two-factor-field");
    const input = element("input");
    input.type = "password";
    input.name = "password";
    input.required = true;
    input.autocomplete = "current-password";
    label.append(element("span", "", "Password"), input);
    const actions = element("div", "upload-actions");
    const submit = button(action === "disable" ? "Turn off" : "Make new codes",
      action === "disable" ? "danger-button" : "primary-button", null, "submit");
    actions.append(submit, button("Cancel", "secondary-button", renderState));
    form.append(intro, label, actions);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const path = action === "disable" ? "/users/me/two-factor/disable" : "/users/me/two-factor/recovery-codes";
        const result = await request(path, { password: input.value });
        state = result;
        if (action === "disable") {
          renderState();
          setStatus("Two-step sign-in is off.");
        } else {
          renderRecoveryCodes(result.recovery_codes);
        }
      } catch (error) {
        setStatus(error.message);
        submit.disabled = false;
        input.select();
      }
    });
    view.replaceChildren(form);
    input.focus();
  }

  function renderSetup(setup) {
    const form = element("form", "two-factor-form");
    if (setup.method === "totp") {
      const steps = element("div", "two-factor-setup");
      const qr = element("img", "two-factor-qr");
      qr.src = setup.qr_code;
      qr.alt = window.i18n.t("QR code to add this account to your authenticator app");
      qr.width = 180;
      qr.height = 180;
      const text = element("div", "two-factor-steps");
      text.append(
        element("p", "", "1. Scan the QR code with your authenticator app."),
        element("p", "", "Can't scan it? Enter this key instead:"),
      );
      const key = element("code", "two-factor-key", setup.secret.match(/.{1,4}/g).join(" "));
      key.setAttribute("translate", "no");
      const link = element("a", "", "Open in an authenticator app on this device");
      link.href = setup.otpauth_uri;
      text.append(key, link, element("p", "", "2. Enter the 6-digit code the app shows."));
      steps.append(qr, text);
      form.append(steps);
    } else {
      const sent = element("p", "profile-form-hint");
      sent.append(element("span", "", "We emailed a 6-digit code to"), " ", element("strong", "", setup.email), ".");
      sent.lastElementChild.setAttribute("translate", "no");
      form.append(sent);
    }
    const field = codeField();
    const actions = element("div", "upload-actions");
    const submit = button("Turn on", "primary-button", null, "submit");
    actions.append(submit);
    if (setup.method === "email") actions.append(button("Send a new code", "secondary-button", () => startSetup("email")));
    actions.append(button("Cancel", "secondary-button", renderState));
    form.append(field, actions);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const result = await request("/users/me/two-factor/enable", { code: field.querySelector("input").value });
        state = result;
        renderBadge();
        renderRecoveryCodes(result.recovery_codes);
      } catch (error) {
        setStatus(error.message);
        submit.disabled = false;
      }
    });
    view.replaceChildren(form);
    field.querySelector("input").focus();
  }

  function renderRecoveryCodes(codes) {
    setStatus();
    const intro = element("p", "profile-form-hint",
      "Save these recovery codes somewhere safe. Each one signs you in once if you lose your phone or can't get email. They won't be shown again.");
    const list = element("ol", "recovery-codes");
    list.setAttribute("translate", "no");
    for (const code of codes) list.append(element("li", "", code));
    const text = codes.join("\n");
    const actions = element("div", "upload-actions");
    actions.append(
      button("Copy", "secondary-button", async () => {
        try {
          await navigator.clipboard.writeText(text);
          setStatus("Recovery codes copied.");
        } catch {
          setStatus("Copy them by hand, the browser blocked the clipboard.");
        }
      }),
      button("Download", "secondary-button", () => {
        const link = element("a");
        link.href = URL.createObjectURL(new Blob([`lcpgamecol recovery codes\n\n${text}\n`], { type: "text/plain" }));
        link.download = "lcpgamecol-recovery-codes.txt";
        link.click();
        URL.revokeObjectURL(link.href);
      }),
      button("I've saved them", "primary-button", renderState),
    );
    view.replaceChildren(intro, list, actions);
  }

  async function startSetup(method) {
    setStatus(method === "email" ? "Sending..." : "");
    try {
      renderSetup(await request("/users/me/two-factor/setup", { method }));
      setStatus();
    } catch (error) {
      setStatus(error.message);
    }
  }

  async function load() {
    try {
      state = await request("/users/me/two-factor");
      renderState();
    } catch (error) {
      setStatus(error.message);
    }
  }

  document.addEventListener("profilesaved", () => {
    if (state && !view.querySelector("form, .recovery-codes")) load();
  });
  // Re-render translated text, unless the user is part-way through a step.
  document.addEventListener("languagechange", () => {
    if (state && !view.querySelector("form, .recovery-codes")) renderState();
  });
  // The profile page shows this section once it knows who is signed in.
  const observer = new MutationObserver(() => {
    if (!document.getElementById("profile-view").hidden && !state) load();
  });
  observer.observe(document.getElementById("profile-view"), { attributes: true, attributeFilter: ["hidden"] });
})();
