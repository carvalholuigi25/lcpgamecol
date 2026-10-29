// The second sign-in step for accounts with two-factor sign-in (backend/auth/two_factor.py).
// When POST /auth/token answers { two_factor_required: true, ... }, the sign-in forms call
// window.twoFactorLogin.complete(challenge); it resolves true once a code is accepted (the
// session cookie is then set) or false if the user cancels. Styled with the inbox dialog.
(() => {
  const CODE_LENGTH = 6;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  async function readError(response) {
    try {
      const body = await response.json();
      if (typeof body.detail === "string") return body.detail;
    } catch {
      // Use the generic message.
    }
    return "That code is not right. Try again.";
  }

  function postJson(path, body) {
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  function complete(challenge) {
    return new Promise((resolve) => {
      let recoveryMode = false;
      let settled = false;
      const dialog = element("dialog", "inbox-dialog two-factor-dialog");
      dialog.setAttribute("aria-labelledby", "two-factor-title");
      const header = element("div", "inbox-dialog-header");
      const heading = element("h2", "", "Two-step sign-in");
      heading.id = "two-factor-title";
      header.append(heading);
      const status = element("p", "inbox-status");
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");

      const form = element("form", "inbox-compose two-factor-form");
      const intro = element("p", "two-factor-intro");
      const label = element("label", "inbox-field");
      const labelText = element("span");
      const input = element("input", "two-factor-code");
      input.name = "code";
      input.required = true;
      input.autocomplete = "one-time-code";
      input.spellcheck = false;
      label.append(labelText, input);

      const actions = element("div", "inbox-actions");
      const verify = element("button", "inbox-primary", "Verify");
      verify.type = "submit";
      const cancel = element("button", "inbox-secondary", "Cancel");
      cancel.type = "button";
      actions.append(verify, cancel);

      const extra = element("div", "two-factor-links");
      const switchMode = element("button", "inbox-text-button");
      switchMode.type = "button";
      extra.append(switchMode);
      let resend = null;
      if (challenge.method === "email") {
        resend = element("button", "inbox-text-button", "Send a new code");
        resend.type = "button";
        extra.append(resend);
      }
      form.append(intro, label, actions, extra);
      const body = element("div", "inbox-dialog-body");
      body.append(form);
      dialog.append(header, status, body);
      document.body.append(dialog);

      function render() {
        status.textContent = "";
        input.value = "";
        if (recoveryMode) {
          intro.textContent = window.i18n.t("Enter one of the recovery codes you saved when you turned on two-step sign-in. Each works once.");
          labelText.textContent = window.i18n.t("Recovery code");
          input.inputMode = "text";
          input.maxLength = 12;
          input.placeholder = "xxxx-xxxx";
          switchMode.textContent = window.i18n.t("Use a sign-in code instead");
        } else {
          intro.textContent = challenge.method === "email"
            ? window.i18n.t("We emailed a 6-digit code to {email}.", { email: challenge.email || "" })
            : window.i18n.t("Enter the 6-digit code from your authenticator app.");
          labelText.textContent = window.i18n.t("Code");
          input.inputMode = "numeric";
          input.maxLength = CODE_LENGTH;
          input.placeholder = "123456";
          switchMode.textContent = window.i18n.t("Use a recovery code");
        }
        if (resend) resend.hidden = recoveryMode;
        input.focus();
      }

      function finish(result) {
        if (settled) return;
        settled = true;
        dialog.close();
        dialog.remove();
        resolve(result);
      }

      switchMode.addEventListener("click", () => {
        recoveryMode = !recoveryMode;
        render();
      });
      cancel.addEventListener("click", () => finish(false));
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        finish(false);
      });
      // Authenticator codes are sent as soon as all six digits are in.
      input.addEventListener("input", () => {
        if (!recoveryMode && /^\d{6}$/.test(input.value.replace(/\s/g, ""))) form.requestSubmit();
      });
      resend?.addEventListener("click", async () => {
        resend.disabled = true;
        try {
          const response = await postJson("/auth/two-factor/resend", { challenge_token: challenge.challenge_token });
          status.textContent = window.i18n.t(response.ok ? "A new code is on its way." : await readError(response));
        } catch {
          status.textContent = window.i18n.t("The server could not be reached.");
        } finally {
          window.setTimeout(() => { resend.disabled = false; }, 30000);
        }
      });
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        verify.disabled = true;
        status.textContent = window.i18n.t("Checking...");
        try {
          const response = await postJson("/auth/two-factor/verify", {
            challenge_token: challenge.challenge_token,
            code: input.value.trim(),
          });
          if (response.ok) {
            finish(true);
            return;
          }
          const message = await readError(response);
          status.textContent = window.i18n.t(message);
          // These end the challenge, so the password has to be entered again.
          if (/Sign in again\.$/.test(message)) {
            verify.disabled = true;
            input.disabled = true;
            return;
          }
          // Cleared, so typing the next six digits sends them straight away.
          input.value = "";
          input.focus();
        } catch {
          status.textContent = window.i18n.t("The server could not be reached.");
        }
        verify.disabled = false;
      });

      dialog.showModal();
      render();
    });
  }

  window.twoFactorLogin = { complete };
})();
