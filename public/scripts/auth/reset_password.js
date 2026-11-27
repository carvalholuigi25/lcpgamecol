// The forgotten-password page (/reset-password), served by backend/auth/routes.py.
// Without a token it asks for a username or email and sends a link; with ?token=… it
// lets the user choose a new password. Password checks come from register.js.
const views = {
  request: document.getElementById("request-view"),
  confirm: document.getElementById("confirm-view"),
  invalid: document.getElementById("invalid-view"),
  done: document.getElementById("done-view"),
};
const requestForm = document.getElementById("request-form");
const requestStatus = document.getElementById("request-status");
const confirmForm = document.getElementById("confirm-form");
const confirmStatus = document.getElementById("confirm-status");
const passwordField = document.getElementById("new-password");
const confirmField = document.getElementById("new-password-confirm");
let resetToken = null;
let resetUsername = "";

function show(name) {
  for (const [key, view] of Object.entries(views)) view.hidden = key !== name;
}

async function readError(response, fallback) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg.replace(/^Value error, /, "");
  } catch {
    // Use the fallback.
  }
  return fallback;
}

function postJson(path, body) {
  return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

requestForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = document.getElementById("request-submit");
  submit.disabled = true;
  requestStatus.textContent = window.i18n.t("Sending...");
  try {
    const response = await postJson("/auth/password-reset/request", {
      identifier: requestForm.elements.identifier.value.trim(),
    });
    if (!response.ok) throw new Error(await readError(response, "The link could not be sent. Try again later."));
    requestStatus.textContent = window.i18n.t((await response.json()).detail);
  } catch (error) {
    requestStatus.textContent = window.i18n.t(error.message === "Failed to fetch" ? "The server could not be reached." : error.message);
  } finally {
    submit.disabled = false;
  }
});

function validate() {
  const password = passwordField.value;
  // Validity messages are shown by the browser, outside the DOM that i18n.js translates.
  passwordField.setCustomValidity(password ? window.i18n.t(registrationPasswordProblem(password, resetUsername)) : "");
  confirmField.setCustomValidity(
    confirmField.value && confirmField.value !== password ? window.i18n.t("The passwords do not match.") : "",
  );
  const score = passwordStrength(password, resetUsername);
  document.getElementById("new-password-meter").value = score;
  document.getElementById("new-password-strength").textContent = password
    ? window.i18n.t("Strength: {label}", { label: window.i18n.t(strengthLabels[score]) })
    : "";
}

confirmForm.addEventListener("input", validate);
confirmForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  validate();
  if (!confirmForm.reportValidity()) return;
  const submit = document.getElementById("confirm-submit");
  submit.disabled = true;
  confirmStatus.textContent = window.i18n.t("Saving...");
  try {
    const response = await postJson("/auth/password-reset/confirm", { token: resetToken, password: passwordField.value });
    if (!response.ok) throw new Error(await readError(response, "The password could not be changed."));
    confirmForm.reset();
    show("done");
  } catch (error) {
    confirmStatus.textContent = window.i18n.t(error.message === "Failed to fetch" ? "The server could not be reached." : error.message);
    submit.disabled = false;
  }
});

async function initReset() {
  const url = new URL(window.location.href);
  resetToken = url.searchParams.get("token");
  if (!resetToken) {
    show("request");
    requestForm.elements.identifier.focus();
    return;
  }
  // Keep the token out of the address bar, history and screenshots.
  window.history.replaceState(null, "", url.pathname);
  try {
    const response = await fetch(`/auth/password-reset/check?token=${encodeURIComponent(resetToken)}`);
    const result = response.ok ? await response.json() : { valid: false };
    if (!result.valid) {
      show("invalid");
      return;
    }
    resetUsername = result.username;
    document.getElementById("confirm-username").textContent = result.username;
    // Lets password managers save the new password under the right account.
    document.getElementById("confirm-username-field").value = result.username;
    show("confirm");
    passwordField.focus();
  } catch {
    show("request");
    requestStatus.textContent = window.i18n.t("The server could not be reached.");
  }
}

document.addEventListener("languagechange", () => {
  if (passwordField.value) validate();
});

initReset();
